-- 업무 DB(`var/app.db`) 스키마. 테이블·필드 이름과 값 목록은 docs/data-model.md를 따른다.
--
-- - DATE는 `YYYY-MM-DD` TEXT, DATETIME은 로컬 시각 `YYYY-MM-DDTHH:MM:SS` TEXT다.
-- - JSON 필드(conditions, quality_issues, nutrients, basis_values, items, cautions)는 TEXT다.
-- - 열거값은 CHECK로 막는다. NULL을 허용하는 열은 `x IN (...)`이 NULL이면 통과한다.
-- - 사진과 끼니는 서로 참조하므로 그 외래 키는 DEFERRABLE INITIALLY DEFERRED로 건다.
-- - BEGIN·COMMIT은 넣지 않는다. 트랜잭션은 `create_schema(begin=True)`가 연다.
-- - 칸별 섭취의 칸 무결성 트리거는 별도 Story에서 추가한다.

-- 1. 환자 --------------------------------------------------------------------

CREATE TABLE patients (
    patient_id        TEXT NOT NULL PRIMARY KEY,
    display_name      TEXT NOT NULL,
    room              TEXT,
    sex               TEXT NOT NULL CHECK (sex IN ('female', 'male')),
    birth_year        INTEGER NOT NULL,
    height_cm         REAL,
    default_diet_type TEXT NOT NULL,
    conditions        TEXT NOT NULL DEFAULT '[]',
    diet_restrictions TEXT NOT NULL DEFAULT '',
    ckd_dialysis      TEXT NOT NULL CHECK (ckd_dialysis IN ('none', 'ckd', 'dialysis')),
    observation_start TEXT NOT NULL,
    data_source       TEXT NOT NULL CHECK (data_source IN ('mock', 'upload'))
);

CREATE TABLE patient_weights (
    patient_id  TEXT NOT NULL REFERENCES patients (patient_id),
    measured_on TEXT NOT NULL,
    weight_kg   REAL NOT NULL,
    PRIMARY KEY (patient_id, measured_on)
);

CREATE TABLE patient_targets (
    patient_id     TEXT NOT NULL REFERENCES patients (patient_id),
    effective_from TEXT NOT NULL,
    energy_kcal    REAL NOT NULL,
    protein_g      REAL NOT NULL,
    source         TEXT NOT NULL CHECK (source IN ('team_set', 'espen_weight', 'kdri')),
    note           TEXT,
    PRIMARY KEY (patient_id, effective_from)
);

CREATE TABLE patient_assessments (
    patient_id  TEXT NOT NULL REFERENCES patients (patient_id),
    assessed_on TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN (
        'mna_sf', 'nutrition_screening', 'swallowing', 'chewing',
        'appetite_assist', 'pressure_injury', 'refeeding_risk'
    )),
    result      TEXT,
    score       REAL,
    note        TEXT,
    PRIMARY KEY (patient_id, assessed_on, kind)
);

-- 2. 예정 식단 ---------------------------------------------------------------

CREATE TABLE meal_plans (
    meal_plan_id      TEXT NOT NULL PRIMARY KEY,
    date              TEXT NOT NULL,
    meal              TEXT NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'dinner')),
    diet_type         TEXT NOT NULL,
    baseline_photo_id TEXT REFERENCES photos (photo_id) DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (date, meal, diet_type)
);

-- 미배식 칸: menu_name IS NULL, served_g = 0, energy_kcal = 0, protein_g = 0 을 함께만 쓴다.
CREATE TABLE meal_plan_slots (
    meal_plan_id TEXT NOT NULL REFERENCES meal_plans (meal_plan_id),
    slot_id      TEXT NOT NULL,
    position     TEXT NOT NULL,
    dish_type    TEXT NOT NULL CHECK (dish_type IN ('rice', 'soup', 'main', 'side', 'kimchi')),
    menu_name    TEXT,
    served_g     REAL NOT NULL CHECK (served_g >= 0),
    energy_kcal  REAL NOT NULL,
    protein_g    REAL NOT NULL,
    PRIMARY KEY (meal_plan_id, slot_id),
    CHECK ((served_g = 0) = (menu_name IS NULL)),
    CHECK (served_g <> 0 OR (energy_kcal = 0 AND protein_g = 0))
);

-- 3. 실제 발주된 식사 --------------------------------------------------------

CREATE TABLE meal_orders (
    meal_order_id     TEXT NOT NULL PRIMARY KEY,
    patient_id        TEXT NOT NULL REFERENCES patients (patient_id),
    meal_plan_id      TEXT NOT NULL REFERENCES meal_plans (meal_plan_id),
    diet_category     TEXT,
    diet_code         TEXT,
    order_status      TEXT NOT NULL CHECK (order_status IN ('ordered', 'npo', 'cancelled')),
    order_from        TEXT,
    order_note        TEXT,
    record_status     TEXT CHECK (record_status IN (
        'not_recorded', 'pending', 'recorded', 'not_determinable', 'failed'
    )),
    post_photo_id     TEXT REFERENCES photos (photo_id) DEFERRABLE INITIALLY DEFERRED,
    staff_zero_reason TEXT CHECK (staff_zero_reason IN ('refused', 'not_eaten')),
    energy_kcal_est   REAL,
    protein_g_est     REAL,
    incomplete        INTEGER NOT NULL DEFAULT 0 CHECK (incomplete IN (0, 1)),
    data_source       TEXT NOT NULL CHECK (data_source IN ('mock', 'upload')),
    UNIQUE (patient_id, meal_plan_id)
);

CREATE INDEX idx_meal_orders_patient_id ON meal_orders (patient_id);
CREATE INDEX idx_meal_orders_meal_plan_id ON meal_orders (meal_plan_id);

-- slot_id가 배식 계획의 배식 칸인지는 트리거로 보장한다(meal_plan_id 열이 없어 복합 FK 불가).
CREATE TABLE slot_intakes (
    meal_order_id       TEXT NOT NULL REFERENCES meal_orders (meal_order_id),
    slot_id             TEXT NOT NULL,
    intake_fraction_est REAL CHECK (
        intake_fraction_est IS NULL OR (intake_fraction_est >= 0 AND intake_fraction_est <= 1)
    ),
    status              TEXT NOT NULL CHECK (status IN ('estimated', 'not_determinable')),
    quality_issues      TEXT NOT NULL DEFAULT '[]',
    -- `vlm:<어댑터>` / staff / mock. GLOB은 대소문자를 구분한다.
    estimate_basis      TEXT NOT NULL CHECK (
        estimate_basis IN ('mock', 'staff') OR estimate_basis GLOB 'vlm:?*'
    ),
    PRIMARY KEY (meal_order_id, slot_id)
);

-- 4. 사진 --------------------------------------------------------------------

CREATE TABLE photos (
    photo_id      TEXT NOT NULL PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('baseline', 'post')),
    meal_plan_id  TEXT NOT NULL
        REFERENCES meal_plans (meal_plan_id) DEFERRABLE INITIALLY DEFERRED,
    meal_order_id TEXT
        REFERENCES meal_orders (meal_order_id) DEFERRABLE INITIALLY DEFERRED,
    uploader_role TEXT NOT NULL CHECK (uploader_role IN ('dietitian', 'caregiver')),
    file_path     TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN (
        'uploaded', 'waiting_baseline', 'queued', 'analyzing', 'done',
        'not_determinable', 'failed'
    )),
    stage         TEXT CHECK (stage IN ('intake', 'nutrition', 'alert', 'recommendation')),
    outcome       TEXT CHECK (outcome IN ('no_change', 'alert_changed', 'warning_raised')),
    error         TEXT,
    uploaded_at   TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    data_source   TEXT NOT NULL CHECK (data_source IN ('mock', 'upload'))
);

CREATE INDEX idx_photos_status ON photos (status);

-- 5. 환자 기준으로 쌓이는 데이터 ---------------------------------------------

-- 기록된 끼니가 없는 날은 섭취량과 %가 NULL이다.
CREATE TABLE daily_intakes (
    patient_id       TEXT NOT NULL REFERENCES patients (patient_id),
    date             TEXT NOT NULL,
    energy_kcal      REAL,
    protein_g        REAL,
    energy_pct       REAL,
    protein_pct      REAL,
    recorded_meals   INTEGER NOT NULL,
    unrecorded_meals INTEGER NOT NULL,
    npo_meals        INTEGER NOT NULL,
    PRIMARY KEY (patient_id, date)
);

CREATE TABLE alerts (
    alert_id         TEXT NOT NULL PRIMARY KEY,
    patient_id       TEXT NOT NULL REFERENCES patients (patient_id),
    evaluated_at     TEXT NOT NULL,
    level            TEXT NOT NULL CHECK (level IN ('none', 'caution', 'warning')),
    basis_period     TEXT,
    basis_values     TEXT,
    nutrients        TEXT NOT NULL DEFAULT '[]',
    unrecorded_meals INTEGER NOT NULL
);

CREATE INDEX idx_alerts_patient_evaluated_at ON alerts (patient_id, evaluated_at);

CREATE TABLE chat_threads (
    thread_id  TEXT NOT NULL PRIMARY KEY,
    patient_id TEXT NOT NULL REFERENCES patients (patient_id),
    created_at TEXT NOT NULL,
    title      TEXT
);

CREATE TABLE recommendations (
    recommendation_id TEXT NOT NULL PRIMARY KEY,
    patient_id        TEXT NOT NULL REFERENCES patients (patient_id),
    alert_id          TEXT REFERENCES alerts (alert_id),
    items             TEXT NOT NULL,
    cautions          TEXT NOT NULL DEFAULT '[]',
    last_modified_by  TEXT NOT NULL CHECK (last_modified_by IN ('agent', 'chat', 'doctor')),
    thread_id         TEXT REFERENCES chat_threads (thread_id),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN (
        'active', 'superseded', 'confirmed', 'failed'
    ))
);

CREATE INDEX idx_recommendations_patient_status ON recommendations (patient_id, status);

CREATE TABLE prescriptions (
    prescription_id   TEXT NOT NULL PRIMARY KEY,
    patient_id        TEXT NOT NULL REFERENCES patients (patient_id),
    recommendation_id TEXT REFERENCES recommendations (recommendation_id),
    items             TEXT NOT NULL,
    confirmed_at      TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('confirmed'))
);

-- 6. 시드 메타 ---------------------------------------------------------------

-- schema_version, demo_date, seeded_at, (정리 전까지만) cleanup_pending
CREATE TABLE seed_meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT
);
