# SQLite 저장소와 시드 적재

> `var/app.db` SQLite 스키마, `app/storage/` 접근 층, `demo_seed.json` 적재, 앱을 끈 상태의 CLI 리셋, 앱 시작 때 자동 시드 (팀 제안안 기준).

## 개요

업무 데이터는 SQLite 파일 하나(`var/app.db`)에 둔다. 빈 상태에서 앱을 시작하거나 CLI를 한 번 실행하면 시드 파일(`data/seed/demo_seed.json`)이 시연일 D 기준 절대 날짜·ID로 바뀌어 들어간다. 이때 파생 테이블(`daily_intakes`, `alerts`)도 설정된 `NutritionEngine`으로 계산해 넣는다. 시연 중에는 앱을 끈 뒤 CLI 리셋으로 같은 시작 상태로 되돌린다.

후속 토픽(사진 흐름·환자 API·대화)은 이 스키마와 연결 규칙 위에 자기 조회·쓰기 함수를 더한다. 테이블·필드 이름과 상태 값은 `docs/data-model.md`를 정본으로 따른다.

## 구조 / 스키마

```
backend/
  app/
    config.py              Settings(var_dir · seed_path · demo_date), StoragePaths, resolve_demo_date()
    main.py                lifespan: 시연일 형식 검사 → 앱 잠금 → ensure_storage → 이벤트 버스 루프 연결 → 앱 시계 고정 → (종료) 런타임 종료 → 잠금 해제
    storage/
      schema.sql           CREATE TABLE·INDEX·TRIGGER 전체
      db.py                connect(), create_schema(), SCHEMA_VERSION
      records.py           조회 결과 frozen dataclass
      queries.py           시드 대상 조회 함수
      codec.py             JSON TEXT 열의 인코딩·디코딩 짝
      photos.py            new_photo_id(), save_photo_bytes(), clear_photos()
      errors.py            저장소·시드·리셋 오류
      app_lock.py          AppLock: var/app.lock 배타 잠금 (앱·CLI 공용)
      seed_models.py       demo_seed.json Pydantic 검증 모델
      seed_file.py         load_seed_file(), check_demo_date_range()
      seed_load.py         build_database(), build_engine()
      seed_derived.py      파생 테이블 계산
      seed_reset.py        rebuild_storage(), reset_storage(), finish_cleanup(), ensure_storage()
      seed.py              위 진입점을 다시 내보낸다 (CLI·lifespan이 여기서 import)
  scripts/seed.py          리셋 CLI
var/                       (git 제외) app.db · checkpoints.db · photos/ · app.lock
```

### 설정

| 설정(환경 변수) | 기본값 | 의미 |
| --- | --- | --- |
| `VAR_DIR` | `<저장소 루트>/var` | 실행 중 생기는 파일의 루트. 상대 경로는 저장소 루트 기준, `~`는 펼친다 |
| `SEED_PATH` | `<저장소 루트>/data/seed/demo_seed.json` | 시드 원본. 경로 규칙은 `VAR_DIR`와 같다 |
| `DEMO_DATE` | 없음 | 시연일 D(`YYYY-MM-DD`) |

- 시연일 우선순위는 CLI `--demo-date` → `DEMO_DATE` → 그날 로컬 날짜다. 앱 시작은 뒤의 둘만 쓴다.
- 입력한 시연일이 `YYYY-MM-DD` 실제 날짜가 아니면 DB 작업과 잠금 전에 `ConfigError("시연일 형식이 잘못됐다(YYYY-MM-DD)")`로 실패한다.
- `StoragePaths(app_db, checkpoints_db, photos_dir, app_lock)`는 `var_dir`에서 계산하고, 경로만 계산할 뿐 파일을 만들지 않는다.

### 테이블

- **업무 14개**: `patients`, `patient_weights`, `patient_targets`, `patient_assessments`, `meal_plans`, `meal_plan_slots`, `meal_orders`, `slot_intakes`, `photos`, `daily_intakes`, `alerts`, `chat_threads`, `recommendations`, `prescriptions`
- **운영 1개**: `seed_meta`(`key TEXT PK, value TEXT`)

| 항목 | 규칙 |
| --- | --- |
| 날짜·시각 | DATE는 `YYYY-MM-DD`, DATETIME은 로컬 `YYYY-MM-DDTHH:MM:SS` TEXT |
| JSON 열 | `conditions`, `quality_issues`, `nutrients`, `basis_values`, `items`, `cautions`. 읽고 쓰는 형식은 `codec.py` 한 곳에 둔다 |
| 열거값 | data-model.md 값 목록으로 CHECK. `estimate_basis`는 `mock`·`staff`·`vlm:%`만 허용 |
| 범위 | `intake_fraction_est`는 NULL 또는 0~1. `meal_plan_slots`는 `served_g >= 0`이고, `served_g = 0`과 `menu_name IS NULL`이 함께 성립한다(미배식 칸). 미배식 칸은 열량·단백질이 0이다 |
| 기본 키 | 이력 테이블은 복합 키: `patient_weights(patient_id, measured_on)`, `patient_targets(patient_id, effective_from)`, `patient_assessments(patient_id, assessed_on, kind)` |
| 유일 제약 | `meal_plans(date, meal, diet_type)`, `meal_orders(patient_id, meal_plan_id)` |
| 사진 참조 | `meal_plans`·`meal_orders` ↔ `photos`는 서로 참조하므로 `DEFERRABLE INITIALLY DEFERRED` 외래 키 |
| 인덱스 | `meal_orders(patient_id)`, `meal_orders(meal_plan_id)`, `alerts(patient_id, evaluated_at)`, `recommendations(patient_id, status)`, `photos(status)` |
| `seed_meta` | `schema_version`, `demo_date`, `seeded_at`(실제 적재 시각). `cleanup_pending`은 교체 뒤 정리를 마치기 전까지만 있다 |

**칸별 섭취의 칸 트리거.** `slot_intakes`에는 `meal_plan_id` 열이 없어 복합 외래 키 대신 트리거로 같은 보장을 만든다.
- `slot_intakes` 삽입·`meal_order_id`/`slot_id` 변경: 발주의 배식 계획에 없는 칸이나 미배식 칸이면 거절한다.
- `meal_orders.meal_plan_id`의 변경과 `meal_plan_slots`의 키 변경은 거절한다. `INSERT OR REPLACE` 경로도 포함한다.
- 칸별 섭취가 있는 칸은 미배식(`served_g = 0`)으로 바꾸거나 삭제할 수 없다.

## 동작

### 연결

`connect(db_path, *, journal_mode="WAL", checkpoint_on_close=True)`는 컨텍스트 매니저다.
- 열 때 `journal_mode`(`WAL` 또는 `DELETE`), `foreign_keys=ON`, `busy_timeout=5000`, `row_factory=sqlite3.Row`를 맞춘다.
- 블록이 끝나면 커밋하고, 예외가 나면 롤백한 뒤 다시 던진다. 커밋 때 지연 외래 키 위반도 예외로 넘긴다.
- 저장소 함수는 동기 함수이고, 작업 단위마다 짧게 연결한다.

### 조회 함수 (`queries.py`)

모든 함수는 첫 인자로 연결을 받고(`demo_timestamp` 제외), frozen dataclass와 `tuple`을 돌려준다. JSON 열은 파싱하고, 열거값은 기존 `StrEnum`으로 바꾼다. 기간 인자는 양 끝을 포함한다.

| 함수 | 돌려주는 것 |
| --- | --- |
| `get_demo_date(conn)` | `seed_meta.demo_date`. 후속 서비스는 "오늘"을 이 값으로 읽는다 |
| `demo_timestamp(demo_date, now)` | `<demo_date>T<now의 시:분:초>`. 시연 중 판정·기록 시각 |
| `list_patients(conn)` / `get_patient(conn, patient_id)` | `patient_id` 순 / 없으면 `None` |
| `get_patient_history(conn, patient_id)` | 체중·목표·평가 이력, 날짜 오름차순 |
| `get_meal_plan(conn, on, meal, diet_type="general")` | 칸 6개, `slot_id` 순 |
| `list_meal_orders(conn, patient_id, start, end)` | 날짜·끼니 순, 칸별 섭취 포함 |
| `list_daily_intakes(conn, patient_id, start, end)` | 날짜 오름차순 |
| `list_alerts(conn, patient_id, start, end)` | `evaluated_at` 오름차순, 같으면 `alert_id` 순. 기간은 판정일(날짜 부분) 기준 |
| `get_latest_alert(conn, patient_id, on)` | 판정일이 `on` 이하인 최신 판정(`evaluated_at`, 같으면 `alert_id`가 큰 것), 없으면 `None` |
| `get_alert(conn, patient_id, alert_id)` | 그 환자의 판정. 없거나 다른 환자의 판정이면 `None` |
| `list_left_menu_candidates(conn, patient_id, start, end, *, min_meals, max_avg_fraction, limit)` | 기간 안 `recorded` 발주의 메뉴별 평균 섭취 비율·끼니 수(`LeftMenu`). 끼니 수 `min_meals` 이상·평균 `max_avg_fraction` 이하만, 평균 오름차순 → 끼니 수 내림차순 → `menu_name` 순으로 최대 `limit`개 |

추천 카드·처방 SQL은 `storage/recommendations.py`, 추천 항목 JSON 변환은 `storage/codec.py`에 있다(`docs/specs/patient-recommendation-api.md`).

### 사진 파일 (`photos.py`)

- `new_photo_id()`는 `ph_` + `uuid4().hex`를 만든다.
- `save_photo_bytes(photos_dir, photo_id, data)`는 다음 순서로 저장한다.
  1. `photo_id`가 `ph_[0-9a-f]{32}`가 아니면 `ValueError`를 던진다.
  2. `resolve()`로 최종 경로가 `photos_dir` 안인지 확인한다.
  3. 임시 파일에 쓴 뒤 `os.replace`로 `<photo_id>.jpg`로 옮긴다.
- `clear_photos(photos_dir)`는 디렉토리 바로 아래의 파일과 심볼릭 링크만 지운다. 하위 디렉토리는 건드리지 않고, 링크는 따라가지 않는다.
- 이미지 내용 검증과 크기 상한은 업로드 API가 맡는다.

### 시드 적재

1. `load_seed_file(path)`가 JSON을 읽어 Pydantic 모델(`extra="forbid"`)로 형태를 검증한다. 이어서 관계를 검증한다. 대상은 ID 중복, 발주의 환자·배식 계획 참조, 칸별 섭취의 칸이 계획에 있고 미배식 칸이 아닌지다.
2. `check_demo_date_range(seed, demo_date)`가 오프셋을 더한 날짜와 출생 연도가 `date` 범위(1~9999년) 안인지 확인한다.
3. `build_database(db_path, seed, demo_date, engine)`가 한 트랜잭션으로 넣는다. 순서는 원본 테이블 → 파생 테이블 → `seed_meta`다.

| 시드 필드 | 저장 값 |
| --- | --- |
| `*_offset` | `demo_date + offset일` |
| 배식 계획 ID | `<날짜>_<meal>_<diet_type>` (예: `2026-11-20_breakfast_general`) |
| 발주 ID | `<patient_id>_<날짜>_<meal>` (예: `NS01_2026-11-20_breakfast`) |
| `age_at_d0` | `birth_year = demo_date.year - age_at_d0` |
| `order_from_offset` | `"<날짜> <끼니>"`, 끼니가 없으면 `breakfast` |
| 금식 발주의 `record_status: null` | `not_recorded` |
| `source_note` | 버린다 |
| `energy_kcal_est`·`protein_g_est`·`incomplete` | 시드 값 그대로 |

**파생 테이블.** 환자별로 관찰 시작일부터 D-1까지 각 날짜 `d`에 대해 계산한다. 현재 시드는 모든 환자가 D-7에 시작한다.
- `daily_intakes`: `engine.daily_target(..., on=d)`로 목표를 구하고, `engine.daily_intake(d, meals, target)`로 섭취를 계산한다.
- `alerts`: `engine.evaluate_alert(history[≤d], AlertRules(), on=d)`로 하루 한 행을 만든다. 각 행의 값은 다음과 같다.
  - `alert_id = "alert_<patient_id>_<d>"`
  - `evaluated_at = "<d>T23:59:59"`
- D0에는 일별 섭취·경고를 만들지 않는다. D0에 있는 것은 배식 계획과 발주(`not_recorded`·`npo`)뿐이다.
- 엔진은 `NUTRITION_ENGINE` 설정으로 고른다. 엔진을 바꾸면 리셋만 다시 하면 된다.

### 앱 잠금

`AppLock(path)`는 `var/app.lock`에 `fcntl.flock(LOCK_EX | LOCK_NB)`를 잡는다. 이미 다른 프로세스가 쥐고 있으면 `AppLockedError`를 던진다. 프로세스가 죽으면 잠금이 풀리므로 따로 지울 파일이 없다.

| 쥐는 쪽 | 잡는 때 | 놓는 때 | 잡지 못하면 |
| --- | --- | --- | --- |
| 앱 | lifespan 시작(시연일 형식 검사 뒤) | lifespan 종료. 런타임 종료(앱 소유 태스크 취소 → 실행 중인 DB 쓰기 완료 대기) 뒤 | 시작 실패 |
| CLI 리셋 | 리셋 시작 | 리셋 종료 | 종료 코드 1, DB를 건드리지 않음 |

DB를 직접 여는 외부 도구(sqlite3 셸, DB 브라우저)는 리셋 중에 열지 않는 것을 운영 전제로 둔다.

### 리셋 절차 (`rebuild_storage`)

앱 잠금을 쥔 상태에서만 부른다.

1. **준비**
   - 시드를 검증하고 시연일 범위를 확인한다.
   - 이전 실행이 남긴 `app.db.tmp`와 그 보조 파일(`-journal`, `-wal`, `-shm`)을 지운다.
   - `app.db.tmp`에 `journal_mode=DELETE`로 스키마와 시드를 만든다. `seed_meta.cleanup_pending = 1`도 함께 넣는다.
2. **기존 WAL 반영:** 기존 `app.db`가 있으면 `PRAGMA wal_checkpoint(TRUNCATE)`를 실행한다.
   - 결과가 `busy == 0`이고 `log == checkpointed`일 때만 연결을 닫고 `app.db-wal`·`app.db-shm`을 지운다.
   - 결과가 그렇지 않으면 `ResetBusyError`를 던진다.
3. **교체**
   - 본체 없이 남은 `app.db-wal`·`app.db-shm`이 있으면 먼저 지운다.
   - `os.replace(app.db.tmp, app.db)`로 교체한다. 기존 `app.db`를 미리 지우지 않는다.
4. **정리** (`finish_cleanup`)
   - `checkpoints.db`(+보조 파일)와 사진 파일을 모두 삭제 시도한다.
   - 둘 다 성공하면 `cleanup_pending`을 지운다.
   - 하나라도 실패하면 표시를 남긴 채 실패 항목을 담은 `ResetCleanupError`를 던진다.
   - 없는 파일 삭제는 성공으로 치므로, 다시 실행해도 안전하다.
5. `ResetResult(demo_date, patients, meal_orders, daily_intakes, alerts)` 행 수를 돌려준다.

1~3단계에서 실패하면 기존 DB는 리셋 전과 같은 데이터로 남는다. `finally`에서 임시 파일 삭제를 시도하고, 원래 예외를 다시 던진다.

| 오류 | 단계 | 원인 |
| --- | --- | --- |
| `SeedError` | 1 | 형태·관계 검증 실패, 적재 중 `IntegrityError` |
| `DemoDateRangeError` (`ConfigError` 하위) | 1 | 시연일 + 오프셋이 날짜 범위를 벗어남 |
| `StoragePrepareError` | 1~3 | 파일 시스템 오류, `IntegrityError`가 아닌 `sqlite3.Error`, 보조 파일 삭제 실패 |
| `ResetBusyError` | 2 | WAL을 모두 반영하지 못함 |
| `StorageReplaceError` | 3 | `os.replace` 실패 |
| `ResetCleanupError` | 4 | 대화 DB·사진·정리 표시 중 실패 항목 |

### 앱 시작 (`ensure_storage`)

lifespan이 앱 잠금을 잡은 뒤에 부른다.

- `app.db`가 없으면 `rebuild_storage` 전체를 실행한다. 남은 사진·`checkpoints.db`·보조 파일·임시 파일도 이때 지운다.
- `app.db`가 있으면 업무 데이터와 남은 `app.db.tmp`를 건드리지 않는다.
  - `cleanup_pending`이 있을 때만 `finish_cleanup`을 다시 실행한다.
  - 그 정리가 실패하면 `ResetCleanupError`로 앱 시작을 멈춘다.
- `DEMO_DATE`가 없고 `seed_meta.demo_date`가 오늘과 다르면 WARNING 로그만 남긴다. 자동으로 리셋하지는 않는다.
- 모듈 수준 `app = create_app()`은 import만으로 잠금을 잡거나 파일을 만들지 않는다.

### 리셋 CLI

```bash
cd backend
uv run python -m scripts.seed [--demo-date YYYY-MM-DD]
```

- 시연일을 정한 뒤 `reset_storage(settings, demo_date=...)`를 실행하고 행 수를 출력한다.
- 알려진 오류는 종료 코드 1과 한국어 안내(표준 오류)로 바꾼다. 대상은 `AppLockedError`, `ConfigError`, `SeedError`, `StoragePrepareError`, `StorageReplaceError`, `ResetBusyError`, `ResetCleanupError`다.
- 시연 중 되돌리기 절차는 다음과 같다: 앱 종료 → `uv run python -m scripts.seed` → 앱 시작 → 화면 다시 불러오기.

### 시연 전 준비

시드의 `daily_intakes`·`alerts`는 적재할 때 설정된 `NUTRITION_ENGINE`으로 계산한다. Fake 엔진은 목표를 1,500 kcal(`kdri`), 경고를 `none`으로 고정한다. 그래서 Fake 엔진으로 시드하면 대표 시연 환자 NS03의 시작 상태가 "주의"가 되지 않는다. 시드 값은 다음과 같다.

- 목표 1,700 kcal(`team_set`)
- D0 아침 배식 698 kcal
- 일별 환산율 D-4 47%, D-3 28%, D-2 21%, D-1 30%. 50% 이하가 4일 연속이다.

실제 영양 엔진이 등록되면 시연 전에 다음 순서로 준비한다.

1. `backend/.env`의 `NUTRITION_ENGINE`을 실제 엔진 이름으로 바꾼다.
2. 앱을 끈다.
3. `uv run python -m scripts.seed`로 리셋한다.
4. 앱을 시작한다.

기존 `app.db`가 있으면 앱 시작만으로는 파생 테이블을 다시 계산하지 않는다. 그래서 3단계 리셋이 필요하다.

## 제약사항

- 리셋은 앱을 끈 상태에서 CLI로만 한다. `POST /api/admin/reset`, 화면의 리셋 버튼, 리셋 이벤트는 없다.
- 스키마 마이그레이션은 없다. 스키마가 바뀌면 리셋한다. 앱 시작은 `seed_meta.schema_version`을 비교하지 않는다.
- 조회 함수는 시드 대상만 있다. 다음은 후속 토픽이 더한다.
  - 사진 상태 전이와 업로드 기록
  - D0 일별 섭취 재계산
  - 추천·처방·스레드 쓰기
  - `SqlitePatientData`
- 배식 계획과 발주는 시드로만 넣는다. 키 변경은 트리거로 막는다.
- `checkpoints.db`는 리셋 때 지우기만 한다. 만드는 일은 대화 체크포인터가 맡는다.
- 파생 테이블 값은 설정된 엔진의 결과다. Fake 엔진에서는 목표 1,500 kcal, 경고 `none`이다.
- 테스트는 `VAR_DIR`를 `tmp_path`로 덮어쓰며, 저장소 경로에 파일을 만들지 않는다.
