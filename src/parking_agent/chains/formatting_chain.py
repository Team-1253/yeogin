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
                "당신은 주차장 추천 답변의 도입부를 쓰는 작성자입니다.\n"
                "사용자 발화에 대화형으로 반응하는 한두 문장만 쓰시오.\n"
                "숫자, 금액, 거리, 시간, 주차장명을 절대 쓰지 마시오. "
                "목록은 뒤에 따로 붙으므로 항목을 나열하지 마시오.\n"
                "한국어 외 다른 언어를 섞지 마시오.\n"
                f"'{REQUIRED_NOTICE}' 문구도 쓰지 마시오 (목록 뒤에 자동 추가됨).\n"
                "간결한 한국어로 답하시오.",
            ),
            (
                "human",
                "목적지: {place}\n사용자 발화: {utterance}\n위 발화에 맞는 도입부를 써주세요.",
            ),
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
