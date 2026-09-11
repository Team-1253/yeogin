"""Validation stage — 입력 가드레일 (business validation)"""

from __future__ import annotations

from ..guardrails.input import check_request
from ..types import ParkingState

try:
    from langchain_core.runnables import RunnableLambda

    def _validate(state: dict) -> dict:
        ok, msg = check_request(state["params"])
        return {**state, "is_valid": ok, "validation_message": msg}

    validation_stage = RunnableLambda(_validate).with_config(run_name="validate_input")

except ImportError:  # pragma: no cover

    def _validate(state: dict) -> dict:  # type: ignore[no-redef]
        ok, msg = check_request(state["params"])
        return {**state, "is_valid": ok, "validation_message": msg}

    validation_stage = _validate  # type: ignore[assignment]
