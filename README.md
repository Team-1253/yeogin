# 여긴어때

목적지 근처 서울시 공영주차장을 조건에 맞춰 3곳 추천하는 에이전트입니다.
SKALA 10반 3조 · 생성형 AI 서비스 개발 종합실습

---

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 키 없이 전체 흐름 검증
PARKING_AGENT_NO_LLM=1 python scripts/demo_cli.py "강남역 근처 2시간 주차"

# 대화형 (리랭킹 포함)
python scripts/demo_cli.py

# 테스트
python -m pytest tests/ -q
ruff check src/ scripts/ tests/
```

## 동작 예시

```
$ PARKING_AGENT_NO_LLM=1 python scripts/demo_cli.py "강남역 근처 2시간 주차"
강남역 근처 주차장 3곳입니다.
1. 강남역지하공영주차장 · 106m · 7,800원 · 잔여 2면 · 24시간
2. 역삼동공영주차장 · 508m · 5,500원 · 잔여 18면 · 23:00 마감 (11시간 38분 남음)
3. 서초구민회관주차장 · 1685m · 4,400원 · 잔여 25면 · 18:00 마감 (6시간 38분 남음)
현재 조회 데이터 기준이며 실제 현장 상황과 다를 수 있습니다.
```

## 설계 원칙

**LLM은 말의 앞뒤를 맡고, 코드는 가운데를 맡습니다.**

발화 해석과 문장 생성에만 LLM을 쓰고, 조회·계산·정렬은 전부 결정론적 코드입니다.
요금·거리·잔여면처럼 검증 가능한 수치를 LLM이 산출하는 일은 없으며,
출력 가드레일이 답변의 수치를 도구 결과와 대조합니다.

확인할 수 없는 값은 추정하지 않고 `None`으로 두어 "확인 불가"로 노출합니다.
필수조건을 만족하는 후보가 없으면 임의로 추천하지 않고 탈락 사유를 안내합니다.

## 구조

```
src/parking_agent/
├── types.py              계약 (P1 전용)
├── context.py            실행 컨텍스트 (P1)
├── pipeline.py           조립 (P1)
├── extract.py            발화 → 파라미터 (P2)
├── format.py             결과 → 문장 (P6)
├── guardrails/
│   ├── input.py          입력 차단 (P2)
│   └── output.py         수치 대조 (P6)
├── tools/
│   ├── geocode.py        목적지 → 좌표·자치구 (P3)
│   ├── districts.py      자치구 인접 맵 (P3)
│   ├── search.py         주차장 조회 (P4)
│   ├── evaluate.py       거리·시간·요금 계산 (P5)
│   └── rank.py           정렬·Top 3 (P6)
└── sources/
    └── seoul_api.py      서울시 API 어댑터 (P4)
```

분업 규칙과 데이터 계약은 [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)를 먼저 읽으십시오.

## 현재 상태

| 구간 | 상태 |
|---|---|
| 파이프라인 조립 | 동작 |
| 발화 추출 (규칙) | 동작 · LLM 경로 미구현 |
| 지오코딩 | 랜드마크 5곳 하드코딩 |
| 주차장 조회 | 시드 CSV · 서울시 API 미연동 |
| 계산·판정 | 동작 · 요일별 운영시간 미반영 |
| 랭킹·응답 | 동작 · LLM 문장 생성 미구현 |
| 출력 가드레일 | 동작 |

`PARKING_SOURCE=mock`이 기본값이라 키 없이도 전체 흐름이 검증됩니다.
