from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from ..utils.time import now_db_utc


class ExpiredToken(Base):
    """JWT tokens that have expired or been revoked."""

    __tablename__ = "expired_tokens"

    jti: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="JWT ID to uniquely identify a token",
    )
    expired_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="Timestamp when token expired or was revoked",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_db_utc,
        nullable=False,
        comment="When this record was created",
    )
