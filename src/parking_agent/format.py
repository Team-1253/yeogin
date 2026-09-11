"""최종 응답 문장을 생성합니다. [담당: P6]

이 모듈은 수치를 계산하지 않습니다. Recommendation의 완성된 문자열만 인용합니다.
"""

from __future__ import annotations

from .context import is_llm_disabled
from .types import RankingParams, RankResult, RequestContext

FIELD_LABELS = {"duration_minutes": "주차 시간은 1시간 기준"}
REQUIRED_NOTICE = "현재 조회 데이터 기준"


def format_answer(
    result: RankResult,
    params: RankingParams,
    ctx: RequestContext,
    utterance: str = "",
) -> str:
    """추천 결과를 사용자 문장으로 만듭니다.

    LLM 경로는 도입부(발화에 대한 대화형 반응) + 결정론적 목록으로 구성하고,
    실패 시 템플릿으로 폴백합니다.
    """
    if result.is_empty:
        return _format_empty(result, params)

    if is_llm_disabled():
        return _format_by_template(result, params)
    return (
        _format_by_llm(result, params, ctx, utterance)
        or _format_by_template(result, params)
    )


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


def format_with_intro(
    result: RankResult, params: RankingParams, utterance: str
) -> str | None:
    """LLM 도입부 + 템플릿 목록을 합칩니다.

    도입부는 발화에 대한 대화형 반응 한두 문장으로, 숫자·금액·거리·주차장명·
    시각을 포함하지 않도록 체인 프롬프트에서 금지합니다. 목록과 고지 문구는
    템플릿이 그대로 담당하므로 환각 원천이 없습니다. 도입부 생성 실패·빈값이면
    None을 돌려 템플릿 전체 폴백으로 갑니다.
    """
    try:
        from .chains.formatting_chain import formatting_chain

        if formatting_chain is None:
            return None
        intro = formatting_chain.invoke(
            {"place": params.place, "utterance": utterance}
        )
        intro = intro.strip() if isinstance(intro, str) else ""
        if not intro:
            return None
        return intro + "\n" + _format_by_template(result, params)
    except Exception:
        return None


def _format_by_llm(result, params, ctx, utterance: str = "") -> str | None:
    """LLM 도입부를 생성합니다. 실패 시 None으로 템플릿 폴백합니다."""
    return format_with_intro(result, params, utterance)
