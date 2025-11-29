from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from api_v1.comments.schemas import SimpleMeta


class StatsRangeDTO(BaseModel):
    since: int
    until: int


class MonthInsightsDTO(BaseModel):
    month: str
    range: StatsRangeDTO
    insights: Dict[str, Any] = Field(default_factory=dict)


class StatsReportPayload(BaseModel):
    period: str
    generated_at: str
    months: List[MonthInsightsDTO]


class StatsReportResponse(BaseModel):
    meta: SimpleMeta
    payload: StatsReportPayload


class AccountInsightsPayload(BaseModel):
    username: str | None = None
    media_count: int | None = None
    followers_count: int | None = None
    follows_count: int | None = None
    id: str | None = None


class AccountInsightsResponse(BaseModel):
    meta: SimpleMeta
    payload: AccountInsightsPayload


class ModerationSummaryDTO(BaseModel):
    total_verified_content: int
    complaints_total: int
    complaints_processed: int
    average_reaction_time_seconds: float | None = None


class ModerationOtherViolations(BaseModel):
    count: int
    examples: List[str] = Field(default_factory=list)


class ModerationViolationsDTO(BaseModel):
    spam_advertising: int
    adult_content: int
    insults_toxicity: int
    other: ModerationOtherViolations


class ActionBreakdown(BaseModel):
    ai: int = 0
    manual: int = 0


class AIModeratorStatsDTO(BaseModel):
    deleted_content: ActionBreakdown
    hidden_comments: ActionBreakdown


class ModerationMonthInsightsDTO(BaseModel):
    month: str
    range: StatsRangeDTO
    summary: ModerationSummaryDTO
    violations: ModerationViolationsDTO
    ai_moderator: AIModeratorStatsDTO


class ModerationStatsPayload(BaseModel):
    period: str
    generated_at: str
    months: List[ModerationMonthInsightsDTO]


class ModerationStatsResponse(BaseModel):
    meta: SimpleMeta
    payload: ModerationStatsPayload
