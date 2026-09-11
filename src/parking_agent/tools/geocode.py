"""목적지명을 좌표와 자치구로 변환합니다. [담당: P3]

예외를 던지지 않습니다. 실패는 GeocodeResult.message로 표현합니다.
현재 위치는 RequestContext에서 읽습니다. 도구가 GPS를 직접 호출하지 않습니다.
"""

from __future__ import annotations

import math

from ..types import GeocodeResult, Place, RequestContext

#: TODO(P3): 실지오코딩 연동 전까지 사용하는 랜드마크 테이블입니다.
#: 30~50곳으로 확장하십시오. (이름, 주소, 위도, 경도, 자치구)
LANDMARKS: dict[str, tuple[str, float, float, str]] = {
    "강남역": ("서울 강남구 강남대로 396", 37.4979, 127.0276, "강남구"),
    "홍대입구": ("서울 마포구 양화로 160", 37.5570, 126.9245, "마포구"),
    "시청": ("서울 중구 세종대로 110", 37.5663, 126.9779, "중구"),
    "역삼역": ("서울 강남구 테헤란로 156", 37.5006, 127.0364, "강남구"),
    "코엑스": ("서울 강남구 영동대로 513", 37.5115, 127.0595, "강남구"),
}

SUPPORTED_HINT = " · ".join(LANDMARKS)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 사이의 직선 거리를 미터로 반환합니다."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def geocode_place(place: str, ctx: RequestContext) -> GeocodeResult:
    """장소 이름을 좌표로 변환합니다. 목적지가 언급되면 가장 먼저 호출하세요.

    동명 장소가 여러 곳이면 사용자의 현재 위치에서 가까운 순으로 정렬해
    최대 3곳을 반환하므로, 2곳 이상이면 임의로 고르지 말고 되물으세요.
    자치구가 직접 주어진 경우에는 호출하지 마세요.
    """
    matched = [(k, v) for k, v in LANDMARKS.items() if k in place or place in k]
    if not matched:
        return GeocodeResult(
            candidates=[],
            message=f"지원하지 않는 장소입니다. 다음 중에서 선택해 주세요: {SUPPORTED_HINT}",
        )

    candidates = []
    for name, (address, lat, lng, district) in matched:
        distance = None
        if ctx.user_lat is not None and ctx.user_lng is not None:
            distance = haversine_m(ctx.user_lat, ctx.user_lng, lat, lng)
        candidates.append(
            Place(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                district=district,
                distance_from_user_m=distance,
            )
        )

    candidates.sort(key=lambda p: p.distance_from_user_m or 0)
    return GeocodeResult(candidates=candidates[:3])
