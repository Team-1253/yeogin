"""Extract stage — 발화 → RankingParams (도메인 로직은 extract_params에 위임)"""

from __future__ import annotations

from ..extract import extract_params
from ..types import ParkingState

try:
    from langchain_core.runnables import RunnableLambda

    def _extract(state: dict) -> dict:
        params = extract_params(state["utterance"], state.get("prev_params"))
        return {**state, "params": params}

    extract_stage = RunnableLambda(_extract).with_config(run_name="extract")

except ImportError:  # pragma: no cover

    def _extract(state: dict) -> dict:  # type: ignore[no-redef]
        params = extract_params(state["utterance"], state.get("prev_params"))
        return {**state, "params": params}

    extract_stage = _extract  # type: ignore[assignment]
