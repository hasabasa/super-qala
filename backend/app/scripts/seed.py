"""Первичное заполнение базы.

Создаёт пользователя по номеру телефона и выдаёт ему роль администратора
платформы. Без этого первую организацию создать невозможно: эндпоинт
закрыт как раз этой ролью.

Запуск:
    docker compose exec api python -m app.scripts.seed +77011234567
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import SessionFactory
from app.modules.auth.models import User, UserRole
from app.shared.enums import UserRoleType
from app.shared.phone import normalize_phone


async def grant_platform_admin(raw_phone: str) -> None:
    phone = normalize_phone(raw_phone)

    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.phone == phone))
        if user is None:
            user = User(phone=phone)
            session.add(user)
            await session.flush()
            print(f"Создан пользователь {phone}")
        else:
            print(f"Найден пользователь {phone}")

        existing = await session.scalar(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role == UserRoleType.PLATFORM_ADMIN,
            )
        )
        if existing is not None:
            print("Роль администратора платформы уже выдана")
            return

        session.add(UserRole(user_id=user.id, role=UserRoleType.PLATFORM_ADMIN))
        await session.commit()
        print("Выдана роль администратора платформы")
        print(f"Теперь войдите в приложение под номером {phone}")


def main() -> None:
    if len(sys.argv) != 2:
        print("Укажите номер телефона: python -m app.scripts.seed +77011234567")
        raise SystemExit(1)
    asyncio.run(grant_platform_admin(sys.argv[1]))


if __name__ == "__main__":
    main()
