"""입력 가드레일입니다. [담당: P2]

LLM 호출 전에 규칙으로 차단하여 비용과 지연을 줄입니다.
파라미터 수준의 판정만 수행합니다. 좌표 조회 결과에 따른 분기는
geocode_place 이후에서 처리합니다.
"""

from __future__ import annotations

from ..types import RankingParams

MAX_DURATION_MINUTES = 24 * 60
MAX_BUDGET_WON = 500_000

INJECTION_PATTERNS = (
    "이전 지시",
    "system prompt",
    "너는 이제",
    "무시하고",
    "개발자 모드",
)


def check_request(params: RankingParams) -> tuple[bool, str | None]:
    """요청을 통과시킬지 판정합니다.

    Returns:
        (통과 여부, 차단 시 안내 문구)
    """
    if not params.place.strip():
        return False, "어느 장소 근처를 찾아 드릴까요? 목적지를 알려주세요."

    lowered = params.place.lower()
    if any(p in lowered for p in INJECTION_PATTERNS):
        return False, "주차장 안내와 관련된 내용만 도와드릴 수 있습니다."

    # 범위 보정은 차단이 아니라 값 조정입니다.
    if params.duration_minutes is not None:
        params.duration_minutes = max(1, min(params.duration_minutes, MAX_DURATION_MINUTES))
    if params.budget_won is not None:
        params.budget_won = max(0, min(params.budget_won, MAX_BUDGET_WON))

    return True, None
