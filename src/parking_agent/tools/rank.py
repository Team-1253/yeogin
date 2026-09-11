"""후보를 정렬하고 상위 3곳을 선정합니다. [담당: P6]

정렬은 결정론적으로 수행합니다. LLM에 맡기지 않습니다.
"""

from __future__ import annotations

from ..types import (
    Evaluation,
    EvaluationResult,
    RankingParams,
    RankResult,
    Recommendation,
    RequestContext,
)


def rank_candidates(
    evaluation: EvaluationResult,
    params: RankingParams,
    ctx: RequestContext,
) -> RankResult:
    """필수조건을 통과한 후보를 정렬하고 Top 3을 선정합니다.

    추천 목록을 확정하기 직전에 호출하며, 정렬과 선정을 직접 수행하지 마세요.
    조건을 만족하는 후보가 없으면 빈 목록을 반환합니다. 임의로 추천하지 않습니다.
    """
    ordered = sorted(evaluation.passed, key=_sort_key(params.sort_by))
    top = ordered[: ctx.policy.top_k]

    assumed = top[0].assumed_fields if top else []
    return RankResult(
        recommendations=[_to_recommendation(i + 1, e) for i, e in enumerate(top)],
        rejected=evaluation.rejected,
        sort_by=params.sort_by,
        assumed_fields=list(assumed),
    )


def _sort_key(sort_by: str):
    """정렬 기준을 반환합니다.

    잔여 정보가 확인되는 후보를 먼저 배치한 뒤, 선택한 기본 기준의
    확인 불가 값(``None``)을 후순위로 보냅니다. 모든 키가 같은 후보는
    ``sorted``의 안정 정렬에 따라 입력 순서를 유지합니다.
    """

    def key(e: Evaluation):
        availability_unknown = e.lot.available_slots is None
        if sort_by == "price":
            primary_missing = e.estimated_fee is None
            primary = e.estimated_fee if e.estimated_fee is not None else 0
        else:
            primary_missing = False
            primary = e.distance_m
        return (availability_unknown, primary_missing, primary, e.distance_m)

    return key


def _to_recommendation(rank: int, e: Evaluation) -> Recommendation:
    """응답에 노출될 문자열을 완성합니다.

    수치를 문자열로 만드는 책임은 여기까지입니다.
    format_answer는 이 값을 그대로 인용하며 계산하지 않습니다.
    """
    fee_text = f"{e.estimated_fee:,}원" if e.estimated_fee is not None else "계산 불가"

    slots = e.lot.available_slots
    availability_text = f"{slots}면" if slots is not None else "확인 불가"

    if e.minutes_until_close is None:
        hours_text = "24시간"
    else:
        h, m = divmod(e.minutes_until_close, 60)
        close = f"{e.lot.close_time[:2]}:{e.lot.close_time[2:]}" if e.lot.close_time else ""
        hours_text = f"{close} 마감 ({h}시간 {m}분 남음)".strip()

    return Recommendation(
        rank=rank,
        name=e.lot.name,
        distance_m=e.distance_m,
        fee_text=fee_text,
        availability_text=availability_text,
        hours_text=hours_text,
    )
