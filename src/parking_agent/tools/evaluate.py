"""거리·운영시간·요금을 계산하고 필수조건을 판정합니다. [담당: P5]

이 모듈의 모든 수치는 결정론적으로 계산합니다. LLM을 호출하지 않습니다.
계산할 수 없는 항목은 None으로 두고 사유를 기록합니다.
"""

from __future__ import annotations

from ..types import (
    Evaluation,
    EvaluationResult,
    ParkingLot,
    Place,
    RankingParams,
    Rejection,
    RejectReason,
    RequestContext,
    SearchResult,
)
from .geocode import haversine_m

MINUTES_PER_DAY = 24 * 60


def evaluate_candidates(
    search: SearchResult,
    destination: Place,
    params: RankingParams,
    ctx: RequestContext,
) -> EvaluationResult:
    """후보별 거리·운영 여부·예상 요금을 계산하고 필수조건으로 거릅니다.

    필수조건을 만족하지 못한 후보는 제외하되 사유를 함께 반환합니다.
    확인할 수 없는 값은 추정하지 않습니다.
    """
    duration = params.duration_minutes or ctx.policy.default_duration_minutes
    assumed = [] if params.duration_minutes else ["duration_minutes"]

    passed: list[Evaluation] = []
    rejected: list[Rejection] = []

    for lot in search.lots:
        reasons: list[RejectReason] = []

        if lot.lat is None or lot.lng is None:
            continue  # 좌표 없는 후보는 거리 계산 불가이므로 조용히 제외합니다.
        distance = haversine_m(destination.lat, destination.lng, lot.lat, lot.lng)
        if distance > ctx.policy.max_distance_m:
            reasons.append("거리 초과")

        is_open, remaining = _check_hours(lot, ctx)
        if not is_open:
            reasons.append("영업 종료")
        elif remaining is not None and remaining < duration:
            reasons.append("영업시간 부족")

        if lot.available_slots is not None and lot.available_slots <= 0:
            reasons.append("만차")

        fee, basis, note = _calculate_fee(lot, duration)
        if params.budget_won is not None and fee is not None and fee > params.budget_won:
            reasons.append("예산 초과")

        if reasons:
            rejected.append(Rejection(lot_name=lot.name, reasons=reasons))
            continue

        passed.append(
            Evaluation(
                lot=lot,
                distance_m=distance,
                is_open=is_open,
                minutes_until_close=remaining,
                estimated_fee=fee,
                fee_basis=basis,
                fee_note=note,
                assumed_fields=list(assumed),
            )
        )

    return EvaluationResult(passed=passed, rejected=rejected)


def _check_hours(lot: ParkingLot, ctx: RequestContext) -> tuple[bool, int | None]:
    """운영 여부와 마감까지 남은 분을 반환합니다.
    """
    if not lot.open_time or not lot.close_time:
        return True, None
    if lot.open_time == "0000" and lot.close_time in ("2400", "0000"):
        return True, None

    now = ctx.request_time.hour * 60 + ctx.request_time.minute
    open_m = int(lot.open_time[:2]) * 60 + int(lot.open_time[2:])
    close_m = int(lot.close_time[:2]) * 60 + int(lot.close_time[2:])

    if open_m < close_m:
        if not (open_m <= now < close_m):
            return False, 0
        return True, close_m - now

    # 자정을 넘기는 운영시간입니다. 예: 22:00~02:00
    if now >= open_m:
        return True, MINUTES_PER_DAY - now + close_m
    if now < close_m:
        return True, close_m - now
    return False, 0


def _calculate_fee(
    lot: ParkingLot, duration_minutes: int
) -> tuple[int | None, str | None, str | None]:
    """예상 요금과 계산 근거를 반환합니다.

    요금 규칙이 없으면 (None, None, 사유)를 반환합니다. 추정하지 않습니다.
    """
    if lot.base_fee is None or lot.base_minutes is None:
        return None, None, "요금 정보 미제공"

    fee = lot.base_fee
    basis = f"기본 {lot.base_minutes}분 {lot.base_fee:,}원"
    extra_minutes = max(0, duration_minutes - lot.base_minutes)

    if extra_minutes and lot.extra_fee and lot.extra_minutes:
        units = -(-extra_minutes // lot.extra_minutes)  # 올림
        fee += units * lot.extra_fee
        basis += f" + 추가 {extra_minutes}분 {units * lot.extra_fee:,}원"
    elif extra_minutes:
        return None, None, "추가 요금 규칙 미제공"

    return fee, basis, "할인·무료시간은 반영되지 않았습니다"
