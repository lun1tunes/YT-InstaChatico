"""Repository for instrument token usage logging."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.instrument_token_usage import InstrumentTokenUsage


class InstrumentTokenUsageRepository(BaseRepository[InstrumentTokenUsage]):
    """Simple repository to persist instrument token usage entries."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstrumentTokenUsage, session)

    async def log(
        self,
        *,
        tool: str,
        task: str,
        model: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        comment_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> InstrumentTokenUsage:
        entry = InstrumentTokenUsage(
            tool=tool,
            task=task,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            comment_id=comment_id,
            details=details,
        )
        await self.create(entry)
        return entry
