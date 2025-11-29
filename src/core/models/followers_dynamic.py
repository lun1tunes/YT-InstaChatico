from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from ..utils.time import now_db_utc


class FollowersDynamic(Base):
    __tablename__ = "followers_dynamic"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    followers_count: Mapped[int] = mapped_column(Integer, nullable=False)
    follows_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_db_utc, nullable=False)
