# NutriSight 영양 계산·경고 알고리즘 구현 가이드

**담당** 조윤서 · **대상** 영양 엔진 구현 및 백엔드 연동 팀원  
**기준 브랜치** [AI-SMTP/NutriSight `develop`](https://github.com/AI-SMTP/NutriSight/tree/develop)

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

[최종 제안서의 영양 환산 규칙](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/proposal.md#L27)

## 3. 날짜별 환자 목표 · `daily_target`

| 우선순위 | 선택 조건 | 반환값과 출처 |
| --- | --- | --- |
| 1 | `effective_from <= on`인 진료팀 설정 중 가장 최근 값 | 설정 kcal·g, `team_set` |
| 2 | `measured_on <= on`인 체중 중 가장 최근 값 | 체중 × 30 kcal, 체중 × 1.0 g, `espen_weight` |
| 3 | 적용 가능한 진료팀 설정과 체중이 모두 없음 | 성별·연령별 파일럿 참고값, `kdri` |

| 파일럿 연령 구간 | 남성 | 여성 |
| --- | --- | --- |
| 65–74세 | 2,000 kcal / 단백질 60 g | 1,600 kcal / 단백질 50 g |
| 75세 이상 | 1,900 kcal / 단백질 60 g | 1,500 kcal / 단백질 50 g |

- `PatientProfile`에는 출생연도가 있으므로 파일럿에서는 `on.year - birth_year`로 연령 구간을 구하는 방안을 제안한다.
- 일별 집계에 당일 `DailyTarget`과 출처를 함께 담는다. 과거 기록은 각 날짜에 적용됐던 목표를 유지한다. 시연 환자 10명은 진료팀 설정값을 쓴다.
- 65세 미만이면서 목표와 체중이 모두 없는 사례의 대체값은 파일럿 표에서 정하지 않았다. 해당 환자군을 포함할 때 기준을 정한다.

[목표 이력 모델](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/data-model.md#L218) · [파일럿 참고값](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/pilot-design-review.md#근거-기준)

## 4. 하루 섭취량과 환산율 · `daily_intake`

아침·점심·저녁을 대상으로 `order_status`를 확인한 뒤, 발주된 끼니의 `record_status`를 확인한다. 간식은 집계 범위에서 제외한다.

| 상태 | 섭취량 합계 | 건수 |
| --- | --- | --- |
| `ordered` + `recorded` | 기록된 kcal·g 포함 | `recorded_meals` +1 |
| 직원이 확인한 전량 거부·전량 미섭취 | 0 kcal / 0 g 포함 | `recorded_meals` +1 |
| `ordered` + `not_recorded` / `not_determinable` / `failed` | 제외 | `unrecorded_meals` +1 |
| `ordered` + `pending` | 집계 보류 | 건수 변화 없음 |
| `npo` 또는 `cancelled` | 제외 | `npo_meals` +1 |

```text
하루 목표 대비 환산율(%) = 기록된 섭취 합계 × (3 ÷ 기록 끼니 수) ÷ 당일 목표 × 100
```

- 에너지와 단백질 각각에 적용한다. 아침 400 kcal만 기록되고 목표가 1,500 kcal이면 **기록 합계 400 kcal, 환산율 80%, 기록 범위 1/3끼**다.
- 금식·취소가 섞여도 환산식의 기준 끼니 수는 3이다. 기록 끼니가 0개면 합계와 환산율은 모두 `None`이며 상태별 건수는 반환한다.
- 환산율은 100%를 넘을 수 있다. 경고 판정에는 계산값을 사용하고 화면 표시 단계에서 반올림한다.

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

## 6. 테스트와 시연 검산

기존 `NutritionEngineContract`를 실제 엔진에 적용하고 업무 규칙 테스트를 추가한다. `backend/`에서 `uv run pytest`로 실행한다.

| 테스트 입력 | 기대 결과 |
| --- | --- |
| 칸 순서 변경 및 판단 불가 칸 포함 | ID 기준 연결, 판단 가능한 칸 합산, `incomplete=True` |
| 미등록 칸 ID | `ValueError` |
| 적용된 팀 목표, 미래 목표, 체중이 모두 존재 | 당일 기준 최신 `team_set` |
| 팀 목표 없이 기존 50 kg과 미래 체중이 존재 | 1,500 kcal / 50 g, `espen_weight` |
| 전량 거부 1끼, 미기록 1끼, 금식 1끼 | 합계와 환산율 0, 세 상태의 건수 각각 1 |
| 전부 미기록 또는 전부 금식 | 합계와 환산율 `None`, 해당 상태 건수 3 |
| 목표 1,500 kcal, 유일한 기록 끼니 600 kcal | 합계 600 kcal, 환산율 120% |
| 경고 조건 없이 평균 75.0% / 74.9% | 각각 `none` / `caution` |
| 같은 영양소 50.0%가 4일 / 5일 연속 | 각각 경고 조건 미충족 / `warning` |
| 저섭취 사이에 날짜 누락 또는 `None` | 해당 날짜에서 연속 집계 중단 |
| 에너지 저섭취 3일 후 단백질 저섭취 2일 | 영양소별 연속 집계. 두 구간으로 경고를 만들지 않음 |
| 단백질 5일 연속 경고, 에너지 평균 75% 미만 | `warning`, 해당 영양소는 단백질 |
| 창 이동으로 5일 연속 구간의 첫날이 빠짐 | 다른 경고 조건이 없으면 평균 기준으로 재평가 |

**NS03 통합 시연** · 현재 GitHub 시드는 D-1까지 에너지 환산율 50% 이하가 4일 연속이다. D0 아침 6칸의 섭취율을 각각 30%로 입력하면 `698 × 0.30 = 209.4 kcal`다. 하루 목표 1,700 kcal 기준으로 `209.4 × 3 ÷ 1,700 × 100 ≈ 37.0%`(`1/3끼`)다. 에너지 50% 이하가 5일 연속이 되어 **`caution → warning`**을 기대한다. 풀무원 식단으로 교체할 때는 해당 시드의 배식값으로 기대치를 다시 검산한다. [계약 테스트](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/tests/contracts/nutrition.py) · [NS03 시연 기준](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/proposal.md#L76)

## 7. 구현과 백엔드 연결

| 작업 | 전달 내용 |
| --- | --- |
| 영양 엔진 | 구현 파일을 `backend/app/nutrition/engine.py`로 두는 안이다. 기존 계약으로 네 메서드를 작성하고 계약·업무 테스트를 적용한다. |
| 설정 등록 | `backend/app/wiring.py`의 `NUTRITION_ENGINES`에 등록해 `NUTRITION_ENGINE` 설정으로 선택할 수 있게 한다. |
| T2 저장소 | 목표·체중·끼니·일별 이력을 엔진 타입으로 변환한다. 시드의 일별 값과 경고를 그대로 적재할지, 적재할 때 엔진으로 계산할지 결정한다. 금식·취소 발주의 DB 기록 상태가 비어 있을 때 변환 규약을 맞춘다. |
| T3 사진 처리 / T4 환자·추천 API | 사진 분석 완료 또는 직원 0% 확인 뒤 끼니와 하루를 재집계하고 경고를 평가한다. 서비스가 수준 변경 시 `alert.changed`를 발행하고, 수준 상승 시 추천 생성을 요청한다. 경고 근거 기간의 무자료 표기는 API 담당과 맞춘다. |

**완료 기준** · 네 메서드의 계약·업무 테스트를 통과하고, NS03에서 209.4 kcal와 약 37.0%를 재현해 `caution → warning`을 확인한다. 엔진 단위 구현과 테스트는 T2~T4 연동 전에 진행할 수 있다. [설정 등록부](https://github.com/AI-SMTP/NutriSight/blob/develop/backend/app/wiring.py#L46) · [구현 순서](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/build-plan.md#L139) · [T2 #3](https://github.com/AI-SMTP/NutriSight/issues/3) · [T3 #4](https://github.com/AI-SMTP/NutriSight/issues/4) · [T4 #5](https://github.com/AI-SMTP/NutriSight/issues/5)
