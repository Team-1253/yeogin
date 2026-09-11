"""대화형 데모입니다. [담당: P1]

python scripts/demo_cli.py "강남역 근처 2시간 주차"
PARKING_AGENT_NO_LLM=1 python scripts/demo_cli.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from parking_agent.context import build_context  # noqa: E402
from parking_agent.pipeline import run  # noqa: E402


def main() -> None:
    ctx = build_context(user_lat=37.4979, user_lng=127.0276)
    prev = None

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
        response = run(utterance, ctx, prev)
        print(response.answer)
        if response.verdict != "SAFE":
            print(f"[가드레일] {response.verdict_reason}")
        prev = response.params


if __name__ == "__main__":
    main()
