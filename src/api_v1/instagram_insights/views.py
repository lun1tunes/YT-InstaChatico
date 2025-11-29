from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from api_v1.comments.views import JsonApiError
from api_v1.comments.schemas import SimpleMeta
from api_v1.instagram_insights.schemas import (
    StatsReportResponse,
    StatsReportPayload,
    AccountInsightsResponse,
    ModerationStatsResponse,
    ModerationStatsPayload,
)
from core.dependencies import (
    get_generate_stats_report_use_case,
    get_container,
    get_generate_moderation_stats_use_case,
)
from core.use_cases.generate_stats_report import (
    GenerateStatsReportUseCase,
    StatsPeriod,
    StatsReportError,
)
from core.use_cases.generate_moderation_stats import (
    GenerateModerationStatsUseCase,
    ModerationStatsError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["Instagram Insights"])


@router.get(
    "/instagram_insights",
    response_model=StatsReportResponse,
    summary="Get Instagram insights for the selected period",
    description=(
        "Returns a consolidated report for the requested period. "
        "Past months are served from the `stats_reports` cache, while the current month "
        "is fetched from the Instagram API and stored for reuse."
    ),
)
async def get_stats_report(
    period: StatsPeriod = Query(StatsPeriod.LAST_MONTH),
    use_case: GenerateStatsReportUseCase = Depends(get_generate_stats_report_use_case),
):
    try:
        result = await use_case.execute(period)
    except StatsReportError as exc:
        logger.error("Stats report error | period=%s | error=%s", period.value, exc)
        raise JsonApiError(exc.status_code, 5008, str(exc))

    payload = StatsReportPayload(**result)
    return StatsReportResponse(meta=SimpleMeta(), payload=payload)


@router.get(
    "/moderation",
    response_model=ModerationStatsResponse,
    summary="Get moderation statistics for the selected period",
    description="Aggregates comment classification, complaint, and moderation action metrics per month.",
)
async def get_moderation_stats_report(
    period: StatsPeriod = Query(StatsPeriod.LAST_MONTH),
    use_case: GenerateModerationStatsUseCase = Depends(get_generate_moderation_stats_use_case),
):
    try:
        result = await use_case.execute(period)
    except ModerationStatsError as exc:
        logger.error("Moderation stats error | period=%s | error=%s", period.value, exc)
        raise JsonApiError(exc.status_code, 5010, str(exc))

    payload = ModerationStatsPayload(**result)
    return ModerationStatsResponse(meta=SimpleMeta(), payload=payload)


@router.get(
    "/account",
    response_model=AccountInsightsResponse,
    summary="Get Instagram account profile counters",
    description=(
        "Fetches `username`, `media_count`, `followers_count`, `follows_count`, "
        "and `id` for the configured Instagram business account."
    ),
)
async def get_account_insights(
    container = Depends(get_container),
):
    instagram_service = container.instagram_service()
    try:
        result = await instagram_service.get_account_profile()
    except Exception as exc:
        logger.error("Account insights error | error=%s", exc)
        raise JsonApiError(502, 5009, "Failed to fetch Instagram account insights")

    if not result.get("success"):
        error_message = result.get("error") or "Instagram account lookup failed"
        logger.error("Instagram account insights failed | error=%s", error_message)
        raise JsonApiError(502, 5009, "Failed to fetch Instagram account insights")

    payload = result.get("data", {})
    return AccountInsightsResponse(meta=SimpleMeta(), payload=payload)
