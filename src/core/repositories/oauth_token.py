"""Repository for OAuth token storage."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.oauth_token import OAuthToken


class OAuthTokenRepository(BaseRepository[OAuthToken]):
    """Data access layer for OAuth tokens."""

    def __init__(self, session: AsyncSession):
        super().__init__(OAuthToken, session)

    async def get_by_provider_account(self, provider: str, account_id: str) -> Optional[OAuthToken]:
        stmt = select(OAuthToken).where(
            OAuthToken.provider == provider,
            OAuthToken.account_id == account_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_provider(self, provider: str) -> Optional[OAuthToken]:
        stmt = (
            select(OAuthToken)
            .where(OAuthToken.provider == provider)
            .order_by(OAuthToken.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        provider: str,
        account_id: str,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        token_type: Optional[str],
        scope: Optional[str],
        expires_at: Optional[datetime],
    ) -> OAuthToken:
        existing = await self.get_by_provider_account(provider, account_id)
        if existing:
            existing.access_token_encrypted = access_token_encrypted
            existing.refresh_token_encrypted = refresh_token_encrypted
            existing.token_type = token_type
            existing.scope = scope
            existing.expires_at = expires_at
            existing.updated_at = datetime.utcnow()
            await self.session.flush()
            return existing

        record = OAuthToken(
            provider=provider,
            account_id=account_id,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            token_type=token_type,
            scope=scope,
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record
