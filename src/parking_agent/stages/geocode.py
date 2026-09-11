"""Geocode stage — RankingParams.place → GeocodeResult

대기 후보(pending)가 있고 발화가 선택이면 geocode 호출 없이 확정합니다.
"""

from __future__ import annotations

from dataclasses import replace

from ..tools.geocode import geocode_place, resolve_choice
from ..types import GeocodeResult, ParkingState


def _resolve_pending(state: dict) -> dict | None:
    """pending 선택이 확정되면 destination을 채운 state를 돌려줍니다.

    확정된 후보가 곧 유효 장소이므로 params.place도 후보명으로 갱신합니다.
    아니면 None을 돌려 정상 geocode 경로로 갑니다.
    """
    pending = state.get("pending")
    if not pending:
        return None
    resolved = resolve_choice(pending, state.get("utterance", ""))
    if resolved is None:
        return None
    return {
        **state,
        "params": replace(state["params"], place=resolved.name),
        "geocode_result": GeocodeResult(candidates=[resolved]),
        "destination": resolved,
        "pending": None,
    }


def _run_geocode(state: dict) -> dict:
    pending_state = _resolve_pending(state)
    if pending_state is not None:
        return pending_state
    result = geocode_place(state["params"].place, state["ctx"])
    destination = result.candidates[0] if result.is_confirmed else None
    pending = None if result.is_confirmed else result.candidates
    if not result.candidates:
        pending = None
    return {
        **state,
        "geocode_result": result,
        "destination": destination,
        "pending": pending,
    }


try:
    from langchain_core.runnables import RunnableLambda

    def _geocode(state: dict) -> dict:
        return _run_geocode(state)

    geocode_stage = RunnableLambda(_geocode).with_config(run_name="geocode")

except ImportError:  # pragma: no cover

    def _geocode(state: dict) -> dict:  # type: ignore[no-redef]
        return _run_geocode(state)

    geocode_stage = _geocode  # type: ignore[assignment]
