"""Format stage — RankResult → answer 문자열

응답 조립은 format_answer에 위임합니다. LLM 경로는 도입부 + 결정론적 목록,
실패 시 템플릿 폴백입니다.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Stage wrapper
# --------------------------------------------------------------------------

try:
    from langchain_core.runnables import RunnableLambda

    def _format(state: dict) -> dict:
        from ..format import format_answer

        rank_result = state.get("rank_result")
        params = state["params"]

        # rank_result가 None인 경우는 geocode 실패 등으로 이미 answer가 결정된 경우
        if rank_result is None:
            return state

        answer = format_answer(
            rank_result, params, state["ctx"], state.get("utterance", "")
        )
        return {**state, "answer": answer}

    format_stage = RunnableLambda(_format).with_config(run_name="format")

except ImportError:  # pragma: no cover

    def _format(state: dict) -> dict:  # type: ignore[no-redef]
        from ..format import format_answer

        rank_result = state.get("rank_result")
        params = state["params"]
        if rank_result is None:
            return state
        answer = format_answer(
            rank_result, params, state["ctx"], state.get("utterance", "")
        )
        return {**state, "answer": answer}

    format_stage = _format  # type: ignore[assignment]
