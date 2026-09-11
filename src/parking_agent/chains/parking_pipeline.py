"""LCEL 주차 파이프라인 — 논리적 pipeline을 Runnable graph로 승격

계획서 5.1/8장의 목표를 구현한다:

    extract → validation → branch
                            ├─ invalid → answer (early return)
                            └─ valid → geocode → branch
                                              ├─ no candidates → answer
                                              ├─ ambiguous → answer
                                              └─ confirmed → search → evaluate → rank → format → output_guard

LCEL의 RunnableBranch / RunnablePassthrough를 사용해 Python if문이 아니라
composition 자체가 실행 그래프가 되도록 한다.
"""

from __future__ import annotations

from typing import Any

from ..stages.evaluate import evaluate_stage
from ..stages.extract import extract_stage
from ..stages.format import format_stage
from ..stages.geocode import geocode_stage
from ..stages.output_guard import output_guard_stage
from ..stages.rank import rank_stage
from ..stages.search import search_stage
from ..stages.validate import validation_stage
from ..types import AgentResponse, ParkingState

try:
    from langchain_core.runnables import RunnableBranch, RunnableLambda, RunnablePassthrough

    HAS_LCEL = True
except ImportError:  # pragma: no cover
    HAS_LCEL = False

# --------------------------------------------------------------------------
# Early-return helpers — 각 분기의 leaf가 state에 answer를 채운다
# --------------------------------------------------------------------------

def _validation_failed(state: dict) -> dict:
    msg = state.get("validation_message") or ""
    return {**state, "answer": msg, "rank_result": None, "verdict": "SAFE", "verdict_reason": None}


def _geocode_no_result(state: dict) -> dict:
    msg = state["geocode_result"].message or ""
    return {**state, "answer": msg, "rank_result": None, "verdict": "SAFE", "verdict_reason": None}


def _geocode_ambiguous(state: dict) -> dict:
    candidates = state["geocode_result"].candidates
    options = " / ".join(f"{i+1}. {p.name}" for i, p in enumerate(candidates))
    place = state["params"].place
    return {
        **state,
        "answer": f"'{place}' 근처로 보이는 곳이 여러 곳 있습니다. 어느 곳을 말씀하시나요? {options}",
        "rank_result": None,
        "verdict": "SAFE",
        "verdict_reason": None,
    }


# --------------------------------------------------------------------------
# Final mapper — ParkingState → AgentResponse (호환성 facade에서 사용)
# --------------------------------------------------------------------------

def _to_response(state: dict) -> AgentResponse:
    return AgentResponse(
        answer=state.get("answer", ""),
        params=state["params"],
        rank_result=state.get("rank_result"),
        verdict=state.get("verdict", "SAFE"),
        verdict_reason=state.get("verdict_reason"),
        pending=state.get("pending"),
    )


# --------------------------------------------------------------------------
# LCEL graph 정의
# --------------------------------------------------------------------------

if HAS_LCEL:
    # Leaf runnables for branching (answer채움)
    validation_failed_stage = RunnableLambda(_validation_failed).with_config(run_name="validation_failed")
    geocode_no_result_stage = RunnableLambda(_geocode_no_result).with_config(run_name="geocode_no_result")
    geocode_ambiguous_stage = RunnableLambda(_geocode_ambiguous).with_config(run_name="geocode_ambiguous")

    # Geocode 분기: empty → no_result, ambiguous → ambiguous, confirmed → search 이후
    geocode_branch = RunnableBranch(
        (lambda s: not s["geocode_result"].candidates, geocode_no_result_stage),
        (lambda s: not s["geocode_result"].is_confirmed, geocode_ambiguous_stage),
        # confirmed → 나머지 파이프라인
        (search_stage | evaluate_stage | rank_stage | format_stage | output_guard_stage),
    ).with_config(run_name="geocode_branch")

    # Validation 분기
    validation_branch = RunnableBranch(
        (lambda s: not s.get("is_valid", True), validation_failed_stage),
        (geocode_stage | geocode_branch),
    ).with_config(run_name="validation_branch")

    # 전체 파이프라인: extract → validate → (validation_branch)
    # validation_branch 내부에서 이미 format/output_guard까지 수행되므로
    # 추가로 output_guard를 한번 더 적용할 때 answer 없는 경우만 동작하도록 idempotent하게 설계
    parking_pipeline = (
        extract_stage | validation_stage | validation_branch
    ).with_config(run_name="parking_pipeline")

    # AgentResponse 매핑 체인
    parking_pipeline_with_response = parking_pipeline | RunnableLambda(_to_response).with_config(run_name="to_response")

else:  # pragma: no cover
    # langchain 없이도 동작하는 폴백 — 기존 pipeline.run과 동일한 순차 로직
    def _fallback_pipeline(state: dict) -> dict:
        state = _extract(state) if False else state  # placeholder to satisfy type checker
        return state

    # 단순 함수형 폴백
    def _fallback_invoke(state: dict) -> dict:
        from ..extract import extract_params
        from ..guardrails.input import check_request
        from ..guardrails.output import check_response
        from ..tools.evaluate import evaluate_candidates
        from ..tools.geocode import geocode_place, resolve_choice
        from ..tools.rank import rank_candidates
        from ..tools.search import search_parking
        from ..format import format_answer

        # 1 extract
        params = extract_params(state["utterance"], state.get("prev_params"))
        state = {**state, "params": params}
        # 2 validation (pending 선택은 통과)
        pending = state.get("pending")
        if pending and resolve_choice(pending, state.get("utterance", "")) is not None:
            state = {**state, "is_valid": True, "validation_message": None}
        else:
            ok, msg = check_request(params)
            state = {**state, "is_valid": ok, "validation_message": msg}
        if not ok:
            return {**state, "answer": msg or "", "rank_result": None, "verdict": "SAFE"}
        # 3 geocode (pending 선택이면 호출 없이 확정)
        resolved = (
            resolve_choice(pending, state.get("utterance", "")) if pending else None
        )
        if resolved is not None:
            from dataclasses import replace

            from ..types import GeocodeResult

            geo = GeocodeResult(candidates=[resolved])
            params = replace(params, place=resolved.name)
            state = {
                **state,
                "params": params,
                "geocode_result": geo,
                "destination": resolved,
                "pending": None,
            }
            dest = resolved
        else:
            geo = geocode_place(params.place, state["ctx"])
            dest = geo.candidates[0] if geo.is_confirmed else None
            state = {**state, "geocode_result": geo, "destination": dest}
            state = {
                **state,
                "pending": None if geo.is_confirmed or not geo.candidates else geo.candidates,
            }
        if not geo.candidates:
            return {**state, "answer": geo.message or "", "rank_result": None}
        if not geo.is_confirmed:
            options = " / ".join(f"{i+1}. {p.name}" for i, p in enumerate(geo.candidates))
            return {
                **state,
                "answer": f"'{params.place}' 근처로 보이는 곳이 여러 곳 있습니다. 어느 곳을 말씀하시나요? {options}",
                "rank_result": None,
            }
        # 4-6 search/evaluate/rank
        sr = search_parking(dest, state["ctx"])
        er = evaluate_candidates(sr, dest, params, state["ctx"])
        rr = rank_candidates(er, params, state["ctx"])
        state = {**state, "search_result": sr, "evaluation_result": er, "rank_result": rr}
        # 7 format
        ans = format_answer(rr, params, state["ctx"], state.get("utterance", ""))
        state = {**state, "answer": ans}
        # 8 guard
        verdict, reason = check_response(ans, rr)
        return {**state, "verdict": verdict, "verdict_reason": reason}

    class _FallbackPipeline:
        def invoke(self, state: dict) -> dict:
            return _fallback_invoke(state)

        def __or__(self, other):  # type: ignore[no-untyped-def]
            # 체인 연산을 위해 간단히 함수 합성 지원
            class _Chained:
                def invoke(self, s):  # type: ignore[no-untyped-def]
                    return other.invoke(_fallback_invoke(s)) if hasattr(other, "invoke") else other(_fallback_invoke(s))

            return _Chained()

    parking_pipeline = _FallbackPipeline()  # type: ignore[assignment]
    parking_pipeline_with_response = parking_pipeline  # type: ignore[assignment]
