"""실행 컨텍스트를 구성합니다. [담당: P1]

위치와 시각은 이곳에서만 읽습니다. 도구 내부에서 datetime.now()나
GPS를 직접 호출하지 않습니다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from .types import DayType, RequestContext, SearchPolicy

KST = timezone(timedelta(hours=9))

#: 2026년 공휴일입니다. 필요한 범위만 등록합니다.
HOLIDAYS_2026 = {"2026-09-24", "2026-09-25", "2026-09-26", "2026-10-03", "2026-10-09"}


def resolve_day_type(dt: datetime) -> DayType:
    """기준 시각의 요일 구분을 반환합니다."""
    if dt.strftime("%Y-%m-%d") in HOLIDAYS_2026:
        return "holiday"
    return "weekend" if dt.weekday() >= 5 else "weekday"


def build_context(
    user_id: str = "demo-user",
    user_lat: float | None = None,
    user_lng: float | None = None,
    now: datetime | None = None,
) -> RequestContext:
    """호출 1회분의 컨텍스트를 만듭니다.

    now를 명시하면 테스트에서 시각을 고정할 수 있습니다.
    """
    request_time = now or datetime.now(KST)
    return RequestContext(
        user_id=user_id,
        request_time=request_time,
        day_type=resolve_day_type(request_time),
        user_lat=user_lat,
        user_lng=user_lng,
        response_mode=os.getenv("RESPONSE_MODE", "normal"),  # type: ignore[arg-type]
        policy=SearchPolicy(),
    )


def is_llm_disabled() -> bool:
    """규칙 기반 모드 여부입니다. 단위 테스트는 항상 이 모드로 실행합니다."""
    return os.getenv("PARKING_AGENT_NO_LLM") == "1"
