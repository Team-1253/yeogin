"""출력 가드레일입니다. [담당: P6]

답변에 등장한 주차장명과 금액이 RankResult 안에 있는지 대조합니다.
LLM 판정 대신 규칙 기반으로 수행해 비용과 지연을 줄입니다.
"""

from __future__ import annotations

import re

from ..types import RankResult


def check_response(answer: str, result: RankResult | None) -> tuple[str, str | None]:
    """답변이 도구 결과에만 근거하는지 판정합니다.

    Returns:
        ("SAFE" 또는 "UNSAFE", UNSAFE인 경우 사유)
    """
    if result is None or result.is_empty:
        return "SAFE", None

    allowed_fees = {r.fee_text for r in result.recommendations}
    allowed_names = {r.name for r in result.recommendations}

    for amount in re.findall(r"[\d,]+원", answer):
        if amount not in allowed_fees:
            return "UNSAFE", f"근거 없는 금액: {amount}"

    rejected_names = {r.lot_name for r in result.rejected}
    for name in rejected_names:
        if name in answer and name not in allowed_names:
            return "UNSAFE", f"제외된 후보가 언급됨: {name}"

    return "SAFE", None
