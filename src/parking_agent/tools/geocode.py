"""목적지명을 좌표와 자치구로 변환합니다. [담당: P3]

예외를 던지지 않습니다. 실패는 GeocodeResult.message로 표현합니다.
현재 위치는 RequestContext에서 읽습니다. 도구가 GPS를 직접 호출하지 않습니다.
"""

from __future__ import annotations

import math
import os
import requests

KAKAO_API_KEY = os.environ["KAKAO_REST_API_KEY"]
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 사이의 직선 거리를 미터로 반환합니다."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))

def geocode_place(lat: float, lng: float, query: str) -> dict | None:
    """
        장소 이름을 좌표로 변환합니다. 목적지가 언급되면 가장 먼저 호출하세요.
        동명 장소가 여러 곳이면 사용자의 현재 위치에서 가까운 순으로 정렬해 최대 5곳을 반환합니다.
        2곳 이상이면 임의로 고르지 말고 되물으세요.
    """
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": query}
    resp = requests.get(KAKAO_KEYWORD_URL, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    documents = resp.json().get("documents")
    if not documents:
        return None

    candidates = [
        {
            "lat": float(doc["y"]),
            "lng": float(doc["x"]),
            "address": doc["address_name"],
            "place_name": doc["place_name"],
            "distance_m": haversine_m(lat, lng, float(doc["y"]), float(doc["x"])),
        }
        for doc in documents
    ]
    candidates.sort(key=lambda c: c["distance_m"])
    return candidates[:5]

print(geocode_place(37.394776, 127.11116, "엽기떡볶이"))