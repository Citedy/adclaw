# OpenRouter Quick Start

Быстрая настройка OpenRouter в AgentHub за 5 минут.

## 1. Получение API ключа

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai)
2. Пополните баланс (или используйте free tier с ограничениями)
3. Скопируйте ключ: `sk-or-v1-xxxxxxxx`

## 2. Базовая настройка

```bash
# В .env файле или переменных окружения
export VALIDATOR_LLM_KEY="sk-or-v1-..."
export VALIDATOR_LLM_URL="https://openrouter.ai/api/v1"
export VALIDATOR_LLM_MODEL="openrouter/auto"
```

## 3. Режимы работы

| Режим | Модель | Когда использовать |
|-------|--------|-------------------|
| **Auto** | `openrouter/auto` | Автоматический выбор модели под задачу |
| **Free** | `openrouter/free` | Только для тестов (бесплатные модели) |
| **Nitro** | `claude-sonnet-4:nitro` | Максимальная скорость |
| **Floor** | `gpt-4:floor` | Минимальная цена |
| **Specific** | `anthropic/claude-opus-4` | Конкретная модель |

## 4. Примеры конфигураций

### Для разработки (автовыбор)
```bash
VALIDATOR_LLM_MODEL="openrouter/auto"
```

### Для production (быстро + дёшево)
```bash
VALIDATOR_LLM_MODEL="anthropic/claude-sonnet-4:nitro"
```

### Для экономии
```bash
VALIDATOR_LLM_MODEL="meta-llama/llama-4-maverick:floor"
```

### Для тестов (бесплатно)
```bash
VALIDATOR_LLM_MODEL="openrouter/free"
```

## 5. Проверка работы

```bash
# Запуск сервера
./agenthub-server --listen :8080 --data ./data

# В логах должно появиться:
# "OpenRouter: requested=openrouter/auto, actual=anthropic/claude-sonnet-4"
```

## 6. Fallback'и (резервные модели)

Если выбранная модель недоступна, OpenRouter автоматически попробует другую:

```bash
# Указывается через запятую в коде или UI
Primary: openrouter/auto
Fallback 1: anthropic/claude-sonnet-4
Fallback 2: openai/gpt-4.1
```

## Полезные ссылки

- [Полная документация](./README.md)
- [Примеры кода](./examples.md)
- [Руководство по внедрению](./implementation.md)
- [Сравнение с другими провайдерами](./comparison.md)
- [OpenRouter Docs](https://openrouter.ai/docs)
- [Цены на модели](https://openrouter.ai/models)

## Troubleshooting

**Проблема:** `401 Unauthorized`
- Проверьте что ключ начинается с `sk-or-v1-`
- Убедитесь что есть положительный баланс

**Проблема:** Модель возвращает неожиданно слабые результаты
- Auto-режим мог недооценить сложность задачи
- Используйте конкретную модель вместо `openrouter/auto`

**Проблема:** Высокая latency
- Используйте `:nitro` суффикс для быстрых провайдеров
- Или переключитесь на прямого провайдера (Aliyun/DashScope)
