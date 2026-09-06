"""Точка входа фонового обработчика arq.

Запуск: arq app.workers.main.WorkerSettings
"""

from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.tasks import (
    deliver_notifications,
    mark_overdue_invoices,
    remind_payment_due,
    shutdown,
    startup,
)


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(str(settings.REDIS_URL))
    functions = [deliver_notifications, mark_overdue_invoices, remind_payment_due]
    on_startup = startup
    on_shutdown = shutdown
    cron_jobs = [
        # Рассылка — часто, остальное раз в сутки утром
        cron(deliver_notifications, minute=set(range(0, 60, 2))),
        cron(mark_overdue_invoices, hour=3, minute=0),
        cron(remind_payment_due, hour=9, minute=0),
    ]
