"""파이프라인 통합 테스트입니다. [담당: P1]

시연 시나리오 S1~S5에 대응합니다.
"""

from __future__ import annotations

from parking_agent.pipeline import run


def test_s2_장소_누락시_명확화_질문(ctx):
    """S2: 장소가 없으면 입력 가드레일이 차단합니다."""
    response = run("주차장 찾아줘", ctx)
    assert "목적지" in response.answer


def test_s3_미지원_장소는_폴백_안내(ctx, monkeypatch):
    """S3: 스택 노출 없이 지원 목록을 안내합니다."""
    # Kakao 키 유무에 결과가 갈리므로 키를 제거해 LANDMARKS-only 모드로 고정합니다.
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    response = run("은평구청 근처 주차장", ctx)
    assert "지원하지 않는" in response.answer
    assert "Traceback" not in response.answer


def test_출력_가드레일이_항상_판정한다(ctx):
    """모든 응답에 verdict가 존재합니다."""
    response = run("강남역 근처 2시간 주차", ctx)
    assert response.verdict in ("SAFE", "UNSAFE")


def test_모호하면_후보를_pending에_담는다(ctx, monkeypatch):
    """모호성 해소 질문과 함께 다음 턴 선택용 후보를 돌려줍니다."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    response = run("시청 근처 주차장", ctx)
    assert response.rank_result is None
    assert response.pending is not None and len(response.pending) == 2


def test_다음턴_번호선택이_후보를_확정한다(ctx, monkeypatch):
    """숫자 선택은 geocode 재호출 없이 대기 후보로 확정됩니다."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    first = run("시청 근처 주차장", ctx)
    second = run("1", ctx, first.params, first.pending)
    assert second.answer != first.answer
    assert second.pending is None


def test_범위밖_선택은_다시_묻는다(ctx, monkeypatch):
    """후보 범위를 벗어나면 다시 묻고 pending을 유지합니다."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    first = run("시청 근처 주차장", ctx)
    second = run("9", ctx, first.params, first.pending)
    assert second.answer == first.answer
    assert second.pending is not None


def test_되묻기에_사용자언급_위치를_반환한다(ctx, monkeypatch):
    """모호성 해소 질문에 사용자가 말한 장소를 함께 돌려줍니다."""
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    response = run("시청 근처 주차장", ctx)
    assert "'시청'" in response.answer


def test_도입부_특수토큰을_제거한다(ctx, monkeypatch):
    """모델이 뱉은 <|endoftext|> 같은 토큰은 응답에 남지 않습니다."""
    import parking_agent.chains.formatting_chain as fc
    from parking_agent.format import format_with_intro
    from parking_agent.types import RankResult, RankingParams, Recommendation

    class FakeChain:
        def invoke(self, inputs):
            return "찾아봤어요. <|endoftext|>"

    monkeypatch.setattr(fc, "formatting_chain", FakeChain())
    result = RankResult(
        recommendations=[
            Recommendation(
                rank=1, name="A", distance_m=100, fee_text="1,000원",
                availability_text="5면", hours_text="24시간",
            )
        ],
        rejected=[],
        sort_by="distance",
    )
    answer = format_with_intro(result, RankingParams(place="a"), "주차장 알려줘")
    assert answer is not None and "<|" not in answer
    assert "1. A" in answer


def test_선택확정은_params_place를_갱신한다(ctx):
    """대기 후보 확정 시 하류 메시지가 후보명을 쓰도록 place를 갱신합니다."""
    from parking_agent.stages.geocode import _run_geocode
    from parking_agent.types import Place, RankingParams

    pending = [
        Place(name="A", address="a", lat=37.5, lng=127.0, district="강남구"),
        Place(name="B", address="b", lat=37.5, lng=127.0, district="강남구"),
    ]
    state = {
        "utterance": "2번",
        "params": RankingParams(place="어디"),
        "ctx": ctx,
        "pending": pending,
    }
    out = _run_geocode(state)
    assert out["destination"].name == "B"
    assert out["params"].place == "B"
    assert out["pending"] is None
