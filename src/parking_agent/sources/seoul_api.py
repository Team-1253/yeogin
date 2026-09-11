"""서울시 공영주차장 API 어댑터입니다. [담당: P4]

원본 응답을 ParkingLot으로 변환하는 책임만 집니다.
확인할 수 없는 값은 추정하지 않고 None으로 둡니다.
"""

from __future__ import annotations

import csv
import os
import pathlib
from collections.abc import Iterable

from ..types import ParkingLot

DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
SEED_CSV = DATA_DIR / "seed_sample.csv"


def load_from_seed() -> list[ParkingLot]:
    """시드 CSV에서 후보를 읽습니다. 키가 없어도 전체 검증이 가능합니다."""
    if not SEED_CSV.exists():
        return []
    with SEED_CSV.open(encoding="utf-8") as f:
        return [_from_row(row) for row in csv.DictReader(f)]


def load_from_api(districts: Iterable[str]) -> list[ParkingLot]:
    """서울시 실시간 API에서 후보를 읽습니다.

    TODO(P4): GetParkingInfo 연동, 캐시, 좌표 백필을 구현하십시오.
    실패 시 예외를 던지지 말고 빈 리스트를 반환하십시오.
    """
    return []


def _from_row(row: dict) -> ParkingLot:
    """CSV 한 행을 ParkingLot으로 변환합니다."""

    def num(key: str):
        value = (row.get(key) or "").strip()
        return int(value) if value.isdigit() else None

    def text(key: str):
        return (row.get(key) or "").strip() or None

    return ParkingLot(
        code=row.get("code", ""),
        name=row.get("name", ""),
        address=row.get("address", ""),
        district=row.get("district", ""),
        lat=float(row["lat"]) if row.get("lat") else None,
        lng=float(row["lng"]) if row.get("lng") else None,
        total_slots=num("total_slots"),
        current_cars=num("current_cars"),
        open_time=text("open_time"),
        close_time=text("close_time"),
        base_fee=num("base_fee"),
        base_minutes=num("base_minutes"),
        extra_fee=num("extra_fee"),
        extra_minutes=num("extra_minutes"),
    )


def is_seoul_source() -> bool:
    """실데이터 모드 여부입니다."""
    return os.getenv("PARKING_SOURCE", "mock") == "seoul"
