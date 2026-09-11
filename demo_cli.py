"""주차장 추천 파이프라인 CLI 데모."""

from parking_agent.context import build_context
from parking_agent.pipeline import run
from parking_agent.types import RankingParams


def main() -> None:
    ctx = build_context()
    prev_params: RankingParams | None = None

    print("여긴어때 주차장 추천 CLI")
    print("종료하려면 'exit' 또는 'quit' 입력")

    while True:
        utterance = input("\n사용자> ").strip()

        if utterance.lower() in {"exit", "quit"}:
            break

        if not utterance:
            continue

        response = run(
            utterance=utterance,
            ctx=ctx,
            prev_params=prev_params,
        )

        print(f"\n에이전트> {response.answer}")

        if response.verdict != "SAFE":
            print(f"[guardrail] {response.verdict}: {response.verdict_reason}")

        prev_params = response.params


if __name__ == "__main__":
    main()
