"""사용자 발화에서 검색 조건을 추출합니다. [담당: P2]

LLM 구조화 출력을 우선 사용하고, 키가 없거나 실패하면 규칙 기반으로 폴백합니다.
미지정 항목을 임의의 기본값으로 채우지 않습니다. None으로 두십시오.
"""

from __future__ import annotations

import os
import re

from .context import is_llm_disabled
from .tools.geocode import LANDMARKS
from .types import RankingParams, SortBy

PRICE_KEYWORDS = ("저렴", "싼", "싸게", "가격", "요금", "비싸")

MINUTES_PER_HOUR = 60
WON_PER_MANWON = 10_000
WON_PER_CHEONWON = 1_000

#: "한시간", "두시간" 같은 표현을 지원합니다.
KOREAN_HOURS = {
    "한": 1,
    "두": 2,
    "세": 3,
    "네": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
}

#: 장소 접미사입니다. P3의 LANDMARKS에 없는 이름도 geocode까지 전달되도록
#: "구"를 포함합니다. ("은평구" → geocode의 "지원하지 않는 장소" 안내)
PLACE_SUFFIXES = r"역|구청|구|동|로|길|점|몰|공원|타워|시장|백화점"

LLM_MODEL_DEFAULT = "gpt-5.6-luna"
LLM_TIMEOUT_SECONDS = 10


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

    langchain이 없거나 키가 없거나 호출이 실패하면 None을 반환해
    규칙 기반 추출로 폴백합니다. 예외를 던지지 않습니다.
    """
    try:
        from langchain_openai import ChatOpenAI
        from pydantic import BaseModel, Field

        class _ExtractSchema(BaseModel):
            """발화에서 뽑는 검색 조건입니다."""

            place: str = Field(
                default="",
                description="핵심 지명만 둡니다. 근처·주변·주차장 같은 접미사는 뗍니다.",
            )
            duration_minutes: int | None = Field(
                default=None, description="주차 시간(분)입니다. 시간은 60을 곱합니다."
            )
            budget_won: int | None = Field(
                default=None, description="예산 상한(원)입니다. 만원은 10000을 곱합니다."
            )
            sort_by: str = Field(
                default="distance",
                description="싼 곳·저렴한 순 같은 정렬 의도가 있을 때만 price입니다. "
                "예산(만원 이하 등) 언급만으로는 distance를 둡니다.",
            )

        model = ChatOpenAI(
            model=os.getenv("MODEL_NAME", LLM_MODEL_DEFAULT),
            temperature=0,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        result = model.with_structured_output(_ExtractSchema).invoke(
            "다음 주차장 요청 발화에서 검색 조건을 추출하십시오. "
            "장소는 핵심 지명만 두고 근처·주차장 같은 말을 떼십시오. "
            "추측하지 마시고 모르는 값은 None으로 두십시오. "
            "예산 언급은 budget_won으로만 처리하고 sort_by를 price로 바꾸지 마십시오.\n"
            f"발화: {utterance}"
        )
        return RankingParams(
            place=_clean_place(result.place),
            duration_minutes=result.duration_minutes,
            budget_won=result.budget_won,
            sort_by=result.sort_by if result.sort_by == "price" else "distance",
        )
    except Exception:
        return None


def _clean_place(place: str) -> str:
    """LLM이 붙인 잔여 접미사(근처·주차장 등)를 걷어냅니다."""
    cleaned = place.strip()
    cleaned = re.sub(r"\s*(?:근처|주변|인근|앞|주차장)+\s*$", "", cleaned)
    return cleaned.strip()


def _extract_by_rule(utterance: str) -> RankingParams:
    """정규식과 키워드로 추출합니다."""
    return RankingParams(
        place=_extract_place(utterance),
        duration_minutes=_extract_duration(utterance),
        budget_won=_extract_budget(utterance),
        sort_by=_extract_sort(utterance),
    )


def _extract_place(utterance: str) -> str:
    """장소 이름을 추출합니다.

    1순위는 P3 랜드마크와 부분일치하고, 2순위는 "~ 근처" 앞 명사구,
    3순위는 장소 접미사 토큰을 봅니다. 못 찾으면 빈 문자열을 둡니다.
    """
    for name in sorted(LANDMARKS, key=len, reverse=True):
        if name in utterance:
            return name
    if m := re.search(r"([가-힣A-Za-z0-9]{2,10})\s*(?:근처|주변|인근|앞)", utterance):
        return m.group(1)
    if m := re.search(rf"([가-힣A-Za-z0-9]+(?:{PLACE_SUFFIXES}))", utterance):
        return m.group(1)
    return ""


def _extract_duration(utterance: str) -> int | None:
    """주차 시간을 분 단위로 추출합니다. 없으면 None을 둡니다."""
    if m := re.search(r"(\d+)\s*시간\s*반", utterance):
        return int(m.group(1)) * MINUTES_PER_HOUR + MINUTES_PER_HOUR // 2
    if m := re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시간\s*반", utterance):
        return KOREAN_HOURS[m.group(1)] * MINUTES_PER_HOUR + MINUTES_PER_HOUR // 2
    if m := re.search(r"(\d+)\s*시간", utterance):
        return int(m.group(1)) * MINUTES_PER_HOUR
    if m := re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시간", utterance):
        return KOREAN_HOURS[m.group(1)] * MINUTES_PER_HOUR
    if "반시간" in utterance:
        return MINUTES_PER_HOUR // 2
    if m := re.search(r"(\d+)\s*분", utterance):
        return int(m.group(1))
    return None


def _extract_budget(utterance: str) -> int | None:
    """예산 상한을 원 단위로 추출합니다. 없으면 None을 둡니다."""
    if m := re.search(r"(\d+)\s*만\s*원", utterance):
        return int(m.group(1)) * WON_PER_MANWON
    if m := re.search(r"(\d+)\s*천\s*원", utterance):
        return int(m.group(1)) * WON_PER_CHEONWON
    if m := re.search(r"(\d[\d,]*)\s*원", utterance):
        return int(m.group(1).replace(",", ""))
    if "만원" in utterance:
        return WON_PER_MANWON
    if "천원" in utterance:
        return WON_PER_CHEONWON
    return None


def _extract_sort(utterance: str) -> SortBy:
    """정렬 기준을 추출합니다. 가격 언급이 있을 때만 price입니다."""
    return "price" if any(k in utterance for k in PRICE_KEYWORDS) else "distance"


def _merge(prev: RankingParams, current: RankingParams) -> RankingParams:
    """직전 조건 위에 이번 발화의 명시 항목만 덮어씁니다.

    sort_by는 RankingParams가 "신호 없음"을 표현할 수 없어
    price(명시 신호)일 때만 덮어쓰고 distance(기본값)면 직전 값을 유지합니다.
    """
    return RankingParams(
        place=current.place if current.place else prev.place,
        duration_minutes=current.duration_minutes
        if current.duration_minutes is not None
        else prev.duration_minutes,
        budget_won=current.budget_won if current.budget_won is not None else prev.budget_won,
        sort_by=current.sort_by if current.sort_by == "price" else prev.sort_by,
        merged_from_previous=True,
    )
