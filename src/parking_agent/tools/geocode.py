"""목적지명을 좌표와 자치구로 변환합니다. [담당: P3]

예외를 던지지 않습니다. 실패는 GeocodeResult.message로 표현합니다.
현재 위치는 RequestContext에서 읽습니다. 도구가 GPS를 직접 호출하지 않습니다.
"""

from __future__ import annotations

import math
import os
import re

from ..types import GeocodeResult, Place, RequestContext

#: TODO(P3): 실지오코딩 연동 전까지 사용하는 랜드마크 테이블입니다.
#: 30~50곳으로 확장하십시오. (이름, 주소, 위도, 경도, 자치구)
LANDMARKS: dict[str, tuple[str, float, float, str]] = {
    "강남역": ("서울 강남구 강남대로 396", 37.4979, 127.0276, "강남구"),
    "홍대입구": ("서울 마포구 양화로 160", 37.5570, 126.9245, "마포구"),
    "시청": ("서울 중구 세종대로 110", 37.5663, 126.9779, "중구"),
    "역삼역": ("서울 강남구 테헤란로 156", 37.5006, 127.0364, "강남구"),
    "코엑스": ("서울 강남구 영동대로 513", 37.5115, 127.0595, "강남구"),
    "시청역": ("서울 중구 세종대로 110", 37.5663, 126.9779, "중구"),
    "잠실역": ("서울 송파구 올림픽로 269", 37.5133, 127.1000, "송파구"),
    "서울역": ("서울 용산구 한강대로 405", 37.5547, 126.9706, "용산구"),
    "여의도": ("서울 영등포구 여의대로 108", 37.5260, 126.9240, "영등포구"),
    "건대입구": ("서울 광진구 능동로 120", 37.5403, 127.0691, "광진구"),
}

SUPPORTED_HINT = " · ".join(sorted(LANDMARKS))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 사이의 직선 거리를 미터로 반환합니다."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def resolve_choice(candidates: list[Place], utterance: str) -> Place | None:
    """대기 후보 중에서 사용자 선택을 확정합니다.

    "1", "1번" 같은 번호나 후보명의 일부를 받습니다. 범위를 벗어나거나
    후보와 무관한 발화면 None을 돌려 정상 신규 검색으로 넘깁니다.
    """
    text = utterance.strip()
    if m := re.match(r"^(\d+)\s*번?$", text):
        idx = int(m.group(1)) - 1
        return candidates[idx] if 0 <= idx < len(candidates) else None
    if len(text) >= 2:
        for cand in candidates:
            if text in cand.name or cand.name in text:
                return cand
    return None


def geocode_place(place: str, ctx: RequestContext) -> GeocodeResult:
    """장소 이름을 좌표로 변환합니다. 목적지가 언급되면 가장 먼저 호출하세요.

    동명 장소가 여러 곳이면 사용자의 현재 위치에서 가까운 순으로 정렬해
    최대 3곳을 반환하므로, 2곳 이상이면 임의로 고르지 말고 되물으세요.
    자치구가 직접 주어진 경우에는 호출하지 마세요.
    """
    # 1) 로컬 랜드마크 테이블 우선
    matched = [(k, v) for k, v in LANDMARKS.items() if k in place or place in k]
    if matched:
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

    # 2) Kakao API 폴백 (키가 있을 때만 시도, 실패 시에도 예외 없이 GeocodeResult로 반환)
    kakao_key = os.getenv("KAKAO_REST_API_KEY")
    if kakao_key:
        try:
            import requests

            headers = {"Authorization": f"KakaoAK {kakao_key}"}
            # RequestContext의 현재 위치가 있으면 거리 정렬에 활용, 없으면 서울시청 기준
            lat_ref = ctx.user_lat if ctx.user_lat is not None else 37.5663
            lng_ref = ctx.user_lng if ctx.user_lng is not None else 126.9779
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers=headers,
                params={"query": place},
                timeout=5,
            )
            resp.raise_for_status()
            documents = resp.json().get("documents") or []
            if documents:
                # Kakao 결과를 Place로 변환 (자치구 추출은 주소에서 파싱)
                candidates = []
                for doc in documents[:3]:
                    addr = doc.get("address_name", "")
                    district = ""
                    for token in addr.split():
                        if token.endswith("구"):
                            district = token
                            break
                    lat = float(doc["y"])
                    lng = float(doc["x"])
                    distance = haversine_m(lat_ref, lng_ref, lat, lng)
                    candidates.append(
                        Place(
                            name=doc.get("place_name", place),
                            address=addr,
                            lat=lat,
                            lng=lng,
                            district=district or "중구",
                            distance_from_user_m=distance,
                        )
                    )
                candidates.sort(key=lambda p: p.distance_from_user_m or 0)
                if candidates:
                    return GeocodeResult(candidates=candidates)
        except Exception:
            pass

    return GeocodeResult(
        candidates=[],
        message=f"지원하지 않는 장소입니다. 다음 중에서 선택해 주세요: {SUPPORTED_HINT}",
    )
