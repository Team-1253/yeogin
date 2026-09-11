"""목적지 자치구와 인접 자치구의 주차장을 조회합니다. [담당: P4]

예외를 던지지 않습니다. 조회 실패는 빈 목록과 message로 표현합니다.
"""

from __future__ import annotations

from ..sources.seoul_api import load_from_api
from ..types import Place, RequestContext, SearchResult
from .districts import get_adjacent


def search_parking(destination: Place, ctx: RequestContext) -> SearchResult:
    """목적지가 속한 자치구와 인접 자치구의 공영주차장을 조회합니다.

    geocode_place로 목적지가 확정된 뒤에 호출하세요.
    주차장명, 주소, 시간당 요금, 총 주차면수, 실시간 잔여면을 반환합니다.
    자치구를 직접 지정해 반복 호출하지 마세요.
    """
    districts = get_adjacent(destination.district, ctx.policy.adjacent_district_count)
    if not districts:
        return SearchResult(
            lots=[],
            searched_districts=[],
            message="서울시 자치구가 아니어서 조회할 수 없습니다.",
        )

    lots = load_from_api(districts)

    if not lots:
        return SearchResult(
            lots=[],
            searched_districts=districts,
            message=f"{', '.join(districts)}에서 조회된 주차장이 없습니다.",
        )
    return SearchResult(lots=lots, searched_districts=districts)
