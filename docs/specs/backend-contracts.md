# 백엔드 골격과 병행 트랙 계약

> `backend/` FastAPI 골격, 병행 트랙이 구현할 계약 4종, 계약별 Fake 구현과 계약 테스트, 설정으로 구현을 바꾸는 방법 (팀 제안안 기준).

## 개요

하루 파일럿의 백엔드는 프로세스 하나(FastAPI)로 동작한다. 이 골격은 비전 인식(VLM)·판단 알고리즘·가이드라인 검색(RAG)·업무 저장소(T4)를 각자 구현하는 병행 트랙이 같은 계약을 보고 시작하도록 계약 4종을 고정한다. 각 계약에는 실행 중 더미로 쓰는 Fake 구현과, 구현별 하위 클래스가 픽스처만 바꿔 상속하는 계약 테스트가 붙어 있다. 앱은 시작할 때 설정값으로 네 구현을 골라 `app.state`에 둔다.

이름·단위·상태 값은 `docs/data-model.md`를 정본으로 따른다.

## 구조 / 스키마

```
backend/
  pyproject.toml · uv.lock · .python-version (3.12)
  app/
    main.py                          create_app(settings=None), GET /api/health, lifespan(앱 잠금·자동 시드)
    config.py                        Settings, ConfigError, StoragePaths, resolve_demo_date()
    wiring.py                        계약별 이름 등록부, build_components()
    intake/types.py                  IntakeEstimator 계약
    intake/fake.py                   FakeEstimator
    nutrition/types.py               NutritionEngine 계약
    nutrition/fake.py                FakeNutritionEngine
    recommender/guideline_types.py   GuidelineSearch 계약
    recommender/fake_guideline.py    FakeGuidelineSearch
    services/ports.py                PatientDataPort 계약, 추천 카드 타입, 포트 예외
    services/fake_patient_data.py    FakePatientData
    storage/                         SQLite 저장소·시드·리셋 (docs/specs/storage-seed.md)
  scripts/seed.py                    리셋 CLI
  tests/
    conftest.py                      설정 환경 변수 고정
    contracts/{intake,nutrition,guideline,patient_data}.py   계약 테스트 기반 클래스
    test_fake_*.py                   Fake별 계약 하위 클래스 + Fake 전용 테스트
    test_config.py · test_wiring.py · test_health.py
```

### 공통 규칙

- 모든 레코드는 `@dataclass(frozen=True)`, 컬렉션 필드는 `tuple`, 열거값은 소문자 값의 `StrEnum`이다.
- 단위는 이름에 붙인다(`_kcal`, `_g`, `_ms`, `_s`). `_fraction`은 0~1 비율, `_pct`는 0 이상 백분율(상한 없음)이다.
- 도메인 처리 결과(판단 불가 등)는 `status` 값으로, 외부 호출 실패는 `EstimationError`, 포트 조회 실패는 `PatientDataError` 계층, 설정 오류는 `ConfigError`, 잘못된 인자는 `ValueError`로 표현한다.

### 계약 4종

| 계약 | 형태 | 파일 |
| --- | --- | --- |
| `IntakeEstimator` | `name: str`, async `estimate(EstimationRequest) -> EstimationResult` | `app/intake/types.py` |
| `NutritionEngine` | 동기 순수 메서드 `meal_nutrients`·`daily_target`·`daily_intake`·`evaluate_alert` | `app/nutrition/types.py` |
| `GuidelineSearch` | async `search(query, limit=5) -> tuple[GuidelineHit, ...]` | `app/recommender/guideline_types.py` |
| `PatientDataPort` | async `get_intake_summary(patient_id, days, on)`·`get_recommendation(patient_id)`·`update_recommendation(recommendation_id, items, modified_by, thread_id)` | `app/services/ports.py` |

- **섭취 추정**: `SlotSpec`, `EstimationRequest`, `SlotStatus`(`estimated`/`not_determinable`), `QualityIssue`(`blur`/`occluded`/`angle`/`lighting`/`tray_mismatch`), `SlotEstimate`, `EstimationResult`, `EstimationError`. 필드는 `docs/system-architecture.md` 5절과 같다.
- **판단 알고리즘**: 열거형 7종(`Sex`, `TargetSource`, `MealType`, `OrderStatus`, `RecordStatus`, `AlertLevel`, `Nutrient`)과 레코드 12종(`SlotIntake`, `SlotNutrition`, `MealNutrients`, `PatientProfile`, `TargetRecord`, `WeightRecord`, `DailyTarget`, `MealRecord`, `DailyIntake`, `AlertRules`, `AlertResult`, `NutrientEvidence`). `AlertRules` 기본값은 75.0 % / 7일 / 50.0 % / 5일이다. 입력을 고치지 않고 외부 호출을 하지 않는다.
- **가이드라인 검색**: `GuidelineHit(doc_id, section, text, source_url)`. `doc_id`·`section`은 추천 항목 `evidence`와 같은 값이다.
- **환자 데이터 포트**: 열거형 `PrescriptionType`(7종, `docs/data-model.md` 6절), `AddedBy`, `ModifiedBy`, `RecommendationStatus`. 레코드 `IntakeSummary`, `LeftMenu`, `RecommendationItem`, `EvidenceRef`, `RecommendationCard`. 예외 `PatientNotFoundError`, `RecommendationNotFoundError`, `RecommendationNotEditableError`(공통 기반 `PatientDataError`).

## 동작

### 환자 데이터 포트 규칙

- `get_recommendation`: 상태가 `active` 또는 `failed`인 카드 중 `created_at`이 가장 늦은 것을 돌려준다. 시각이 같으면 `recommendation_id`가 사전순으로 큰 것을 고른다(상태 우선순위 없음). `confirmed`·`superseded`는 고르지 않는다. 후보가 없으면 `None`, 환자가 없으면 `PatientNotFoundError`.
- `get_intake_summary`: 기간은 `[on - (days - 1)일, on]`이다. `daily`는 기간 안에 발주가 있는 날만 오래된 날부터 담는다. `alert`는 판정일이 `on` 이하인 판정 중 가장 최근 것이고, 없으면 `None`이다. `days < 1`이면 `ValueError`.
- `update_recommendation`: 카드 없음 → `RecommendationNotFoundError`, `active`가 아님 → `RecommendationNotEditableError`, 규칙 위반 → `ValueError`. 규칙은 `modified_by = chat`이면 `thread_id`가 있어야 하고 `agent`·`doctor`이면 `None`이어야 하며, 카드 안 `item_id`가 유일해야 한다는 것이다. 바뀌는 필드는 `items`, `last_modified_by`, `thread_id`, `updated_at`뿐이고, 거부된 수정은 카드를 바꾸지 않는다.

### Fake 구현

| Fake | 동작 |
| --- | --- |
| `FakeEstimator(scenarios=None, delay_s=0.0)` | `meal_order_id`별 시나리오(`success`/`slot_not_determinable`/`image_not_determinable`/`error`)대로 결과를 낸다. 기본은 성공이며 칸 순서대로 비율 1.0, 0.8, 0.5, 0.3, 0.0, 0.6을 반복한다. `estimate_basis = "vlm:fake"`. `delay_s`만큼 `asyncio.sleep`한다. |
| `FakeNutritionEngine()` | `daily_target`은 항상 1,500 kcal·55 g·`kdri`, `evaluate_alert`는 항상 `none`. `meal_nutrients`·`daily_intake`는 계약을 지키는 최소 계산만 한다(기준 구현이 아니다). |
| `FakeGuidelineSearch()` | 질의와 무관하게 고정 구절 3개(`espen_geriatrics` R20·R23, `kjg_elderly_nutrition_2019`) 중 앞에서 `limit`개를 돌려준다. |
| `FakePatientData(clock=None, cards=None)` | 환자 4명(`NS01`~`NS04`)과 카드 7장의 고정 배치를 메모리에 둔다. 인스턴스마다 저장소를 새로 만들고 수정할 때 새 카드 객체로 바꿔 둔다. `cards`로 초기 카드를 주입할 수 있다(`default_cards()`, `late_failed_cards()`). |

### 계약 테스트

`tests/contracts/<name>.py`의 `*Contract` 기반 클래스는 모든 구현이 지켜야 하는 불변 조건만 검사한다. 새 구현은 테스트 파일에서 하위 클래스를 만들고 픽스처만 정의한다. 하위 클래스 이름에는 기반 클래스 이름 전체를 넣지 않는다(예: `TestFakeNutritionContract`).

| 계약 클래스 | 하위 클래스가 정의할 픽스처 | 덮어쓸 수 있는 기본 픽스처 |
| --- | --- | --- |
| `IntakeEstimatorContract` | `estimator` | `estimation_request`(합성 PNG 2장 + 6칸 배치) |
| `NutritionEngineContract` | `engine` | 칸·끼니·목표·이력 샘플 (`build_*` 함수로도 공개) |
| `GuidelineSearchContract` | `search` | `query` |
| `PatientDataPortContract` | `port`, `port_fixture: PortFixture`, `late_failed_port`, `late_failed: LateFailedFixture` | — |

`PortFixture`는 스펙 §3.4 배치(환자 4명, 카드 7장)의 ID·날짜를 알려 준다. 여기에는 기간·기준일을 바꾼 대체 입력(`alt_summary_days`, `alt_summary_on`과 기대값)과 채팅 수정에 쓸 `chat_thread_id`가 들어 있다. T4 저장소 구현은 테스트 DB에 같은 배치를 넣고, `chat_threads` 행 하나를 시드해 그 ID를 넘긴다.

외부 API를 부르는 실제 구현의 하위 클래스는 외부 응답을 `monkeypatch`·`unittest.mock`으로 모의한다. 실제 네트워크 호출은 평가 스크립트에서 확인한다.

### 구현 전환

1. `Settings`가 환경 변수와 `backend/.env`(실행 위치와 무관한 경로)에서 값을 읽는다. 환경 변수가 우선한다.

   | 설정(환경 변수) | 기본값 | 등록부 | `app.state` 속성 |
   | --- | --- | --- | --- |
   | `INTAKE_ADAPTER` | `fake` | `INTAKE_ESTIMATORS` | `intake_estimator` |
   | `NUTRITION_ENGINE` | `fake` | `NUTRITION_ENGINES` | `nutrition_engine` |
   | `GUIDELINE_SEARCH` | `fake` | `GUIDELINE_SEARCHES` | `guideline_search` |
   | `PATIENT_DATA` | `fake` | `PATIENT_DATA_PORTS` | `patient_data` |
   | `FAKE_INTAKE_DELAY_S` | `2.0` (0 이상) | — | `FakeEstimator.delay_s` |

   저장소 경로와 시연일 설정(`VAR_DIR`, `SEED_PATH`, `DEMO_DATE`)은 `docs/specs/storage-seed.md`에 정리했다.

2. `create_app()`이 `build_components(settings)`로 네 구현을 만들어 `app.state`에 둔다. 등록되지 않은 이름이면 설정 이름과 값을 담은 `ConfigError`를 던진다.
3. 실제 구현은 `app/wiring.py`의 해당 등록부에 `이름 → 생성 함수(Settings)`로 추가한다. 생성 함수 안에서 구현 모듈을 import해, 그 이름이 선택됐을 때만 SDK·색인을 읽게 한다.

   ```python
   def _build_vlm_estimator(settings: Settings) -> IntakeEstimator:
       from app.intake.vlm import VlmEstimator  # 선택됐을 때만 로드

       return VlmEstimator(...)
   ```

4. 테스트는 `monkeypatch.setitem(wiring.<등록부>, "alt", factory)`로 대체 구현을 등록한다. `tests/conftest.py`가 설정 환경 변수를 기본값으로 고정하므로, 설정을 추가하면 `SETTING_ENV_DEFAULTS`에도 넣는다.

### 실행

```bash
cd backend
uv sync --locked
uv run ruff check && uv run ruff format --check
uv run pytest --cov=app
uv run fastapi dev        # http://127.0.0.1:8000/api/health → 200 (var/app.db가 없으면 시드를 적재한다)
uv run python -m scripts.seed   # 앱을 끈 상태에서 DB 리셋
```

## 제약사항

- Python 3.12 계열만 지원한다(`requires-python = ">=3.12,<3.13"`). 의존성 버전은 `uv.lock`으로 고정한다.
- HTTP 엔드포인트는 `GET /api/health`뿐이다. SQLite 저장소와 시드는 있지만(`docs/specs/storage-seed.md`) 업무 API, 이벤트·SSE, 에이전트, 실제 VLM·영양 규칙·가이드라인 검색, 프론트엔드는 후속 토픽과 병행 트랙에서 붙인다.
- 접근 제어와 rate limiting이 없다(파일럿 전제). 서버는 기본 호스트 `127.0.0.1`로 띄운다.
- `EstimationRequest`의 이미지 경로는 계약 단계에서 검증하지 않는다. 사진을 실제로 여는 구현(VLM 어댑터·업로드 API)은 경로가 `var/photos/` 안인지 확인하고 이미지 내용을 검증해야 한다.
- 타입 검사기(mypy·pyright), CI, Docker는 쓰지 않는다.
- Fake 데이터는 모의 환자만 쓴다. 판정 수준은 계약 검증용 고정 배치 값이며 `AlertRules`로 계산한 값이 아니다.
