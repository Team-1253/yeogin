# LCEL 리팩터링 wmux 에이전트 감시 기록

> 원 계획서: `docs/yeogin_langchain_lcel_refactoring_plan.md`
> 본 문서는 감시자(별도 에이전트)가 작업 에이전트의 수행이 계획서에 부합하는지
> 실시간으로 평가한 기록이다. 계획서 본문은 수정하지 않는다.

- 감시 시각(UTC): 2026-09-11 — 1차 스냅샷 + 2차 검증(본 절) 포함
- 브랜치: `develop` (HEAD `5ffb841`, 변동 없음)
- 감시 방법:
  - `wmux list-panes / tree / list-workspaces / prompts / read-screen` 으로 작업 pane 식별
  - `git status --porcelain`, `git diff --stat`, `git ls-files --others` 로 변경 범위 확인
  - `stages/*`, `chains/*`, `types.py`, `tools/geocode.py`, `tools/districts.py` 직접 판독
  - `pytest` + `PYTHONPATH=src` import/smoke + `parking_pipeline.invoke()` 종단 실행으로 검증

## 1. 감시 대상 스냅샷

- 활성 pane 2개 중 작업 에이전트는 `surf-3e191beb-…` (pane-068e…)로 식별.
  - 화면 제목: "yeogin_langchain_lcel 리팩토링 실행계획 평가"
  - Todo 상태: Hotfix ✓ / Phase 0 ✓ / Phase 1 ✓ / Phase 2 ✓ / Phase 3 진행중(•) /
    Phase 4·5·6·7 미착수(□) — 단, 화면에는 이미 `chains/parking_pipeline.py`,
    `chains/formatting_chain.py`, `stages/output_guard.py` 작성 흔적이 있어
    Phase 4·5를 선행 착수한 것으로 보인다 (순서 선후관계만 어긋남, 방향은 계획 부합).
  - 동일 화면에서 `pytest 45 passed, 4 skipped` 확인.
- 워킹트리 변경 (2차 검증 시점):
  - 수정(M): `format.py` (§7.6 native 교체), `pipeline.py` (§13 facade),
    `tools/districts.py`, `tools/geocode.py`, `types.py`
  - 신규(??): 상동 + 본 문서(`lcel_refactoring_monitoring.md`)
- 본 감시자의 검증: `pytest 45 passed, 4 skipped` 재현됨.
  `stages` import OK, `parking_pipeline.invoke()` 종단 실행 OK
  (예: "시청 근처 2시간" → geocode ambiguous 분기 → 확인 질문 answer 생성).

## 2. 계획서 부합 평가 (요약)

| 계획서 항목 | 판정 | 근거 |
|---|---|---|
| §4.1 LangChain 도입 자체가 목표가 아님 | 준수 | stage들은 `RunnableLambda` 얇은 adapter에 그침. 도메인 재구현 없음 |
| §4.2 A/B/C 분리 | 준수 | 도메인(`tools/*`, `format.py`) 유지 + `stages/*`가 adapter 역할만 수행 |
| §5.1 수동 orchestration → Runnable composition | 준수 | `parking_pipeline = extract\|validate\|validation_branch` 구성 + `pipeline.py run()`이 `parking_pipeline.invoke → _to_response` facade로 전환됨 (2차 검증에서 diff 확인) |
| §6 ParkingState | 준수 (경미한 적응) | `types.ParkingState` 동결. 계획서 예시(`candidates/evaluations/ranking`) 대신 기존 타입명(`search_result/evaluation_result/rank_result`, `geocode_result`, `is_valid` 등) 사용 — 기존 dataclass와 정합되어 정당 |
| §7.1 Extract | 준수 | `extract_params` 계약 유지 + `extract_stage`는 state→state. `bind_tools`는 extract에만 존재 |
| §7.2 Geocode | 준수 | 도메인 유지 + `geocode_stage` 노출. Kakao top-level `os.environ` 크래시·`print()` 제거된 hotfix는 정당 |
| §7.3 Search | 준수 | `search_stage`는 `RunnableLambda`. `@tool` 오남용 없음 |
| §7.4 Evaluate | 준수 | `evaluate_candidates` 위임만 수행 |
| §7.5 Rank | 준수 | `rank_candidates` 위임, LLM 위임 없음 |
| §7.6 Format 모듈 승격 | 준수 (중복 미해소) | `format.py`가 per-call 생성 제거 후 `chains.formatting_chain.invoke` 재사용으로 전환됨 (2차 검증에서 diff 확인). 단 `stages/format.py`의 `format_llm_chain`과 `chains/formatting_chain.py`의 `formatting_chain`이 여전히 병존하므로 하나로 통합 권장 (아래 §4-1) |
| §8 Branching LCEL 명시 | 준수 | `RunnableBranch`로 validation/geocode 분기 구현. Python `if`는 leaf 내부 early-return 헬퍼에만 존재 (허용 범위) |
| §9 Runnable ≠ Tool | 준수 | Tool은 extract 슬롯 선택에만 사용. search/evaluate/rank를 Tool화하지 않음. 철학(`LLM→params→deterministic→LLM`) 유지 |
| §10 Guardrail 분리 | 부분 | `validation_stage`/`output_guard_stage`가 business validation 위임. schema/parser 네이티브 전환은 Phase 5 잔여 |
| §11 Retry/Fallback 감사 | 대기 | 아직 명시적 audit 흔적 없음 (Phase 5 잔여). 단 extract의 규칙 폴백, format의 템플릿 폴백은 기존 동작 유지로 위반 아님 |
| §12 Parallel 감사 | 대기 | `RunnableParallel` 미사용. 무리한 병렬화 없음은 오히려 계획 부합 ("억지로 병렬화하지 않는다") |
| §13 기존 API 호환 | 준수 | `pipeline.run(utterance, ctx, prev)` 시그니처 유지 + 내부 `parking_pipeline.invoke → _to_response`. 2차 검증에서 4케이스(모호/미지원/장소누락/정상) `run() == chain` 동등 확인 |
| §14 Observability | 준수 | 전 stage `with_config(run_name=…)` 설정됨 |
| §15 Phase 순서 | 관찰 | Todo는 Phase 3 진행중 표기이나 실제로 Phase 4·5 파일 선행 생성. 역행이 아니라 선행 착수이며 회귀 없음(테스트 통과). 순서 표기만 정리 권장 |
| §16 목표 아키텍처 | 부분 | `stages/`, `chains/` 분리 방향 부합. `domain/` 분리는 미착수 (계획상 조정 가능 범위) |
| §18 성공 기준 1–5 | 조건부 (규칙 경로만 충족) | LCEL 명시 ✓ / 도메인 분리 ✓ / 불필요 재구현 없음 ✓ / Runnable·Tool 구분 ✓ / 회귀 없음 ✓(45 passed) — 단 3차 검증 원칙에 따라 live 미검증이므로 "아키텍처 개선"까지만 인정하고 "검증 완료"로 표기하지 않음 |
| §19 설계 철학 | 준수 | LLM 판단 위임 확대 없음 |

## 3. 검증 증거와 검증 한계 (3차 검증: "pytest 통과 ≠ 검증")

> 원칙: 본 프로젝트는 폴백이 촘촘히 구현되어 있어(`conftest.py:17`이 전 테스트에
> `PARKING_AGENT_NO_LLM=1` 강제 + 실패 시 규칙/템플릿 폴백) pytest 초록불은
> 규칙 기반 경로만 통과했음을 의미한다. 실API(LLM·Kakao) 시나리오는 아래 미검증 목록으로
> 별도 관리하며, 초록불을 검증 완료로 평가하지 않는다.

### 3.1 통과 사실 (규칙 기반 경로에 한정)

1. `python -m pytest tests/ -q` → `45 passed, 4 skipped` (2차·3차 검증에서 재현).
2. `from parking_agent.stages import …` 8종 import 성공.
   `bind_tools`/`_lc_tool` 사용처는 `extract.py`에만 존재 (`@tool` 오남용 없음).
3. NO_LLM 모드 facade 동등성: 4케이스
   (모호 / 미지원 / 장소누락 / 정상 조건부 요청) 모두
   `pipeline.run() == _to_response(parking_pipeline.invoke())`.
4. 관측성: 8 stage + 2 branch + pipeline/to_response 전체 `run_name` 설정 확인.
5. 한글 깨짐 오탐 주의: 터미널 한글 깨짐은 콘솔 디코딩 artifact이며 바이트 확인 결과
   파일은 UTF-8 정상. 파일 인코딩 결함 아님.

### 3.2 폴백에 가려져 미검증인 실API 시나리오 (3차 검증 특정)

- 전제: `OPENAI_API_KEY`·`KAKAO_REST_API_KEY` 미설정, `PARKING_AGENT_LIVE_TEST` 미설정 확인.
  `langchain_core`·`langchain_openai`·`requests`는 설치되어 있음.
- 마스킹 기전 (실측): `ChatOpenAI(...)` 생성자가 키 없이 `OpenAIError: Missing credentials`로
  실패 → `chains/formatting_chain.py:41`·`stages/format.py:45`의 `except Exception`이 삼킴 →
  `formatting_chain is None`·`format_llm_chain is None` 확정 →
  모든 format 호출이 `_format_by_template`으로 조용히 폴백. 즉 §7.6 LCEL 체인은
  본 환경에서 단 한 번도 invoke된 적이 없음.
- 미검증 목록:
  1. extract 실모델 슬롯 선택 (`_run_slot_agent`→`_extract_by_llm` 성공 경로) —
     `test_extract_live.py` 4건 전부 skip (`-rs` 확인). 선택 실패·오선택 시 턴 전체
     규칙 폴백(`extract.py:459`)이 실패를 가리므로 live 없이는 선택 품질 검증 불가.
  2. `formatting_chain.invoke` / `format_llm_chain.invoke` 성공 경로 —
     체인이 None이라 구성 자체(프롬프트·모델·파서 결합)가 실행된 적 없음.
     REQUIRED_NOTICE 포함·수치 그대로 인용·순서 유지 같은 환각 가드가 live에서
     지켜지는지는 검증 불가.
  3. Kakao 지오코딩 폴백 (`tools/geocode.py:71-114`) — 키가 없어 LANDMARKS 테이블 또는
     미지원 안내만 실행됨. Kakao 응답→Place 변환·자치구 파싱·거리 정렬 경로는 미실행.
  4. `HAS_LCEL=False` 폴백 파이프라인 (`chains/parking_pipeline.py:106-163`) —
     현 환경 `HAS_LCEL=True`라 데드 코드. `_extract(state) if False` placeholder 포함.
  5. §11 retry/fallback 네이티브 전환 — `with_retry`/`with_fallbacks` 미사용이 확인되나,
     수동 `try/except → 폴백`이 LLM 장애를 정상 흐름처럼 보이게 하므로 장애 시 동작은 미검증.

### 3.3 목(mock) 배선 검증 (실API 대체가 아닌 배선 증명)

키 없이 실행 가능한 범위에서 LCEL 배선 자체는 가짜 체인 주입으로 증명함:

- format: `FakeChain(ret=' LLM ANSWER ')` 주입 시 `_format_by_llm → 'LLM ANSWER'`,
  호출 인자 `{place, recommendations}` 확인. raise·빈 문자열·`None` 체인 모두
  `None` 반환 → 템플릿 폴백 확인. 단, 이는 배선 증명이며 실모델 출력 품질 검증이 아님.
- extract: `_run_slot_agent` 스텁(`['place','duration','sort']`) 주입 시
  `_extract_by_llm`이 규칙 도구를 선택 실행해 `place/duration/sort=price` 산출 확인.
  `None` 반환 시 턴 전체 폴백(`None`) 확인. 실모델의 선택 정확도는 미검증.
- 배선 검증의 한계: 주입점 발견 — `_format_by_llm`은 `parking_agent.format` 네임스페이스가
  아니라 `parking_agent.chains.formatting_chain` 모듈에서 체인을 매번 재import하므로,
  테스트 더블은 chains 모듈에 주입해야 한다. 향후 live/mock 테스트 작성 시 유의.

### 3.4 Live 검증 게이트 (키 확보 후 수행 → 4차 검증에서 실행됨)

- `PARKING_AGENT_LIVE_TEST=1` + `OPENAI_API_KEY` 설정 후 `test_extract_live.py` 4건 실행.
- format live: `NO_LLM` 해제 상태에서 체인 성공 응답에 `REQUIRED_NOTICE` 포함·수치 일치·
  순서 유지 assert (신규 테스트 필요 — 현재 해당 assert는 존재하지 않음).
- Kakao 키 설정 후 geocode 폴백 경로 실행 (자치구 파싱·3건 절단·거리 정렬).
- `HAS_LCEL=False` 분기는 단위 테스트에서 강제 분기로 1회 실행 후 placeholder 정리.

### 3.5 Live 실행 결과 (4차 검증, `.env` 키 사용 — 비밀 미기록)

- extract live: 기본 모델(`gpt-5.6-luna`, `extract.py:69`)에서 **2 failed / 2 passed**.
  원인 실측: `OpenAIInvalidRequestError: Function tools with reasoning_effort are not
  supported for gpt-5.6-luna in /v1/chat/completions` — 기본 모델이 `bind_tools`와
  비호환이라 `_run_slot_agent`가 예외로 `None` 반환 → 턴 전체 규칙 폴백도 아닌
  `None` 전파로 live 테스트 실패. pytest 초록불이 가렸던 실결함 1건.
  `MODEL_NAME=gpt-4o-mini` 오버라이드 시 **4 passed** — 배선 자체는 정상이므로
  원인은 코드가 아니라 기본 모델 설정. 조치 필요: 기본값을 tool 호출 가능 모델로
  변경하거나, luna 계열은 responses API/`reasoning_effort='none'` 분기 추가.
- format live: 키 로드 시 `formatting_chain is None → False`로 정상 구성.
  실 invoke 1회 결과 `REQUIRED_NOTICE` 포함·`7,800원`·`106m` 그대로 인용 확인.
  단 이를 assert하는 테스트는 없음 (신규 테스트 권장).
- Kakao live: 비랜드마크 조회 3건 반환·자치구 파싱(`송파구`)·거리 정렬 확인.
  무의미 입력은 0건 + 미지원 안내 확인. 매핑 경로 정상.
- 전체 live suite (`MODEL_NAME=gpt-4o-mini`): **48 passed, 1 failed** —
  실패는 `test_s3_미지원_장소는_폴백_안내` (`"은평구청"`이 Kakao 실결과 3건을 반환해
  `"지원하지 않는"` 분기로 가지 않음). 테스트가 LANDMARKS-only 모드를 전제로 작성되어
  키 유무에 따라 결과가 갈리는 환경 결합 결함. 코드는 의도대로 동작하므로
  테스트 쪽 수정 권장 (지원 불가 확정 쿼리 사용 또는 키 제거 monkeypatch).
  `HAS_LCEL=False` 분기는 여전히 미실행.

## 4. 조치 요청 / 다음 감시 포인트 (2차 검증 반영)

1. **[잔여-권장] format chain 중복 통합** — 2차 검증 결과 미해소:
   `stages/format.py:43 format_llm_chain`과 `chains/formatting_chain.py:39 formatting_chain`
   병존 확인. `stages/format.py`가 chains 정본을 import하도록 전환 권장
   (§7.6 "모듈 수준 1개" 원칙).
2. **[해소] `pipeline.run()` facade 전환** — 2차 검증에서 전환 완료 확인
   (구 orchestration 8단계 본문 → `invoke → _to_response`로 축소, 시그니처 유지).
3. **[확인] `districts.py` 인접구 데이터 변경** — `get_adjacent(district, count)` 시그니처는
   `search.py:20` 호출부와 정합(`ctx.policy.adjacent_district_count` 전달)함을 2차 검증에서 재확인.
   강남구(+성동구·광진구)·마포구(+영등포구) 데이터 변경의 근거를 커밋 메시지에 명시 권장.
   회귀 테스트(45 passed)로 커버됨은 확인됨.
4. **[잔여-정리] fallback 코드** — 2차 검증 결과 미해소:
   `chains/parking_pipeline.py:108`의 `_extract(state) if False` placeholder와
   `_FallbackPipeline.__or__` 핵 잔존 확인. 정리 권장. 기능 영향은 없음
   (HAS_LCEL=True 경로가 정상 동작, `with_retry`/`with_fallbacks`/`RunnableParallel`
   신규 사용 없음 — §11·§12의 무리한 도입이 없어 계획 부합).
5. **다음 감시 주기**: §3.4 live 게이트 + Phase 6 Tool 경계 문서화 + Phase 7 최종 검증(§18) +
   잔여 2건(1·4) 해소 여부를 `read-screen` + `git diff` + `pytest -rs`로 재확인 예정.
   `pytest` 결과 보고 시 반드시 `-rs` 스킵 사유와 함께 "규칙 경로만 통과, live 4건 skip"을 명기.

## 5. 최종 평가 (리팩터링 총평, 5차 검증)

- 상태: rule-mode `45 passed, 4 skipped` (재확인). 변경 범위는 4차 검증과 동일.
- 총평: **아키텍처 리팩터링으로서는 잘 되었으나, 병합 게이트 미통과 (조건부)**.
- 잘된 점: ① `pipeline.py` 8단계 수동 호출 → `invoke → _to_response` facade + LCEL 그래프
  (§5.1·§8·§13, facade 동등성 4케이스 실증). ② stages는 얇은 adapter로 도메인 무수정 위임
  (§4.2). ③ Tool은 extract 슬롯 4종에만 존재, search/evaluate/rank Tool화 없음 (§9,
  철학 유지). ④ `ParkingState`는 기존 타입명 재사용 적응으로 정당 (§6).
  ⑤ format per-call 생성 제거 + chains 정본 재사용 (§7.6). ⑥ 전 stage `run_name` (§14).
  ⑦ `with_retry`/`RunnableParallel` 무리한 도입 없음 (§11·§12).
- 문제점: [상] 기본 모델 `gpt-5.6-luna` + `bind_tools` 비호환으로 live 2 failed (§3.5-1).
  [상] S3 테스트가 LANDMARKS-only를 전제해 키 있으면 실패 (§3.5). [중] format chain
  이중 정의 (`stages/format.py:43` vs `chains/formatting_chain.py:39`). [중]
  `HAS_LCEL=False` 데드 코드 + `if False` placeholder 미실행 잔존. [하] districts 변경
  근거 미기록, format live assert 부재.
- §18 채점: ① LCEL 명시 충족 ② 도메인 분리 충족 ③ 재구현 제거 충족
  ④ Runnable/Tool 구분 충족 ⑤ 무회귀 — 규칙만 충족, live 미충족 → **조건부**.
- 병합 판정: 위 [상] 2건(기본 모델·S3 테스트) 해소 후 병합可. [중] 2건은 후속 정리로 허용.

### 5.1 게이트 해소 기록 (6차 검증)

- [상-1 해소] `extract.py:69` 기본 모델을 `gpt-4o-mini`로 변경 (tool 호출 가능 모델,
  format 체인 기본값과 일치). live extract 4/4 통과를 기본 설정 그대로 재현.
- [상-2 해소] `test_s3`에 `monkeypatch.delenv("KAKAO_REST_API_KEY")` 추가로
  LANDMARKS-only 모드 고정. 키 유무와 무관하게 결정적.
- 최종: rule-mode `45 passed, 4 skipped` + live 전체 **`49 passed`** (skip·fail 없음).
  §18-⑤ live 기준 충족으로 변경 → **병합 게이트 통과**. 잔여 [중] 2건은 후속 정리로 이월可.

### 5.2 luna 복귀 (7차 검증, (b)안)

- 정정: `langchain-openai 1.6.2`는 `use_responses_api`·`reasoning`을 지원한다
  (pydantic field라 `inspect.signature`에 안 보였을 뿐). 버전이 문제가 아니라
  기본값(chat/completions 경로)으로 호출한 것이 원인이었다.
- 조치: `extract._chat_model()` 신설 — luna/gpt-5 계열은
  `use_responses_api=True, reasoning={"effort": "none"}` (슬롯 선택=분류 작업),
  그 외는 기존 `temperature=0` 경로. 기본 모델을 `gpt-5.6-luna`로 복귀.
  `chains/formatting_chain.py`도 동일 분기 (`effort: low`, GPT-5는 temperature
  기본값만 허용하므로 미지정). `MODEL_NAME`/`OPENAI_MODEL` 오버라이드 유지.
- 중복 해소 ([중] 1건): `stages/format.py`의 자체 체인 정의를 삭제하고
  호출 시점에 chains 정본을 가져오는 `_stage_chain()`으로 전환
  (모듈 로드 시 import는 순환 참조 유발하므로 지연 import).
- 검증: rule `45 passed, 4 skipped` + 순환 import 없음 +
  extract live 4/4 (luna) + format 실 invoke 가드 확인
  (REQUIRED_NOTICE·수치 인용) + live 전체 **`49 passed`** (오버라이드 없음).
   잔여 [중]은 `HAS_LCEL=False` 데드 코드 1건만.
   실시간 추적 명령 예:
   `wmux read-screen --surface surf-3e191beb-8bba-4208-92e8-c64627ddb285 --lines 60`

### 5.3 통합본 실행검증 기록

- 통합본(dev, `2158cf3`, origin 동기화) 실행검증: rule `45 passed, 4 skipped` +
  live 전체 **`49 passed**`. 푸시 후 동일 결과 재현.

### 5.4 모호성 선택 해소 (pending)

- 결함: 되묻기 후 "1" 입력이 신규 검색으로 처리되어 같은 질문 무한 반복.
  원인 — 파이프라인에 선택 대기 상태가 없고 `run()`은 `prev_params`만 수신.
- 조치: `ParkingState.pending` + `AgentResponse.pending` 추가.
  `tools/geocode.resolve_choice` (번호/후보명, 범위 밖은 None),
  `geocode_stage` 선두에서 확정 시 geocode 생략, `validate_stage`는 선택 턴 통과,
  `run(..., pending=None)` + `demo_cli` 턴 전달.
- 검증: rule `48 passed, 4 skipped` + live 전체 **`52 passed`**.
  "2번"→2번 후보 확정, "9"→재질문+pending 유지 실증.
