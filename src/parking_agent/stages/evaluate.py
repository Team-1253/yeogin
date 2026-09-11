"""Evaluate stage — 후보 계산 및 필수조건 판정"""

from __future__ import annotations

from ..tools.evaluate import evaluate_candidates
from ..types import ParkingState

try:
    from langchain_core.runnables import RunnableLambda

    def _evaluate(state: dict) -> dict:
        dest = state.get("destination")
        sr = state.get("search_result")
        if dest is None or sr is None:
            return state
        result = evaluate_candidates(sr, dest, state["params"], state["ctx"])
        return {**state, "evaluation_result": result}

    evaluate_stage = RunnableLambda(_evaluate).with_config(run_name="evaluate")

except ImportError:  # pragma: no cover

    def _evaluate(state: dict) -> dict:  # type: ignore[no-redef]
        dest = state.get("destination")
        sr = state.get("search_result")
        if dest is None or sr is None:
            return state
        result = evaluate_candidates(sr, dest, state["params"], state["ctx"])
        return {**state, "evaluation_result": result}

    evaluate_stage = _evaluate  # type: ignore[assignment]
