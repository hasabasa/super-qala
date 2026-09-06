"""Точка входа приложения SmartQala."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.redis import redis_client
from app.core.storage import ensure_bucket
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.chat.router import router as chat_router
from app.modules.files.router import router as files_router
from app.modules.classifieds.router import router as classifieds_router
from app.modules.finance.router import router as finance_router
from app.modules.meters.router import router as meters_router
from app.modules.notifications.router import router as notifications_router
from app.modules.properties.router import router as properties_router
from app.modules.requests.router import router as requests_router
from app.modules.residents.router import router as residents_router
from app.modules.voting.router import router as voting_router

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.ENV, traces_sample_rate=0.1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    await ensure_bucket()
    yield
    await redis_client.aclose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API платформы управления жилым комплексом",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.ENV}


# Роутеры модулей. Добавляя новый модуль — подключи его здесь.
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(properties_router, prefix=settings.API_PREFIX)
app.include_router(billing_router, prefix=settings.API_PREFIX)
app.include_router(residents_router, prefix=settings.API_PREFIX)
app.include_router(requests_router, prefix=settings.API_PREFIX)
app.include_router(chat_router, prefix=settings.API_PREFIX)
app.include_router(notifications_router, prefix=settings.API_PREFIX)
app.include_router(meters_router, prefix=settings.API_PREFIX)
app.include_router(voting_router, prefix=settings.API_PREFIX)
app.include_router(finance_router, prefix=settings.API_PREFIX)
app.include_router(classifieds_router, prefix=settings.API_PREFIX)
app.include_router(files_router, prefix=settings.API_PREFIX)
