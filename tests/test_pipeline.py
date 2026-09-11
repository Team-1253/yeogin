"""파이프라인 통합 테스트입니다. [담당: P1]

시연 시나리오 S1~S5에 대응합니다.
"""

from __future__ import annotations

from parking_agent.pipeline import run


def test_s2_장소_누락시_명확화_질문(ctx):
    """S2: 장소가 없으면 입력 가드레일이 차단합니다."""
    response = run("주차장 찾아줘", ctx)
    assert "목적지" in response.answer


def test_s3_미지원_장소는_폴백_안내(ctx):
    """S3: 스택 노출 없이 지원 목록을 안내합니다."""
    response = run("은평구청 근처 주차장", ctx)
    assert "지원하지 않는" in response.answer
    assert "Traceback" not in response.answer


def test_출력_가드레일이_항상_판정한다(ctx):
    """모든 응답에 verdict가 존재합니다."""
    response = run("강남역 근처 2시간 주차", ctx)
    assert response.verdict in ("SAFE", "UNSAFE")
