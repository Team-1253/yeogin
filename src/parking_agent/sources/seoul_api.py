"""서울시 공영주차장 API 어댑터입니다. [담당: P4]

원본 응답을 ParkingLot으로 변환하는 책임만 집니다.
확인할 수 없는 값은 추정하지 않고 None으로 둡니다.
"""

from __future__ import annotations

import os
import pathlib
import requests

from collections.abc import Iterable

from ..types import ParkingLot

DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"

def load_coordinates(code: str) -> tuple[float | None, float | None]:
    """주차장 코드로 좌표를 조회하며, 확인할 수 없으면 None을 반환합니다."""
    key = os.getenv("SEOUL_OPENAPI_KEY")
    if not key:
        return None, None

    timeout_seconds = 10

    try:
        url = (
            f"http://openapi.seoul.go.kr:8088/{key}"
            f"/json/GetParkInfo/1/5/%20/{code}"
        )
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()["GetParkInfo"]

        if data["RESULT"]["CODE"] != "INFO-000":
            return None, None

        for row in data.get("row", []):
            if str(row["PKLT_CD"]) != code:
                continue

            lat = float(row["LAT"])
            lng = float(row["LOT"])

            # 서울 주차장에서 사용할 수 없는 좌표를 제외합니다.
            if not (0 < lat <= 90 and 0 < lng <= 180):
                continue

            return lat, lng

    except Exception:
        return None, None

    return None, None


def load_from_api(districts: Iterable[str]) -> list[ParkingLot]:
    """서울시 실시간 API에서 후보를 읽습니다.

    TODO(P4): GetParkingInfo 연동, 캐시, 좌표 백필을 구현하십시오.
    실패 시 예외를 던지지 말고 빈 리스트를 반환하십시오.
    """
    # 하나의 자치구
    # 키 읽기 -> url 구성 -> 요청 -> 오류 확인 -> JSON 해석 -> GetParkingInfo.RESULT.CODE 확인 → row 목록 추출
    
    # 유효한, 음이 아니 정수만 반환
    def to_int(value: object) -> int | None:
        """유효한 음이 아닌 정수만 반환합니다."""
        try:
            number = float(str(value))
            return int(number) if number >= 0 and number.is_integer() else None
        except (ValueError, OverflowError):
            return None

    # api key
    key = os.getenv("SEOUL_OPENAPI_KEY")

    # 없으면 빈 리스트 반환
    if not key:
        return []

    lots = []
    timeout_seconds = 10
    
    try:
        for district in districts:
            url = (
                f"http://openapi.seoul.go.kr:8088/{key}"
                f"/json/GetParkingInfo/1/100/{district}"
            )
            response = requests.get(url, timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json()["GetParkingInfo"]

            # 예외 처리 (정상 응답이 아니라면 리턴)
            if data["RESULT"]["CODE"] != "INFO-000":
                return []

            # 불러온 주차장 데이터 -> 구조화
            for row in data.get("row", []):
                # 주차장 위도 경도 계산 (API)
                lat, lng = load_coordinates(str(row["PKLT_CD"]))
                lots.append(
                    ParkingLot(
                        code=str(row["PKLT_CD"]),
                        name=row["PKLT_NM"],
                        address=row["ADDR"],
                        district=district,
                        total_slots=to_int(row.get("TPKCT")),
                        current_cars=(
                            to_int(row.get("NOW_PRK_VHCL_CNT"))
                            if str(row.get("PRK_STTS_YN")) == "1"
                            else None
                        ),
                        open_time=row.get("WD_OPER_BGNG_TM"), # 평일기준
                        close_time=row.get("WD_OPER_END_TM"),
                        base_fee=to_int(row.get("BSC_PRK_CRG")),
                        base_minutes=to_int(row.get("BSC_PRK_HR")),
                        extra_fee=to_int(row.get("ADD_PRK_CRG")),
                        extra_minutes=to_int(row.get("ADD_PRK_HR")),
                        lat=lat,
                        lng=lng
                    )
                )
    except Exception:
        return []
    
    return lots

