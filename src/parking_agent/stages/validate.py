"""Validation stage — 입력 가드레일 (business validation)

대기 후보에 대한 선택 발화("1", 후보명)는 장소 추출 없이 통과시켜
geocode 단계에서 확정하도록 합니다.
"""

from __future__ import annotations

from ..guardrails.input import check_request
from ..tools.geocode import resolve_choice


def _run_validate(state: dict) -> dict:
    pending = state.get("pending")
    if pending and resolve_choice(pending, state.get("utterance", "")) is not None:
        return {**state, "is_valid": True, "validation_message": None}
    ok, msg = check_request(state["params"])
    return {**state, "is_valid": ok, "validation_message": msg}


try:
    from langchain_core.runnables import RunnableLambda

    def _validate(state: dict) -> dict:
        return _run_validate(state)

    validation_stage = RunnableLambda(_validate).with_config(run_name="validate_input")

except ImportError:  # pragma: no cover

    def _validate(state: dict) -> dict:  # type: ignore[no-redef]
        return _run_validate(state)

    validation_stage = _validate  # type: ignore[assignment]
