# Реализация поддержки OpenRouter режимов в AgentHub

Этот документ описывает пошаговую интеграцию режимов OpenRouter (auto, nitro, floor, free) в существующую codebase AgentHub.

## Шаг 1: Обновление провайдера в llm_providers.go

Добавьте специальные OpenRouter модели в реестр:

```go
// internal/server/llm_providers.go

var providers = map[string]LLMProvider{
    // ... существующие провайдеры ...
    
    "openrouter": {
        ID:           "openrouter",
        Name:         "OpenRouter",
        BaseURL:      "https://openrouter.ai/api/v1",
        DefaultModel: "openrouter/auto",
        Models: []string{
            // Режимы роутинга
            "openrouter/auto",           // Автоматический выбор
            "openrouter/free",           // Бесплатные модели
            
            // Модели с суффиксами
            "anthropic/claude-sonnet-4:nitro",
            "anthropic/claude-sonnet-4:floor",
            "openai/gpt-5:nitro",
            "openai/gpt-5:floor",
            
            // Стандартные модели
            "anthropic/claude-sonnet-4",
            "anthropic/claude-opus-4",
            "anthropic/claude-haiku-4",
            "openai/gpt-5",
            "openai/gpt-4.1",
            "openai/gpt-4.1-mini",
            "google/gemini-2.5-pro",
            "google/gemini-3.1-flash",
            "deepseek/deepseek-v3",
            "deepseek/deepseek-v3.2",
            "qwen/qwen3-235b",
            "meta-llama/llama-4-maverick",
        },
    },
}
```

## Шаг 2: Добавление OpenRouter-специфичной функции

Создайте новый файл `internal/server/openrouter.go`:

```go
package server

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strings"
    "time"
)

// OpenRouterResponse расширяет стандартный ответ полем model (реально использованная модель)
type OpenRouterResponse struct {
    ID      string `json:"id"`
    Model   string `json:"model"`  // ← Важно: реально использованная модель
    Choices []struct {
        Message struct {
            Role    string `json:"role"`
            Content string `json:"content"`
        } `json:"message"`
        FinishReason string `json:"finish_reason"`
    } `json:"choices"`
    Usage struct {
        PromptTokens     int `json:"prompt_tokens"`
        CompletionTokens int `json:"completion_tokens"`
        TotalTokens      int `json:"total_tokens"`
    } `json:"usage"`
}

// IsOpenRouterMode проверяет, является ли модель специальным OpenRouter режимом
func IsOpenRouterMode(model string) bool {
    return strings.HasPrefix(model, "openrouter/") ||
           strings.Contains(model, ":nitro") ||
           strings.Contains(model, ":floor")
}

// CallOpenRouter делает запрос к OpenRouter API с поддержкой специальных режимов
// Возвращает: контент, реально использованная модель, ошибка
func CallOpenRouter(apiKey, model string, messages []chatMessage, temperature float64, fallbackModels []string) (string, string, error) {
    reqBody := map[string]any{
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
    }
    
    // Добавляем fallback-модели если указаны и не используется auto/free режим
    if len(fallbackModels) > 0 && model != "openrouter/auto" && model != "openrouter/free" {
        // Объединяем primary model с fallback'ами
        allModels := append([]string{model}, fallbackModels...)
        reqBody["models"] = allModels
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
    
    // OpenRouter-специфичные заголовки для атрибуции
    req.Header.Set("HTTP-Referer", "https://agenthub.clawsy.app")
    req.Header.Set("X-Title", "AgentHub")
    
    resp, err := llmHTTP.Do(req)
    if err != nil {
        return "", "", fmt.Errorf("openrouter call: %w", err)
    }
    defer resp.Body.Close()
    
    body, err := io.ReadAll(io.LimitReader(resp.Body, 256*1024))
    if err != nil {
        return "", "", fmt.Errorf("read response body: %w", err)
    }
    
    if resp.StatusCode != 200 {
        return "", "", fmt.Errorf("openrouter error %d: %s", resp.StatusCode, string(body[:min(len(body), 200)]))
    }
    
    var llmResp OpenRouterResponse
    if err := json.Unmarshal(body, &llmResp); err != nil {
        return "", "", fmt.Errorf("parse openrouter response: %w", err)
    }
    
    if len(llmResp.Choices) == 0 {
        return "", "", fmt.Errorf("empty openrouter response")
    }
    
    return llmResp.Choices[0].Message.Content, llmResp.Model, nil
}
```

## Шаг 3: Модификация llm_validator.go

Обновите `callWithFallback` для поддержки OpenRouter:

```go
// internal/server/llm_validator.go

// callWithFallback tries the primary LLM, falls back to secondary providers on error
func (s *Server) callWithFallback(messages []chatMessage, temperature float64) (string, error) {
    providerID := providerFromBaseURL(s.validatorURL)
    
    // Специальная обработка OpenRouter режимов
    if providerID == "openrouter" && IsOpenRouterMode(s.validatorModel) {
        return s.callOpenRouterWithFallback(messages, temperature)
    }
    
    // Стандартная логика для других провайдеров
    result, err := callChatCompletion(providerID, s.validatorURL, s.validatorKey, s.validatorModel, messages, temperature)
    if err == nil {
        return result, nil
    }
    
    // Fallback'и через платформу AgentHub
    for i, fb := range s.fallbacks {
        log.Printf("LLM primary failed (%v), trying fallback #%d", err, i+1)
        result, err = callChatCompletion(fb.Provider, fb.URL, fb.Key, fb.Model, messages, temperature)
        if err == nil {
            return result, nil
        }
    }
    return "", err
}

// callOpenRouterWithFallback использует OpenRouter API с встроенными fallback'ами
func (s *Server) callOpenRouterWithFallback(messages []chatMessage, temperature float64) (string, error) {
    // Собираем fallback-модели из конфигурации сервера
    fallbackModels := make([]string, 0, len(s.fallbacks))
    for _, fb := range s.fallbacks {
        // Для OpenRouter fallback'ов используем модель напрямую
        if fb.Provider == "openrouter" {
            fallbackModels = append(fallbackModels, fb.Model)
        }
    }
    
    content, usedModel, err := CallOpenRouter(
        s.validatorKey,
        s.validatorModel,
        messages,
        temperature,
        fallbackModels,
    )
    
    if err != nil {
        return "", err
    }
    
    // Логируем реально использованную модель (полезно для анализа)
    if s.validatorModel != usedModel {
        log.Printf("OpenRouter: requested=%s, actual=%s", s.validatorModel, usedModel)
    }
    
    return content, nil
}
```

## Шаг 4: Модификация generateTitle для пользовательских LLM

Обновите функцию `generateTitle` чтобы поддерживала OpenRouter:

```go
// internal/server/llm_validator.go — в функции generateTitle

if userID > 0 {
    llmCfg, err := s.db.GetUserLLMConfig(userID)
    if err == nil && llmCfg.Provider != "" && llmCfg.APIKey != "" {
        apiKey, decErr := crypto.Decrypt(llmCfg.APIKey, s.encryptionKey)
        if decErr == nil {
            baseURL := llmCfg.BaseURL
            if baseURL == "" {
                baseURL = getProviderBaseURL(llmCfg.Provider)
            }
            model := llmCfg.Model
            if model == "" {
                model = getProviderDefaultModel(llmCfg.Provider)
            }
            
            if baseURL != "" {
                var result string
                var err error
                
                // Специальная обработка OpenRouter
                if llmCfg.Provider == "openrouter" && IsOpenRouterMode(model) {
                    result, usedModel, err := CallOpenRouter(apiKey, model, messages, 0.3, nil)
                    if err == nil {
                        log.Printf("generate-title: OpenRouter used %s", usedModel)
                        return cleanTitle(result)
                    }
                } else {
                    result, err = callChatCompletion(llmCfg.Provider, baseURL, apiKey, model, messages, 0.3)
                }
                
                if err == nil {
                    return cleanTitle(result)
                }
                log.Printf("generate-title: user LLM failed: %v", err)
            }
        }
    }
}
```

## Шаг 5: Обновление валидации патчей

Добавьте опциональное поле для отслеживания использованной модели:

```go
// ValidationResult расширяется полем UsedModel (только для OpenRouter)
type ValidationResult struct {
    Score        float64  `json:"score"`
    IsBetter     bool     `json:"is_better"`
    Improvements []string `json:"improvements"`
    Regressions  []string `json:"regressions"`
    Reasoning    string   `json:"reasoning"`
    UsedModel    string   `json:"used_model,omitempty"`  // ← Новое поле для OpenRouter
}

// validatePatch обновляется для возврата информации о модели
func validatePatch(providerID, apiKey, baseURL, model, category, baseline, newContent string, checklist []string) (*ValidationResult, error) {
    // ... существующий код формирования промптов ...
    
    // Специальная обработка OpenRouter
    if providerID == "openrouter" && IsOpenRouterMode(model) {
        content, usedModel, err := CallOpenRouter(apiKey, model, []chatMessage{
            {Role: "system", Content: systemPrompt},
            {Role: "user", Content: userPrompt},
        }, 0.1, nil)
        
        if err != nil {
            return nil, err
        }
        
        result, err := parseValidationResult(content)
        if err != nil {
            return nil, err
        }
        
        result.UsedModel = usedModel  // ← Сохраняем информацию о модели
        return result, nil
    }
    
    // Стандартная логика для других провайдеров
    result, err := callLLMJSON[ValidationResult](providerID, apiKey, baseURL, model, systemPrompt, userPrompt, 0.1)
    if err != nil {
        return nil, err
    }
    result.Score = clampScore(result.Score)
    return result, nil
}
```

## Шаг 6: Тестирование

Создайте тесты для OpenRouter интеграции:

```go
// internal/server/openrouter_test.go

package server

import (
    "testing"
)

func TestIsOpenRouterMode(t *testing.T) {
    tests := []struct {
        model    string
        expected bool
    }{
        {"openrouter/auto", true},
        {"openrouter/free", true},
        {"anthropic/claude-sonnet-4:nitro", true},
        {"anthropic/claude-sonnet-4:floor", true},
        {"gpt-4:floor", true},
        {"anthropic/claude-sonnet-4", false},
        {"openai/gpt-4", false},
        {"qwen3.5-plus", false},
    }
    
    for _, tt := range tests {
        t.Run(tt.model, func(t *testing.T) {
            result := IsOpenRouterMode(tt.model)
            if result != tt.expected {
                t.Errorf("IsOpenRouterMode(%q) = %v, want %v", tt.model, result, tt.expected)
            }
        })
    }
}

func TestOpenRouterConfig(t *testing.T) {
    // Проверяем что openrouter есть в реестре
    p, ok := providers["openrouter"]
    if !ok {
        t.Fatal("openrouter provider not found in registry")
    }
    
    // Проверяем наличие специальных моделей
    hasAuto := false
    hasFree := false
    for _, m := range p.Models {
        if m == "openrouter/auto" {
            hasAuto = true
        }
        if m == "openrouter/free" {
            hasFree = true
        }
    }
    
    if !hasAuto {
        t.Error("openrouter/auto not found in models")
    }
    if !hasFree {
        t.Error("openrouter/free not found in models")
    }
}
```

## Шаг 7: Обновление документации API

Добавьте информацию о поддержке OpenRouter в `docs/ARCHITECTURE.md`:

```markdown
### LLM Providers

#### OpenRouter Special Modes

AgentHub поддерживает специальные режимы OpenRouter:

- `openrouter/auto` — автоматический выбор модели на основе промпта
- `openrouter/free` — использование бесплатных моделей
- `:nitro` суффикс — выбор самого быстрого провайдера
- `:floor` суффикс — выбор самого дешёвого провайдера

Примеры моделей:
- `anthropic/claude-sonnet-4:nitro` — Claude с минимальной задержкой
- `openai/gpt-4:floor` — GPT-4 по минимальной цене

Для режимов `auto` и `free` OpenRouter возвращает реально использованную модель 
в поле `model` ответа, которое логируется для анализа.
```

## Проверка интеграции

После внесения изменений:

1. **Сборка:**
   ```bash
   go build -o agenthub-server ./cmd/agenthub-server
   ```

2. **Тестирование:**
   ```bash
   go test ./internal/server -v -run TestOpenRouter
   ```

3. **Запуск с OpenRouter:**
   ```bash
   export VALIDATOR_LLM_KEY="sk-or-v1-..."
   export VALIDATOR_LLM_URL="https://openrouter.ai/api/v1"
   export VALIDATOR_LLM_MODEL="openrouter/auto"
   ./agenthub-server --listen :8080 --data ./data
   ```

4. **Проверка логов:**
   В логах должны появляться записи вида:
   ```
   OpenRouter: requested=openrouter/auto, actual=anthropic/claude-sonnet-4
   ```
