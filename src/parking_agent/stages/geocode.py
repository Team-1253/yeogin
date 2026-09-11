"""Geocode stage — RankingParams.place → GeocodeResult"""

from __future__ import annotations

from ..tools.geocode import geocode_place
from ..types import ParkingState

try:
    from langchain_core.runnables import RunnableLambda

    def _geocode(state: dict) -> dict:
        result = geocode_place(state["params"].place, state["ctx"])
        destination = result.candidates[0] if result.is_confirmed else None
        return {**state, "geocode_result": result, "destination": destination}

    geocode_stage = RunnableLambda(_geocode).with_config(run_name="geocode")

except ImportError:  # pragma: no cover

    def _geocode(state: dict) -> dict:  # type: ignore[no-redef]
        result = geocode_place(state["params"].place, state["ctx"])
        destination = result.candidates[0] if result.is_confirmed else None
        return {**state, "geocode_result": result, "destination": destination}

    geocode_stage = _geocode  # type: ignore[assignment]
