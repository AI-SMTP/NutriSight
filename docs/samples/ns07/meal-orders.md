# NS07 · 실제 발주된 식사 (meal_orders)

**묶음**: 실제 발주된 식사 컬렉션 · [데이터 모델](../../data-model.md) 4절 · 시연용 모의 데이터

NS07에게 2026-11-23에 나간 세 끼의 발주와 급식 결과다. 식단은 [meal-plans.md](meal-plans.md), 환자는 [patient.md](patient.md)를 참조한다.

## meal_orders

| 필드 | 아침 | 점심 | 저녁 |
| --- | --- | --- | --- |
| `meal_order_id` | NS07_2026-11-23_breakfast | NS07_2026-11-23_lunch | NS07_2026-11-23_dinner |
| `meal_plan_id` | 2026-11-23_breakfast_general | 2026-11-23_lunch_general | 2026-11-23_dinner_general |
| `diet_category` | 상식 | 상식 | 상식 |
| `diet_code` | 일반상식 | 일반상식 | 일반상식 |
| `order_status` | ordered | ordered | ordered |
| `order_from` | 2026-11-23 breakfast | 2026-11-23 breakfast | 2026-11-23 breakfast |
| `order_note` | (없음) | (없음) | (없음) |
| `record_status` | recorded | recorded | recorded |
| `post_photo_id` | ph_p_NS07_20261123_bf (모의) | ph_p_NS07_20261123_lu (모의) | ph_p_NS07_20261123_dn (모의) |
| `energy_kcal_est` | 362.9 | 316.5 | 396.4 |
| `protein_g_est` | 13.0 | 14.2 | 16.2 |
| `incomplete` | false | false | false |
| `data_source` | mock | mock | mock |

## slot_intakes

`estimate_basis`는 모두 `mock`이다. 원본 기록에 있던 메뉴의 섭취율은 그대로 두고, 이번에 더한 칸(국, 부찬 2, 김치)의 섭취율은 원본의 패턴(채소 반찬과 딱딱한 반찬을 남김)에 맞춰 설정했다.

### 아침

| `slot_id` | 메뉴 | `intake_fraction_est` | `status` | 섭취 에너지 | 섭취 단백질 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 쌀밥 | 0.7 | estimated | 220.5 kcal | 4.0 g | 원본 |
| slot_2 | 아욱된장국 | 0.5 | estimated | 20.0 kcal | 1.3 g | 추가 |
| slot_3 | 달걀찜 | 1.0 | estimated | 90.0 kcal | 7.0 g | 원본 |
| slot_4 | 애호박볶음 | 0.0 | estimated | 0 kcal | 0 g | 원본 · 그대로 남김 |
| slot_5 | 감자조림 | 0.5 | estimated | 30.0 kcal | 0.6 g | 추가 |
| slot_6 | 배추김치 | 0.3 | estimated | 2.4 kcal | 0.2 g | 추가 |
| | | | | **362.9 kcal** | **13.0 g** | |

### 점심

| `slot_id` | 메뉴 | `intake_fraction_est` | `status` | 섭취 에너지 | 섭취 단백질 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 잡곡밥 | 0.6 | estimated | 192.0 kcal | 4.2 g | 원본 |
| slot_2 | 미역국 | 0.6 | estimated | 27.0 kcal | 1.8 g | 추가 |
| slot_3 | 닭고기볶음 | 0.5 | estimated | 75.0 kcal | 7.0 g | 원본 |
| slot_4 | 시금치나물 | 0.0 | estimated | 0 kcal | 0 g | 원본 · 그대로 남김 |
| slot_5 | 어묵볶음 | 0.3 | estimated | 22.5 kcal | 1.2 g | 추가 |
| slot_6 | 깍두기 | 0.0 | estimated | 0 kcal | 0 g | 추가 · 딱딱한 반찬 |
| | | | | **316.5 kcal** | **14.2 g** | |

### 저녁

| `slot_id` | 메뉴 | `intake_fraction_est` | `status` | 섭취 에너지 | 섭취 단백질 | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 쌀밥 | 0.8 | estimated | 252.0 kcal | 4.6 g | 원본 |
| slot_2 | 소고기무국 | 0.7 | estimated | 42.0 kcal | 3.5 g | 추가 |
| slot_3 | 두부조림 | 1.0 | estimated | 100.0 kcal | 8.0 g | 원본 |
| slot_4 | 무나물 | 0.0 | estimated | 0 kcal | 0 g | 원본 · 그대로 남김 |
| slot_5 | 콩나물무침 | 0.0 | estimated | 0 kcal | 0 g | 추가 |
| slot_6 | 배추김치 | 0.3 | estimated | 2.4 kcal | 0.2 g | 추가 |
| | | | | **396.4 kcal** | **16.2 g** | |

## daily_intakes (계산 결과)

| 필드 | 값 |
| --- | --- |
| `date` | 2026-11-23 |
| 에너지 섭취 | 1,075.8 kcal (목표 1,500 kcal의 **71.7%**) |
| 단백질 섭취 | 43.5 g (목표 55 g의 **79.0%**) |
| 기록된 끼니 / 미기록 끼니 | 3 / 0 |

끼니별 단백질 값은 소수 첫째 자리로 반올림해 표시했다. 하루 합계는 반올림 전 값(43.46 g)으로 계산했다.
