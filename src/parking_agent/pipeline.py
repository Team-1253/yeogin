"""파이프라인을 조립합니다. [담당: P1]

LCEL execution graph를 호출하는 compatibility facade입니다.
내부 orchestration은 chains/parking_pipeline의 Runnable graph가 담당하고,
이 파일은 기존 외부 API(run) 시그니처를 유지합니다.
"""

from __future__ import annotations

from .types import AgentResponse, RankingParams, RequestContext


def run(
    utterance: str,
    ctx: RequestContext,
    prev_params: RankingParams | None = None,
) -> AgentResponse:
    """사용자 발화 1건을 처리해 최종 응답을 반환합니다.

    기존 시그니처를 유지한 채 내부적으로 LCEL 파이프라인을 invoke합니다.
    """
    from .chains.parking_pipeline import _to_response, parking_pipeline

    initial_state = {
        "utterance": utterance,
        "prev_params": prev_params,
        "ctx": ctx,
    }

    # parking_pipeline은 ParkingState를 반환한다
    result_state = parking_pipeline.invoke(initial_state)  # type: ignore[arg-type]
    # HAS_LCEL=False 폴백에서도 ParkingState가 반환됨
    if isinstance(result_state, AgentResponse):
        return result_state
    return _to_response(result_state)  # type: ignore[arg-type]
