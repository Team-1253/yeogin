"""사용자 발화에서 검색 조건을 추출합니다. [담당: P2]

발화의 슬롯(장소·시간·예산·정렬)마다 독립된 도구를 둡니다.
신호가 있는 슬롯만 LLM에 요청하고, 없으면 호출을 생략합니다.
LLM 슬롯 호출을 우선 사용하고, 예외 상황에서만 규칙 도구로 폴백합니다.
미지정 항목을 임의의 기본값으로 채우지 않습니다. None으로 두십시오.
"""

from __future__ import annotations

import os
import re

from pydantic import BaseModel, Field

from .context import is_llm_disabled
from .tools.geocode import LANDMARKS
from .types import RankingParams, SortBy

try:
    from langchain_core.tools import tool as _lc_tool
except ImportError:  # pragma: no cover

    def _lc_tool(fn):
        """langchain 없이도 규칙 경로가 동작하도록 통과시킵니다."""
        return fn


PRICE_KEYWORDS = ("저렴", "싼", "싸게", "가격", "요금", "비싸", "가성비", "최저가")

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * 60
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

#: "오만원", "삼만원" 같은 표현을 지원합니다. 금액은 한자어 수사를 씁니다.
KOREAN_MANWON = {
    "일": 1,
    "이": 2,
    "삼": 3,
    "사": 4,
    "오": 5,
    "육": 6,
    "칠": 7,
    "팔": 8,
    "구": 9,
}

#: 장소 접미사입니다. P3의 LANDMARKS에 없는 이름도 geocode까지 전달되도록
#: "구"를 포함합니다. ("은평구" → geocode의 "지원하지 않는 장소" 안내)
PLACE_SUFFIXES = r"역|구청|구|동|로|길|점|몰|공원|타워|시장|백화점"

LLM_MODEL_DEFAULT = "gpt-5.6-luna"
LLM_TIMEOUT_SECONDS = 10

#: 슬롯 검증 실패 시 같은 슬롯을 재요청하는 횟수입니다. 규칙 폴백이 아닙니다.
LLM_MAX_ATTEMPTS = 2


# --------------------------------------------------------------------------
# 규칙 도구 4종: 결정론적 추출입니다. 예외 상황에서만 폴백으로 씁니다.
# --------------------------------------------------------------------------


def extract_place(utterance: str) -> str:
    """장소 이름을 추출합니다. 목적지 지명이 필요할 때 호출하십시오.

    발화에서 장소를 찾을 때만 호출하십시오. 시간·예산·정렬 판단에는
    호출하지 마십시오. 못 찾으면 빈 문자열을 둡니다.

    Args:
        utterance: 사용자 발화 원문입니다.
    """
    if (name := _match_landmark(utterance)) is not None:
        return name
    if m := re.search(r"([가-힣A-Za-z0-9]{2,10})\s*(?:근처|주변|인근|앞)", utterance):
        return m.group(1)
    return _suffix_place(utterance)


def _match_landmark(utterance: str) -> str | None:
    """랜드마크와 단어 경계에서 일치하는 이름을 돌려줍니다.

    단순 부분일치는 "임시청사"를 "시청"으로 오인하므로 경계를 둡니다.
    """
    for name in sorted(LANDMARKS, key=len, reverse=True):
        if re.search(rf"(?<![가-힣A-Za-z0-9]){re.escape(name)}(?![가-힣A-Za-z0-9])", utterance):
            return name
    return None


def _suffix_place(utterance: str) -> str:
    """접미사 토큰을 찾습니다. 조사 오탐("2시간으로"의 로 등)은 제외합니다."""
    for m in re.finditer(rf"([가-힣A-Za-z0-9]+(?:{PLACE_SUFFIXES}))", utterance):
        if _is_place_token(m.group(1)):
            return m.group(1)
    return ""


def _is_place_token(token: str) -> bool:
    """접미사 매칭이 조사·부사 오탐이 아닌지 봅니다."""
    if token.endswith("으로"):
        return False
    for suffix in ("구", "동", "로", "길"):
        if token.endswith(suffix) and len(token) < len(suffix) + 2:
            return False
    stem = re.sub(r"(구|동|로|길)$", "", token)
    if stem in ("이하", "이내", "까지"):
        return False
    return True


def extract_duration(utterance: str) -> int | None:
    """주차 시간을 분 단위로 추출합니다. 시간 표현 해석이 필요할 때 호출하십시오.

    시간 언급이 있는 발화에만 호출하십시오. 장소·예산·정렬 판단에는
    호출하지 마십시오. 없으면 None을 둡니다.

    Args:
        utterance: 사용자 발화 원문입니다.
    """
    if m := re.search(r"(\d+)\s*박\s*(\d+)\s*일", utterance):
        return int(m.group(2)) * MINUTES_PER_DAY
    if m := re.search(r"(\d+)\s*일", utterance):
        return int(m.group(1)) * MINUTES_PER_DAY
    if re.search(r"종일|온종일|하루", utterance):
        return MINUTES_PER_DAY
    if m := re.search(r"(\d+)\s*시간\s*(\d+)\s*분", utterance):
        return int(m.group(1)) * MINUTES_PER_HOUR + int(m.group(2))
    if m := re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시간\s*(\d+)\s*분", utterance):
        return KOREAN_HOURS[m.group(1)] * MINUTES_PER_HOUR + int(m.group(2))
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


def extract_budget(utterance: str) -> int | None:
    """예산 상한을 원 단위로 추출합니다. 금액 표현 해석이 필요할 때 호출하십시오.

    금액 언급이 있는 발화에만 호출하십시오. 장소·시간·정렬 판단에는
    호출하지 마십시오. 없으면 None을 둡니다.

    Args:
        utterance: 사용자 발화 원문입니다.
    """
    if m := re.search(r"(\d+)\s*만\s*(\d+)\s*천\s*원", utterance):
        return int(m.group(1)) * WON_PER_MANWON + int(m.group(2)) * WON_PER_CHEONWON
    if m := re.search(r"(일|이|삼|사|오|육|칠|팔|구)\s*만\s*원", utterance):
        return KOREAN_MANWON[m.group(1)] * WON_PER_MANWON
    if m := re.search(r"(\d+)\s*만\s*원", utterance):
        return int(m.group(1)) * WON_PER_MANWON
    if m := re.search(r"(\d+)\s*천\s*원", utterance):
        return int(m.group(1)) * WON_PER_CHEONWON
    if m := re.search(r"(\d[\d,]*)\s*원", utterance):
        return int(m.group(1).replace(",", ""))
    if "만원" in utterance and not re.search(r"[수몇]\s*만원", utterance):
        return WON_PER_MANWON
    if "천원" in utterance and not re.search(r"[수몇]\s*천원", utterance):
        return WON_PER_CHEONWON
    return None


def extract_sort(utterance: str) -> SortBy:
    """정렬 기준을 추출합니다. 가격 정렬 의도 확인이 필요할 때 호출하십시오.

    정렬 의도 판정에만 호출하십시오. 장소·시간·예산 판단에는
    호출하지 마십시오. 가격 언급이 있을 때만 price입니다.

    Args:
        utterance: 사용자 발화 원문입니다.
    """
    return "price" if any(k in utterance for k in PRICE_KEYWORDS) else "distance"


# --------------------------------------------------------------------------
# LLM 슬롯 4종: 슬롯별 집중 추출입니다. 우선 경로로 씁니다.
# --------------------------------------------------------------------------


class _PlaceSlot(BaseModel):
    """장소 슬롯의 구조화 출력입니다. reasoning을 먼저 채웁니다."""

    reasoning: str = Field(default="", description="추출 과정을 단계별로 적은 메모입니다.")
    place: str = Field(default="", description="핵심 지명만 둡니다.")


class _DurationSlot(BaseModel):
    """시간 슬롯의 구조화 출력입니다. reasoning을 먼저 채웁니다."""

    reasoning: str = Field(default="", description="추출 과정을 단계별로 적은 메모입니다.")
    duration_minutes: int | None = Field(default=None, description="주차 시간(분)입니다.")


class _BudgetSlot(BaseModel):
    """예산 슬롯의 구조화 출력입니다. reasoning을 먼저 채웁니다."""

    reasoning: str = Field(default="", description="추출 과정을 단계별로 적은 메모입니다.")
    budget_won: int | None = Field(default=None, description="예산 상한(원)입니다.")


class _SortSlot(BaseModel):
    """정렬 슬롯의 구조화 출력입니다. reasoning을 먼저 채웁니다."""

    reasoning: str = Field(default="", description="추출 과정을 단계별로 적은 메모입니다.")
    sort_by: str = Field(default="distance", description="정렬 의도가 있을 때만 price입니다.")


_PLACE_PROMPT = (
    "발화에서 목적지 지명을 찾습니다. "
    "근처·주변·주차장 같은 말은 떼고 핵심 지명만 둡니다. "
    "없으면 빈 문자열입니다. 먼저 reasoning에 과정을 적으십시오."
)
_DURATION_PROMPT = (
    "발화에서 주차 시간을 찾아 분으로 둡니다. 시간은 60을 곱합니다. "
    "언급이 없으면 None이며 값을 지어내지 않습니다. 먼저 reasoning에 과정을 적으십시오."
)
_BUDGET_PROMPT = (
    "발화에서 예산 상한을 찾아 원으로 둡니다. 만원은 10000을 곱합니다. "
    "언급이 없으면 None이며 값을 지어내지 않습니다. 먼저 reasoning에 과정을 적으십시오."
)
_SORT_PROMPT = (
    "싼 곳·저렴한 순 같은 정렬 의도가 있을 때만 price이고 아니면 distance입니다. "
    "가격 불만 표현(너무 비싸, 비싸다)도 정렬 의도로 봅니다. "
    "예산 언급만으로는 distance를 둡니다. 먼저 reasoning에 과정을 적으십시오."
)

_SLOT_SCHEMAS = {
    "place": (_PlaceSlot, _PLACE_PROMPT),
    "duration": (_DurationSlot, _DURATION_PROMPT),
    "budget": (_BudgetSlot, _BUDGET_PROMPT),
    "sort": (_SortSlot, _SORT_PROMPT),
}


def _call_slot_llm(slot: str, utterance: str, feedback: str | None = None) -> BaseModel | None:
    """슬롯 1개를 LLM에 1회 요청합니다.

    한 번에 한 슬롯만 다룹니다. 다른 슬롯이 필요하면 호출하지 마십시오.
    구조화 실패는 그대로 돌려주어 검증 단계가 다룹니다.
    예외 상황(미설치·키 없음·호출 실패)이면 None을 반환합니다.

    Args:
        slot: "place", "duration", "budget", "sort" 중 하나입니다.
        utterance: 사용자 발화 원문입니다.
        feedback: 검증 지적 사항입니다. 재요청 때만 씁니다.
    """
    try:
        from langchain_openai import ChatOpenAI

        schema, prompt = _SLOT_SCHEMAS[slot]
        model = ChatOpenAI(
            model=os.getenv("MODEL_NAME", LLM_MODEL_DEFAULT),
            temperature=0,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        if feedback:
            prompt = f"{prompt}\n이전 추출 문제점: {feedback}\n위 문제를 고쳐 다시 추출하십시오."
        return model.with_structured_output(schema).invoke(f"{prompt}\n발화: {utterance}")
    except Exception:
        return None


def _validate_place(utterance: str, result: _PlaceSlot) -> list[str]:
    """장소 슬롯이 발화에 근거하는지 봅니다. 값을 고치지 않고 판정만 합니다."""
    place = _clean_place(result.place)
    if place and place.replace(" ", "") not in utterance.replace(" ", ""):
        return [f"장소 '{place}'가 발화에 없습니다"]
    return []


def _validate_duration(utterance: str, result: _DurationSlot) -> list[str]:
    """시간 슬롯이 발화에 근거하는지 봅니다. 값을 고치지 않고 판정만 합니다."""
    if result.duration_minutes is None:
        return []
    if result.duration_minutes <= 0:
        return ["주차 시간이 0 이하입니다"]
    if not _has_time_expression(utterance):
        return ["시간 언급이 없는데 주차 시간이 있습니다"]
    return []


def _validate_budget(utterance: str, result: _BudgetSlot) -> list[str]:
    """예산 슬롯이 발화에 근거하는지 봅니다. 값을 고치지 않고 판정만 합니다."""
    if result.budget_won is None:
        return []
    if result.budget_won < 0:
        return ["예산이 음수입니다"]
    if not _has_money_expression(utterance):
        return ["금액 언급이 없는데 예산이 있습니다"]
    return []


def _validate_sort(utterance: str, result: _SortSlot) -> list[str]:
    """정렬 슬롯이 발화에 근거하는지 봅니다. 값을 고치지 않고 판정만 합니다."""
    if result.sort_by not in ("price", "distance"):
        return ["정렬 값이 price/distance가 아닙니다"]
    if result.sort_by == "price" and not _has_sort_intent(utterance):
        return ["정렬 의도 언급이 없는데 price입니다"]
    return []


_SLOT_VALIDATORS = {
    "place": _validate_place,
    "duration": _validate_duration,
    "budget": _validate_budget,
    "sort": _validate_sort,
}


def _validate_slot(slot: str, utterance: str, result: BaseModel) -> list[str]:
    """슬롯 검증기로 판정만 합니다. 비어 있으면 정상입니다."""
    return _SLOT_VALIDATORS[slot](utterance, result)


def _has_time_expression(utterance: str) -> bool:
    """시간 언급이 있는지 봅니다."""
    if "반시간" in utterance:
        return True
    if re.search(r"\d+\s*시간", utterance):
        return True
    if re.search(r"(한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*시간", utterance):
        return True
    if re.search(r"\d+\s*분", utterance):
        return True
    if re.search(r"\d+\s*박", utterance):
        return True
    if re.search(r"\d+\s*일", utterance):
        return True
    return re.search(r"종일|온종일|하루", utterance) is not None


def _has_money_expression(utterance: str) -> bool:
    """금액 언급이 있는지 봅니다. "공원"의 원 같은 오탐을 제외합니다."""
    return re.search(r"만원|천원|\d[\d,]*\s*원|예산", utterance) is not None


def _has_sort_intent(utterance: str) -> bool:
    """정렬 의도 언급이 있는지 봅니다."""
    return any(k in utterance for k in PRICE_KEYWORDS)


def _has_place_signal(utterance: str) -> bool:
    """장소 언급이 있는지 봅니다. 없으면 place 슬롯을 생략합니다."""
    if _match_landmark(utterance) is not None:
        return True
    if re.search(r"[가-힣A-Za-z0-9]{2,10}\s*(?:근처|주변|인근|앞)", utterance):
        return True
    return _suffix_place(utterance) != ""


def _needed_slots(utterance: str) -> list[str]:
    """LLM 호출이 필요한 슬롯만 고릅니다.

    규칙 게이트이며 추출이 아닙니다. 신호가 없는 슬롯은 호출하지 않고
    생략값(place ""·duration None·budget None·sort "distance")으로 둡니다.
    생략값은 _merge에서 직전 조건 유지로 해석됩니다.
    """
    slots: list[str] = []
    if _has_place_signal(utterance):
        slots.append("place")
    if _has_time_expression(utterance):
        slots.append("duration")
    if _has_money_expression(utterance):
        slots.append("budget")
    if _has_sort_intent(utterance):
        slots.append("sort")
    return slots


#: 마지막 `_extract_by_llm` 호출에서 실제 요청한 슬롯 목록입니다.
#: 재시도도 1회로 셉니다. 턴당 호출 수 확인용 진단 값이며,
#: 단일 스레드 데모·테스트에서만 읽습니다.
LAST_SLOT_CALLS: list[str] = []


def _clean_place(place: str) -> str:
    """LLM이 붙인 잔여 접미사를 걷어냅니다.

    근처·주차장 같은 말과 조사(에·에서·으로 등)를 뗍니다.
    로는 지명 일부(역삼로)일 수 있어 떼지 않습니다.
    """
    cleaned = place.strip()
    cleaned = re.sub(r"\s*(?:근처|주변|인근|앞|주차장)+\s*$", "", cleaned)
    cleaned = re.sub(
        r"(?:에서|에게|한테|부터|까지|보다|처럼|으로|에|를|을|이|가|은|는|와|과|도|만)+$",
        "",
        cleaned,
    )
    return cleaned.strip()


# --------------------------------------------------------------------------
# 조립: 계약 인터페이스입니다. 시그니처를 바꾸지 않습니다.
# --------------------------------------------------------------------------


def extract_params(
    utterance: str,
    prev: RankingParams | None = None,
) -> RankingParams:
    """발화를 RankingParams로 변환합니다.

    prev가 있으면 이번 발화에 명시된 필드만 덮어쓰고 나머지는 유지합니다.
    """
    global LAST_SLOT_CALLS
    if is_llm_disabled():
        LAST_SLOT_CALLS = []
        params = _extract_by_rule(utterance)
    else:
        params = _extract_by_llm(utterance) or _extract_by_rule(utterance)

    if prev is not None:
        params = _merge(prev, params)
    return params


def _extract_by_llm(utterance: str) -> RankingParams | None:
    """LLM 슬롯 호출로 추출합니다. LLM 우선 경로입니다.

    신호가 있는 슬롯만 호출합니다. 생략된 슬롯은 생략값으로 두어
    _merge에서 직전 조건 유지로 해석됩니다.
    슬롯 1개라도 예외 상황이면 None을 반환해 턴 전체를 규칙으로 폴백합니다.
    슬롯별 검증 문제는 같은 슬롯을 재요청해 교정합니다.
    호출 내역은 LAST_SLOT_CALLS에 남깁니다. 예외를 던지지 않습니다.
    """
    global LAST_SLOT_CALLS
    called: list[str] = []
    slots: dict[str, BaseModel] = {}
    for slot in _needed_slots(utterance):
        result = _call_slot_llm(slot, utterance)
        called.append(slot)
        if result is None:
            LAST_SLOT_CALLS = called
            return None
        if issues := _validate_slot(slot, utterance, result):
            retry = _call_slot_llm(slot, utterance, feedback="; ".join(issues))
            called.append(slot)
            if retry is not None:
                result = retry
        slots[slot] = result
    LAST_SLOT_CALLS = called

    return RankingParams(
        place=_clean_place(slots["place"].place)  # type: ignore[attr-defined]
        if "place" in slots
        else "",
        duration_minutes=slots["duration"].duration_minutes  # type: ignore[attr-defined]
        if "duration" in slots
        else None,
        budget_won=slots["budget"].budget_won  # type: ignore[attr-defined]
        if "budget" in slots
        else None,
        sort_by=slots["sort"].sort_by  # type: ignore[attr-defined]
        if "sort" in slots and slots["sort"].sort_by == "price"  # type: ignore[attr-defined]
        else "distance",
    )


def _extract_by_rule(utterance: str) -> RankingParams:
    """규칙 도구 4종으로 추출합니다. 예외 상황의 폴백 경로입니다."""
    return RankingParams(
        place=extract_place(utterance),
        duration_minutes=extract_duration(utterance),
        budget_won=extract_budget(utterance),
        sort_by=extract_sort(utterance),
    )


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


# --------------------------------------------------------------------------
# 에이전트 루프용 tool 객체입니다. 파이프라인 내부는 plain 함수를 씁니다.
# --------------------------------------------------------------------------
extract_place_tool = _lc_tool(extract_place)
extract_duration_tool = _lc_tool(extract_duration)
extract_budget_tool = _lc_tool(extract_budget)
extract_sort_tool = _lc_tool(extract_sort)
