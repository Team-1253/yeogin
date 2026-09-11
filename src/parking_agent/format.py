"""최종 응답 문장을 생성합니다. [담당: P6]

이 모듈은 수치를 계산하지 않습니다. Recommendation의 완성된 문자열만 인용합니다.
"""

from __future__ import annotations

import os

from .context import is_llm_disabled
from .types import RankingParams, RankResult, RequestContext

FIELD_LABELS = {"duration_minutes": "주차 시간은 1시간 기준"}
REQUIRED_NOTICE = "현재 조회 데이터 기준"


def format_answer(result: RankResult, params: RankingParams, ctx: RequestContext) -> str:
    """추천 결과를 사용자 문장으로 만듭니다."""
    if result.is_empty:
        return _format_empty(result, params)

    if is_llm_disabled():
        return _format_by_template(result, params)
    return _format_by_llm(result, params, ctx) or _format_by_template(result, params)


def _format_empty(result: RankResult, params: RankingParams) -> str:
    """후보 0건 안내입니다. 문구를 고정해 환각 가능성을 차단합니다."""
    if not result.rejected:
        return f"{params.place} 근처에서 조회된 주차장이 없습니다. 다른 목적지로 찾아 드릴까요?"

    counts: dict[str, int] = {}
    for r in result.rejected:
        for reason in r.reasons:
            counts[reason] = counts.get(reason, 0) + 1
    detail = ", ".join(f"{k} {v}곳" for k, v in counts.items())
    return (
        f"{params.place} 근처에서 조건을 만족하는 주차장을 찾지 못했습니다. "
        f"({detail}) 예산을 올리거나 다른 목적지로 다시 찾아 드릴까요?"
    )


def _format_by_template(result: RankResult, params: RankingParams) -> str:
    """템플릿 응답입니다. 키가 없어도 전체 흐름이 검증됩니다."""
    lines = [f"{params.place} 근처 주차장 {len(result.recommendations)}곳입니다."]
    for r in result.recommendations:
        lines.append(
            f"{r.rank}. {r.name} · {r.distance_m}m · {r.fee_text} · "
            f"잔여 {r.availability_text} · {r.hours_text}"
        )
    if result.assumed_fields:
        notes = [FIELD_LABELS.get(f, f) for f in result.assumed_fields]
        lines.append(f"({', '.join(notes)}으로 계산했습니다.)")
    lines.append("현재 조회 데이터 기준이며 실제 현장 상황과 다를 수 있습니다.")
    return "\n".join(lines)


def _format_by_llm(result, params, ctx) -> str | None:
    """LLM으로 설명 문장을 생성합니다.

    LLM은 설명의 자연스러움만 담당하고, 추천 수치의 원천은 ``result``로
    고정합니다. 모듈 레벨의 formatting_chain을 재사용하며, 실패 시 None을 반환해
    템플릿으로 폴백합니다.
    """
    try:
        # Phase 5: 모듈 레벨 체인 재사용 (매 호출마다 prompt/model 생성 제거)
        from .chains.formatting_chain import formatting_chain

        if formatting_chain is None:
            return None

        recommendations = "\n".join(
            f"{r.rank}. {r.name} | 거리={r.distance_m}m | 요금={r.fee_text} | "
            f"잔여={r.availability_text} | 운영={r.hours_text}"
            for r in result.recommendations
        )
        response = formatting_chain.invoke(
            {"place": params.place, "recommendations": recommendations}
        )
        return response.strip() if isinstance(response, str) and response.strip() else None
    except Exception:
        return None
