# SmartQala — Архитектура и технические решения

> Живой документ. Обновляется по мере принятия решений.
> Последнее обновление: 06.09.2026

---

## 1. Контекст и ограничения

**Команда:** основатель + Claude Code. Всё своими силами, подрядчиков нет.
**Порядок работ:** сначала бэкенд целиком, затем клиентская часть.

**Финансирование:** собственные средства + грант Astana Hub. Без внешних инвестиций.

**Что из этого следует для архитектуры:**

| Ограничение | Следствие |
|---|---|
| Нет инвестиций → минимальный burn | Всё должно работать на одном сервере. Никакого Kubernetes, никаких managed-сервисов там, где хватает контейнера |
| Backend пишется вдвоём с ИИ | Код должен быть предсказуемым и однообразным: один паттерн на всё, минимум магии. Явное лучше умного |
| Фронтенд пишется позже и тем же составом | **API — это контракт.** OpenAPI-схема генерируется автоматически и остаётся единственным источником правды. Из неё же генерируется клиент — руками его не пишем |
| Сроки жёсткие (MVP к ноябрю) | Режем всё, что можно отложить. Модуль либо в MVP, либо не начат |

---

## 2. Стек — принятые решения

| Слой | Решение | Почему |
|---|---|---|
| **Backend** | Python 3.12 + FastAPI | Основная работа проекта — обработка данных: парсинг прайсов и реестров, OCR счётчиков, сверка платежей. Это домашняя территория Python. Автогенерация OpenAPI критична для работы с внешним фронтендером |
| **БД** | PostgreSQL 16 | — |
| **ORM / миграции** | SQLAlchemy 2.0 (async) + Alembic | — |
| **Кэш, pub/sub, брокер** | Redis 7 | Один сервис на три задачи — меньше движущихся частей |
| **Realtime** | WebSocket внутри процесса FastAPI + Redis pub/sub | Нагрузка не требует отдельного сервиса. Redis pub/sub добавлен сразу, чтобы горизонтальное масштабирование не потребовало переписывания |
| **Фоновые задачи** | arq | Async-native, работает на том же Redis. Celery избыточен |
| **Клиент для жильцов** | Решение пересматривается | Подрядчика нет. Выбор между Flutter и React/PWA не закрыт — см. §3 |
| **Админ-панели (4 шт.)** | Refine (React) поверх REST | Не пишем руками — генерируем. Экономия ~месяца разработки |
| **Хранение файлов** | S3-совместимое хранилище | Фото заявок, чеки, показания счётчиков |
| **Push** | Firebase Cloud Messaging | — |
| **Пакетный менеджер** | uv | Быстрее poetry на порядок, один инструмент на venv и зависимости |
| **Контейнеризация** | Docker + docker compose | Один compose-файл поднимает всё окружение |
| **Линтеры** | ruff (lint + format), mypy | Один инструмент вместо black + isort + flake8 |
| **Тесты** | pytest + pytest-asyncio + httpx | — |

### Явно отвергнутые варианты

| Что | Почему нет |
|---|---|
| Микросервисы (9 сервисов из исходного ТЗ) | Команда из двух человек. Микросервисы — это налог на коммуникацию, которого у нас нет. Пишем модульный монолит с жёсткими границами: разрезать можно будет позже, границы уже проведены |
| Go | Проиграл на задачах парсинга, OCR и работы с данными. Нагрузка не требует его преимуществ |
| PHP | Не даёт преимуществ ни в одной части задачи, слабее в realtime |
| Celery + RabbitMQ | Лишний брокер. arq на Redis решает ту же задачу |
| Kubernetes | На одном сервере не нужен, стоит времени |

---

## 3. Открытые вопросы (блокеры)

| # | Вопрос | Блокирует | Срочность |
|---|---|---|---|
| 1 | **Хостинг в РК.** Закон о персональных данных требует хранения ПД граждан РК на территории Казахстана. В базе — ФИО, телефоны, адреса квартир. AWS/DigitalOcean, вероятно, не подходят для основной БД. Кандидаты: ps.kz, облако Казахтелекома, площадки партнёров Astana Hub | Выбор инфраструктуры, деплой | **Высокая** — ошибка здесь стоит переезда на 20-м ЖК |
| 2 | **Статус пилотных ОСИ в Kaspi** — подключены ли как поставщики услуг (биллеры) | Весь модуль billing | **Критическая** |
| 3 | SMS-провайдер: основной + резервный | Регистрация пользователей | Средняя |
| 4 | OCR для счётчиков: облако или self-hosted | Модуль meters (не в первой волне) | Низкая |

---

## 4. Структура репозитория

```
super-qala/
├── backend/
│   ├── app/
│   │   ├── main.py              — точка входа, сборка приложения
│   │   ├── core/                — конфиг, БД, безопасность, зависимости
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── security.py
│   │   │   ├── deps.py          — общие Depends: current_user, роли, пагинация
│   │   │   ├── exceptions.py
│   │   │   └── redis.py
│   │   ├── modules/             — бизнес-модули, каждый самодостаточен
│   │   │   ├── auth/
│   │   │   ├── properties/      — ОСИ, ЖК, дома, подъезды, квартиры
│   │   │   ├── residents/       — жильцы, привязка и верификация квартиры
│   │   │   ├── billing/         — начисления, квитанции, платежи, сверка
│   │   │   ├── requests/        — заявки в ОСИ с SLA
│   │   │   ├── chat/            — каналы и сообщения
│   │   │   ├── meters/          — показания счётчиков
│   │   │   ├── voting/          — собрания и голосования
│   │   │   ├── finance/         — прозрачность расходов ОСИ
│   │   │   ├── classifieds/     — доска объявлений
│   │   │   └── notifications/   — push, SMS, история
│   │   ├── workers/             — фоновые задачи arq
│   │   └── shared/              — общие утилиты, схемы, типы
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── admin/                       — Refine, 4 панели
├── docs/
├── docker-compose.yml
└── .env.example
```

### Устройство модуля

Каждый модуль — одинаковый набор файлов. Однообразие важнее гибкости: код пишется в паре с ИИ, а читается внешним разработчиком.

```
modules/<name>/
├── models.py      — таблицы SQLAlchemy
├── schemas.py     — Pydantic: запросы и ответы
├── service.py     — бизнес-логика. Не знает про HTTP
├── router.py      — HTTP-эндпоинты. Тонкий слой: валидация → service → ответ
├── repository.py  — запросы к БД (там, где сложнее CRUD)
└── exceptions.py  — доменные исключения
```

**Правила границ модулей:**
1. Модуль обращается к другому **только через его `service.py`**, никогда напрямую к чужим моделям или таблицам.
2. Циклические зависимости между модулями запрещены. Если нужны — общее выносится в `shared/`.
3. `router.py` не содержит бизнес-логики. Если в роутере появился `if` про предметную область — он не на своём месте.

---

## 5. Схема базы данных

### 5.1. Организации и недвижимость

```sql
organizations          -- ОСИ / КСК / УК — клиент, который платит
  id, name, bin, type, phone, email, address,
  tariff, status, trial_ends_at, created_at

complexes              -- жилой комплекс
  id, organization_id, name, address, city, lat, lon, created_at

buildings              -- дом (у ЖК может быть несколько)
  id, complex_id, number, floors_count, entrances_count

entrances              -- подъезд
  id, building_id, number

apartments             -- квартира
  id, entrance_id, number, floor, area_sqm, rooms_count
  UNIQUE (entrance_id, number)
```

Иерархия `organization → complex → building → entrance → apartment` кажется избыточной для одного дома, но без неё невозможно обслуживать УК с десятком домов — а это самый ценный тип клиента.

### 5.2. Пользователи и доступ

```sql
users
  id, phone (unique), first_name, last_name, avatar_url,
  language, is_active, created_at, last_seen_at

user_roles             -- роль всегда в контексте организации
  id, user_id, organization_id, role, granted_by, created_at
  -- role: resident | osi_admin | osi_moderator | osi_finance
  --     | store_owner | master | platform_admin

apartment_residents    -- связь жильца с квартирой
  id, user_id, apartment_id, relation, status,
  verified_by, verified_at, invited_by, created_at
  -- relation: owner | tenant | family_member
  -- status:   pending | verified | rejected | revoked

verification_codes     -- код с квитанции для самостоятельной привязки
  id, apartment_id, code, expires_at, used_by, used_at
```

**Верификация квартиры** — самое чувствительное место системы: она открывает доступ к чату соседей и к финансовым данным. Три пути, по убыванию доверия:
1. Код с бумажной квитанции + номер лицевого счёта → автоматическая привязка.
2. Ручное подтверждение администратором ОСИ по списку жильцов.
3. Приглашение от уже верифицированного собственника (для арендаторов и членов семьи) — с урезанными правами: без доступа к начислениям.

### 5.3. Начисления и платежи

```sql
service_types          -- виды услуг ОСИ
  id, organization_id, name, unit, is_metered

accounts               -- лицевой счёт
  id, apartment_id, organization_id, external_number, balance
  UNIQUE (organization_id, external_number)

billing_periods
  id, organization_id, year, month, status, published_at
  -- status: draft | published | closed

charges                -- начисление
  id, account_id, billing_period_id, service_type_id,
  amount, volume, tariff, created_at

invoices               -- квитанция = начисления за период
  id, account_id, billing_period_id, total_amount,
  paid_amount, status, due_date, pdf_url
  -- status: issued | partially_paid | paid | overdue

payment_claims         -- «я оплатил» от жильца
  id, invoice_id, user_id, amount, paid_at,
  receipt_url, receipt_ref, source, status, created_at
  -- source: kaspi_deeplink | manual_receipt | cash
  -- status: pending | matched | rejected

payment_facts          -- подтверждённый платёж из реестра ОСИ/банка
  id, account_id, amount, paid_at, external_ref,
  source, imported_at, matched_invoice_id
  -- source: kaspi_registry | bank_statement | manual

reconciliation_log     -- журнал сверки
  id, payment_fact_id, payment_claim_id, invoice_id,
  action, performed_by, created_at
```

**Ключевой принцип модуля:** деньги через нас не проходят. Платёж идёт напрямую на счёт ОСИ, мы фиксируем факт. Поэтому `payment_claim` (заявление жильца) и `payment_fact` (выписка) — **разные сущности**, и источник истины — всегда `payment_fact`. Смешать их значит получить через месяц «оплаченные» долги.

Ночной воркер сводит claims и facts по лицевому счёту, сумме и дате. Несведённое попадает на экран ручной сверки в панели ОСИ — этот экран нужен всегда: люди платят с чужого номера, не той суммой и за два месяца сразу.

### 5.4. Заявки в ОСИ

```sql
request_categories
  id, organization_id, name, sla_hours, is_active

service_requests
  id, organization_id, apartment_id, author_id, category_id,
  title, description, status, priority,
  assigned_to, sla_due_at, closed_at, rating, created_at
  -- status: new | accepted | in_progress | done | rejected | closed

request_attachments
  id, request_id, file_url, file_type, uploaded_by

request_events         -- история статусов и комментариев
  id, request_id, author_id, event_type, comment, created_at
```

`sla_due_at` рассчитывается при создании из `category.sla_hours`. Просроченные заявки — главный отчёт в панели ОСИ и основной аргумент при продаже тарифа.

### 5.5. Чат

```sql
channels
  id, complex_id, building_id, entrance_id, type, name,
  is_readonly, created_at
  -- type: announcements | complex | building | entrance | marketplace

channel_members
  id, channel_id, user_id, role, muted_until, joined_at

messages
  id, channel_id, author_id, text, reply_to_id,
  is_pinned, deleted_at, created_at

message_attachments
  id, message_id, file_url, file_type, width, height, size_bytes

message_reads
  id, channel_id, user_id, last_read_message_id, updated_at
```

Разделение на каналы — не украшение: один общий чат на 300 человек превращается в помойку за две недели, и люди возвращаются в WhatsApp. `announcements` — только для ОСИ, читается всеми, дублируется push-уведомлением.

### 5.6. Счётчики

```sql
meters
  id, apartment_id, type, serial_number, installed_at,
  next_check_at, is_active
  -- type: cold_water | hot_water | electricity | gas | heating

meter_readings
  id, meter_id, value, previous_value, photo_url,
  ocr_value, ocr_confidence, source, submitted_by,
  period_year, period_month, status, created_at
  -- source: manual | ocr | osi_import
  -- status: pending | accepted | rejected
```

OCR не заменяет человека, а подставляет значение в поле: пользователь фотографирует, видит распознанное число и подтверждает. `ocr_confidence` ниже порога — поле остаётся пустым, ввод вручную.

### 5.7. Собрания и голосования

```sql
meetings
  id, complex_id, title, description, type,
  starts_at, ends_at, quorum_percent, status, protocol_url
  -- type: annual | extraordinary | survey
  -- status: draft | active | finished | cancelled

meeting_questions
  id, meeting_id, order_num, text, options, majority_type

ballots
  id, meeting_id, apartment_id, user_id,
  weight, submitted_at, ip_address
  -- weight = доля площади квартиры (голосование по площади, не по головам)

ballot_answers
  id, ballot_id, question_id, answer

meeting_results
  id, meeting_id, question_id, option, votes_count,
  votes_weight, percent
```

Голос весит по площади квартиры — так требует законодательство о жилищных отношениях. Один голос от квартиры, а не от человека: `UNIQUE (meeting_id, apartment_id)`. Точные требования к юридической силе протокола нужно сверить с юристом до релиза модуля.

### 5.8. Прозрачность финансов ОСИ

```sql
budget_periods
  id, organization_id, complex_id, year, month, status, published_at

budget_items
  id, budget_period_id, direction, category, title,
  amount, document_url, created_by
  -- direction: income | expense
```

Самая дешёвая в разработке функция с самым высоким эффектом на доверие: снимает вечный конфликт «куда ушли наши деньги».

### 5.9. Объявления

```sql
listings
  id, complex_id, author_id, type, category, title,
  description, price, status, views_count,
  published_at, expires_at
  -- type: sell | buy | service | give_away
  -- status: draft | active | archived | sold | blocked

listing_photos
  id, listing_id, file_url, order_num

listing_promotions     -- платное продвижение
  id, listing_id, type, amount, starts_at, ends_at, payment_ref
  -- type: pin_top | highlight | push
```

Размещение бесплатное — платное убивает ликвидность доски. Монетизация только через продвижение.

### 5.10. Уведомления

```sql
devices
  id, user_id, fcm_token, platform, app_version, last_seen_at

notifications
  id, user_id, type, title, body, payload,
  channel, status, sent_at, read_at
  -- channel: push | sms | in_app
```

---

## 6. Сквозные технические решения

### Аутентификация
Вход по номеру телефона + код из SMS. Пароля нет вообще — меньше кода, меньше проблем с безопасностью, привычнее пользователю.
- Access token — JWT, 15 минут
- Refresh token — в БД с возможностью отзыва, 90 дней
- Rate limit на отправку кода: 3 в час на номер, 10 в час на IP

### Мультитенантность
Каждая таблица с пользовательскими данными несёт `organization_id`. Проверка доступа — в общей зависимости `deps.py`, а не в каждом роутере. Администратор ОСИ физически не может увидеть чужой ЖК: фильтр по организации накладывается на уровне запроса.

### Идемпотентность
Все POST-эндпоинты, приводящие к финансовым последствиям или отправке сообщений, принимают заголовок `Idempotency-Key`. Мобильный клиент на плохой связи будет ретраить — это данность, а не исключение.

### Работа с плохой сетью
Требование из ТЗ — 2G/3G. Следствия: пагинация курсорная, а не по offset; списки отдаются компактно; чат догружается порциями; тяжёлые изображения отдаются через ресайз на стороне сервера.

### Логирование и ошибки
Структурные логи в JSON, `request_id` сквозной через все слои. Sentry с первого дня — дешевле любого другого способа узнать, что у пользователя сломалось.

### Работа с внешним Flutter-разработчиком
- OpenAPI-схема генерируется FastAPI автоматически и публикуется на staging
- Клиент для Flutter генерируется из схемы, а не пишется руками
- Мок-сервер поднимается из той же схемы — фронтендер начинает работу, не дожидаясь готовности бэка
- Любое изменение контракта — только через изменение Pydantic-схемы

---

## 7. Порядок разработки

Модули идут не по «важности», а по зависимостям: следующий не начинается, пока предыдущий не отдаёт рабочий API.

| Волна | Модули | Результат |
|---|---|---|
| **1** | core, auth, properties, residents | Пользователь регистрируется и привязывается к квартире. Есть админка ОСИ со списком жильцов и импортом из CSV |
| **2** | billing | Квитанции, оплата, архив чеков, ручная и автоматическая сверка. **Это продукт, за который платит ОСИ** |
| **3** | requests, chat | Заявки с SLA и каналы вместо WhatsApp. Это то, что удерживает жильца |
| **4** | notifications, meters | Push-уведомления и показания счётчиков |
| **5** | voting, finance, classifieds | Тариф «Про» и монетизация продвижения |

Отложено за пределы MVP: маркетплейс магазинов, мастера, домофония, гостевые пропуска.
