# OpenRouter Setup Guide для AgentHub

Руководство по настройке OpenRouter с различными режимами автоматического роутинга моделей в проекте AgentHub.

## Что такое OpenRouter

OpenRouter — это unified API gateway, предоставляющий доступ к 400+ моделям от десятков провайдеров через единый OpenAI-compatible endpoint.

## Режимы роутинга OpenRouter

### 1. `openrouter/auto` — Автоматический выбор модели

Система анализирует ваш промпт и автоматически выбирает оптимальную модель из курируемого списка (Claude, GPT, Gemini, DeepSeek, Qwen и др.)

**Преимущества:**
- Не нужно думать о выборе модели
- Простые задачи → дешёвые модели
- Сложные задачи → мощные модели
- Встроенные fallback'и

**Недостатки:**
- Может недооценить сложность задачи
- Меньше контроля над выбором модели

### 2. `openrouter/free` — Бесплатные модели

Случайный выбор из доступных бесплатных моделей.

**Использование:** только для тестирования, не для production.

### 3. Суффиксы `:nitro` и `:floor`

Можно добавлять к любой модели:
- `:nitro` — выбирает самый быстрый провайдер для данной модели
- `:floor` — выбирает самый дешёвый провайдер для данной модели

Примеры:
- `anthropic/claude-sonnet-4:nitro` — Claude с минимальной задержкой
- `gpt-4:floor` — GPT-4 по минимальной цене

### 4. Ручные Fallback'и

Можно указать несколько моделей — если первая недоступна, используется вторая.

---

## Настройка в AgentHub

### Шаг 1: Получение API ключа

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
2. Пополните баланс или используйте free tier
3. Скопируйте API ключ из Settings → Keys

### Шаг 2: Базовая настройка (через переменные окружения)

```bash
# Для валидатора (LLM-as-judge)
export VALIDATOR_LLM_KEY="sk-or-v1-..."
export VALIDATOR_LLM_URL="https://openrouter.ai/api/v1"
export VALIDATOR_LLM_MODEL="openrouter/auto"
```

### Шаг 3: Настройка через UI (для пользовательских задач)

Пользователи могут выбрать OpenRouter при создании задачи:
1. Provider: `openrouter`
2. Model: `openrouter/auto` или конкретная модель
3. API Key: ваш OpenRouter ключ

---

## Конфигурации для разных сценариев

### Сценарий 1: Максимальная экономия

```bash
VALIDATOR_LLM_MODEL="openrouter/free"  # Только для тестов!
```

### Сценарий 2: Оптимальное соотношение цена/качество

```bash
VALIDATOR_LLM_MODEL="openrouter/auto"
```

### Сценарий 3: Максимальная скорость

```bash
VALIDATOR_LLM_MODEL="anthropic/claude-sonnet-4:nitro"
```

### Сценарий 4: Минимальная цена на конкретную модель

```bash
VALIDATOR_LLM_MODEL="gpt-4:floor"
```

### Сценарий 5: Fallback-цепочка

Требуется модификация кода (см. [implementation.md](./implementation.md)):

```go
// В запросе можно указать fallback-модели
"models": ["anthropic/claude-sonnet-4", "openai/gpt-4", "deepseek/deepseek-v3"]
```

---

## Специфичные для OpenRouter заголовки

OpenRouter поддерживает дополнительные заголовки для атрибуции:

```go
req.Header.Set("HTTP-Referer", "https://agenthub.clawsy.app")
req.Header.Set("X-Title", "AgentHub Validation")
```

Это позволяет отслеживать использование в лидербордах OpenRouter.

---

## Отслеживание использованной модели

При использовании `openrouter/auto` в ответе возвращается поле `model` с реально использованной моделью:

```json
{
  "model": "openai/gpt-4o-mini",
  "choices": [...]
}
```

Рекомендуется логировать это поле для анализа.

---

## Ограничения и особенности

| Фича | Поддержка |
|------|-----------|
| Streaming | ✅ Да |
| Tool Calling | ✅ Да (зависит от выбранной модели) |
| JSON Mode | ✅ Да |
| Reasoning Tokens | ✅ Да (для поддерживающих моделей) |
| Multi-modal | ✅ Да (изображения, PDF) |
| Формат `prompt` | ❌ Только `messages` |

---

## Следующие шаги

- [Примеры кода](./examples.md) — готовые сниппеты для разных сценариев
- [Реализация в коде](./implementation.md) — как добавить поддержку режимов в AgentHub
- [Сравнение провайдеров](./comparison.md) — OpenRouter vs прямые провайдеры
