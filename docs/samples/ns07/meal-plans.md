# 2026-11-23 · 예정 식단 (meal_plans)

**묶음**: 예정 식단 컬렉션 · [데이터 모델](../../data-model.md) 3절 · 시연용 모의 데이터

일반식을 받는 모든 환자에게 같은 식단이다. NS07 원본 기록의 메뉴(밥, 주찬, 부찬 1)는 그대로 두고, 국내 일반식 표준 구성에 맞춰 국, 부찬 2, 김치를 더했다. `slot_id`는 끼니마다 같은 칸 위치를 뜻한다.

배식량과 영양성분은 일반적인 1인분 기준의 **근사 모의값**이다. 실측 배식량과 식약처 식품영양성분 데이터로 바꾼다.

## meal_plans

| `meal_plan_id` | `date` | `meal` | `diet_type` | `baseline_photo_id` |
| --- | --- | --- | --- | --- |
| 2026-11-23_breakfast_general | 2026-11-23 | breakfast | general | ph_b_20261123_bf (모의) |
| 2026-11-23_lunch_general | 2026-11-23 | lunch | general | ph_b_20261123_lu (모의) |
| 2026-11-23_dinner_general | 2026-11-23 | dinner | general | ph_b_20261123_dn (모의) |

## meal_plan_slots

### 아침 · 2026-11-23_breakfast_general

| `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 아랫줄 왼쪽 | rice | 쌀밥 | 210 | 315 | 5.7 |
| slot_2 | 아랫줄 오른쪽 | soup | 아욱된장국 | 250 | 40 | 2.5 |
| slot_3 | 윗줄 1 | main | 달걀찜 | 100 | 90 | 7.0 |
| slot_4 | 윗줄 2 | side | 애호박볶음 | 60 | 35 | 1.0 |
| slot_5 | 윗줄 3 | side | 감자조림 | 60 | 60 | 1.2 |
| slot_6 | 윗줄 4 | kimchi | 배추김치 | 40 | 8 | 0.6 |
| | | | **합계** | | **548** | **18.0** |

### 점심 · 2026-11-23_lunch_general

| `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 아랫줄 왼쪽 | rice | 잡곡밥 | 210 | 320 | 7.0 |
| slot_2 | 아랫줄 오른쪽 | soup | 미역국 | 250 | 45 | 3.0 |
| slot_3 | 윗줄 1 | main | 닭고기볶음 | 80 | 150 | 14.0 |
| slot_4 | 윗줄 2 | side | 시금치나물 | 50 | 25 | 1.5 |
| slot_5 | 윗줄 3 | side | 어묵볶음 | 50 | 75 | 4.0 |
| slot_6 | 윗줄 4 | kimchi | 깍두기 | 40 | 12 | 0.6 |
| | | | **합계** | | **627** | **30.1** |

### 저녁 · 2026-11-23_dinner_general

| `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- |
| slot_1 | 아랫줄 왼쪽 | rice | 쌀밥 | 210 | 315 | 5.7 |
| slot_2 | 아랫줄 오른쪽 | soup | 소고기무국 | 250 | 60 | 5.0 |
| slot_3 | 윗줄 1 | main | 두부조림 | 80 | 100 | 8.0 |
| slot_4 | 윗줄 2 | side | 무나물 | 50 | 20 | 0.5 |
| slot_5 | 윗줄 3 | side | 콩나물무침 | 50 | 20 | 1.5 |
| slot_6 | 윗줄 4 | kimchi | 배추김치 | 40 | 8 | 0.6 |
| | | | **합계** | | **523** | **21.3** |

**하루 계획 합계**: 에너지 1,698 kcal · 단백질 69.4 g. NS07의 목표(1,500 kcal · 55 g)보다 많으므로, 계획대로 다 먹으면 목표를 넘는다.
