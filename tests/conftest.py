"""테스트 공통 픽스처입니다. [담당: P3]

단위 테스트는 항상 규칙 기반 모드로 실행합니다.
시각을 고정해 결과가 매번 같도록 합니다.
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import datetime

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ["PARKING_AGENT_NO_LLM"] = "1"

from parking_agent.context import KST, build_context  # noqa: E402


@pytest.fixture
def ctx():
    """2026-09-11(금) 14:00 KST 기준 컨텍스트입니다."""
    return build_context(
        user_lat=37.4979,
        user_lng=127.0276,
        now=datetime(2026, 9, 11, 14, 0, tzinfo=KST),
    )
