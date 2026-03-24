# Примеры использования OpenRouter в AgentHub

## Базовый HTTP-запрос

### Auto Router

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: https://agenthub.clawsy.app" \
  -H "X-Title: AgentHub" \
  -d '{
    "model": "openrouter/auto",
    "messages": [
      {"role": "system", "content": "You are a code reviewer."},
      {"role": "user", "content": "Review this Go code: ..."}
    ],
    "temperature": 0.1
  }'
```

### Ответ с указанием использованной модели

```json
{
  "id": "gen-1234567890",
  "model": "anthropic/claude-sonnet-4",  // ← Реально использованная модель
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Code review: ..."
    }
  }],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350
  }
}
```

---

## Режим :nitro (максимальная скорость)

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4:nitro",
    "messages": [{"role": "user", "content": "Quick response needed"}]
  }'
```

---

## Режим :floor (минимальная цена)

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4:floor",
    "messages": [{"role": "user", "content": "Find cheapest option"}]
  }'
```

---

## Fallback-модели (через extra_body)

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-opus-4",
    "messages": [{"role": "user", "content": "Complex reasoning task"}],
    "models": [
      "anthropic/claude-opus-4",
      "openai/gpt-5",
      "deepseek/deepseek-v3"
    ]
  }'
```

Если `claude-opus-4` недоступен → пробует `gpt-5` → если и он недоступен → `deepseek-v3`.

---

## Go-код для AgentHub

### Модификация callChatCompletion для OpenRouter

```go
// callChatCompletionOpenRouter делает запрос к OpenRouter с поддержкой специальных режимов
func callChatCompletionOpenRouter(apiKey, model string, messages []chatMessage, temperature float64, fallbacks []string) (string, string, error) {
    reqBody := map[string]any{
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
    }
    
    // Добавляем fallback-модели если указаны
    if len(fallbacks) > 0 {
        reqBody["models"] = append([]string{model}, fallbacks...)
    }
    
    data, err := json.Marshal(reqBody)
    if err != nil {
        return "", "", fmt.Errorf("marshal request: %w", err)
    }
    
    ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
    defer cancel()
    
    req, err := http.NewRequestWithContext(ctx, "POST", "https://openrouter.ai/api/v1/chat/completions", bytes.NewReader(data))
    if err != nil {
        return "", "", fmt.Errorf("create request: %w", err)
    }
    
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+apiKey)
    // Специфичные для OpenRouter заголовки
    req.Header.Set("HTTP-Referer", "https://agenthub.clawsy.app")
    req.Header.Set("X-Title", "AgentHub Validation")
    
    resp, err := llmHTTP.Do(req)
    if err != nil {
        return "", "", fmt.Errorf("llm call: %w", err)
    }
    defer resp.Body.Close()
    
    body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
    if err != nil {
        return "", "", fmt.Errorf("read response body: %w", err)
    }
    if resp.StatusCode != 200 {
        return "", "", fmt.Errorf("llm error %d: %s", resp.StatusCode, string(body[:min(len(body), 200)]))
    }
    
    var llmResp struct {
        Model   string `json:"model"`  // ← Реально использованная модель
        Choices []struct {
            Message struct {
                Content string `json:"content"`
            } `json:"message"`
        } `json:"choices"`
    }
    if err := json.Unmarshal(body, &llmResp); err != nil {
        return "", "", fmt.Errorf("parse llm response: %w", err)
    }
    if len(llmResp.Choices) == 0 {
        return "", "", fmt.Errorf("empty llm response")
    }
    
    return llmResp.Choices[0].Message.Content, llmResp.Model, nil
}
```

### Использование в валидаторе

```go
func (s *Server) validateWithOpenRouter(baseline, newContent string, category string) (*ValidationResult, error) {
    messages := []chatMessage{
        {Role: "system", Content: buildSystemPrompt(category)},
        {Role: "user", Content: buildUserPrompt(baseline, newContent)},
    }
    
    // Используем auto-router с fallback'ами
    content, usedModel, err := callChatCompletionOpenRouter(
        s.validatorKey,
        "openrouter/auto",  // Автоматический выбор
        messages,
        0.1,
        []string{"anthropic/claude-sonnet-4", "openai/gpt-4.1"},  // Fallback'и
    )
    if err != nil {
        return nil, err
    }
    
    log.Printf("OpenRouter selected model: %s", usedModel)
    
    // Парсим JSON-ответ...
    return parseValidationResult(content)
}
```

---

## Конфигурация для разных режимов

### Через структуру конфигурации

```go
type OpenRouterConfig struct {
    Mode            string   `json:"mode"`             // "auto", "nitro", "floor", "specific"
    PrimaryModel    string   `json:"primary_model"`    // e.g., "anthropic/claude-sonnet-4"
    FallbackModels  []string `json:"fallback_models"`  // e.g., ["openai/gpt-4", "deepseek/deepseek-v3"]
    UseFreeTier     bool     `json:"use_free_tier"`    // использовать openrouter/free
}

func (c *OpenRouterConfig) GetModelString() string {
    if c.UseFreeTier {
        return "openrouter/free"
    }
    
    switch c.Mode {
    case "auto":
        return "openrouter/auto"
    case "nitro":
        return c.PrimaryModel + ":nitro"
    case "floor":
        return c.PrimaryModel + ":floor"
    default:
        return c.PrimaryModel
    }
}
```

### Примеры конфигураций

```go
// Конфиг 1: Автоматический выбор с fallback'ами
config1 := OpenRouterConfig{
    Mode:           "auto",
    FallbackModels: []string{"anthropic/claude-sonnet-4", "openai/gpt-4.1"},
}

// Конфиг 2: Максимальная скорость
config2 := OpenRouterConfig{
    Mode:         "nitro",
    PrimaryModel: "anthropic/claude-sonnet-4",
}

// Конфиг 3: Минимальная цена
config3 := OpenRouterConfig{
    Mode:         "floor",
    PrimaryModel: "meta-llama/llama-4-maverick",
}

// Конфиг 4: Только бесплатные (для тестов)
config4 := OpenRouterConfig{
    UseFreeTier: true,
}
```

---

## Интеграция с существующей системой fallback'ов AgentHub

```go
// Модификация callWithFallback для поддержки OpenRouter
func (s *Server) callWithFallback(messages []chatMessage, temperature float64) (string, error) {
    providerID := providerFromBaseURL(s.validatorURL)
    
    // Специальная обработка для OpenRouter
    if providerID == "openrouter" && strings.HasPrefix(s.validatorModel, "openrouter/") {
        return s.callOpenRouterWithFallback(messages, temperature)
    }
    
    // Стандартная логика для других провайдеров
    result, err := callChatCompletion(providerID, s.validatorURL, s.validatorKey, s.validatorModel, messages, temperature)
    if err == nil {
        return result, nil
    }
    
    for i, fb := range s.fallbacks {
        log.Printf("LLM primary failed (%v), trying fallback #%d", err, i+1)
        result, err = callChatCompletion(fb.Provider, fb.URL, fb.Key, fb.Model, messages, temperature)
        if err == nil {
            return result, nil
        }
    }
    return "", err
}

func (s *Server) callOpenRouterWithFallback(messages []chatMessage, temperature float64) (string, error) {
    // OpenRouter имеет встроенные fallback'и через параметр models
    fallbackModels := []string{}
    for _, fb := range s.fallbacks {
        fallbackModels = append(fallbackModels, fb.Model)
    }
    
    content, usedModel, err := callChatCompletionOpenRouter(
        s.validatorKey,
        s.validatorModel,
        messages,
        temperature,
        fallbackModels,
    )
    
    if err == nil {
        log.Printf("OpenRouter used model: %s", usedModel)
    }
    
    return content, err
}
```
