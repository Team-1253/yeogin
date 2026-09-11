"""사용자 발화에서 검색 조건을 추출합니다. [담당: P2]

LLM 구조화 출력을 우선 사용하고, 키가 없거나 실패하면 규칙 기반으로 폴백합니다.
미지정 항목을 임의의 기본값으로 채우지 않습니다. None으로 두십시오.
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field

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

#: 구조화 실패 시 같은 경로에서 재요청하는 횟수입니다. 규칙 폴백이 아닙니다.
LLM_MAX_ATTEMPTS = 2

LLM_SYSTEM_PROMPT = (
    "주차장 요청 발화에서 검색 조건을 추출합니다. "
    "다음 순서로 생각하고 reasoning에 그 과정을 적으십시오.\n"
    "1. 목적지 지명을 찾습니다. 근처·주변·주차장 같은 말은 뗍니다. "
    "없으면 빈 문자열입니다.\n"
    "2. 주차 시간을 찾습니다. 시간은 60을 곱해 분으로 둡니다. "
    "언급이 없으면 None이며 값을 지어내지 않습니다.\n"
    "3. 예산 상한을 찾습니다. 만원은 10000을 곱합니다. "
    "언급이 없으면 None이며 값을 지어내지 않습니다.\n"
    "4. 정렬을 정합니다. 싼 곳·저렴한 순 같은 정렬 의도가 있을 때만 price이고, "
    "예산 언급만으로는 distance입니다."
)


class _ExtractSchema(BaseModel):
    """LLM 구조화 출력 스키마입니다.

    reasoning을 먼저 채우게 해 단계별로 생각한 뒤 값을 정합니다.
    """

    reasoning: str = Field(default="", description="추출 과정을 단계별로 적은 메모입니다.")
    place: str = Field(default="", description="핵심 지명만 둡니다.")
    duration_minutes: int | None = Field(default=None, description="주차 시간(분)입니다.")
    budget_won: int | None = Field(default=None, description="예산 상한(원)입니다.")
    sort_by: str = Field(default="distance", description="정렬 의도가 있을 때만 price입니다.")


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
    """LLM 구조화 출력으로 추출합니다. LLM 우선 경로입니다.

    API 호출 같은 예외 상황에서만 None을 반환해 규칙으로 폴백합니다.
    구조화 문제는 검증을 거쳐 같은 경로에서 재요청으로 교정합니다.
    예외를 던지지 않습니다.
    """
    result = _call_llm(utterance)
    if result is None:
        return None

    if _validate_extraction(utterance, result) and LLM_MAX_ATTEMPTS > 1:
        retry = _call_llm(utterance, feedback="; ".join(_validate_extraction(utterance, result)))
        if retry is not None:
            result = retry

    return RankingParams(
        place=_clean_place(result.place),
        duration_minutes=result.duration_minutes,
        budget_won=result.budget_won,
        sort_by=result.sort_by if result.sort_by == "price" else "distance",
    )


def _call_llm(utterance: str, feedback: str | None = None) -> _ExtractSchema | None:
    """LLM에 구조화 추출을 1회 요청합니다.

    예외 상황(미설치·키 없음·호출 실패)이면 None을 반환합니다.
    구조화 실패는 None이 아니라 스키마 그대로 돌려주어 검증 단계가 다룹니다.
    """
    try:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=os.getenv("MODEL_NAME", LLM_MODEL_DEFAULT),
            temperature=0,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        prompt = LLM_SYSTEM_PROMPT
        if feedback:
            prompt += f"\n이전 추출 문제점: {feedback}\n위 문제를 고쳐 다시 추출하십시오."
        prompt += f"\n발화: {utterance}"
        return model.with_structured_output(_ExtractSchema).invoke(prompt)
    except Exception:
        return None


def _validate_extraction(utterance: str, result: _ExtractSchema) -> list[str]:
    """구조화 출력이 발화에 근거하는지 검증합니다. 문제점 목록을 반환합니다.

    비어 있으면 정상입니다. 값을 고치지 않고 판정만 합니다.
    """
    issues: list[str] = []
    squashed = utterance.replace(" ", "")
    place = _clean_place(result.place)
    if place and place.replace(" ", "") not in squashed:
        issues.append(f"장소 '{place}'가 발화에 없습니다")
    if result.duration_minutes is not None:
        if result.duration_minutes <= 0:
            issues.append("주차 시간이 0 이하입니다")
        elif not _has_time_expression(utterance):
            issues.append("시간 언급이 없는데 주차 시간이 있습니다")
    if result.budget_won is not None:
        if result.budget_won < 0:
            issues.append("예산이 음수입니다")
        elif not _has_money_expression(utterance):
            issues.append("금액 언급이 없는데 예산이 있습니다")
    if result.sort_by not in ("price", "distance"):
        issues.append("정렬 값이 price/distance가 아닙니다")
    elif result.sort_by == "price" and not _has_sort_intent(utterance):
        issues.append("정렬 의도 언급이 없는데 price입니다")
    return issues


def _has_time_expression(utterance: str) -> bool:
    """시간 언급이 있는지 봅니다."""
    if "반시간" in utterance:
        return True
    if re.search(r"\d+\s*시간", utterance):
        return True
    if re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시간", utterance):
        return True
    return re.search(r"\d+\s*분", utterance) is not None


def _has_money_expression(utterance: str) -> bool:
    """금액 언급이 있는지 봅니다."""
    return "원" in utterance or "예산" in utterance


def _has_sort_intent(utterance: str) -> bool:
    """정렬 의도 언급이 있는지 봅니다."""
    return any(k in utterance for k in PRICE_KEYWORDS)


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
