# Yeogin LangChain Pipeline 리팩터링 계획

## 1. 문서 목적

이 문서는 `Team-1253/yeogin` 프로젝트의 기존 LangChain 파이프라인을 분석한 결과를 바탕으로, 프로젝트 전체를 LangChain의 `Runnable` 및 LCEL(LangChain Expression Language) 중심 구조로 리팩터링하기 위한 계획을 정리한다.

이번 리팩터링의 목적은 단순히 기존 코드를 LangChain 코드로 다시 작성하는 것이 아니다.

핵심 목표는 다음과 같다.

> 기존에 직접 구현한 LLM application orchestration 중 LangChain이 이미 제공하는 기능과 중복되는 부분을 제거하고, Yeogin 고유의 도메인 로직과 LangChain의 실행 추상화를 명확하게 분리한다.

---

## 2. 현재 구조에 대한 이해

Yeogin을 처음 설계할 당시 각 스테이지의 논리적인 pipeline은 이미 다음과 같이 구상되어 있었다.

```text
utterance
   ↓
extract
   ↓
geocode
   ↓
search
   ↓
evaluate
   ↓
rank
   ↓
format
   ↓
response validation
```

즉, **논리적인 pipeline 자체는 의도적으로 설계되어 있었다.**

다만 초기 설계 당시에는 이 pipeline을 LangChain의 `Runnable` 객체들로 구성하여 LCEL 자체가 실행 그래프가 되도록 한다는 관점이 반영되지 않았다.

그 결과 현재 구조에서는 `pipeline.py`가 각 함수를 직접 순차 호출하면서 orchestration을 담당한다.

예를 들어 개념적으로 다음과 같은 형태이다.

```python
params = extract_params(...)
geo = geocode_place(...)
search = search_parking(...)
evaluation = evaluate_candidates(...)
rank_result = rank_candidates(...)
answer = format_answer(...)
```

따라서 이번 리팩터링은 기존 pipeline의 논리를 폐기하는 것이 아니라,

```text
기존의 논리적 pipeline
        ↓
Runnable abstraction
        ↓
LCEL execution graph
```

로 승격시키는 작업으로 정의한다.

---

## 3. Extractor의 의미

현재 `extract.py`에는 이미 `RunnableLambda`를 이용하여 extraction stage를 Runnable로 노출하려는 흔적이 존재한다.

이는 초기 전체 설계에는 반영되지 않았던 LCEL composition의 가능성을 담당 영역에서 먼저 발견하고 개선을 시도한 결과이다.

현재 extractor의 개념적 구조는 다음과 같다.

```text
utterance
    ↓
LLM의 slot 선택
    ↓
slot function 실행
    ↓
validation
    ↓
RankingParams
```

이 구조 자체는 유지할 가치가 있다.

다만 extractor 하나만 Runnable화하는 것으로 끝내는 것이 아니라, 이번 전체 리팩터링에서는 이 접근을 모든 pipeline stage로 확장한다.

---

# 4. 리팩터링의 핵심 원칙

## 4.1 LangChain 도입 자체가 목표가 아니다

이번 작업을 "LangChain을 더 많이 사용하는 작업"으로 정의하지 않는다.

정확한 목표는 다음과 같다.

> 우리가 직접 구현한 LLM application orchestration과 LangChain이 제공하는 execution abstraction 사이의 중복을 제거한다.

---

## 4.2 도메인 로직과 orchestration을 분리한다

모든 코드를 LangChain으로 다시 작성하지 않는다.

코드를 세 종류로 분류한다.

### A. LangChain이 이미 제공하는 기능

예:

- Prompt composition
- ChatModel invocation
- Structured output
- Output parsing
- Runnable composition
- Conditional branching
- Parallel execution
- Retry
- Fallback
- Streaming
- Tracing
- Tool binding

가능하면 LangChain native abstraction으로 대체한다.

### B. Yeogin의 도메인 로직

예:

- 주차장 데이터 검색
- 거리 계산
- 가격 계산
- 후보 평가
- ranking
- 주차장 정책 판단
- 공공데이터 처리

이 부분은 직접 구현한 로직으로 유지한다.

### C. Domain logic을 Runnable interface로 노출하는 부분

예:

```text
extract_params
geocode_place
search_parking
evaluate_candidates
rank_candidates
format_answer
```

내부 구현을 무리하게 변경하지 않고 Runnable로 composition할 수 있도록 adapter/stage를 만든다.

---

# 5. 현재 구조에서 개선해야 할 주요 지점

## 5.1 `pipeline.py`의 수동 orchestration

현재는 Python 함수 호출 순서가 pipeline 구조를 결정한다.

```text
extract()
  ↓
geocode()
  ↓
search()
  ↓
evaluate()
  ↓
rank()
  ↓
format()
```

이를 Runnable composition으로 옮긴다.

목표 개념:

```python
parking_pipeline = (
    extract_stage
    | validation_stage
    | geocode_stage
    | search_stage
    | evaluate_stage
    | rank_stage
    | format_stage
    | response_validation_stage
)
```

단, 실제 구현에서는 각 stage가 필요한 이전 state를 사용할 수 있도록 state-preserving composition을 사용한다.

---

# 6. Pipeline State 정의

Runnable화 전에 pipeline 전체가 공유할 state를 명확하게 정의한다.

예:

```python
class ParkingState(TypedDict, total=False):
    utterance: str
    prev_params: RankingParams | None
    ctx: RequestContext

    params: RankingParams
    destination: Destination
    candidates: list[Parking]
    evaluations: list[Evaluation]
    ranking: RankingResult
    answer: str
```

각 stage는 이 state를 기반으로 자신의 결과를 추가한다.

개념적으로:

```text
Initial State
    │
    ├── utterance
    ├── prev_params
    └── ctx
         ↓
      + params
         ↓
      + destination
         ↓
      + candidates
         ↓
      + evaluations
         ↓
      + ranking
         ↓
      + answer
```

이를 통해 함수 호출 관계가 아니라 **state transition 자체가 pipeline을 표현하도록 만든다.**

---

# 7. 각 Stage의 Runnable화

## 7.1 Extract

현재:

```text
utterance
    ↓
extract_params()
    ↓
RankingParams
```

목표:

```text
utterance
    ↓
extract_runnable
    ↓
params
```

가능하다면 LLM 결과를 문자열로 받은 뒤 직접 JSON parsing하는 구조는 LangChain의 structured output 및 Pydantic 기반 validation으로 대체한다.

개념:

```text
현재

LLM
 ↓
string
 ↓
json.loads()
 ↓
Pydantic validation


개선

LLM
 ↓
structured output
 ↓
Pydantic model
```

---

## 7.2 Geocode

도메인 geocoding 구현은 유지한다.

다만 pipeline에서 호출할 수 있는 Runnable stage로 노출한다.

```text
params
   ↓
geocode_runnable
   ↓
destination
```

---

## 7.3 Search

공공데이터/API 검색과 후보 생성 로직은 도메인 구현으로 유지한다.

```text
destination + ctx
        ↓
search_runnable
        ↓
candidates
```

여기서 중요한 원칙은 `search_parking()`이 Python 함수라는 이유만으로 `@tool`로 만들 필요는 없다는 것이다.

---

## 7.4 Evaluate

후보 평가 및 조건 계산은 Yeogin의 도메인 로직이다.

따라서 내부 계산은 유지하고 Runnable adapter만 추가한다.

```text
candidates
destination
params
ctx
   ↓
evaluate_runnable
   ↓
evaluations
```

---

## 7.5 Rank

ranking은 명백한 도메인 로직이다.

```text
evaluations
params
ctx
   ↓
rank_runnable
   ↓
ranking
```

LLM에게 ranking 판단을 위임하는 방향으로 변경하지 않는다.

---

## 7.6 Format

현재 코드에서 특히 명확한 개선 대상이다.

현재 구조가 다음과 같이 함수 내부에서 매번 Prompt와 LLM chain을 생성한다면:

```python
def _format_by_llm(...):
    prompt = ChatPromptTemplate(...)
    model = ChatOpenAI(...)
    chain = prompt | model | StrOutputParser()
    return chain.invoke(...)
```

이를 모듈 수준의 LCEL chain으로 승격한다.

```python
format_chain = (
    format_prompt
    | model
    | StrOutputParser()
)
```

그리고 pipeline의 Runnable stage로 연결한다.

목표:

```text
ranking
   ↓
format input
   ↓
ChatPromptTemplate
   ↓
ChatModel
   ↓
StrOutputParser
   ↓
answer
```

---

# 8. Branching을 LCEL로 명시한다

현재 `pipeline.py`의 다음과 같은 구조를 조사한다.

```python
if not ok:
    return ...

if not geo.candidates:
    return ...

if not geo.is_confirmed:
    return ...
```

이러한 분기는 현재 Python `if` 문에 숨어 있다.

이를 Runnable 기반 conditional execution으로 표현한다.

개념:

```text
extract
   ↓
validation
   ↓
branch
 ┌────────────────┬──────────────────┐
 │ invalid        │ valid            │
 ↓                ↓
response        geocode
                  ↓
                branch
             ┌────┼──────────────┐
             │    │              │
           no result ambiguous confirmed
             │    │              │
             ↓    ↓              ↓
          response response      search
```

이렇게 하면 코드 구조 자체가 실제 실행 그래프를 표현한다.

---

# 9. Runnable과 Tool을 구분한다

이번 리팩터링에서 가장 중요한 설계 원칙 중 하나이다.

## Runnable

pipeline 내부의 실행 단위이다.

```text
extract
geocode
search
evaluate
rank
format
```

## Tool

LLM이 어떤 기능을 사용할지 선택해야 하는 capability이다.

따라서 다음과 같은 함수들이 단순히 Python 함수라는 이유로 Tool이 되어서는 안 된다.

```text
search_parking
evaluate_candidates
rank_candidates
```

현재 Yeogin의 구조는:

```text
LLM
 ↓
params
 ↓
deterministic code
 ↓
recommendation
 ↓
LLM
```

이라는 철학을 가지고 있으므로 이를 유지한다.

특히 `extractor`에서 LLM이 어떤 slot function을 선택해야 하는 경우처럼 실제로 LLM의 tool selection이 필요한 부분에서는 Tool abstraction이 의미가 있다.

즉:

```text
Runnable ≠ Tool
```

이라는 구분을 유지한다.

---

# 10. Guardrail 리팩터링

현재의 `check_request()`와 `check_response()` 같은 guardrail을 모두 제거하지 않는다.

대신 두 종류로 분리한다.

## LangChain/Pydantic으로 이동할 수 있는 validation

예:

- 출력 schema 검사
- 필수 field 검사
- 구조화 출력 검증
- parser 수준의 형식 검증

가능한 경우 native structured output / parser / Pydantic을 사용한다.

## Yeogin이 직접 담당해야 하는 business validation

예:

- 주차장 정책
- 특정 조건 만족 여부
- 도메인 규칙
- 검색 결과의 유효성
- 추천 결과의 business constraint

이 부분은 직접 구현한다.

결과적으로:

```text
Guardrail
├── schema validation
│      └── LangChain / Pydantic
│
└── business validation
       └── Yeogin domain logic
```

구조를 목표로 한다.

---

# 11. Retry / Fallback 감사

전체 코드에서 다음과 같은 수동 구현을 검색한다.

```python
try:
    ...
except:
    ...
```

특히 LLM 호출에 대해 직접 retry 또는 fallback을 구현했다면 LangChain Runnable의 retry/fallback abstraction으로 대체할 수 있는지 검토한다.

목표 개념:

```text
Runnable
 ├── retry
 └── fallback
```

즉, 실행에 대한 공통 관심사를 개별 함수에 흩어놓지 않고 Runnable layer에서 관리한다.

---

# 12. Parallelization 감사

Runnable graph로 변경하면서 독립적인 작업이 존재하는지 조사한다.

예:

```text
destination
   ├── parking search
   └── metadata lookup
```

서로 독립적이라면 Runnable parallel execution을 검토한다.

개념:

```python
RunnableParallel(
    parking=parking_search,
    metadata=metadata_lookup,
)
```

다만 현재 실제 dependency가 존재하는 단계까지 억지로 병렬화하지 않는다.

---

# 13. 기존 API 호환성 유지

기존 외부 호출부와 테스트의 변경을 최소화하기 위해 `pipeline.run()` 같은 기존 API는 compatibility facade로 남길 수 있다.

개념:

```python
def run(
    utterance: str,
    ctx: RequestContext,
    prev_params: RankingParams | None = None,
) -> AgentResponse:

    return parking_pipeline.invoke({
        "utterance": utterance,
        "prev_params": prev_params,
        "ctx": ctx,
    })
```

즉:

```text
Existing API
     ↓
run()
     ↓
parking_pipeline.invoke()
     ↓
LCEL graph
```

구조를 만든다.

이렇게 하면 내부 orchestration은 교체하면서 외부 API의 breaking change를 최소화할 수 있다.

---

# 14. Tracing / Observability

Runnable 기반 구조로 변경하는 또 하나의 목적은 각 stage를 명시적인 execution unit으로 만드는 것이다.

기존에는:

```text
pipeline.run()
 ├── extract_params()
 ├── geocode_place()
 ├── search_parking()
 ├── evaluate_candidates()
 ├── rank_candidates()
 └── format_answer()
```

가 단순 Python 함수 호출이다.

Runnable화하면:

```text
pipeline
 ├── extract
 ├── geocode
 ├── search
 ├── evaluate
 ├── rank
 └── format
```

각각을 독립적인 실행 단위로 관찰할 수 있다.

향후 LangSmith 등의 observability 기능을 사용할 때 stage별 latency, 입력/출력, 오류 등을 추적하기 쉬워진다.

---

# 15. 전체 리팩터링 단계

## Phase 0 — 기존 동작 고정

코드를 변경하기 전에 현재 pipeline의 동작을 테스트로 고정한다.

필수 케이스:

- 정상 요청
- 조건이 포함된 요청
- 장애인 주차장 관련 요청
- 가격 조건
- 거리 조건
- 잘못된 장소
- 모호한 장소
- 검색 결과 없음
- extraction 실패
- 응답 validation 실패

목표는 리팩터링 이후 기존 기능의 regression을 방지하는 것이다.

---

## Phase 1 — LangChain 중복 구현 Audit

전체 `src`를 대상으로 다음을 조사한다.

```text
LLM 호출
Prompt 생성
JSON parsing
Pydantic validation
Output parsing
branch
retry
fallback
parallel execution
streaming
tool
```

각 항목을 다음 기준으로 분류한다.

| 분류 | 의미 |
|---|---|
| 유지 | Yeogin 고유 도메인 로직 |
| Runnable화 | 기존 함수를 Runnable stage로 노출 |
| Native 교체 | LangChain이 이미 제공하는 기능으로 대체 |
| 삭제 | 중복 orchestration 제거 |
| Tool 유지 | LLM이 선택적으로 호출해야 하는 capability |

이 결과를 리팩터링 backlog로 사용한다.

---

## Phase 2 — State 정의

`ParkingState`를 정의하고 각 stage의 input/output contract를 확정한다.

예:

```text
extract:
Input  → utterance + prev
Output → params

geocode:
Input  → params
Output → destination

search:
Input  → destination + ctx
Output → candidates

evaluate:
Input  → candidates + destination + params
Output → evaluations

rank:
Input  → evaluations + params
Output → ranking

format:
Input  → ranking + params
Output → answer
```

---

## Phase 3 — 각 Stage Runnable화

다음 stage들을 Runnable interface로 만든다.

```text
extract_runnable
geocode_runnable
search_runnable
evaluate_runnable
rank_runnable
format_runnable
```

단, 각 도메인 함수의 내부 구현을 불필요하게 변경하지 않는다.

---

## Phase 4 — LCEL Pipeline 구축

Runnable들을 전체 실행 그래프로 연결한다.

필요한 경우:

```text
RunnablePassthrough.assign
RunnableBranch
RunnableParallel
```

등을 사용한다.

목표는 Python 함수 호출 순서가 아니라 LCEL composition이 pipeline의 실행 구조가 되도록 만드는 것이다.

---

## Phase 5 — LangChain Native 기능으로 중복 구현 제거

다음 항목을 우선적으로 제거/대체한다.

```text
직접 Prompt 조립
직접 LLM invoke orchestration
직접 JSON parsing
직접 structured output parsing
직접 retry
직접 fallback
직접 branch orchestration
직접 parallel orchestration
```

단, 도메인 validation과 business logic은 유지한다.

---

## Phase 6 — Tool Boundary 재정의

각 기능을 다음 중 하나로 명확하게 분류한다.

```text
Runnable
Tool
일반 Python function
```

판단 기준:

> LLM이 실행 여부나 실행할 기능을 선택해야 하는가?

Yes → Tool 후보

No → Runnable 또는 일반 domain function

---

## Phase 7 — Observability 및 품질 검증

최종적으로:

- stage별 실행 추적
- latency 확인
- LLM 호출 확인
- retry/fallback 동작 확인
- 기존 테스트 통과
- regression 확인

을 수행한다.

---

# 16. 목표 아키텍처

권장하는 책임 분리는 다음과 같다.

```text
src/parking_agent/
│
├── domain/
│   ├── models.py
│   ├── parking.py
│   ├── evaluation.py
│   └── ranking.py
│
├── stages/
│   ├── extract.py
│   ├── geocode.py
│   ├── search.py
│   ├── evaluate.py
│   ├── rank.py
│   └── format.py
│
├── chains/
│   ├── extraction_chain.py
│   ├── formatting_chain.py
│   └── parking_pipeline.py
│
├── tools/
│   └── ...
│
└── pipeline.py
```

파일 구조 자체는 현재 프로젝트의 필요에 따라 조정할 수 있지만, 책임은 다음과 같이 분리하는 것을 목표로 한다.

```text
domain
   ↓
순수 비즈니스 로직

stages
   ↓
domain logic을 Runnable execution unit으로 노출

chains
   ↓
Runnable들을 LCEL로 composition

pipeline.py
   ↓
기존 API compatibility facade
```

---

# 17. 리팩터링 전후의 핵심 차이

## 현재

```text
Python orchestration
        │
        ├── extract()
        ├── geocode()
        ├── search()
        ├── evaluate()
        ├── rank()
        └── format()
```

각 함수 호출 순서가 pipeline을 정의한다.

## 목표

```text
                 LCEL Pipeline
                      │
                      ▼
              ┌───────────────┐
              │    Extract    │
              └───────┬───────┘
                      ↓
                 Validation
                      ↓
              ┌───────┴───────┐
              │    Geocode    │
              └───────┬───────┘
                      ↓
                   Search
                      ↓
                 Evaluate
                      ↓
                    Rank
                      ↓
             ChatPromptTemplate
                      ↓
                  ChatModel
                      ↓
              StrOutputParser
                      ↓
              Response Guard
```

즉, **논리적 pipeline을 실행 가능한 Runnable graph로 승격**시키는 것이다.

---

# 18. 리팩터링의 성공 기준

이번 작업은 "LangChain 클래스를 얼마나 많이 사용했는가"로 평가하지 않는다.

다음 조건을 만족하면 성공으로 본다.

### 1. Pipeline 구조가 LCEL로 명시된다

```text
Runnable → Runnable → Runnable
```

구조가 코드에서 직접 드러나야 한다.

### 2. 도메인 로직이 LangChain 코드와 분리된다

주차장 검색, 평가, ranking 등의 핵심 알고리즘은 LangChain에 종속되지 않아야 한다.

### 3. LangChain이 이미 제공하는 기능을 직접 재구현하지 않는다

특히:

- prompt composition
- structured output
- parsing
- retry
- fallback
- branching
- composition

등을 불필요하게 직접 구현하지 않는다.

### 4. Runnable과 Tool의 의미가 명확하다

모든 함수가 Tool이 되거나 모든 함수가 Runnable이 되는 식의 무분별한 추상화를 피한다.

### 5. 기존 기능의 regression이 없다

리팩터링은 architecture 개선이지 기능 변경이 아니다.

---

# 19. 최종적으로 유지해야 할 설계 철학

Yeogin의 기존 설계에서 가장 중요한 부분은 다음 구조이다.

```text
             LLM
              │
              │ interpretation
              ▼
          structured params
              │
              ▼
       deterministic domain logic
              │
              ├── search
              ├── evaluate
              └── rank
              │
              ▼
          recommendation
              │
              ▼
             LLM
              │
              ▼
           response
```

이번 리팩터링은 이 철학을 Agent 중심 구조로 변경하는 것이 아니다.

오히려:

```text
LLM responsibility
        +
Domain responsibility
        +
LangChain execution abstraction
```

을 명확하게 분리하는 작업이다.

---

# 20. 결론

이번 리팩터링의 핵심은 다음 한 문장으로 정리할 수 있다.

> **Yeogin이 이미 설계한 논리적 pipeline을 LangChain Runnable 기반의 명시적인 LCEL execution graph로 승격시키고, 그 과정에서 우리가 직접 구현한 orchestration 기능 중 LangChain이 이미 제공하는 기능을 제거하여 domain logic과 framework logic을 분리한다.**

따라서 `extract.py`에서 먼저 시도했던 Runnable화는 전체 리팩터링의 방향을 검증한 작은 프로토타입으로 볼 수 있다.

최종 목표는 단순히:

```python
RunnableLambda(function)
```

를 많이 만드는 것이 아니라,

```text
Domain Function
      ↓
Runnable Stage
      ↓
LCEL Composition
      ↓
Executable Pipeline
```

이라는 계층을 만드는 것이다.

그리고 특히 다음 원칙을 유지한다.

> **LangChain을 사용하는 것이 목적이 아니라, LangChain이 이미 해결한 문제를 우리가 다시 해결하고 있는 부분을 제거하는 것이 목적이다.**
