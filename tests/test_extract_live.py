"""실제 모델 호출 테스트입니다. [담당: P2]

기본 실행(`pytest tests/`)에서는 건너뜁니다. 과금·지연·응답 변동이 있어
CI나 평소 검증에 넣지 않습니다.

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
    """S1 발화를 실제 모델로 파싱합니다. (API 1회 호출)"""
    params = _extract_by_llm("강남역 근처 2시간 주차, 만원 이하")
    assert params is not None
    assert params.place == "강남역"
    assert params.duration_minutes == 120
    assert params.budget_won == 10000
    assert params.sort_by == "distance"


def test_live_가격의도를_구분한다():
    """정렬 의도는 price, 예산 언급은 distance로 구분합니다. (API 2회 호출)"""
    cheap = _extract_by_llm("역삼역 근처 저렴한 순으로 2시간")
    plain = _extract_by_llm("코엑스 근처 1시간 주차")
    assert cheap is not None and plain is not None
    assert cheap.sort_by == "price"
    assert plain.sort_by == "distance"


def test_live_extract_params가_llm을_쓴다(monkeypatch):
    """NO_LLM을 끄면 파이프라인 진입점도 실제 모델을 씁니다. (API 1회 호출)"""
    monkeypatch.setenv("PARKING_AGENT_NO_LLM", "0")
    params = extract_params("역삼역 근처 저렴한 순으로 2시간")
    assert params.place == "역삼역"
    assert params.duration_minutes == 120
    assert params.sort_by == "price"
