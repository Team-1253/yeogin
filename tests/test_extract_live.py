"""실제 모델 호출 테스트입니다. [담당: P2]

기본 실행(`pytest tests/`)에서는 건너뜁니다. 과금·지연·응답 변동이 있어
CI나 평소 검증에 넣지 않습니다. 선택 에이전트는 턴당 선택 호출 1회이고,
선택된 도구 실행은 API 호출이 아닙니다.

실행법 (PowerShell, .venv 기준):
  1. `.env`를 세션에 올립니다 (프로젝트 README의 키 검증 절차 참고).
  2. $env:PARKING_AGENT_LIVE_TEST="1"
  3. .\\.venv\\Scripts\\python.exe -m pytest tests/test_extract_live.py -v
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("langchain_openai")

from parking_agent.extract import _extract_by_llm, extract_params  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.getenv("PARKING_AGENT_LIVE_TEST") != "1" or not os.getenv("OPENAI_API_KEY"),
    reason="PARKING_AGENT_LIVE_TEST=1과 OPENAI_API_KEY가 있을 때만 실행합니다.",
)


def test_live_S1을_파싱한다():
    """S1 발화를 실제 모델로 파싱합니다. (선택 호출 1회)"""
    import parking_agent.extract as extract_mod

    params = _extract_by_llm("강남역 근처 2시간 주차, 만원 이하")
    assert params is not None
    assert params.place == "강남역"
    assert params.duration_minutes == 120
    assert params.budget_won == 10000
    assert params.sort_by == "distance"
    assert "place" in extract_mod.LAST_SLOT_CALLS


def test_live_가격의도를_구분한다():
    """정렬 의도는 price, 예산 언급은 distance로 구분합니다. (선택 호출 3회)"""
    import parking_agent.extract as extract_mod

    cheap = _extract_by_llm("역삼역 근처 저렴한 순으로 2시간")
    assert cheap is not None and cheap.sort_by == "price"
    assert "sort" in extract_mod.LAST_SLOT_CALLS

    plain = _extract_by_llm("코엑스 근처 1시간 주차")
    assert plain is not None and plain.sort_by == "distance"

    complaint = _extract_by_llm("너무 비싸")
    assert complaint is not None and complaint.sort_by == "price"
    assert extract_mod.LAST_SLOT_CALLS == ["sort"]


def test_live_extract_params가_llm을_쓴다(monkeypatch):
    """NO_LLM을 끄면 파이프라인 진입점도 실제 모델을 씁니다. (선택 호출 1회)"""
    monkeypatch.setenv("PARKING_AGENT_NO_LLM", "0")
    params = extract_params("역삼역 근처 저렴한 순으로 2시간")
    assert params.place == "역삼역"
    assert params.duration_minutes == 120
    assert params.sort_by == "price"


def test_live_빈슬롯은_None이다(monkeypatch):
    """장소만 있는 발화는 나머지 슬롯이 비어 있습니다. (선택 호출 1회)"""
    monkeypatch.setenv("PARKING_AGENT_NO_LLM", "0")
    params = extract_params("코엑스 주차장")
    assert params.place == "코엑스"
    assert params.duration_minutes is None
    assert params.budget_won is None
    assert params.sort_by == "distance"
