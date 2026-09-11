"""출력 가드레일입니다. [담당: P6]

답변에 등장한 주차장명·금액·거리·잔여면·마감 시각이 RankResult 안에 있는지 대조합니다.
외부 링크·연락처, 실시간 정보를 확정적으로 표현한 문장도 차단합니다.
LLM 판정 대신 규칙 기반으로 수행해 비용과 지연을 줄입니다.

대조 원칙은 세 가지입니다.
- 표기가 달라도 값이 같으면 통과합니다. ("7800원" = "7,800원" = "7천8백원")
- 값이 조금이라도 다르면 차단합니다. 반올림과 단위 환산 오차도 허용하지 않습니다.
- 추천이 0건이면 답변에 금액·거리·잔여면·시각이 하나도 없어야 합니다.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ..types import RankResult

SAFE = "SAFE"
UNSAFE = "UNSAFE"

#: 추천이 있는 답변에 반드시 들어가야 하는 안내 문구입니다. (설계서 3.3 실시간 정보 과신 방지)
REQUIRED_NOTICE = "현재 조회 데이터 기준"

#: 실시간 조회 결과를 확정적으로 표현하는 금지 표현입니다.
OVERCONFIDENT_PHRASES = ("보장합니다", "보장됩니다", "확실히", "무조건", "틀림없이", "100%")

#: 이름이 아니라 일반 명사로 쓰이는 '~주차장' 표현입니다. 이름 대조에서 제외합니다.
GENERIC_LOT_WORDS = frozenset(
    {
        "주차장",
        "공영주차장",
        "노상주차장",
        "노외주차장",
        "민영주차장",
        "부설주차장",
        "지하주차장",
        "기계식주차장",
        "유료주차장",
        "무료주차장",
    }
)

#: 판정 사유의 최대 길이입니다. (설계서 2.4 GuardrailVerdict.reason 50자 이내)
MAX_REASON_CHARS = 50
#: 사유에 인용하는 항목의 최대 길이입니다. (설계서 2.4 unsupported_items 20자 이내)
MAX_ITEM_CHARS = 20

_MASK = "§"
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_KM_UNITS = ("km", "㎞", "킬로미터", "킬로")
_KOREAN_UNITS = (("만", 10_000), ("천", 1_000), ("백", 100))

_LINK = re.compile(r"https?://|www\.|[\w-]+\.(?:com|net|org|kr|io|me|ly)\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:0\d{1,2}|1\d{3})-\d{3,4}(?:-\d{4})?(?!\d)")
#: '~주차장 근처'처럼 목적지를 가리키는 표현은 주차장명으로 보지 않습니다.
_LOT_NAME = re.compile(r"[가-힣A-Za-z0-9]*주차장(?!\s*(?:근처|주변|인근|앞))")
_WON = re.compile(
    rf"(?:(?:{_NUM})?\s*만\s*)?(?:(?:{_NUM})?\s*천\s*)?(?:(?:{_NUM})?\s*백\s*)?(?:{_NUM})?\s*원"
)
_WON_SYMBOL = re.compile(rf"₩\s*{_NUM}|{_NUM}\s*KRW\b", re.IGNORECASE)
_DISTANCE = re.compile(rf"({_NUM})\s*(km|㎞|킬로미터|킬로|m|미터)(?![A-Za-z])")
_SLOTS = re.compile(rf"({_NUM})\s*(?:면|자리|대)(?!로|학|적|비|당)")
_SLOTS_INVERTED = re.compile(rf"잔여\s*(?:주차\s*)?면수?\s*(?:은|는|이|:)?\s*({_NUM})")
_CLOCK = re.compile(r"(?<!\d)([01]?\d|2[0-4]):([0-5]\d)(?!\d)")


def check_response(answer: str, result: RankResult | None) -> tuple[str, str | None]:
    """답변이 도구 결과에만 근거하는지 판정합니다.

    result가 None이면 랭킹 이전 단계의 고정 안내 문구이므로 대조하지 않습니다.

    Returns:
        ("SAFE" 또는 "UNSAFE", UNSAFE인 경우 50자 이내 사유)
    """
    if result is None:
        return SAFE, None

    violations = collect_violations(answer, result)
    if violations:
        return UNSAFE, violations[0][:MAX_REASON_CHARS]
    return SAFE, None


def collect_violations(answer: str, result: RankResult) -> list[str]:
    """답변에서 도구 결과와 맞지 않는 항목을 모두 찾아 사유 목록으로 반환합니다.

    format_answer가 LLM 답변을 재생성할 때 이 목록을 피드백으로 사용합니다.
    """
    violations: list[str] = []
    allowed_names = [r.name for r in result.recommendations]
    rejected_names = [r.lot_name for r in result.rejected]

    text, mentioned_rejected = _mask_names(answer, allowed_names, rejected_names)
    violations += [_describe("제외된 후보가 언급됨", name) for name in mentioned_rejected]

    violations += [_describe("근거 없는 외부 링크 유도", m.group(0)) for m in _LINK.finditer(text)]
    violations += [_describe("근거 없는 연락처", m.group(0)) for m in _PHONE.finditer(text)]
    violations += [
        _describe("실시간 정보 과신 표현", phrase)
        for phrase in OVERCONFIDENT_PHRASES
        if phrase in text
    ]
    violations += [
        _describe("근거 없는 주차장명", token)
        for token in _LOT_NAME.findall(text)
        if token not in GENERIC_LOT_WORDS
    ]

    fees = {v for r in result.recommendations for _, v in _extract_amounts(r.fee_text)}
    distances = {Decimal(r.distance_m) for r in result.recommendations}
    slots = {v for r in result.recommendations for _, v in _extract_slots(r.availability_text)}
    clocks = {c for r in result.recommendations for c in _extract_clocks(r.hours_text)}

    violations += [
        _describe("근거 없는 금액", raw)
        for raw, value in _extract_amounts(text)
        if value is None or value not in fees
    ]
    violations += [
        _describe("근거 없는 거리", raw)
        for raw, value in _extract_distances(text)
        if value not in distances
    ]
    violations += [
        _describe("근거 없는 잔여면", raw)
        for raw, value in _extract_slots(text)
        if value not in slots
    ]
    violations += [
        _describe("근거 없는 운영시간", clock)
        for clock in _extract_clocks(text)
        if clock not in clocks
    ]

    if not result.is_empty and REQUIRED_NOTICE not in answer:
        violations.append(_describe("안내 문구 누락", REQUIRED_NOTICE))
    return violations


# --------------------------------------------------------------------------
# 주차장명
# --------------------------------------------------------------------------


def _mask_names(
    answer: str, allowed: list[str], rejected: list[str]
) -> tuple[str, list[str]]:
    """알려진 주차장명을 가리고, 답변에 언급된 제외 후보명을 함께 반환합니다.

    이름 속 숫자가 수치 대조에 섞이지 않도록 가립니다. 긴 이름부터 대조하므로
    추천 후보명이 제외 후보명을 포함하는 경우에도 오판하지 않습니다.
    """
    is_allowed: dict[str, bool] = {}
    for name in rejected:
        for variant in _name_variants(name):
            is_allowed.setdefault(variant, False)
    for name in allowed:
        for variant in _name_variants(name):
            is_allowed[variant] = True  # 동명 후보가 양쪽에 있으면 추천 후보로 봅니다.
    if not is_allowed:
        return answer, []

    ordered = sorted(is_allowed, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(v) for v in ordered))
    mentioned: list[str] = []

    def replace(m: re.Match[str]) -> str:
        if not is_allowed[m.group(0)] and m.group(0) not in mentioned:
            mentioned.append(m.group(0))
        return _MASK

    return pattern.sub(replace, answer), mentioned


def _name_variants(name: str) -> set[str]:
    """이름 표기 변형입니다. 괄호 접미사("(시)")와 공백 생략을 허용합니다."""
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    variants = {name.strip(), base, name.replace(" ", ""), base.replace(" ", "")}
    return {v for v in variants if len(v) >= 2 and v not in GENERIC_LOT_WORDS}


# --------------------------------------------------------------------------
# 수치 추출
# --------------------------------------------------------------------------


def _extract_amounts(text: str) -> list[tuple[str, Decimal | None]]:
    """금액 표현과 원 단위 값을 추출합니다. 해석할 수 없는 금액은 None입니다."""
    found: list[tuple[str, Decimal | None]] = []
    for m in _WON.finditer(text):
        raw = m.group(0).strip()
        if re.search(r"[\d만천백]", raw):  # '공원'처럼 금액이 아닌 '원'은 건너뜁니다.
            found.append((raw, _parse_amount(raw)))
    for m in _WON_SYMBOL.finditer(text):
        raw = m.group(0).strip()
        found.append((raw, _parse_amount(raw)))
    return found


def _parse_amount(raw: str) -> Decimal | None:
    """"1만 5천원" · "7,800원" · "₩7,800" 을 원 단위 값으로 바꿉니다."""
    body = re.sub(r"[\s,원₩]|krw", "", raw, flags=re.IGNORECASE)
    total = Decimal(0)
    try:
        for unit, scale in _KOREAN_UNITS:
            if unit in body:
                head, body = body.split(unit, 1)
                total += (Decimal(head) if head else Decimal(1)) * scale
        if body:
            total += Decimal(body)
    except InvalidOperation:
        return None
    return total


def _extract_distances(text: str) -> list[tuple[str, Decimal]]:
    """거리 표현과 미터 단위 값을 추출합니다."""
    found: list[tuple[str, Decimal]] = []
    for m in _DISTANCE.finditer(text):
        value = _to_decimal(m.group(1))
        if m.group(2) in _KM_UNITS:
            value *= 1000
        found.append((m.group(0), value))
    return found


def _extract_slots(text: str) -> list[tuple[str, Decimal]]:
    """잔여면 표현과 값을 추출합니다. "2면"과 "잔여면 2" 어순을 모두 봅니다."""
    found = [(m.group(0), _to_decimal(m.group(1))) for m in _SLOTS.finditer(text)]
    found += [(m.group(0), _to_decimal(m.group(1))) for m in _SLOTS_INVERTED.finditer(text)]
    return found


def _extract_clocks(text: str) -> list[str]:
    """"HH:MM" 시각을 두 자리 시로 정규화해 추출합니다."""
    return [f"{int(h):02d}:{m}" for h, m in _CLOCK.findall(text)]


def _to_decimal(number: str) -> Decimal:
    return Decimal(number.replace(",", ""))


def _describe(label: str, item: str) -> str:
    return f"{label}: {item.strip()[:MAX_ITEM_CHARS]}"
