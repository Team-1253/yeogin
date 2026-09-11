"""Format stage — RankResult → answer 문자열

chains 정본(formatting_chain)을 호출 시점에 가져와 쓰고,
규칙 템플릿 폴백을 유지한다.
"""

from __future__ import annotations

from ..types import ParkingState


def _stage_chain():
    """chains의 formatting_chain을 늦게 가져옵니다.

    모듈 로드 시점에 가져오면 chains/__init__ ↔ stages 순환 import가 생기므로
    호출 시점에 가져옵니다. 없으면 None을 돌려 템플릿 폴백으로 갑니다.
    """
    try:
        from ..chains.formatting_chain import formatting_chain

        return formatting_chain
    except Exception:  # pragma: no cover
        return None

# --------------------------------------------------------------------------
# Stage wrapper
# --------------------------------------------------------------------------

try:
    from langchain_core.runnables import RunnableLambda

    def _format(state: dict) -> dict:
        from ..context import is_llm_disabled
        from ..format import _format_by_template

        rank_result = state.get("rank_result")
        params = state["params"]

        # rank_result가 None인 경우는 geocode 실패 등으로 이미 answer가 결정된 경우
        if rank_result is None:
            return state

        # 빈 추천도 template으로 처리 (format_answer의 _format_empty와 동일)
        if rank_result.is_empty:
            from ..format import _format_empty

            answer = _format_empty(rank_result, params)
            return {**state, "answer": answer}

        if is_llm_disabled():
            answer = _format_by_template(rank_result, params)
            return {**state, "answer": answer}

        chain = _stage_chain()
        if chain is None:
            answer = _format_by_template(rank_result, params)
            return {**state, "answer": answer}

        try:
            recommendations = "\n".join(
                f"{r.rank}. {r.name} | 거리={r.distance_m}m | 요금={r.fee_text} | "
                f"잔여={r.availability_text} | 운영={r.hours_text}"
                for r in rank_result.recommendations
            )
            response = chain.invoke(
                {"place": params.place, "recommendations": recommendations}
            )
            answer = response.strip() if isinstance(response, str) and response.strip() else None
            if answer:
                return {**state, "answer": answer}
        except Exception:
            pass

        # 폴백
        from ..format import _format_by_template

        answer = _format_by_template(rank_result, params)
        return {**state, "answer": answer}

    format_stage = RunnableLambda(_format).with_config(run_name="format")

except ImportError:  # pragma: no cover

    def _format(state: dict) -> dict:  # type: ignore[no-redef]
        from ..context import is_llm_disabled
        from ..format import _format_by_template, _format_empty

        rank_result = state.get("rank_result")
        params = state["params"]
        if rank_result is None:
            return state
        if rank_result.is_empty:
            return {**state, "answer": _format_empty(rank_result, params)}
        if is_llm_disabled():
            return {**state, "answer": _format_by_template(rank_result, params)}
        return {**state, "answer": _format_by_template(rank_result, params)}

    format_stage = _format  # type: ignore[assignment]
