# 여긴어때 · 협업 가이드

10반 3조 · 6인 병렬 개발 기준입니다.
이 문서는 **작업을 시작하기 전에 전원이 한 번 읽는 것**을 전제로 합니다.

---

## 0. 세 줄 요약

1. `types.py`가 유일한 계약입니다. 모듈 간에는 여기 정의된 타입만 주고받습니다.
2. **파일 소유권이 1:1입니다.** 남의 파일을 고치지 않으면 머지 충돌이 발생하지 않습니다.
3. 모든 함수는 **예외를 던지지 않고** 실패를 반환값으로 표현합니다.

---

## 1. 파이프라인 개요

```
사용자 발화
   │
   ├─[P2] extract_params          발화 → RankingParams
   │      check_request           장소 누락·범위 이탈 차단
   │
   ├─[P3] geocode_place           place → GeocodeResult (좌표 + 자치구)
   │
   ├─[P4] search_parking          자치구 + 인접구 → SearchResult
   │
   ├─[P5] evaluate_candidates     거리·운영시간·요금 계산 + 필수조건 필터
   │                              → EvaluationResult
   │
   ├─[P6] rank_candidates         정렬 + Top 3 → RankResult
   │      format_answer           RankResult → 문장
   │      check_response          답변 수치 ↔ RankResult 대조
   │
   └─[P1] pipeline.run()          위 단계를 조립하고 AgentResponse 반환
```

**LLM이 관여하는 구간은 양 끝뿐입니다.** 발화 해석(P2)과 문장 생성(P6)에만 쓰고,
가운데의 조회·계산·정렬은 전부 결정론적 코드입니다.
요금·거리·잔여면 같은 검증 가능한 수치를 LLM이 산출하는 일은 없습니다.

---

## 2. 담당과 파일 소유권

각자 **자기 소유 파일만** 수정합니다. 남의 파일에 손대야 하는 상황이 생기면
직접 고치지 말고 조 채널에 요청하십시오.

| 담당 | 역할 | 소유 파일 |
|---|---|---|
| **P1** | 계약·통합·데모 | `types.py` · `context.py` · `pipeline.py` · `scripts/demo_cli.py` · `docs/` |
| **P2** | 입력 이해 | `extract.py` · `guardrails/input.py` · `tests/test_extract.py` |
| **P3** | 지오코딩·자치구 | `tools/geocode.py` · `tools/districts.py` · `tests/test_geocode.py` |
| **P4** | 데이터 소스 | `tools/search.py` · `sources/seoul_api.py` · `data/` · `tests/test_search.py` |
| **P5** | 계산·판정 | `tools/evaluate.py` · `tests/test_evaluate.py` |
| **P6** | 랭킹·응답·출력검증 | `tools/rank.py` · `format.py` · `guardrails/output.py` · `tests/test_rank.py` |

### 작업 크기와 의존성

```
P1 ─── 계약 확정 (착수 30분 내 완료, 전원 대기 해제)
        │
        ├── P2  독립      · 중간   · LLM 구조화 출력 + 규칙 폴백
        ├── P3  독립      · 작음   · 좌표 테이블 + 자치구 판정 + 인접구 맵
        ├── P4  독립      · 큼     · 외부 API · 캐시 · 좌표 백필
        ├── P5  독립      · 큼     · 하버사인 · 운영시간 · 요금 계산
        └── P6  독립      · 중간   · 정렬 + 문장 생성 + 수치 대조
```

**전원이 동시에 착수할 수 있습니다.** 스텁이 더미 값을 반환하므로,
남의 모듈이 미완성이어도 자기 파트를 끝까지 만들고 테스트할 수 있습니다.

P3이 가장 가벼우므로, 먼저 끝나면 **시연 시나리오 3종 픽스처 작성**과
**설계서-코드 동기화 점검**을 맡습니다.
P4는 외부 API 의존이 커서 막힐 위험이 가장 높습니다. 1시간 안에 실데이터가
안 나오면 `data/seed_sample.csv` 고정으로 전환하고 P1에 공유하십시오.

---

## 3. 데이터 계약

전체 정의는 `src/parking_agent/types.py`에 있습니다. 요약하면 이렇습니다.

| 단계 | 입력 | 출력 |
|---|---|---|
| extract_params | `str`, `RankingParams \| None` | `RankingParams` |
| check_request | `RankingParams` | `tuple[bool, str \| None]` |
| geocode_place | `str`, `RequestContext` | `GeocodeResult` |
| search_parking | `Place`, `RequestContext` | `SearchResult` |
| evaluate_candidates | `SearchResult`, `Place`, `RankingParams`, `RequestContext` | `EvaluationResult` |
| rank_candidates | `EvaluationResult`, `RankingParams`, `RequestContext` | `RankResult` |
| format_answer | `RankResult`, `RankingParams`, `RequestContext` | `str` |
| check_response | `str`, `RankResult` | `tuple[str, str \| None]` |

### 계약 변경 절차

`types.py` 수정은 **P1만** 합니다. 필드가 필요하면:

1. 조 채널에 `[계약변경] 필드명 / 타입 / 이유`를 올립니다
2. P1이 반영하고 `계약 v2 반영 완료`를 공지합니다
3. 전원이 `git pull` 후 자기 모듈을 맞춥니다

**착수 후 1시간이 지나면 계약을 동결합니다.** 그 뒤의 변경은
`Optional` 필드 추가만 허용합니다. 기존 필드의 타입이나 이름은 바꾸지 않습니다.

---

## 4. 절대 규칙 4가지

### 4-1. 예외를 던지지 않습니다

모든 모듈 경계 함수는 실패를 **정상 반환값**으로 표현합니다.
에이전트 루프가 죽지 않고, 모델이 상황을 설명할 수 있어야 하기 때문입니다.

```python
# 잘못된 예
def geocode_place(place: str) -> Place:
    raise ValueError(f"{place}를 찾을 수 없습니다")

# 올바른 예
def geocode_place(place: str, ctx: RequestContext) -> GeocodeResult:
    return GeocodeResult(
        candidates=[],
        message="지원하지 않는 장소입니다. 강남역·홍대입구·시청 중에서 선택해 주세요.",
    )
```

내부 헬퍼 함수는 예외를 써도 됩니다. 다만 모듈 경계에서 반드시 잡아 반환값으로 바꿉니다.

### 4-2. 값을 추정하지 않습니다

확인할 수 없는 값은 `None`으로 두고 사유를 함께 기록합니다.
"아마 이 정도일 것"이라는 채움은 금지입니다.

```python
# 잘못된 예
available = lot.total_slots or 10

# 올바른 예
available = lot.available_slots          # 원본이 없으면 None
if available is None:
    evaluation.fee_note = "잔여 정보 미제공"
```

### 4-3. 응답의 모든 수치는 RankResult에서만 옵니다

`format_answer`는 문장을 만들 뿐, 숫자를 계산하거나 만들어내지 않습니다.
`Recommendation`의 `fee_text` · `availability_text` · `hours_text`는
P6이 **완성된 문자열로** 채워서 넘기고, LLM은 그대로 인용합니다.

`check_response`가 답변에 등장한 주차장명과 금액이 `RankResult` 안에
있는지 대조합니다. 없으면 `UNSAFE` 판정입니다.

### 4-4. 위치·시각은 Context에서만 읽습니다

도구 안에서 `datetime.now()`나 GPS를 직접 호출하지 않습니다.
`RequestContext.request_time`과 `user_lat/user_lng`를 씁니다.

한 요청 안의 모든 계산이 같은 기준 시각을 쓰게 하고, 단위 테스트에서
시각을 고정할 수 있게 하기 위함입니다.

---

## 5. 코드 컨벤션

- **주석·docstring은 경어체**입니다. `~합니다` / `~입니다`
- **타입 힌트 필수**입니다. `from __future__ import annotations`를 파일 상단에 둡니다
- **함수명은 동사로 시작**합니다. `search_parking`, `calculate_fee`
- **불리언 변수는 `is_` / `has_`** 접두사를 씁니다
- **매직 넘버 금지**입니다. 상수는 `SearchPolicy`나 모듈 상단 상수로 뺍니다
- 포매팅은 `ruff format`, 린트는 `ruff check`를 통과해야 합니다

### @tool docstring 규칙

LLM이 호출 시점을 판단하는 근거이므로 형식을 맞춥니다.

```python
@tool
def search_parking(district: str, adjacent: list[str]) -> str:
    """<한 줄> 무엇을 하는 도구인지.
    <둘째 줄부터> 언제 호출하는지.
    <셋째 줄> 언제 호출하지 않는지.

    Args:
        district: 인자 설명. 선행 도구가 있으면 여기에 명시합니다.
    """
```

**부정 조건을 반드시 넣으십시오.** 없으면 모델이 도구를 남발합니다.

---

## 6. Git 규칙

### 브랜치

```
main                     # 최종 배포 버전
develop                  # 보호. 직접 푸시 금지
└── feat/p2-extract      # feat/{담당}-{모듈}
    feat/p3-geocode
    feat/p4-search
    feat/p5-evaluate
    feat/p6-rank
```

### 커밋 메시지

```
feat(extract): 예산 표현 파싱 추가
fix(search): 좌표 없는 후보 필터링
test(evaluate): 영업시간 부족 케이스 추가
docs(contributing): 계약 변경 절차 명시
```

### 머지

- **자기 브랜치를 main에 직접 머지하지 않습니다.** P1이 통합합니다
- 머지 요청 전에 `python -m pytest tests/ -q`가 통과해야 합니다
- 다른 사람 파일이 diff에 잡히면 머지하지 않습니다. 잘못 건드린 것입니다

### 충돌이 났다면

파일 소유권을 지켰다면 충돌이 날 수 있는 곳은 `types.py`뿐입니다.
그 경우 **자기 변경을 버리고** P1의 버전을 받은 뒤 재작업하십시오.
계약은 항상 P1 쪽이 정본입니다.

---

## 7. 완료 기준

각 모듈은 아래를 모두 만족해야 완료입니다.

- [ ] 계약에 정의된 타입만 입출력한다
- [ ] 실패 경로가 예외가 아닌 반환값으로 처리된다
- [ ] 확인 불가 값이 `None`으로 유지되고 사유가 기록된다
- [ ] 단위 테스트가 정상 1건 + 실패 1건 이상 포함한다
- [ ] `ruff check`를 통과한다

### 시연 시나리오 (전원 공통 목표)

이 셋이 돌면 개발 종료입니다. **여기까지만** 하십시오.

| ID  | 입력                                | 검증 대상                        |
| --- | ----------------------------------- | -------------------------------- |
| S1  | "강남역 근처 2시간 주차, 만원 이하" | 정상 경로 전 구간                |
| S2  | "주차장 찾아줘"                     | 입력 가드레일 차단 → 명확화 질문 |
| S3  | "은평구 주차장" (미지원 장소)       | 폴백 안내, 스택 노출 없음        |
| S4  | S1 이후 "너무 비싸"                 | 조건 병합 리랭킹                 |
| S5  | (후보 0건 상황)                     | "추천 없음" + 탈락 사유 안내     |

---

## 8. 환경

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # OPENAI_API_KEY, SEOUL_OPENAPI_KEY

python scripts/demo_cli.py "강남역 근처 2시간 주차"
python -m pytest tests/ -q
PARKING_AGENT_NO_LLM=1 python scripts/demo_cli.py "강남역 근처"   # 키 없이 검증
```

`PARKING_AGENT_NO_LLM=1`이면 LLM 호출 없이 규칙 기반으로 동작합니다.
**자기 모듈 테스트는 항상 이 모드로 하십시오.** API 키 소모와 응답 지연을 피하고,
결과가 매번 같아 디버깅이 쉽습니다.
