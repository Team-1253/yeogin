"""Search stage — Place → SearchResult"""

from __future__ import annotations

from ..tools.search import search_parking

try:
    from langchain_core.runnables import RunnableLambda

    def _search(state: dict) -> dict:
        # destination이 None이면 이전 branching에서 이미 early-return 했어야 하지만
        # 방어적으로 빈 SearchResult를 넣는다.
        dest = state.get("destination")
        if dest is None:
            return state
        result = search_parking(dest, state["ctx"])
        return {**state, "search_result": result}

    search_stage = RunnableLambda(_search).with_config(run_name="search")

except ImportError:  # pragma: no cover

    def _search(state: dict) -> dict:  # type: ignore[no-redef]
        dest = state.get("destination")
        if dest is None:
            return state
        result = search_parking(dest, state["ctx"])
        return {**state, "search_result": result}

    search_stage = _search  # type: ignore[assignment]
