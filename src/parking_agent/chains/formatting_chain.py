"""Formatting chain — 모듈 레벨 LCEL chain (Phase 5)

format.py 내부에서 매번 prompt/model/chain을 생성하던 구조를
모듈 로드 시점에 1회 생성하는 chain으로 승격한다.
"""

from __future__ import annotations

import os

from ..format import REQUIRED_NOTICE

try:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    format_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 주차장 추천 안내문 작성자입니다.\n"
                "아래 Recommendation의 값을 그대로 인용하고 숫자를 새로 만들거나 "
                "반올림하지 마시오. Recommendation에 없는 주차장명, 금액, 거리, "
                "잔여면, 시각을 추가하지 마시오.\n"
                f"반드시 '{REQUIRED_NOTICE}' 문구를 포함하시오.\n"
                "간결한 한국어로 답하고, 추천 후보가 제공한 순서를 유지하시오.\n\n"
                "Recommendation:\n{recommendations}",
            ),
            ("human", "{place} 근처 주차장 추천을 안내해 주세요."),
        ]
    )

    _model_name = os.getenv("OPENAI_MODEL", os.getenv("MODEL_NAME", "gpt-5.6-luna"))
    if "luna" in _model_name or _model_name.startswith("gpt-5"):
        # reasoning 모델은 chat/completions에서 tools 호출이 제한되므로
        # Responses API 경로로 호출합니다. 문장 다듬기라 effort는 low로 둡니다.
        # (GPT-5 계열은 temperature 기본값만 허용하므로 지정하지 않습니다.)
        _model = ChatOpenAI(
            model=_model_name,
            use_responses_api=True,
            reasoning={"effort": "low"},
        )
    else:
        _model = ChatOpenAI(
            model=_model_name,
            temperature=0,
        )

    formatting_chain = format_prompt | _model | StrOutputParser()

except Exception:  # pragma: no cover
    formatting_chain = None  # type: ignore[assignment]
