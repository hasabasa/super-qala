# SmartQala

Платформа управления жилым комплексом: квитанции и оплата, заявки в ОСИ, чат жильцов,
показания счётчиков, собрания и голосования, прозрачность расходов, доска объявлений.

## Документация

| Документ | О чём |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | Продуктовая концепция: проблема, функциональность, бизнес-модель, дорожная карта |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Стек, структура модулей, схема БД, порядок разработки |
| [docs/FRONTEND.md](docs/FRONTEND.md) | ТЗ для Flutter-разработчика |
| [sales-plan-valuation.md](sales-plan-valuation.md) | План продаж и оценка стоимости |
| [docs/archive/](docs/archive/) | Архив: исходная концепция, старая финмодель |

## Стек

Backend — Python 3.12 / FastAPI / PostgreSQL 16 / Redis 7 / arq
Mobile — Flutter
Админ-панели — Refine (React)

## Запуск локально

```bash
cp .env.example .env
# сгенерировать ключ: openssl rand -hex 32 → SECRET_KEY
docker compose up -d db redis minio
docker compose up api
```

- API: http://localhost:8000
- Документация API: http://localhost:8000/docs
- OpenAPI-схема: http://localhost:8000/openapi.json
- MinIO: http://localhost:9001

## Миграции

```bash
docker compose exec api alembic revision --autogenerate -m "описание"
docker compose exec api alembic upgrade head
```

## Структура

```
backend/app/core/      конфиг, БД, безопасность, зависимости
backend/app/modules/   бизнес-модули (auth, billing, chat, ...)
backend/app/workers/   фоновые задачи arq
admin/                 админ-панели
docs/                  документация
```
