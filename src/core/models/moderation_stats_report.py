from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from ..utils.time import now_db_utc


class ModerationStatsReport(Base):
    __tablename__ = "moderation_stats_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    range_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_db_utc, nullable=False)
