"""Repository for JWT expired tokens."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.expired_token import ExpiredToken


class ExpiredTokenRepository(BaseRepository[ExpiredToken]):
    """Data access layer for expired JWT tokens."""

    def __init__(self, session: AsyncSession):
        super().__init__(ExpiredToken, session)

    async def get_by_jti(self, jti: str) -> Optional[ExpiredToken]:
        stmt = select(ExpiredToken).where(ExpiredToken.jti == jti)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_expired(self, jti: str, expired_at: datetime) -> ExpiredToken:
        existing = await self.get_by_jti(jti)
        if existing:
            return existing

        token = ExpiredToken(jti=jti, expired_at=expired_at)
        await self.create(token)
        return token
