"""Rank stage — EvaluationResult → RankResult"""

from __future__ import annotations

from ..tools.rank import rank_candidates

try:
    from langchain_core.runnables import RunnableLambda

    def _rank(state: dict) -> dict:
        er = state.get("evaluation_result")
        if er is None:
            return state
        result = rank_candidates(er, state["params"], state["ctx"])
        return {**state, "rank_result": result}

    rank_stage = RunnableLambda(_rank).with_config(run_name="rank")

except ImportError:  # pragma: no cover

    def _rank(state: dict) -> dict:  # type: ignore[no-redef]
        er = state.get("evaluation_result")
        if er is None:
            return state
        result = rank_candidates(er, state["params"], state["ctx"])
        return {**state, "rank_result": result}

    rank_stage = _rank  # type: ignore[assignment]
