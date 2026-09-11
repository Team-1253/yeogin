"""파이프라인을 조립합니다. [담당: P1]

각 단계는 담당자의 모듈을 호출만 합니다. 이 파일에 계산 로직을 넣지 않습니다.
"""

from __future__ import annotations

from .extract import extract_params
from .format import format_answer
from .guardrails.input import check_request
from .guardrails.output import check_response
from .tools.evaluate import evaluate_candidates
from .tools.geocode import geocode_place
from .tools.rank import rank_candidates
from .tools.search import search_parking
from .types import AgentResponse, RankingParams, RequestContext


def run(
    utterance: str,
    ctx: RequestContext,
    prev_params: RankingParams | None = None,
) -> AgentResponse:
    """사용자 발화 1건을 처리해 최종 응답을 반환합니다."""

    # 1. 발화 → 파라미터 (직전 조건 병합)
    params = extract_params(utterance, prev_params)

    # 2. 입력 가드레일
    ok, block_message = check_request(params)
    if not ok:
        return AgentResponse(answer=block_message or "", params=params)

    # 3. 목적지 확정
    geo = geocode_place(params.place, ctx)
    if not geo.candidates:
        return AgentResponse(answer=geo.message or "", params=params)
    if not geo.is_confirmed:
        options = " / ".join(f"{i + 1}. {p.name}" for i, p in enumerate(geo.candidates))
        return AgentResponse(
            answer=f"어느 곳을 말씀하시나요? {options}",
            params=params,
        )
    destination = geo.candidates[0]

    # 4. 후보 조회
    search = search_parking(destination, ctx)

    # 5. 계산과 필수조건 판정
    evaluation = evaluate_candidates(search, destination, params, ctx)

    # 6. 정렬과 Top 3
    rank_result = rank_candidates(evaluation, params, ctx)

    # 7. 응답 생성
    answer = format_answer(rank_result, params, ctx)

    # 8. 출력 가드레일
    verdict, reason = check_response(answer, rank_result)

    return AgentResponse(
        answer=answer,
        params=params,
        rank_result=rank_result,
        verdict=verdict,
        verdict_reason=reason,
    )
