"""대화형 데모입니다. [담당: P1]

python scripts/demo_cli.py "강남역 근처 2시간 주차"
PARKING_AGENT_NO_LLM=1 python scripts/demo_cli.py

repo root의 .env가 있으면 자동으로 읽어들입니다. 이미 셸에 설정된 값은
덮어쓰지 않으므로, live로 돌리려면 셸에서 PARKING_AGENT_NO_LLM=0을
명시적으로 export하면 됩니다.
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from parking_agent.context import build_context  # noqa: E402
from parking_agent.pipeline import run  # noqa: E402


def _load_dotenv() -> None:
    """repo root의 .env를 읽어 비어 있는 환경변수만 채웁니다.

    의존성 없이 stdlib로 파싱합니다. 셸에 이미 설정된 값(명시 export)은
    우선하므로 덮어쓰지 않습니다. .env가 없어도 조용히 넘어갑니다.
    """
    dotenv_path = pathlib.Path(__file__).resolve().parents[1] / ".env"
    try:
        text = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    _load_dotenv()
    ctx = build_context(user_lat=37.4979, user_lng=127.0276)
    prev = None
    pending = None

    if len(sys.argv) > 1:
        response = run(sys.argv[1], ctx)
        print(response.answer)
        return

    print("여긴어때 데모입니다. 종료하려면 빈 줄을 입력하세요.")
    while True:
        try:
            utterance = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not utterance:
            break
        response = run(utterance, ctx, prev, pending)
        print(response.answer)
        if response.verdict != "SAFE":
            print(f"[가드레일] {response.verdict_reason}")
        prev = response.params
        pending = response.pending


if __name__ == "__main__":
    main()
