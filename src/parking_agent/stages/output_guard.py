"""Output guard stage — check_response 대조"""

from __future__ import annotations

from ..guardrails.output import check_response
from ..types import ParkingState

try:
    from langchain_core.runnables import RunnableLambda

    def _output_guard(state: dict) -> dict:
        # answer가 이미 있는 경우만 대조, 없으면 스킵
        if "answer" not in state:
            return state
        rank_result = state.get("rank_result")
        verdict, reason = check_response(state["answer"], rank_result)
        return {**state, "verdict": verdict, "verdict_reason": reason}

    output_guard_stage = RunnableLambda(_output_guard).with_config(run_name="output_guard")

except ImportError:  # pragma: no cover

    def _output_guard(state: dict) -> dict:  # type: ignore[no-redef]
        if "answer" not in state:
            return state
        rank_result = state.get("rank_result")
        verdict, reason = check_response(state["answer"], rank_result)
        return {**state, "verdict": verdict, "verdict_reason": reason}

    output_guard_stage = _output_guard  # type: ignore[assignment]
