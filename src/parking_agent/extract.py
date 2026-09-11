"""사용자 발화에서 검색 조건을 추출합니다. [담당: P2]

LLM 구조화 출력을 우선 사용하고, 키가 없거나 실패하면 규칙 기반으로 폴백합니다.
미지정 항목을 임의의 기본값으로 채우지 않습니다. None으로 두십시오.
"""

from __future__ import annotations

import re

from .context import is_llm_disabled
from .types import RankingParams

PRICE_KEYWORDS = ("저렴", "싼", "싸게", "가격", "요금", "비싸")


def extract_params(
    utterance: str,
    prev: RankingParams | None = None,
) -> RankingParams:
    """발화를 RankingParams로 변환합니다.

    prev가 있으면 이번 발화에 명시된 필드만 덮어쓰고 나머지는 유지합니다.
    """
    if is_llm_disabled():
        params = _extract_by_rule(utterance)
    else:
        params = _extract_by_llm(utterance) or _extract_by_rule(utterance)

    if prev is not None:
        params = _merge(prev, params)
    return params


def _extract_by_llm(utterance: str) -> RankingParams | None:
    """LLM 구조화 출력으로 추출합니다. 실패 시 None을 반환합니다.

    TODO(P2): ChatPromptTemplate | with_structured_output(RankingParams)
    """
    return None


def _extract_by_rule(utterance: str) -> RankingParams:
    """정규식과 키워드로 추출합니다.

    TODO(P2): 장소 추출 정확도를 올리십시오. 현재는 최소 동작만 합니다.
    """
    place = ""
    # 1순위: "~ 근처/주변" 앞의 명사구를 장소로 봅니다.
    if m := re.search(r"([가-힣A-Za-z0-9]{2,10})\s*(?:근처|주변|인근|앞)", utterance):
        place = m.group(1)
    # 2순위: 장소를 뜻하는 접미사가 붙은 토큰을 찾습니다.
    elif m := re.search(r"([가-힣A-Za-z0-9]+(?:역|구청|동|점|몰|공원|타워))", utterance):
        place = m.group(1)

    minutes: int | None = None
    if m := re.search(r"(\d+)\s*시간", utterance):
        minutes = int(m.group(1)) * 60
    elif m := re.search(r"(\d+)\s*분", utterance):
        minutes = int(m.group(1))

    budget: int | None = None
    if m := re.search(r"(\d[\d,]*)\s*원", utterance):
        budget = int(m.group(1).replace(",", ""))
    elif m := re.search(r"(\d+)\s*만\s*원", utterance):
        budget = int(m.group(1)) * 10000

    sort_by = "price" if any(k in utterance for k in PRICE_KEYWORDS) else "distance"
    return RankingParams(place=place, duration_minutes=minutes, budget_won=budget, sort_by=sort_by)


def _merge(prev: RankingParams, current: RankingParams) -> RankingParams:
    """직전 조건 위에 이번 발화의 명시 항목만 덮어씁니다."""
    return RankingParams(
        place=current.place or prev.place,
        duration_minutes=current.duration_minutes or prev.duration_minutes,
        budget_won=current.budget_won or prev.budget_won,
        sort_by=current.sort_by,
        merged_from_previous=True,
    )
