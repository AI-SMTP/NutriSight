# NutriSight 영양 계산·경고 알고리즘 구현 가이드

**담당** 조윤서 · **대상** 영양 엔진 구현 및 백엔드 연동 팀원  
**기준 브랜치** [AI-SMTP/NutriSight `develop`](https://github.com/AI-SMTP/NutriSight/tree/develop)  
**보완** 2026-11-29 — 65세 미만 목표값, 끼니·판정 경계 규칙, 현재 시드 기준 NS03 검산, 연동 현황을 반영했다. 바뀐 곳은 각 절의 "보완" 표시로 구분한다. 모든 규칙은 팀 제안안이다.

## 1. 구현 범위

식판 칸별 섭취율을 에너지·단백질 섭취량으로 환산하고, 환자의 날짜별 목표로 하루 환산율을 구한다. 최근 7일의 기록에서 섭취 부족 위험과 판정 근거를 반환한다.

| 메서드 | 입력 | 반환 |
| --- | --- | --- |
| `meal_nutrients(slot_intakes, plan_slots)` | 칸별 섭취율과 표준 배식 영양값 | `MealNutrients` |
| `daily_target(profile, targets, weights, on)` | 환자 정보, 목표·체중 이력, 적용일 | `DailyTarget` |
| `daily_intake(on, meals, target)` | 해당 날짜의 끼니 기록과 하루 목표 | `DailyIntake` |
| `evaluate_alert(history, rules, on)` | 한 환자의 일별 이력, 규칙 설정, 판정일 | `AlertResult` |

기존 `NutritionEngine`의 타입과 시그니처를 사용한다. 네 메서드는 입력을 변경하지 않는 동기 순수 함수다. 사진 분석 결과는 섭취 추정 모듈에서 받고, 저장·이벤트 발행·추천 호출은 백엔드 서비스가 맡는다. [타입 계약](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/app/nutrition/types.py#L178) · [시스템 구조](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/system-architecture.md#L276)

## 2. 한 끼 영양량 · `meal_nutrients`

1. `slot_id`로 섭취 결과와 표준 배식 계획을 연결한다. 등록되지 않은 칸 ID는 `ValueError`로 처리한다.
2. 칸별 배식 기준 `energy_kcal`와 `protein_g`에 각각 `intake_fraction_est`를 곱한다. 섭취율 단위는 0~1이며 `0.0`은 확인된 0%다.
3. 판단 불가 칸은 합계에서 제외하고 `incomplete=True`로 표시한다. 사진 전체가 판단 불가이면 사진 파이프라인에서 끼니를 `not_determinable`로 표시한다.
4. 합계를 `energy_kcal_est`, `protein_g_est`로 반환한다.

| 칸 | 표준 배식 기준 | 섭취율 | 섭취 영양량 |
| --- | --- | --- | --- |
| 밥 | 300 kcal / 6 g | 0.5 | 150 kcal / 3 g |
| 반찬 | 200 kcal / 20 g | 0.3 | 60 kcal / 6 g |
| 국 | 80 kcal / 4 g | 판단 불가 | 합계에서 제외 |
| **결과** | | | **210 kcal / 9 g, `incomplete=True`** |

**보완 · 입력 경계**
- `status = estimated`인데 `intake_fraction_est`가 `None`이거나 0~1을 벗어나면 `ValueError`다. `not_determinable` 칸의 섭취율은 보지 않는다.
- 배식 계획에는 있지만 섭취 결과에 없는 칸(미배식 칸 포함)은 합계에 더하지 않고 `incomplete`에도 영향을 주지 않는다. 배식 칸이 빠지지 않았는지는 섭취 추정 결과 검증(사진 파이프라인)이 맡는다.

[최종 제안서의 영양 환산 규칙](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/proposal.md#L27)

## 3. 날짜별 환자 목표 · `daily_target`

| 우선순위 | 선택 조건 | 반환값과 출처 |
| --- | --- | --- |
| 1 | `effective_from <= on`인 진료팀 설정 중 가장 최근 값 | 설정 kcal·g, `team_set` |
| 2 | `measured_on <= on`인 체중 중 가장 최근 값 | 체중 × 30 kcal, 체중 × 1.0 g, `espen_weight` |
| 3 | 적용 가능한 진료팀 설정과 체중이 모두 없음 | 성별·연령별 2025 한국인 영양소 섭취기준, `kdri` |

**보완 · 연령 구간 전체**: 2025 한국인 영양소 섭취기준 요약표(보건복지부·한국영양학회)의 에너지 필요추정량과 단백질 권장섭취량이다. 65세 미만 구간을 더해 "65세 미만 대체값 미정" 공백을 없앴다.

| 연령 구간 | 남성 | 여성 |
| --- | --- | --- |
| 19–29세 | 2,600 kcal / 단백질 65 g | 2,000 kcal / 단백질 55 g |
| 30–49세 | 2,500 kcal / 단백질 65 g | 1,900 kcal / 단백질 50 g |
| 50–64세 | 2,200 kcal / 단백질 60 g | 1,700 kcal / 단백질 50 g |
| 65–74세 | 2,000 kcal / 단백질 60 g | 1,600 kcal / 단백질 50 g |
| 75세 이상 | 1,900 kcal / 단백질 60 g | 1,500 kcal / 단백질 50 g |

- 연령은 `on.year - birth_year`로 구한다. 시드의 `birth_year`는 `시연일 연도 - age_at_d0`라서 시연일 기준 나이와 같다.
- 19세 미만은 파일럿 대상이 아니다. 계약상 목표는 항상 돌려줘야 하므로 19–29세 값을 쓴다(제안).
- 같은 날짜에 진료팀 설정이 여러 개면 입력 순서상 마지막 값을, 같은 날짜에 체중이 여러 개면 마지막 값을 쓴다. 저장소는 `(patient_id, effective_from)`·`(patient_id, measured_on)`이 기본 키라 실제로는 생기지 않는다.
- 일별 집계에 당일 `DailyTarget`과 출처를 함께 담는다. 과거 기록은 각 날짜에 적용됐던 목표를 유지한다. 시연 환자 10명은 진료팀 설정값을 쓴다.

[목표 이력 모델](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/data-model.md#L218) · [파일럿 참고값](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/pilot-design-review.md#근거-기준) · [2025 섭취기준 요약표](https://www.kns.or.kr/data/FileRoom/2025123102020340340.pdf)

## 4. 하루 섭취량과 환산율 · `daily_intake`

아침·점심·저녁을 대상으로 `order_status`를 확인한 뒤, 발주된 끼니의 `record_status`를 확인한다. 간식은 집계 범위에서 제외한다.

| 상태 | 섭취량 합계 | 건수 |
| --- | --- | --- |
| `ordered` + `recorded` | 기록된 kcal·g 포함 (전량 거부·전량 미섭취는 0 kcal / 0 g로 들어온다) | `recorded_meals` +1 |
| `ordered` + `not_recorded` / `not_determinable` / `failed` | 제외 | `unrecorded_meals` +1 |
| `ordered` + `pending` | 집계 보류 | 건수 변화 없음 |
| `npo` 또는 `cancelled` | 제외 | `npo_meals` +1 |

```text
하루 목표 대비 환산율(%) = 기록된 섭취 합계 × (3 ÷ 기록 끼니 수) ÷ 당일 목표 × 100
```

- 에너지와 단백질 각각에 적용한다. 아침 400 kcal만 기록되고 목표가 1,500 kcal이면 **기록 합계 400 kcal, 환산율 80%, 기록 범위 1/3끼**다.
- 금식·취소가 섞여도 환산식의 기준 끼니 수는 3이다. 기록 끼니가 0개면 합계와 환산율은 모두 `None`이며 상태별 건수는 반환한다.
- 환산율은 100%를 넘을 수 있다. 경고 판정에는 계산값을 사용하고 화면 표시 단계에서 반올림한다.

**보완 · 입력 경계**
- 직원이 확인한 전량 거부·전량 미섭취는 별도 상태가 아니다. `MealRecord`에는 직원 확인 여부가 없고, 전량 기록은 `recorded`와 추정치 0으로 저장되므로 첫 행으로 처리된다. 엔진이 따로 구분하지 않는다.
- `recorded`인데 `energy_kcal_est` 또는 `protein_g_est`가 `None`이면 `ValueError`다. 데이터 모델상 기록된 끼니에는 추정치가 있어야 하며, 0으로 바꿔 넣으면 섭취 부족을 실제보다 크게 만든다. 현재 시드에는 이런 끼니가 없다.

[끼니 상태별 집계](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/data-model.md#L344) · [일별 환산 규칙](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/data-model.md#L420)

## 5. 최근 7일 위험 판정 · `evaluate_alert`

1. `on`을 포함한 최근 7개 달력 날짜를 평가한다. 12월 6일 판정이면 11월 30일~12월 6일이다. 창 크기와 임계값은 `AlertRules`에서 읽는다.
2. 에너지와 단백질 각각에 대해 계산 가능한 일별 환산율 평균(`avg_pct`)과 50% 이하 최장 연속 일수(`low_days_streak`)를 구한다. 확인된 0%는 포함한다. 날짜 행이 없거나 환산율이 `None`이면 평균에서 제외하고 해당 영양소의 연속 일수를 끊는다. 5일 연속 구간이 평가 범위에 남아 있으면 판정일 전에 회복했어도 경고가 유지된다.
3. 아래 우선순위에 따라 수준과 해당 수준을 유발한 영양소를 선택한다.

| 우선순위 | 수준 | 기본 조건 |
| --- | --- | --- |
| 1 | `warning` | 같은 영양소가 **50% 이하인 날 5일 이상 연속** |
| 2 | `caution` | 경고 조건이 없고, 에너지 또는 단백질 평균이 **75% 미만** |
| 3 | `none` | 조건에 해당하지 않음. `nutrients=()` |

`AlertResult`에 수준, 해당 영양소, 평가 기간, 평균·연속 일수 근거, 평가 기간의 미기록 끼니 합계를 담는다. 평가 가능한 값이 전혀 없으면 `none`으로 반환한다. 화면에서는 일별 결측값으로 기록 없음을 표시한다. [최종 경고 규칙](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/proposal.md#L34) · [설정·반환 타입](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/app/nutrition/types.py#L147)

**보완 · 반환값 세부 규칙**

| 항목 | 규칙 |
| --- | --- |
| `nutrients` | `warning`이면 연속 조건을 채운 영양소만, `caution`이면 평균이 75% 미만인 영양소만 담는다. 순서는 `energy`, `protein` |
| `evidence` | 수준과 무관하게 에너지·단백질 두 항목을 이 순서로 담는다. 계산 가능한 값이 없는 영양소는 `avg_pct = None`, `low_days_streak = 0` |
| `period_start`·`period_end` | 창 안에 계산 가능한 환산율이 하나라도 있으면 창의 첫날과 `on`, 하나도 없으면 둘 다 `None` |
| `unrecorded_meals` | 창 안 날짜 행의 `unrecorded_meals` 합계. 금식·취소(`npo_meals`)는 더하지 않는다 |
| 창 밖 이력 | `on`보다 뒤이거나 창 첫날보다 앞선 날짜 행은 무시한다 |
| 같은 날짜 행 두 개 이상 | `ValueError` (호출자 오류) |
| 경계값 | 평균은 75% **미만**만 주의(75.0%는 아님), 연속은 50% **이하**를 포함(50.0%는 포함) |

## 6. 테스트와 시연 검산

기존 `NutritionEngineContract`를 실제 엔진에 적용하고 업무 규칙 테스트를 추가한다. `backend/`에서 `uv run pytest`로 실행한다.

| 테스트 입력 | 기대 결과 |
| --- | --- |
| 칸 순서 변경 및 판단 불가 칸 포함 | ID 기준 연결, 판단 가능한 칸 합산, `incomplete=True` |
| 미등록 칸 ID | `ValueError` |
| `estimated` 칸의 섭취율 `None`·1.1 (보완) | `ValueError` |
| 적용된 팀 목표, 미래 목표, 체중이 모두 존재 | 당일 기준 최신 `team_set` |
| 팀 목표 없이 기존 50 kg과 미래 체중이 존재 | 1,500 kcal / 50 g, `espen_weight` |
| 목표·체중 없음, 여성 58세 / 남성 80세 (보완) | 1,700 kcal / 50 g, 1,900 kcal / 60 g, `kdri` |
| 전량 거부 1끼, 미기록 1끼, 금식 1끼 | 합계와 환산율 0, 세 상태의 건수 각각 1 |
| 전부 미기록 또는 전부 금식 | 합계와 환산율 `None`, 해당 상태 건수 3 |
| 목표 1,500 kcal, 유일한 기록 끼니 600 kcal | 합계 600 kcal, 환산율 120% |
| `recorded` 끼니의 추정치 `None` (보완) | `ValueError` |
| 경고 조건 없이 평균 75.0% / 74.9% | 각각 `none` / `caution` |
| 같은 영양소 50.0%가 4일 / 5일 연속 | 각각 경고 조건 미충족 / `warning` |
| 저섭취 사이에 날짜 누락 또는 `None` | 해당 날짜에서 연속 집계 중단 |
| 에너지 저섭취 3일 후 단백질 저섭취 2일 | 영양소별 연속 집계. 두 구간으로 경고를 만들지 않음 |
| 단백질 5일 연속 경고, 에너지 평균 75% 미만 | `warning`, 해당 영양소는 단백질 |
| 창 이동으로 5일 연속 구간의 첫날이 빠짐 | 다른 경고 조건이 없으면 평균 기준으로 재평가 |
| 계산 가능한 값이 하나도 없음 (보완) | `none`, 기간 `None`, 근거 두 항목 모두 `avg_pct = None` |
| 같은 날짜 행 두 개 (보완) | `ValueError` |

**보완 · 시드 검산 테스트**: 현재 시드(`data/seed/demo_seed.json`)를 엔진으로 계산한 D-1 판정이 [시연 환자 표](samples/README.md)와 같아야 한다. 다음 값은 이 문서의 규칙으로 계산해 확인했다.

| 환자 | D-1 판정 | 7일 평균 (에너지 · 단백질) | 50% 이하 최장 연속 |
| --- | --- | --- | --- |
| NS09 | 경고 (에너지·단백질) | 46.2% · 53.3% | 5일 · 5일 |
| NS04 | 경고 (단백질) | 57.3% · 43.1% | 0일 · 7일 |
| NS03 | 주의 (에너지·단백질) | 35.8% · 39.0% | 4일 · 4일 |
| NS02 | 주의 (에너지·단백질) | 70.1% · 51.8% | 0일 · 1일 |
| NS06 | 주의 (에너지) | 71.9% · 82.0% | 1일 · 1일 |
| NS05 | 정상 | 75.5% · 89.5% | 1일 · 0일 |
| NS01 · NS07 · NS08 · NS10 | 정상 | 78.6~99.2% | 0일 |

**NS03 통합 시연 (보완: 현재 시드 기준)** · 풀무원 식단으로 바꾼 뒤 NS03은 D-1에 에너지 50% 이하가 6일 연속이라 시작부터 경고였다. 시드의 D-5 세 끼 밥·주찬 섭취율을 올려(D-5 에너지 53.6%, 단백질 61.8%) 연속을 D-4~D-1의 4일로 끊었다. 그래서 D-1 판정은 주의다.

- D-1까지 에너지 환산율: D-6 46.0% · D-5 53.6% · D-4 35.2% · D-3 21.4% · D-2 17.0% · D-1 21.5%
- D0 아침 6칸의 섭취율을 각각 30%로 입력하면 `698 × 0.30 = 209.4 kcal`다. 하루 목표 1,700 kcal 기준으로 `209.4 × 3 ÷ 1,700 × 100 ≈ 37.0%`(`1/3끼`)다. 단백질은 `30.7 × 0.30 = 9.2 g`, `9.2 × 3 ÷ 60 × 100 ≈ 46.0%`다.
- 창이 D-6~D0으로 옮겨 가고, 에너지·단백질 모두 D-4~D0이 50% 이하 5일 연속이 되어 **`caution → warning`**을 기대한다. 판정 영양소는 에너지·단백질이다.
- 보조 시연 NS05: D0 점심을 55%로 기록하면 7일 평균 에너지가 74.1%가 되어 `none → caution`이다.

[계약 테스트](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/tests/contracts/nutrition.py) · [NS03 시연 기준](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/proposal.md#L76)

## 7. 구현과 백엔드 연결

**보완 · 연동 현황 반영**: 원본에서 결정이 필요하다고 적었던 항목은 T2·T3에서 정해졌다.

| 작업 | 전달 내용 |
| --- | --- |
| 영양 엔진 | 구현 파일을 `backend/app/nutrition/engine.py`로 두는 안이다. 기존 계약으로 네 메서드를 작성하고 계약·업무·시드 검산 테스트를 적용한다. 새 의존성은 없다. |
| 설정 등록 | `backend/app/wiring.py`의 `NUTRITION_ENGINES`에 등록해 `NUTRITION_ENGINE` 설정으로 선택할 수 있게 한다. T3(사진 흐름)가 같은 파일의 바로 위 `INTAKE_ESTIMATORS` 줄을 고치므로, **등록과 기본값 전환은 T3 머지 뒤 작은 변경으로 한다.** 엔진 구현·테스트는 그 전에 머지할 수 있다. |
| T2 저장소 (결정됨) | 시드의 일별 섭취와 경고는 적재할 때 설정된 엔진으로 계산한다. 금식 발주의 비어 있는 기록 상태는 `not_recorded`로 바꿔 넣는다. 엔진을 등록한 뒤에는 앱을 끄고 `uv run python -m scripts.seed`로 리셋해야 파생 테이블이 실제 엔진 값이 된다([저장소 참조 문서](specs/storage-seed.md) '시연 전 준비'). |
| T3 사진 처리 (스펙 확정) | 사진 분석 완료·판단 불가·실패·전량 기록 뒤 그날 일별 섭취를 저장하고 새 판정을 넣는다. 수준이 바뀌면 `alert.changed`를 발행하고, 오르면 T4 훅으로 추천 카드를 만든다. |
| T4 환자·추천 API (머지됨) | 일별 이력은 `services.patients.daily_rows`가 저장 행 또는 엔진 계산값으로 만든다. 판정에 근거 기간이 없으면 API의 `period_start`·`period_end`는 `null`이다. |

**완료 기준** · 네 메서드의 계약·업무 테스트를 통과하고, 시드 검산 테스트에서 10명의 D-1 판정이 위 표와 같다. NS03에서 209.4 kcal와 약 37.0%를 재현해 `caution → warning`을 확인한다. 엔진 단위 구현과 테스트는 T2~T4 연동 전에 진행할 수 있다. [설정 등록부](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/app/wiring.py#L46) · [구현 순서](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/build-plan.md#L139) · [T2 #3](https://github.com/AI-SMTP/NutriSight/issues/3) · [T3 #4](https://github.com/AI-SMTP/NutriSight/issues/4) · [T4 #5](https://github.com/AI-SMTP/NutriSight/issues/5)
