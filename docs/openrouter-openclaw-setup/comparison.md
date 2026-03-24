# Сравнение OpenRouter с прямыми провайдерами

## Когда использовать OpenRouter

### ✅ Преимущества OpenRouter

| Аспект | OpenRouter | Прямые провайдеры |
|--------|------------|-------------------|
| **Количество моделей** | 400+ | 5-20 на провайдера |
| **Единый API** | Один ключ, один формат | Отдельные ключи и форматы |
| **Fallback'и** | Встроенные на уровне API | Нужно реализовывать самому |
| **Автовыбор модели** | `openrouter/auto` | Нет |
| **Цена** | Без наценки (только для кредитов +5.5%) | Прямая цена провайдера |
| **BYOK** | Можно использовать свои ключи (+5% комиссия) | Не применимо |

### ❌ Недостатки OpenRouter

| Аспект | OpenRouter | Прямые провайдеры |
|--------|------------|-------------------|
| **Задержка** | +25ms на роутинг | Прямое соединение |
| **Контроль** | Ограниченный выбор моделей в auto-режиме | Полный контроль |
| **Privacy** | Промпты проходят через третью сторону | Прямая передача |
| **SLA** | Нет гарантий uptime | Enterprise SLA у крупных |
| **Fine-tuning** | Нет доступа к fine-tuned моделям | Полный доступ |

---

## Сравнение по сценариям использования

### Сценарий 1: Прототипирование и тестирование

**Рекомендация:** OpenRouter `openrouter/free` или `openrouter/auto`

```bash
# Быстрое тестирование без настройки множества ключей
VALIDATOR_LLM_MODEL="openrouter/auto"
```

**Почему:** Не нужно регистрироваться у множества провайдеров, автоматический выбор модели.

---

### Сценарий 2: Production с высокой доступностью

**Рекомендация:** OpenRouter с fallback'ами ИЛИ собственная система fallback'ов

```bash
# Вариант A: OpenRouter с встроенными fallback'ами
VALIDATOR_LLM_MODEL="anthropic/claude-sonnet-4"
# + fallback models: ["openai/gpt-4", "deepseek/deepseek-v3"]

# Вариант B: Собственные fallback'ы AgentHub
VALIDATOR_LLM_MODEL="qwen3.5-plus"  # Aliyun
# Fallback 1: anthropic/claude-sonnet-4
# Fallback 2: openai/gpt-4
```

**Почему:** OpenRouter упрощает failover, но собственные fallback'и дают больше контроля.

---

### Сценарий 3: Оптимизация затрат

**Рекомендация:** OpenRouter `:floor` или прямые провайдеры с низкими ценами

```bash
# Вариант A: Самый дешёвый провайдер для GPT-4
VALIDATOR_LLM_MODEL="openai/gpt-4:floor"

# Вариант B: Дешёвые модели напрямую
VALIDATOR_LLM_MODEL="qwen3.5-plus"  # Aliyun — дешевле GPT-4
```

**Почему:** `:floor` помогает найти дешёвый провайдер, но Aliyun/DashScope часто дешевле западных.

---

### Сценарий 4: Максимальная производительность (latency)

**Рекомендация:** OpenRouter `:nitro` ИЛИ прямой доступ к ближайшему дата-центру

```bash
# Вариант A: Самый быстрый провайдер для Claude
VALIDATOR_LLM_MODEL="anthropic/claude-sonnet-4:nitro"

# Вариант B: Прямой доступ к regional endpoint
VALIDATOR_LLM_URL="https://coding-intl.dashscope.aliyuncs.com/v1"  # Singapore
VALIDATOR_LLM_MODEL="qwen3.5-plus"
```

**Почему:** `:nitro` выбирает быстрый провайдер, но географическая близость важнее.

---

### Сценарий 5: Строгие требования privacy

**Рекомендация:** Прямые провайдеры с ZDR (Zero Data Retention)

```bash
# Не OpenRouter! Прямой доступ:
VALIDATOR_LLM_URL="https://api.anthropic.com/v1"
VALIDATOR_LLM_MODEL="claude-sonnet-4"
# + включить ZDR в настройках Anthropic
```

**Почему:** OpenRouter = дополнительная точка прохождения данных. Для HIPAA/GDPR лучше прямой доступ.

---

### Сценарий 6: Специфичные модели

**Рекомендация:** Зависит от модели

| Модель | Где доступна | Рекомендация |
|--------|--------------|--------------|
| GPT-5 | OpenAI, Azure, OpenRouter | OpenRouter для гибкости |
| Claude 4 | Anthropic, OpenRouter, AWS | Прямой Anthropic для production |
| Qwen 3.5 | Aliyun, OpenRouter | Прямой Aliyun (дешевле, быстрее) |
| DeepSeek | DeepSeek, Aliyun, OpenRouter | Прямой DeepSeek (дешевле) |
| Gemini | Google, OpenRouter | OpenRouter для унификации |

---

## Матрица решений

```
┌─────────────────────────────────────────────────────────────────┐
│  Нужно быстро протестировать?                                   │
│  ├─ Да → OpenRouter auto/free                                   │
│  └─ Нет →                                                       │
│       Нужна максимальная privacy?                               │
│       ├─ Да → Прямые провайдеры с ZDR                          │
│       └─ Нет →                                                  │
│            Важна минимальная latency?                           │
│            ├─ Да → Прямой доступ к regional endpoint           │
│            └─ Нет →                                             │
│                 Нужны fallback'и без кода?                      │
│                 ├─ Да → OpenRouter с models параметром         │
│                 └─ Нет →                                        │
│                      Оптимизация цены приоритетна?              │
│                      ├─ Да → OpenRouter :floor или Aliyun      │
│                      └─ Нет → Прямые провайдеры                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Рекомендации для AgentHub

### Рекомендуемая конфигурация по умолчанию

```bash
# Для production — проверенная китайская экосистема
VALIDATOR_LLM_URL="https://coding-intl.dashscope.aliyuncs.com/v1"
VALIDATOR_LLM_KEY="$ALIYUN_INTERNATIONAL_KEY"
VALIDATOR_LLM_MODEL="qwen3.5-plus"

# Fallback'и через OpenRouter для resilience
# (настраивается в коде через s.fallbacks)
```

### Конфигурация для международного доступа

```bash
# Если Aliyun недоступен или нужны западные модели
VALIDATOR_LLM_URL="https://openrouter.ai/api/v1"
VALIDATOR_LLM_KEY="$OPENROUTER_KEY"
VALIDATOR_LLM_MODEL="openrouter/auto"
```

### Конфигурация для разработки

```bash
# Быстрое тестирование без затрат
VALIDATOR_LLM_URL="https://openrouter.ai/api/v1"
VALIDATOR_LLM_KEY="$OPENROUTER_KEY"
VALIDATOR_LLM_MODEL="openrouter/free"
```

---

## Ценовое сравнение (примерные данные)

| Модель | Прямой провайдер | OpenRouter | Разница |
|--------|------------------|------------|---------|
| GPT-4.1 | $2.00 / $8.00 | $2.11 / $8.44 (+5.5%) | +5.5% |
| Claude Sonnet 4 | $3.00 / $15.00 | $3.17 / $15.83 (+5.5%) | +5.5% |
| Qwen 3.5 | $0.40 / $1.20 (Aliyun) | $0.42 / $1.26 (+5.5%) | +5.5% |
| DeepSeek V3 | $0.10 / $0.50 | $0.11 / $0.53 (+5.5%) | +5.5% |

**Вывод:** OpenRouter добавляет ~5.5% к цене провайдера при использовании кредитов. При BYOK комиссия 5%.

---

## Итоговая рекомендация

| Критерий | Лучший выбор |
|----------|--------------|
| Простота | OpenRouter |
| Контроль | Прямые провайдеры |
| Privacy | Прямые провайдеры + ZDR |
| Цена | Прямые провайдеры (особенно Aliyun) |
| Надёжность | OpenRouter (fallback'и) или собственная система |
| Скорость | Прямые провайдеры (geographic proximity) |
| Гибкость | OpenRouter (400+ моделей) |

**Для AgentHub:** Рекомендуется гибридный подход — основной провайдер (Aliyun) + OpenRouter как fallback для resilience.
