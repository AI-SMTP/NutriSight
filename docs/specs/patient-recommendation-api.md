# 환자·추천·처방 API

> 의사 화면이 쓰는 환자·섭취 추이·경고·추천 카드·처방 HTTP API 10개, 서비스 함수와 작업 단위(`run_in_db`), 추천 생성기 계약과 Fake, 경고 상승 훅, 프로세스 안 이벤트 버스, `SqlitePatientData` (팀 제안안 기준).

## 개요

의사 화면(③)과 에이전트 도구가 같은 데이터를 본다. 화면은 HTTP API로, 에이전트는 `PatientDataPort`로 들어오고, 둘 다 같은 서비스 함수를 거쳐 `var/app.db`를 읽고 쓴다. 추천 카드 수정은 화면 경로(PATCH)와 포트 경로가 `save_items` 하나를 공유한다.

- 환자 목록·요약·섭취 추이·경고·현재 추천 카드를 읽는다. 기준일은 요청마다 `seed_meta.demo_date`에서 읽고 서버 날짜를 쓰지 않는다.
- 의사가 추천 카드 항목을 고치고(PATCH), 항목을 골라 처방으로 확정하고, 추천 없이 처방을 직접 만든다. 확정된 처방을 바꾸는 API는 없다.
- 추천 카드를 다시 만들거나(`manual`), 경고 수준이 올라갔을 때 만든다(`auto`, 훅 `on_alert_evaluated`). 생성기는 계약(`RecommendationGenerator`)과 고정 카드 Fake로 두고 실제 에이전트가 같은 등록부에 들어온다.
- 모든 DB 쓰기는 단일 스레드 쓰기 실행기에서 실행하고, 커밋 직후 같은 작업 안에서 이벤트를 발행한다.
- `PATIENT_DATA` 기본값은 `sqlite`이고 `fake`는 등록부에 남아 있다.

섭취 추정·`GET /api/events` SSE 직렬화·판정 저장(`alerts`·`daily_intakes` 쓰기)·`on_alert_evaluated`를 실제로 부르는 연결은 이 문서 범위 밖이다(T3). 이름·상태 값은 `docs/data-model.md`를 정본으로 따른다.

## 구조 / 스키마

### 파일 구성

```
backend/app/
  api/
    patients.py          환자 목록·요약·섭취·경고·추천 조회, 다시 만들기, 처방 작성·이력
    recommendations.py   PATCH 추천, 확정
    schemas.py           요청·응답 Pydantic 모델
    deps.py              deps(request), read_db, write_db
    errors.py            http_errors: 서비스 예외 → HTTP 오류
  events/bus.py          Event, EventBus, SubscriptionOverflowError
  recommender/
    generator_types.py   RecommendationGenerator 계약, GeneratedCard, GenerationError
    fake_generator.py    FakeRecommendationGenerator
  services/
    unit_of_work.py      run_in_db, WriteResult
    runtime.py           AppRuntime, TaskRegistry, WriteExecutor, RuntimeClosedError
    clock.py             AppClock, 시각 형식·단조 증가 보정 함수
    item_rules.py        ItemEdit, 항목·근거·카드 공통 검증 규칙
    patients.py          환자 목록·요약·섭취 기간·일별 섭취·자주 남긴 메뉴 (동기)
    recommendations.py   카드 조회·수정·확정 (save_items, edit_by_doctor, merge_doctor_edit, confirm_recommendation)
    prescriptions.py     처방 작성·이력, insert_prescription_record
    generation.py        create_recommendation, on_alert_evaluated, RecommendationDeps, PatientLocks
    sqlite_patient_data.py  SqlitePatientData (PatientDataPort 구현)
  storage/
    recommendations.py   recommendations·prescriptions 읽기·쓰기 SQL
    codec.py             항목·주의 문구 JSON 인코딩 (items_to_json 등)
    queries.py           get_demo_date, get_latest_alert, get_alert, list_left_menu_candidates 등
  config.py              recommender, recommendation_timeout_s, patient_data 기본값 sqlite
  wiring.py              RECOMMENDATION_GENERATORS 등록부, 포트 생성 함수가 (settings, runtime)을 받음
  main.py                라우터 등록, app.state.runtime·event_bus·recommendation_generator·recommendation_deps
```

`create_recommendation`, `on_alert_evaluated`, `RecommendationDeps`, `PatientLocks`는 모두 `services/generation.py`에 있다. 이 모듈은 `services/recommendations.py`를 import하지 않고 저장소 SQL(`storage/recommendations.py`)만 함께 쓴다.

### 계층과 작업 단위

호출 방향은 라우터 → 서비스 → 저장소다.

- 라우터는 요청 검증과 예외 → 상태 코드 변환만 한다.
- 서비스 함수는 열린 `sqlite3.Connection`과 값(엔진, 시각)을 인자로 받는 동기 함수다. 연결을 열거나 닫지 않고, 커밋하지 않고, 이벤트를 발행하지 않는다.
- 쓰기 서비스는 `WriteResult(value, events)`를 돌려준다. 쓰기 서비스는 트랜잭션을 시작하지 않으므로 다른 쓰기 서비스를 불러도(`edit_by_doctor` → `save_items`) 같은 트랜잭션 안에서 이어진다.
- 저장소 함수는 SQL만 한다.

모든 DB 연결은 `services/unit_of_work.py`의 `run_in_db(db_path, fn, *, mode)` 하나로 연다. 연결을 연 스레드가 그 연결을 쓰고 닫으며 `sqlite3`의 스레드 검사를 끄지 않는다. 블록이 끝나면 `connect()`가 커밋하고, 예외면 롤백한 뒤 다시 던진다.

| mode | 시작 문 | 용도 |
| --- | --- | --- |
| `read` | 없음 | 트랜잭션을 열지 않는 읽기 |
| `snapshot` | `BEGIN DEFERRED` | 읽기 트랜잭션. 안의 여러 조회가 첫 읽기 시점의 스냅샷을 본다 |
| `write` | `BEGIN IMMEDIATE` | 쓰기 직렬화. 쓰기 실행기 스레드에서만 부른다 |

`read`는 트랜잭션을 열지 않으므로 여러 조회를 묶어도 서로 일관된 시점을 보장하지 않는다. 지금은 여러 조회로 이뤄진 읽기도 `read`로 실행한다: HTTP 읽기 라우트 전부(`read_db`)와 `SqlitePatientData.get_intake_summary`가 그렇다. 추천 생성 맥락만 `snapshot`을 쓴다(동작 절). 이 점은 제약사항 절에 적었다.

경로별 실행 위치는 다음과 같다.

| 경로 | 읽기 | 쓰기 | 이벤트 발행 |
| --- | --- | --- | --- |
| 동기 라우터(`def`) | 요청 스레드의 `read_db` | `write_db` → `writer.run_sync(fn)`, 요청 스레드는 결과를 기다림 | 쓰기 실행기 작업이 커밋 직후 |
| 비동기 경로(다시 만들기, 훅, `SqlitePatientData`) | `asyncio.to_thread(run_in_db, …)` | `await writer.run_write(fn)` | 쓰기 실행기 작업이 커밋 직후 |

연결용 `Depends`는 쓰지 않는다. 다시 만들기만 `async def`다.

### AppRuntime

`create_app`이 맨 먼저 `AppRuntime.create(app_db)`로 만들어 `app.state.runtime`에 두고, `build_components(settings, runtime)`과 `RecommendationDeps`가 같은 인스턴스를 쓴다.

| 구성 | 내용 |
| --- | --- |
| `bus: EventBus` | 프로세스 안 이벤트 버스 |
| `tasks: TaskRegistry` | 앱 소유 태스크 등록부. `spawn(coro)`는 강한 참조를 두고 끝나면 놓으며, `close()` 뒤에는 `RuntimeClosedError`를 낸다. `run_shielded(coro, label=…)`는 `spawn` 후 `shield`로 기다린다. 호출자가 취소돼도 태스크는 계속 돌고, 그 뒤 태스크가 실패하면 ERROR 로그를 남긴다. `cancel_all()`은 새 태스크를 막고 남은 태스크를 취소한다 |
| `writer: WriteExecutor` | `ThreadPoolExecutor(max_workers=1)`. 작업 하나는 "`run_in_db(mode="write")`로 커밋 → `WriteResult.events` 발행"이다. `run_write(fn)`는 비동기, `run_sync(fn, timeout=None)`은 동기 입구다. `db_path` 속성이 있다. `shutdown()`은 실행 중인 작업을 기다리고 시작 전 작업은 버린다 |
| `clock: AppClock` | 앱 시계 (다음 절) |

`aclose()`는 종료 정책 앞 세 단계를 한다: `tasks.close()` → 남은 태스크 취소·대기 → `writer.shutdown`(스레드에서 기다림).

### 앱 시계와 시각 형식

- 앱이 만드는 시각(`recommendations.created_at`·`updated_at`, `prescriptions.confirmed_at`)은 시간대 없는 `YYYY-MM-DDTHH:MM:SS.ffffff` 문자열이다. 마이크로초가 0이어도 6자리를 쓴다. 문자열 정렬이 시간 순서와 같다.
- 값은 실제 현재 시각에 시연일 차이를 더한 것이다. 시연일 차이는 `seed_meta.demo_date - 앱 시작일`(일 단위)이며 lifespan이 `runtime.clock.anchor(demo_date, today)`로 한 번 고정한다. 고정 전에 `now()`를 부르면 `RuntimeError`다.
- 단조 증가 보정은 같은 트랜잭션에서 읽은 기준값보다 크게 만든다. 후보가 기준 이하이면 기준 + 1µs다.

| 값 | 기준 |
| --- | --- |
| 새 카드의 `created_at`·`updated_at` | 그 환자 카드들의 최대 `created_at` |
| 카드 수정·확정의 `updated_at` | 그 카드의 기존 `updated_at` |
| 처방의 `confirmed_at` | 그 환자 처방들의 최대 `confirmed_at` |

- `parse_app_timestamp`는 엄격 파서다. 다시 형식화한 값이 원문과 다르면 `ValueError`다.
- 테스트는 `AppClock(now_fn=…)`으로 가짜 현재 시각을 주입한다.

### 시작과 종료

lifespan 시작 순서:

1. 런타임이 이미 닫혔으면 `RuntimeError("앱 인스턴스는 한 번만 시작한다")`.
2. 시연일 형식 검사(`resolve_demo_date`, 실패 시 `ConfigError`).
3. 앱 잠금(`AppLock.acquire`).
4. `ensure_storage`.
5. `bus.bind_loop(실행 중인 루프)`.
6. 시계 고정(`get_demo_date`로 읽은 DB의 시연일과 오늘의 차이).

3단계 뒤 종료·실패 정리는 `AsyncExitStack`이 등록 역순으로 한다: `runtime.aclose()` → `lock.release()`. 런타임 종료가 실패해도 잠금은 놓는다.

앱 인스턴스는 한 번만 시작한다. 2·3단계(시연일 형식 오류, 잠금 충돌)에서 실패한 앱은 런타임을 닫지 않았으므로 같은 인스턴스로 다시 시작할 수 있다. 잠금을 잡은 뒤 실패했거나 정상 종료한 앱은 런타임이 닫혀 있어 두 번째 시작이 `RuntimeError`다. 새 앱은 `create_app`으로 만든다.

종료 순서는 다음과 같다.

1. `tasks.close()`로 새 태스크를 막는다.
2. 남은 앱 소유 태스크(생성·포트 수정)를 모두 즉시 취소한다. 잠금 대기·맥락 읽기·생성기 대기 중이던 생성은 아무것도 쓰지 않고 끝난다.
3. `writer.shutdown`이 실행 중인 쓰기가 끝나기를 기다린다. 제한 시간은 없다. 시작 전 쓰기는 버린다.
4. 앱 잠금을 놓는다. 그래서 리셋 CLI는 쓰는 중인 DB를 바꾸지 못한다.

3단계에서 끝난 쓰기도 작업 안에서 발행까지 하지만, 종료 중에는 구독자가 이미 끊겼을 수 있다.

## 동작

### HTTP API

모든 경로는 `/api` 아래다.

| 메서드 · 경로 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- |
| `GET /patients` | — | 200 `PatientListItem[]` (`patient_id` 순) | — |
| `GET /patients/{id}` | — | 200 `PatientDetail` | 404 |
| `GET /patients/{id}/intake` | `days` 기본 14, 1~60 | 200 `IntakeTrend` | 404, 422 |
| `GET /patients/{id}/alert` | — | 200 `Alert` 또는 `null` | 404 |
| `GET /patients/{id}/recommendation` | — | 200 `Recommendation` 또는 `null` | 404 |
| `PATCH /recommendations/{id}` | `{items, expected_updated_at}` | 200 `Recommendation` | 404, 409, 422 |
| `POST /recommendations/{id}/confirm` | `{item_ids, expected_updated_at}` | 201 `Prescription` | 404, 409, 422 |
| `POST /patients/{id}/recommendation/regenerate` | — | 201 `Recommendation` | 404 |
| `POST /patients/{id}/prescriptions` | `{items}` | 201 `Prescription` | 404, 422 |
| `GET /patients/{id}/prescriptions` | — | 200 `Prescription[]` (확정 시각 내림차순) | 404 |

처방 수정·삭제 경로는 없다.

### 요청 모델

모든 요청 모델은 `extra="forbid"`라서 모르는 필드(`added_by`, `evidence` 등)를 422로 거부한다.

| 모델 | 필드와 제한 |
| --- | --- |
| `ItemInput` | `item_id`: `^[A-Za-z0-9_-]{1,32}$`. `type`: `PrescriptionType` 7종. `title`: 1~100자. `detail`: 0~1000자. `duration_days`: 엄격 정수 1~365 또는 `null`(`true`·`"7"` 거부). `review_date`: `YYYY-MM-DD` 문자열 또는 `null` |
| `RecommendationPatch` | `items: ItemInput[]`(개수 상한 없음, 빈 목록 허용, `item_id` 유일), `expected_updated_at: str` |
| `ConfirmRequest` | `item_ids: str[]`(1~100개), `expected_updated_at: str` |
| `PrescriptionCreate` | `items: ItemInput[]`(1~100개, `item_id` 유일) |

`expected_updated_at`은 카드 응답의 `updated_at` 문자열을 그대로 돌려준 값이며 `datetime`으로 바꾸지 않는다.

### 응답 모델

- `PatientListItem` = `{patient_id, display_name, room, alert_level: none|caution|warning|null, alert_nutrients}`. 판정이 없으면 `alert_level`은 `null`이다.
- `PatientDetail` = `{patient_id, display_name, room, sex, age, height_cm, conditions, diet_restrictions, ckd_dialysis, latest_weight, weight_change_30d, bmi, target, assessments}`.
  - `age = 시연일 연도 - birth_year`.
  - 체중·평가는 시연일 이하만 쓴다.
  - `weight_change_30d`는 시연일 30일 이전(포함) 가장 가까운 측정값과 최근 측정값의 차이 `{kg, pct}`이며 둘 중 하나가 없으면 `null`이다. `bmi`·`pct`는 반올림하지 않는다.
  - `target` = `{energy_kcal, protein_g, source, effective_from}`. `NutritionEngine.daily_target(…, 시연일)`이며 `effective_from`은 `team_set`일 때만 적용 시작일, 아니면 `null`이다.
  - `assessments`는 `kind`별 최신 한 건을 `kind` 순으로 담는다.
- `IntakeTrend` = `{patient_id, period_start, period_end, days, prescriptions}`.
  - `days`는 포트 `IntakeSummary.daily`와 같은 함수(`daily_rows`)로 만든다. 항목은 `{date, energy_kcal, protein_g, energy_pct, protein_pct, recorded_meals, unrecorded_meals, npo_meals, target}`이고 `target`은 그날 `{energy_kcal, protein_g, source}`다.
  - `prescriptions` = `{prescription_id, confirmed_at}[]`. `confirmed_at`의 날짜가 `[period_start, period_end]`에 드는 처방만, `(confirmed_at, prescription_id)` 오름차순으로 담는다. 처방 이력 API(`GET …/prescriptions`)는 내림차순이다.
- `Alert` = `{alert_id, evaluated_at, level, nutrients, period_start, period_end, evidence: {nutrient, avg_pct, low_days_streak}[], unrecorded_meals}`. 판정에 근거 기간이 없으면 `period_start`·`period_end`는 `null`이다.
- `Recommendation` = `{recommendation_id, patient_id, alert_id, items, cautions, last_modified_by, thread_id, created_at, updated_at, status}`. 시각은 저장 문자열 형식이다.
- `Item` = `{item_id, type, title, detail, duration_days, review_date, added_by, evidence: {doc_id, section}[]}`.
- `Prescription` = `{prescription_id, patient_id, recommendation_id | null, items, confirmed_at, status: "confirmed"}`.

ID는 `rec_` + uuid4 hex(추천), `rx_` + uuid4 hex(처방)다.

### 일별 섭취 규칙

`services.patients.daily_rows`가 포트 `daily`와 HTTP `days`를 함께 만든다.

- 기간 안에 그 환자의 발주(`meal_orders` ⋈ `meal_plans.date`)가 하나라도 있는 날만 담는다. 발주가 없는 날은 `daily_intakes` 행이 있어도 뺀다. 오래된 날부터 나열한다.
- 그날 `daily_intakes` 행이 있으면 그 값을 쓴다.
- 행이 없으면 그날 발주를 `MealRecord`로 바꿔 `engine.daily_intake(day, meals, target)`로 계산한다. 계산 결과는 저장하지 않는다. 시드 직후 D0은 `recorded_meals = 0`, 섭취량·%는 `null`이다.
- 목표는 두 경우 모두 그날 기준 `engine.daily_target`이다.

### 자주 남긴 메뉴 규칙

`IntakeSummary.frequently_left_menus`는 `queries.list_left_menu_candidates`가 만든다.

- 대상: 기간 안 `record_status = recorded` 발주의 `slot_intakes` 중 `intake_fraction_est`가 NULL이 아니고 배식 칸의 `menu_name`이 NULL이 아니며 `estimate_basis`가 `staff`가 아닌 행. 전량 거부·미섭취(`staff`)는 메뉴 선호가 아니라 뺀다.
- `(menu_name, dish_type)`으로 묶어 평균 섭취 비율과 끼니 수(발주 수)를 낸다. 끼니 수 2 이상, 평균 0.5 이하만 남긴다.
- 평균 오름차순, 같으면 끼니 수 내림차순, 그다음 `menu_name` 순으로 최대 5개.

### 낙관적 잠금과 카드 수정

- 화면 경로(PATCH·확정)는 `expected_updated_at`을 보낸다. 저장소는 `UPDATE … WHERE recommendation_id = ? AND status = 'active' AND updated_at = ?`를 실행하고, 영향 행이 0이면 카드를 다시 읽어 원인을 가린다.

| 상황 | 예외 | HTTP |
| --- | --- | --- |
| 카드 없음, 환자 없음 | `RecommendationNotFoundError`, `PatientNotFoundError` | 404 |
| 카드가 `active`가 아님 | `RecommendationNotEditableError` | 409, `detail = "not_editable"` |
| `updated_at` 불일치 | `StaleRecommendationError` | 409, `detail = "stale"` |
| 확정 요청의 `item_id`가 카드에 없음 | `UnknownItemError` | 422, `detail`은 문자열 |

- 요청 검증 실패의 422는 FastAPI 기본 `detail` 목록 형식이고, 서비스 오류(없는 `item_id`)의 422는 문자열이다.
- 모든 카드 수정은 `save_items(conn, recommendation_id, items, modified_by, thread_id, expected_updated_at, now)`를 거친다. 받은 항목을 그대로 저장하고 `thread_id` 규칙, 항목 규칙(`validate_items`), `active` 상태, `expected_updated_at`(`None`이면 비교 안 함)을 검사한다. 바뀌는 열은 `items`, `last_modified_by`, `thread_id`, `updated_at`이다.
- `thread_id` 규칙은 `chat`이면 있어야 하고 `agent`·`doctor`이면 `None`이어야 한다.

**PATCH 병합 규칙** (`edit_by_doctor` → `merge_doctor_edit`, 읽기·병합·저장은 한 트랜잭션)

- 요청 `items`가 카드의 새 항목 목록이다. 순서도 요청을 따르고, 빠진 항목은 삭제된다.
- 현재 카드에 있는 `item_id`는 `title`·`detail`·`duration_days`·`review_date`만 요청 값으로 바꾸고 `type`·`added_by`·`evidence`는 현재 값을 유지한다. 요청의 `type`은 무시한다.
- 새 `item_id`는 요청 값으로 만들고 `added_by = doctor`, `evidence = []`다.
- 결과 카드는 `last_modified_by = doctor`, `thread_id = null`이고 `recommendation.updated`를 발행한다.

**확정** (`confirm_recommendation`)

- 오류 판정 순서: 빈 `item_ids` 422(요청 검증) → 카드 없음 404 → `active` 아님 409 → stale 409 → 카드에 없는 `item_id` 422.
- `item_ids`의 중복은 하나로 취급한다. 처방 `items`는 `item_ids` 순서가 아니라 카드 순서대로 고른 항목을 복사한다. 고르지 않은 항목은 처방에 들어가지 않고 카드에 남는다.
- 같은 트랜잭션에서 카드를 `confirmed`로 바꾸고 `updated_at`을 갱신한다. 없는 `item_id`는 카드 상태를 바꾼 뒤 검사하지만 예외로 롤백되므로 카드는 `active`와 기존 `updated_at`으로 남는다.
- 발행하는 이벤트는 `prescription.confirmed` 하나다. 카드의 `recommendation.updated`는 발행하지 않는다. 화면은 이 이벤트를 받으면 처방과 함께 카드도 다시 읽는다.

**처방 직접 작성** (`create_prescription`)은 `ItemInput`을 `added_by = doctor`, `evidence = []` 항목으로 바꿔 `recommendation_id = null` 처방을 만든다. 그 환자의 추천 카드는 건드리지 않는다.

### 추천 생성

**생성기 계약** (`recommender/generator_types.py`)

```python
@dataclass(frozen=True)
class GeneratedCard:
    items: tuple[RecommendationItem, ...]   # 1개 이상, item_id 유일, added_by = agent
    cautions: tuple[str, ...]

class GenerationError(Exception): ...

class RecommendationGenerator(Protocol):
    async def generate(self, patient_id: str, summary: IntakeSummary) -> GeneratedCard: ...
```

`summary`는 `get_intake_summary(patient_id, 14, 시연일)`과 같은 함수(`intake_summary`)로 만든다. 생성기는 이 두 인자만 받고 `PatientDataPort`는 바뀌지 않는다.

**Fake** (`FakeRecommendationGenerator(*, fail=False)`)는 외부 호출 없이 `summary`만으로 고정 카드를 만든다.

- 항상 `fortify`(`food_fortification`, "식사 강화 7일", `duration_days = 7`)와 `review`(`monitoring_review`, "재평가", `review_date = summary.period_end + 7일`)를 넣는다.
- `summary.alert.level`이 `warning`이면 `ons`("경구영양보충 하루 400 kcal")를 더한다.
- 근거는 모두 `EvidenceRef("espen_geriatrics", "R20")`다.
- `cautions`: `summary.alert`가 있고 `unrecorded_meals > 0`이면 `"미기록 끼니 {n}개가 있어 섭취 추이가 실제와 다를 수 있습니다."` 하나, 아니면 빈 tuple.
- `fail=True`면 `GenerationError`를 던진다.

**등록과 설정**: `wiring.RECOMMENDATION_GENERATORS`(`fake`), 설정 `RECOMMENDER`(기본 `fake`), `app.state.recommendation_generator`. `RECOMMENDATION_TIMEOUT_S`(기본 120, 0 초과)는 생성기 시간 제한이다.

**결과 검증**: 생성기 결과는 저장 전에 `item_rules.validate_generated_card`로 전체 필드를 검사한다. 같은 규칙 함수를 Pydantic 검증기(`ItemInput`)와 포트 저장(`save_items`, 위반 시 `ValueError`)이 함께 쓴다.

| 구분 | 규칙 |
| --- | --- |
| 항목 | `item_id` 형식·카드 안 유일, `type`은 `PrescriptionType` 인스턴스(문자열 거부), `title` 1~100자, `detail` 0~1000자, `duration_days` `None` 또는 1~365 정수(`bool` 제외), `review_date` `None` 또는 `date`(`datetime` 제외), `added_by`는 `AddedBy` |
| 근거 | `EvidenceRef` tuple, `doc_id`·`section` 1~100자 |
| 카드 | `GeneratedCard` 인스턴스, `cautions`는 문자열 tuple 최대 10개·각 1~300자, 항목 1개 이상, 모든 항목 `added_by = agent` |

검증 위반·`GenerationError`·시간 초과는 모두 생성 실패이며 `failed` 카드로 저장한다. 사유는 WARNING 로그에 남기고 카드에는 담지 않는다. 그 밖의 생성기 예외는 계약 위반이라 그대로 올라가고 카드는 저장되지 않는다.

**생성 서비스** `create_recommendation(patient_id, *, mode, deps) -> RecommendationCard | None` (`mode`는 `manual` 또는 `auto`, 그 밖은 `ValueError`)

본문 전체를 `runtime.tasks.run_shielded`로 앱 소유 태스크에서 돌린다. 호출자가 취소돼도 잠금 해제까지 끝까지 실행된다.

1. 환자별 `asyncio.Lock`(`deps.locks.get(patient_id)`)을 잡는다. 아래는 모두 잠금 안이다.
2. `to_thread(run_in_db, …, mode="snapshot")` 한 번으로 생성 맥락(`read_generation_context`)을 읽는다: 요약, 시연일 이하 최신 판정의 `alert_id`(없으면 `None`), 현재 카드(포트 규칙). 모두 같은 스냅샷이다. 없는 환자는 `PatientNotFoundError`다.
3. `auto`이고 현재 카드가 있고 그 `alert_id`가 최신 판정 ID와 같으면 생성하지 않고 `None`을 돌려준다. `manual`은 건너뛰지 않으며 경고가 없는 환자도 만든다(`alert_id = null`).
4. 연결 없이 생성기를 `asyncio.wait_for(…, timeout_s)`로 기다리고 결과를 검증한다.
5. `writer.run_write` 한 번 안의 한 트랜잭션(`save_generated_card`)에서 그 환자의 `active`·`failed` 카드를 `superseded`로 바꾸고 새 카드를 넣는다. 성공이면 `status = active`, 실패면 `status = failed`, `items = []`, `cautions = []`다. `last_modified_by = agent`, `thread_id = null`, `alert_id`는 2단계에서 읽은 값이다. `confirmed` 카드는 대체하지 않는다.
6. 같은 쓰기 작업이 커밋 직후 `recommendation.created`를 발행한다. 저장이 실패하면 예외를 올리고 발행하지 않는다.

다시 만들기 API는 `mode = manual`로 부르며, 생성기가 실패해도 201 `failed` 카드를 돌려준다.

**판정이 이어서 바뀔 때**: 카드는 요청 시점이 아니라 잠금을 잡은 뒤 읽은 최신 판정으로 만든다. `auto` 요청이 연달아 오면 먼저 잠금을 잡은 요청이 최신 판정으로 카드를 만들고, 다음 요청은 현재 카드의 `alert_id`가 최신과 같으므로 건너뛴다. 생성기를 기다리는 동안 상승이 아닌 판정이 저장되면 카드는 이전 판정에 연결된 채 남는다. `manual`과 `auto`가 겹쳐도 잠금 순서대로 실행한다.

**생성 중 다른 쓰기와 겹칠 때**: 생성기를 기다리는 동안 PATCH·포트 수정·확정은 막지 않는다. 저장 단계는 저장 시점의 DB 상태를 기준으로 하며 생성 결과는 항상 새 카드로 저장된다.

| 생성 중 일어난 일 | 저장 단계의 결과 |
| --- | --- |
| 이전 카드를 PATCH·포트로 고침 | 고친 내용 그대로 `superseded`가 되고 새 카드가 `active`. 이전 카드에 대한 이후 PATCH·확정은 409 `not_editable` |
| 이전 카드를 확정함 | 이전 카드는 `confirmed`로 남고 처방도 그대로. 새 카드가 `active` |
| 다른 생성이 끝남 | 환자별 잠금으로 겹치지 않는다 |

### 경고 상승 훅

```python
async def on_alert_evaluated(
    patient_id: str, previous_level: AlertLevel | None, alert_id: str, *, deps: RecommendationDeps
) -> RecommendationCard | None
```

- T3은 새 판정을 `alerts`에 저장·커밋한 뒤, 저장 전의 최신 수준을 `previous_level`(판정이 없었으면 `None`)로 넘겨 이 함수를 기다린다.
- `alert_id`의 판정 수준을 `read` 연결로 읽는다. 수준 순서는 `none < caution < warning`이고 `None`은 `none`과 같다. 인자 판정이 `previous_level`보다 높을 때만 `create_recommendation(mode="auto")`를 부르고 그 결과(카드, 건너뛰면 `None`)를 돌려준다. 같거나 낮으면 `None`이다.
- `alert_id`가 없거나 다른 환자의 판정이면 `ValueError`다(호출자의 프로그래밍 오류).
- `alert_id`는 상승 판단에만 쓴다. 카드에 연결되는 판정은 생성 서비스가 2단계 스냅샷에서 읽은 최신 판정이다.
- 생성 실패는 예외로 올리지 않고 `failed` 카드로 돌려준다.
- T3이 판정을 저장할 때는 `runtime.writer.run_write` 또는 `asyncio.to_thread(run_in_db, …, mode="write")`로 저장한다. 이벤트 루프 스레드에서 직접 쓰지 않는다. 추천 저장의 쓰기 잠금과 겹치면 루프가 막힌다.
- `RecommendationDeps`(`generator`, `runtime`, `db_path`, `engine`, `locks: PatientLocks`, `timeout_s`)는 `app.state.recommendation_deps`에 있다. T3은 이것을 꺼내 쓴다.
- 이 훅을 실제로 부르는 연결은 T3 범위다. 이 토픽에서는 단위 테스트로만 검증한다.
- `latest_alert`는 판정일이 시연일 이하인 판정만 본다. 앱 시계가 자정을 넘겨 시연일 + 1이 된 뒤 저장된 판정은 최신 판정에서 빠진다. 그러면 훅이 `auto`에서 조용히 건너뛸 수 있다.

### 이벤트 버스

```python
@dataclass(frozen=True)
class Event:
    name: str
    data: Mapping[str, object]     # 읽기 전용 복사본

class EventBus:
    def publish(self, event: Event) -> None: ...           # 어느 스레드에서나 호출, 막히지 않음
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[Event]]: ...
    def bind_loop(self, loop) -> None: ...
```

- 구독자마다 `asyncio.Queue(maxsize=100)`를 둔다. `publish`는 묶인 루프에 `call_soon_threadsafe`로 넘겨 루프 스레드에서 큐에 넣는다.
- `bind_loop` 전이거나 루프가 닫힌 뒤의 `publish`는 이벤트를 버리고 DEBUG 로그만 남긴다. 예외를 올리지 않으므로 발행 실패가 쓰기를 실패시키지 않는다.
- `subscribe()`는 묶인 루프 안에서만 부른다(아니면 `RuntimeError`). 블록을 나가면 구독이 풀린다.
- 큐 포화는 구독 종료다. 큐가 가득 차면 그 구독자를 버스에서 떼고 WARNING 로그를 남긴다. 그 구독의 반복자는 남은 이벤트를 모두 내보낸 뒤 `SubscriptionOverflowError`를 던진다. 다른 구독자는 영향받지 않는다.
- 복구 계약: SSE 처리기(T3)는 `SubscriptionOverflowError`를 받으면 응답 스트림을 닫고, 브라우저 `EventSource`가 다시 연결하면 화면이 연결(`open`)마다 보던 데이터를 다시 읽는다.

| 이벤트 | 데이터 | 발행 시점 |
| --- | --- | --- |
| `recommendation.created` | `{recommendation_id, patient_id, status, at}` | 새 카드 커밋 뒤 (`active`·`failed` 모두) |
| `recommendation.updated` | `{recommendation_id, patient_id, modified_by, thread_id, at}` | PATCH·포트 수정 커밋 뒤 |
| `prescription.confirmed` | `{prescription_id, patient_id, recommendation_id, at}` | 확정·직접 작성 커밋 뒤 |

`at`은 앱 시각 문자열이다. 이벤트는 커밋이 끝난 뒤에만 발행되고, 쓰기가 실패하면(서비스 예외·저장소 예외) DB도 바뀌지 않고 발행도 없다. 커밋된 쓰기의 이벤트는 호출한 요청 스레드·태스크의 중단과 무관하게 쓰기 실행기 작업이 발행한다.

### SqlitePatientData

`SqlitePatientData(db_path, runtime, engine)`는 `PatientDataPort`의 SQLite 구현이다.

- `db_path.resolve()`가 `runtime.writer.db_path.resolve()`와 다르면 `ValueError`다. 생성 시 DB 파일을 열지 않는다.
- `get_intake_summary`: `services.patients.intake_summary`. 기간은 `[on - (days - 1), on]`, `alert`는 판정일이 `on` 이하인 최신 판정, `daily`는 일별 섭취 규칙, `frequently_left_menus`는 자주 남긴 메뉴 규칙. `days < 1`이면 `ValueError`, 없는 환자는 `PatientNotFoundError`. `to_thread`로 `mode="read"` 실행한다.
- `get_recommendation`: `current_card`(`active`·`failed` 중 `created_at`이 가장 늦은 것, 같으면 ID가 큰 것). HTTP `GET …/recommendation`과 같은 함수다.
- `update_recommendation`: 병합 없이 `save_items(…, expected_updated_at=None)`를 `writer.run_write`로 실행한다. `tasks.run_shielded`로 감싸므로 호출 코루틴이 취소돼도 커밋·발행까지 끝난다. 성공하면 `recommendation.updated`를 발행한다. 카드 없음·`active` 아님·규칙 위반은 포트 예외(`RecommendationNotFoundError`, `RecommendationNotEditableError`, `ValueError`)로 올라가고 발행하지 않는다. 항목 검사가 카드 조회보다 먼저라서 없는 카드에 잘못된 항목을 주면 `ValueError`다.

등록 경로: `PATIENT_DATA_PORTS`의 생성 함수는 `(settings, runtime)`을 받는다. `sqlite`(기본)는 `SqlitePatientData(storage_paths(settings).app_db, runtime, build_nutrition_engine(settings))`, `fake`는 `runtime`을 무시한다. 포트와 `app.state.nutrition_engine`은 인스턴스를 공유하지 않으므로 판단 알고리즘 구현은 상태가 없어야 한다.

## 제약사항

- 접근 제어와 호출 제한(rate limit)이 없다. 파일럿 전제이며 화면의 역할 선택은 권한이 아니다.
- 에이전트 경로(`SqlitePatientData.update_recommendation`)에는 낙관적 잠금이 없다. `active` 조건만 건다. 에이전트가 읽은 뒤 의사가 고친 내용을 에이전트가 덮어쓸 수 있다. 덮어써도 `recommendation.updated`가 발행되므로 화면은 다시 읽는다.
- 대화 수정(`modified_by = chat`)에서 `chat_threads`에 없는 `thread_id`는 `sqlite3.IntegrityError`로 그대로 올라온다. 포트 계약 범위 밖이다.
- `PatientLocks`는 환자 ID별 `asyncio.Lock`을 한 번 만든 뒤 지우지 않는다. 존재하지 않는 환자 ID로 다시 만들기를 부르면 404가 되기 전에 잠금이 생겨 사전이 커진다. 파일럿 규모에서는 감수한다.
- `read` 모드는 트랜잭션을 열지 않아 여러 조회 사이의 일관성을 보장하지 않는다. 지금은 읽기 라우트와 `SqlitePatientData.get_intake_summary`가 여러 조회를 `read`로 실행한다. 판정과 일별 섭취를 쓰는 T3 쓰기가 붙으면 한 응답 안에서 커밋 전·후 값이 섞일 수 있다. `snapshot`으로 바꾸는 것이 제안안이다.
- 생성 맥락(`snapshot`)과 저장(`write`) 사이에는 시간 차가 있다. 그 사이의 변경은 "생성 중 다른 쓰기와 겹칠 때" 표대로 처리한다.
- `latest_alert`의 판정일 ≤ 시연일 조건 때문에, 자정을 넘겨 시연일 + 1이 된 뒤 저장된 판정은 최신 판정에서 빠진다(경고 상승 훅 절).
- 처방을 수정하거나 취소하는 API가 없다. 확정 뒤에는 바꾸지 않는다.
- `GET /api/events` SSE 직렬화는 T3 범위이며 이 문서의 버스는 `subscribe()`까지 제공한다.
- `list_patients_with_alert`는 환자마다 최신 판정을 조회한다(N+1). 시연 규모(환자 10명)에서는 감수한다.
- 확정·처방 작성 요청의 목록은 최대 100개다. PATCH `items`에는 상한이 없다.
- 이 토픽은 시드에 추천 카드와 처방을 넣지 않는다. 카드는 경고 전환(`auto`)이나 다시 만들기(`manual`)로 처음 생긴다.
