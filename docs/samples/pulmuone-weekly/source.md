# NutriSight 모의 환자 10명 · 풀무원 주간 식단

**원본 식단** 2025-12-01~12-07 · **시연 데이터 날짜** 2026-11-30~12-06 · **대상** NS01~NS10

- 원본의 월~일 순서를 기존 시연 주간의 월~일에 매핑했다. 아침·점심·저녁 21끼의 메뉴와 끼니별 열량·단백질 합계를 사용했다. 간식과 간식으로 제공된 죽은 제외했다.
- 12/05(토) 점심은 시연 날짜다. 원본 2025-12-06(토) 점심은 다섯 메뉴여서 배추김치를 김치 칸으로 옮기고 빈 부찬 칸을 미배식(0 g·0 kcal·0 g)으로 기록했다. 원본에서 ‘2/3’으로 표시된 밥은 시연에서도 기준 210 g의 2/3인 140 g으로 설정했다.
- 원본은 메뉴별 배식 중량과 영양값을 제공하지 않는다. 배식량은 6칸 시연 기준값을 적용했고, 칸별 열량·단백질은 음식 유형을 바탕으로 원본 끼니 합계를 나눈 **시연용 추정값**이다. 21끼의 칸별 합계는 원본과 일치한다.
- 환자 프로필·체중·목표·평가 기록과 모의 섭취율은 기존 10명 데이터를 사용했다. 섭취율은 같은 요일·끼니·칸 위치로 옮겼으며, 새 메뉴 기준으로 끼니별 에너지·단백질을 다시 계산했다. 미배식 칸은 0으로 기록했다.
- 실제 사진과 연결하기 전의 사진 ID는 NULL이다. 전량 거부·미섭취는 직원이 확인한 0으로, 미기록·금식은 섭취량 NULL과 칸별 기록 없음으로 표현했다.

[풀무원 요양시설용 식단 원본](https://pulstory.pulmuone.com/bbs/board.php?bo_table=m11_01&wr_id=587) · [GitHub 데이터 모델](https://github.com/AI-SMTP/NutriSight/blob/develop/docs/data-model.md)

## 2. 환자 컬렉션

### `patients`

| `patient_id` | `display_name` | `room` | `sex` | `birth_year` | `height_cm` | `default_diet_type` | `conditions` | `diet_restrictions` | `ckd_dialysis` | `observation_start` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS01 | NS01 | 301호 | male | 1953 | 166 | general | `["고혈압"]` | `""` | none | 2026-11-23 | mock |
| NS02 | NS02 | 301호 | female | 1947 | 155 | general | `["고혈압","이상지질혈증"]` | `""` | none | 2026-11-23 | mock |
| NS03 | NS03 | 302호 | male | 1945 | 163 | general | `["만성폐쇄성폐질환"]` | `""` | none | 2026-11-23 | mock |
| NS04 | NS04 | 302호 | female | 1940 | 152 | general | `["골다공증","고혈압"]` | `""` | none | 2026-11-23 | mock |
| NS05 | NS05 | 303호 | male | 1946 | 164 | general | `["뇌경색 과거력","고혈압"]` | `""` | none | 2026-11-23 | mock |
| NS06 | NS06 | 303호 | female | 1949 | 157 | general | `["제2형 당뇨병"]` | `""` | none | 2026-11-23 | mock |
| NS07 | NS07 | 304호 | female | 1944 | 154 | general | `["고혈압","퇴행성 무릎관절염"]` | `""` | none | 2026-11-23 | mock |
| NS08 | NS08 | 304호 | male | 1950 | 168 | general | `["이상지질혈증"]` | `""` | none | 2026-11-23 | mock |
| NS09 | NS09 | 305호 | female | 1938 | 150 | general | `["골다공증","만성콩팥병(G3b · 투석 안 함)"]` | `""` | ckd | 2026-11-23 | mock |
| NS10 | NS10 | 305호 | male | 1952 | 167 | general | `["고혈압"]` | `""` | none | 2026-11-23 | mock |

### `patient_weights`

| `patient_id` | `measured_on` | `weight_kg` |
| --- | --- | --- |
| NS01 | 2026-10-23 | 63.0 |
| NS01 | 2026-11-23 | 63.0 |
| NS02 | 2026-10-23 | 54.5 |
| NS02 | 2026-11-23 | 54.0 |
| NS03 | 2026-10-23 | 60.0 |
| NS03 | 2026-11-23 | 56.0 |
| NS04 | 2026-10-23 | 50.5 |
| NS04 | 2026-11-23 | 49.0 |
| NS05 | 2026-10-23 | 61.0 |
| NS05 | 2026-11-23 | 61.0 |
| NS06 | 2026-10-23 | 56.0 |
| NS06 | 2026-11-23 | 56.0 |
| NS07 | 2026-10-23 | 52.0 |
| NS07 | 2026-11-23 | 50.0 |
| NS08 | 2026-10-23 | 66.0 |
| NS08 | 2026-11-23 | 66.0 |
| NS09 | 2026-10-23 | 48.5 |
| NS09 | 2026-11-23 | 47.0 |
| NS10 | 2026-10-23 | 64.0 |
| NS10 | 2026-11-23 | 64.0 |

### `patient_targets`

| `patient_id` | `effective_from` | `energy_kcal` | `protein_g` | `source` | `note` |
| --- | --- | --- | --- | --- | --- |
| NS01 | 2026-11-23 | 1800 | 65 | team_set | 모의 진료팀 설정 |
| NS02 | 2026-11-23 | 1550 | 60 | team_set | 모의 진료팀 설정 |
| NS03 | 2026-11-23 | 1700 | 60 | team_set | 모의 진료팀 설정 |
| NS04 | 2026-11-23 | 1600 | 65 | team_set | 모의 진료팀 설정 |
| NS05 | 2026-11-23 | 1750 | 60 | team_set | 모의 진료팀 설정 |
| NS06 | 2026-11-23 | 1600 | 56 | team_set | 모의 진료팀 설정 |
| NS07 | 2026-11-23 | 1500 | 55 | team_set | 모의 진료팀 설정 |
| NS08 | 2026-11-23 | 1850 | 65 | team_set | 모의 진료팀 설정 |
| NS09 | 2026-11-23 | 1500 | 50 | team_set | 모의 진료팀 설정 |
| NS10 | 2026-11-23 | 1800 | 65 | team_set | 모의 진료팀 설정 |

### `patient_assessments`

| `patient_id` | `assessed_on` | `kind` | `result` | `score` | `note` |
| --- | --- | --- | --- | --- | --- |
| NS01 | 2026-11-23 | nutrition_screening | low_risk | NULL | 위험 낮음 |
| NS01 | 2026-11-23 | appetite_assist | observed | NULL | 자력 식사, 삼킴·씹기 불편 보고 없음 |
| NS01 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS01 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS02 | 2026-11-23 | nutrition_screening | at_risk | NULL | 위험 있음 |
| NS02 | 2026-11-23 | appetite_assist | observed | NULL | 자력 식사, 주찬을 반복해 많이 남김 |
| NS02 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS02 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS03 | 2026-11-23 | nutrition_screening | at_risk | NULL | 위험 있음 |
| NS03 | 2026-11-23 | appetite_assist | observed | NULL | 식욕 저하, 식판 배치에 도움 필요 |
| NS03 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS03 | 2026-11-23 | refeeding_risk | not_assessed | NULL | 미평가 |
| NS04 | 2026-11-23 | nutrition_screening | at_risk | NULL | 위험 있음 |
| NS04 | 2026-11-23 | appetite_assist | observed | NULL | 식판 배치 후 자력 식사, 주찬을 반복해 남김 |
| NS04 | 2026-11-23 | pressure_injury | stage_2 | NULL | 2단계 욕창 |
| NS04 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS05 | 2026-11-23 | nutrition_screening | low_risk | NULL | 위험 낮음 |
| NS05 | 2026-11-23 | appetite_assist | observed | NULL | 11/26 점심에 새로 사레 발생, 삼킴 평가 미실시 |
| NS05 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS05 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS05 | 2026-11-26 | swallowing | cough_observed | NULL | 점심 식사 중 새로 사레 발생. 삼킴 평가 미실시 |
| NS06 | 2026-11-23 | nutrition_screening | low_risk | NULL | 위험 낮음 |
| NS06 | 2026-11-23 | appetite_assist | observed | NULL | 평소 자력 식사, 11/24·11/27 점심 전 입맛 저하를 보고 |
| NS06 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS06 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS07 | 2026-11-23 | mna_sf | at_risk | 10 | 위험 있음, MNA-SF 10/14점 |
| NS07 | 2026-11-23 | appetite_assist | observed | NULL | 11/23 아침 사레·기침 관찰 없음, 삼킴 평가 미실시. 틀니 불편과 식욕 저하를 보고했고 포장 개봉에 도움 필요 |
| NS07 | 2026-11-23 | swallowing | no_cough_observed | NULL | 아침 식사 중 사레·기침 관찰 없음. 정식 삼킴 평가 미실시 |
| NS07 | 2026-11-23 | chewing | denture_discomfort | NULL | 딱딱한 반찬을 씹을 때 틀니가 불편하다고 말함 |
| NS07 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS07 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS08 | 2026-11-23 | nutrition_screening | low_risk | NULL | 위험 낮음 |
| NS08 | 2026-11-23 | appetite_assist | observed | NULL | 자력 식사, 삼킴·씹기 불편 보고 없음 |
| NS08 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS08 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |
| NS09 | 2026-11-23 | nutrition_screening | not_assessed | NULL | 미평가 |
| NS09 | 2026-11-23 | appetite_assist | observed | NULL | 식욕 저하를 보고, 식판 준비에 도움 필요 |
| NS09 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS09 | 2026-11-23 | refeeding_risk | not_assessed | NULL | 미평가 |
| NS10 | 2026-11-23 | nutrition_screening | low_risk | NULL | 위험 낮음 |
| NS10 | 2026-11-23 | appetite_assist | observed | NULL | 자력 식사, 삼킴·씹기 불편 보고 없음 |
| NS10 | 2026-11-23 | pressure_injury | none | NULL | 없음 |
| NS10 | 2026-11-23 | refeeding_risk | not_high | NULL | 고위험 해당 없음 |

## 3. 예정 식단 컬렉션

### `meal_plans`

| `meal_plan_id` | `date` | `meal` | `diet_type` | `baseline_photo_id` |
| --- | --- | --- | --- | --- |
| 2026-11-30_breakfast_general | 2026-11-30 | breakfast | general | NULL |
| 2026-11-30_lunch_general | 2026-11-30 | lunch | general | NULL |
| 2026-11-30_dinner_general | 2026-11-30 | dinner | general | NULL |
| 2026-12-01_breakfast_general | 2026-12-01 | breakfast | general | NULL |
| 2026-12-01_lunch_general | 2026-12-01 | lunch | general | NULL |
| 2026-12-01_dinner_general | 2026-12-01 | dinner | general | NULL |
| 2026-12-02_breakfast_general | 2026-12-02 | breakfast | general | NULL |
| 2026-12-02_lunch_general | 2026-12-02 | lunch | general | NULL |
| 2026-12-02_dinner_general | 2026-12-02 | dinner | general | NULL |
| 2026-12-03_breakfast_general | 2026-12-03 | breakfast | general | NULL |
| 2026-12-03_lunch_general | 2026-12-03 | lunch | general | NULL |
| 2026-12-03_dinner_general | 2026-12-03 | dinner | general | NULL |
| 2026-12-04_breakfast_general | 2026-12-04 | breakfast | general | NULL |
| 2026-12-04_lunch_general | 2026-12-04 | lunch | general | NULL |
| 2026-12-04_dinner_general | 2026-12-04 | dinner | general | NULL |
| 2026-12-05_breakfast_general | 2026-12-05 | breakfast | general | NULL |
| 2026-12-05_lunch_general | 2026-12-05 | lunch | general | NULL |
| 2026-12-05_dinner_general | 2026-12-05 | dinner | general | NULL |
| 2026-12-06_breakfast_general | 2026-12-06 | breakfast | general | NULL |
| 2026-12-06_lunch_general | 2026-12-06 | lunch | general | NULL |
| 2026-12-06_dinner_general | 2026-12-06 | dinner | general | NULL |

### 끼니별 제공 영양량과 출처

| `meal_plan_id` | 끼니 | 제공 에너지 (kcal) | 제공 단백질 (g) | 합계 출처 |
| --- | --- | --- | --- | --- |
| 2026-11-30_breakfast_general | 아침 | 468 | 23.0 | 식단표 표기 |
| 2026-11-30_lunch_general | 점심 | 527 | 14.0 | 식단표 표기 |
| 2026-11-30_dinner_general | 저녁 | 698 | 19.0 | 식단표 표기 |
| 2026-12-01_breakfast_general | 아침 | 432 | 24.0 | 식단표 표기 |
| 2026-12-01_lunch_general | 점심 | 674 | 27.0 | 식단표 표기 |
| 2026-12-01_dinner_general | 저녁 | 599 | 27.0 | 식단표 표기 |
| 2026-12-02_breakfast_general | 아침 | 464 | 28.0 | 식단표 표기 |
| 2026-12-02_lunch_general | 점심 | 653 | 20.0 | 식단표 표기 |
| 2026-12-02_dinner_general | 저녁 | 505 | 22.0 | 식단표 표기 |
| 2026-12-03_breakfast_general | 아침 | 478 | 27.0 | 식단표 표기 |
| 2026-12-03_lunch_general | 점심 | 663 | 29.0 | 식단표 표기 |
| 2026-12-03_dinner_general | 저녁 | 516 | 22.0 | 식단표 표기 |
| 2026-12-04_breakfast_general | 아침 | 489 | 15.0 | 식단표 표기 |
| 2026-12-04_lunch_general | 점심 | 676 | 41.0 | 식단표 표기 |
| 2026-12-04_dinner_general | 저녁 | 495 | 17.0 | 식단표 표기 |
| 2026-12-05_breakfast_general | 아침 | 460 | 21.0 | 식단표 표기 |
| 2026-12-05_lunch_general | 점심 | 658 | 32.0 | 식단표 표기 |
| 2026-12-05_dinner_general | 저녁 | 614 | 27.0 | 식단표 표기 |
| 2026-12-06_breakfast_general | 아침 | 475 | 10.0 | 식단표 표기 |
| 2026-12-06_lunch_general | 점심 | 583 | 23.0 | 식단표 표기 |
| 2026-12-06_dinner_general | 저녁 | 543 | 16.0 | 식단표 표기 |

### `meal_plan_slots`

#### 2026-11-30 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-30_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-11-30_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 조갯살연두부국 | 250 | 31 | 2.0 |
| 2026-11-30_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 소고기숙주볶음 | 90 | 119 | 13.4 |
| 2026-11-30_breakfast_general | slot_4 | 윗줄 2 | side | 방풍나물 | 60 | 20 | 1.0 |
| 2026-11-30_breakfast_general | slot_5 | 윗줄 3 | side | 미나리초무침 | 50 | 20 | 1.0 |
| 2026-11-30_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-11-30 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-30_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥2/3 | 140 | 205 | 3.5 |
| 2026-11-30_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 팽이버섯맑은국 | 250 | 47 | 1.0 |
| 2026-11-30_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 오징어우동볶음 | 90 | 178 | 6.7 |
| 2026-11-30_lunch_general | slot_4 | 윗줄 2 | side | 브로컬리맛살무침 | 60 | 59 | 1.7 |
| 2026-11-30_lunch_general | slot_5 | 윗줄 3 | side | 애호박나물 | 50 | 30 | 0.5 |
| 2026-11-30_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-11-30 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-11-30_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙시금치찹쌀밥 | 210 | 270 | 5.0 |
| 2026-11-30_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 달래된장국 | 250 | 62 | 1.3 |
| 2026-11-30_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 마약계란장 | 90 | 238 | 9.1 |
| 2026-11-30_dinner_general | slot_4 | 윗줄 2 | side | 잔멸치볶음 | 60 | 80 | 2.3 |
| 2026-11-30_dinner_general | slot_5 | 윗줄 3 | side | 가지나물 | 50 | 40 | 0.7 |
| 2026-11-30_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-01 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-01_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-01_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 들깨버섯국 | 250 | 25 | 2.1 |
| 2026-12-01_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 닭살단호박조림 | 90 | 97 | 14.1 |
| 2026-12-01_breakfast_general | slot_4 | 윗줄 2 | side | 파래자반볶음 | 60 | 16 | 1.1 |
| 2026-12-01_breakfast_general | slot_5 | 윗줄 3 | side | 세발나물 | 50 | 16 | 1.1 |
| 2026-12-01_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-01 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-01_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙홍국찹쌀밥 | 210 | 270 | 5.0 |
| 2026-12-01_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 김치찌개 | 250 | 83 | 4.5 |
| 2026-12-01_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 치즈돈까스 | 90 | 206 | 12.8 |
| 2026-12-01_lunch_general | slot_4 | 윗줄 2 | side | 햄마카로니샐러드 | 60 | 69 | 3.2 |
| 2026-12-01_lunch_general | slot_5 | 윗줄 3 | side | 오이무침 | 50 | 34 | 0.9 |
| 2026-12-01_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 깍두기 | 40 | 12 | 0.6 |

#### 2026-12-01 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-01_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-01_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 소고기무국 | 250 | 53 | 2.5 |
| 2026-12-01_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 동태양념조림 | 90 | 201 | 16.5 |
| 2026-12-01_dinner_general | slot_4 | 윗줄 2 | side | 유채나물 | 60 | 34 | 1.2 |
| 2026-12-01_dinner_general | slot_5 | 윗줄 3 | side | 김구이 | 50 | 33 | 1.2 |
| 2026-12-01_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-02 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-02_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-12-02_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 낙지연포탕 | 250 | 28 | 2.3 |
| 2026-12-02_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 돈육장조림 | 90 | 105 | 15.2 |
| 2026-12-02_breakfast_general | slot_4 | 윗줄 2 | side | 도토리묵&양념장 | 60 | 35 | 3.8 |
| 2026-12-02_breakfast_general | slot_5 | 윗줄 3 | side | 취나물볶음 | 50 | 18 | 1.1 |
| 2026-12-02_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-02 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-02_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-12-02_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 사골곰국 | 250 | 62 | 1.7 |
| 2026-12-02_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 꼬막무침 | 90 | 235 | 11.1 |
| 2026-12-02_lunch_general | slot_4 | 윗줄 2 | side | 마늘쫑볶음 | 60 | 39 | 0.8 |
| 2026-12-02_lunch_general | slot_5 | 윗줄 3 | side | 부추겉절이 | 50 | 39 | 0.8 |
| 2026-12-02_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-02 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-02_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙강황찹쌀밥 | 210 | 270 | 5.0 |
| 2026-12-02_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 콩나물국 | 250 | 34 | 1.7 |
| 2026-12-02_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 소고기배추볶음 | 90 | 129 | 11.1 |
| 2026-12-02_dinner_general | slot_4 | 윗줄 2 | side | 두부양념조림 | 60 | 43 | 2.8 |
| 2026-12-02_dinner_general | slot_5 | 윗줄 3 | side | 무말랭이무침 | 50 | 21 | 0.8 |
| 2026-12-02_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 단호박백나박김치 | 40 | 8 | 0.6 |

#### 2026-12-03 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-03_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-03_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 냉이된장국 | 250 | 30 | 2.2 |
| 2026-12-03_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 방어시래기조림 | 90 | 113 | 14.5 |
| 2026-12-03_breakfast_general | slot_4 | 윗줄 2 | side | 계란찜 | 60 | 38 | 3.6 |
| 2026-12-03_breakfast_general | slot_5 | 윗줄 3 | side | 참나물무침 | 50 | 19 | 1.1 |
| 2026-12-03_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-03 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-03_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙단호박찹쌀밥 | 210 | 270 | 5.0 |
| 2026-12-03_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 북어채국 | 250 | 83 | 5.4 |
| 2026-12-03_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 돈안심수육채소무침 | 90 | 205 | 15.3 |
| 2026-12-03_lunch_general | slot_4 | 윗줄 2 | side | 감자채볶음 | 60 | 63 | 1.5 |
| 2026-12-03_lunch_general | slot_5 | 윗줄 3 | side | 쪽파김무침 | 50 | 34 | 1.2 |
| 2026-12-03_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-03 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-03_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-03_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 해물누룽지탕 | 250 | 78 | 2.5 |
| 2026-12-03_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 메추리알피망조림 | 90 | 102 | 10.9 |
| 2026-12-03_dinner_general | slot_4 | 윗줄 2 | side | 연근채볶음 | 60 | 38 | 1.7 |
| 2026-12-03_dinner_general | slot_5 | 윗줄 3 | side | 치커리무침 | 50 | 20 | 1.3 |
| 2026-12-03_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-04 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-04_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-12-04_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 순두부찌개 | 250 | 49 | 2.2 |
| 2026-12-04_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 소이로운장조림 | 90 | 122 | 6.2 |
| 2026-12-04_breakfast_general | slot_4 | 윗줄 2 | side | 늙은호박나물 | 60 | 20 | 0.5 |
| 2026-12-04_breakfast_general | slot_5 | 윗줄 3 | side | 콩나물무침 | 50 | 20 | 0.5 |
| 2026-12-04_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-04 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-04_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-12-04_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 모듬어묵국 | 250 | 84 | 7.4 |
| 2026-12-04_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 치킨마크니커리크림소스 | 90 | 209 | 21.1 |
| 2026-12-04_lunch_general | slot_4 | 윗줄 2 | side | 켄터키프라이드두부 | 60 | 70 | 5.3 |
| 2026-12-04_lunch_general | slot_5 | 윗줄 3 | side | 시래기나물 | 50 | 35 | 1.6 |
| 2026-12-04_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-04 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-04_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙클로렐라찹쌀밥 | 210 | 270 | 5.0 |
| 2026-12-04_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 아욱된장국 | 250 | 35 | 1.3 |
| 2026-12-04_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 해물동그랑땡 | 90 | 136 | 8.8 |
| 2026-12-04_dinner_general | slot_4 | 윗줄 2 | side | 새송이버섯조림 | 60 | 23 | 0.7 |
| 2026-12-04_dinner_general | slot_5 | 윗줄 3 | side | 시금치나물 | 50 | 23 | 0.6 |
| 2026-12-04_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-05 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-05_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-05_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 바지락미역국 | 250 | 30 | 1.8 |
| 2026-12-05_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 불고기오믈렛 | 90 | 114 | 11.8 |
| 2026-12-05_breakfast_general | slot_4 | 윗줄 2 | side | 고사리들깨찜 | 60 | 19 | 0.9 |
| 2026-12-05_breakfast_general | slot_5 | 윗줄 3 | side | 양념깻잎지무침 | 50 | 19 | 0.9 |
| 2026-12-05_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-05 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-05_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 훈제오리쌈장볶음밥 | 210 | 305 | 6.5 |
| 2026-12-05_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 애호박새우젓국 | 250 | 63 | 3.1 |
| 2026-12-05_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 옛날소시지전 | 90 | 242 | 20.3 |
| 2026-12-05_lunch_general | slot_4 | 윗줄 2 | side | 건새우마늘쫑볶음 | 60 | 40 | 1.5 |
| 2026-12-05_lunch_general | slot_5 | 윗줄 3 | side | 미배식 | 0 | 0 | 0.0 |
| 2026-12-05_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-05 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-05_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 혼합잡곡밥 | 210 | 270 | 5.0 |
| 2026-12-05_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 닭개장 | 250 | 54 | 2.5 |
| 2026-12-05_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 한입떡갈비구이 | 90 | 208 | 16.5 |
| 2026-12-05_dinner_general | slot_4 | 윗줄 2 | side | 우엉조림 | 60 | 35 | 1.2 |
| 2026-12-05_dinner_general | slot_5 | 윗줄 3 | side | 봄동나물 | 50 | 35 | 1.2 |
| 2026-12-05_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 깍두기 | 40 | 12 | 0.6 |

#### 2026-12-06 · 아침

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-06_breakfast_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥 | 210 | 270 | 5.0 |
| 2026-12-06_breakfast_general | slot_2 | 아랫줄 오른쪽 | soup | 우거지된장국 | 250 | 32 | 0.5 |
| 2026-12-06_breakfast_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 순살삼치무조림 | 90 | 123 | 3.4 |
| 2026-12-06_breakfast_general | slot_4 | 윗줄 2 | side | 죽순채볶음 | 60 | 21 | 0.3 |
| 2026-12-06_breakfast_general | slot_5 | 윗줄 3 | side | 돌나물무침 | 50 | 21 | 0.2 |
| 2026-12-06_breakfast_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-06 · 점심

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-06_lunch_general | slot_1 | 아랫줄 왼쪽 | rice | 미호현미밥2/3 | 140 | 205 | 3.5 |
| 2026-12-06_lunch_general | slot_2 | 아랫줄 오른쪽 | soup | 고추장찌개 | 250 | 79 | 4.0 |
| 2026-12-06_lunch_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 궁중떡볶음 | 90 | 194 | 11.3 |
| 2026-12-06_lunch_general | slot_4 | 윗줄 2 | side | 뱅어포무침 | 60 | 65 | 2.8 |
| 2026-12-06_lunch_general | slot_5 | 윗줄 3 | side | 청경채나물 | 50 | 32 | 0.8 |
| 2026-12-06_lunch_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

#### 2026-12-06 · 저녁

| `meal_plan_id` | `slot_id` | `position` | `dish_type` | `menu_name` | `served_g` | `energy_kcal` | `protein_g` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-12-06_dinner_general | slot_1 | 아랫줄 왼쪽 | rice | 칼슘쏙쏙토마토찹쌀밥 | 210 | 270 | 5.0 |
| 2026-12-06_dinner_general | slot_2 | 아랫줄 오른쪽 | soup | 소고기감자국 | 250 | 48 | 1.7 |
| 2026-12-06_dinner_general | slot_3 | 윗줄 1 (왼쪽 끝) | main | 그린빈스스크램블에그 | 90 | 155 | 7.1 |
| 2026-12-06_dinner_general | slot_4 | 윗줄 2 | side | 숙주나물 | 60 | 31 | 0.8 |
| 2026-12-06_dinner_general | slot_5 | 윗줄 3 | side | 방풍나물장아찌 | 50 | 31 | 0.8 |
| 2026-12-06_dinner_general | slot_6 | 윗줄 4 (오른쪽 끝) | kimchi | 배추김치 | 40 | 8 | 0.6 |

## 4. 실제 발주된 식사 컬렉션

### NS01

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS01_2026-11-30_breakfast | NS01 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 468.0 | 23.00 | false | mock |
| NS01_2026-11-30_lunch | NS01 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 500.7 | 13.12 | false | mock |
| NS01_2026-11-30_dinner | NS01 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 698.0 | 19.00 | false | mock |
| NS01_2026-12-01_breakfast | NS01 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 400.1 | 23.12 | false | mock |
| NS01_2026-12-01_lunch | NS01 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 674.0 | 27.00 | false | mock |
| NS01_2026-12-01_dinner | NS01 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 559.2 | 25.95 | false | mock |
| NS01_2026-12-02_breakfast | NS01 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 464.0 | 28.00 | false | mock |
| NS01_2026-12-02_lunch | NS01 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 653.0 | 20.00 | false | mock |
| NS01_2026-12-02_dinner | NS01 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 485.8 | 20.58 | false | mock |
| NS01_2026-12-03_breakfast | NS01 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 478.0 | 27.00 | false | mock |
| NS01_2026-12-03_lunch | NS01 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 623.5 | 27.78 | false | mock |
| NS01_2026-12-03_dinner | NS01 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 516.0 | 22.00 | false | mock |
| NS01_2026-12-04_breakfast | NS01 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 469.1 | 14.05 | false | mock |
| NS01_2026-12-04_lunch | NS01 | 2026-12-04_lunch_general | 상식 | 일반상식 | npo | 2026-11-30 breakfast | 검사 전 금식 | NULL | NULL | NULL | NULL | NULL | false | mock |
| NS01_2026-12-04_dinner | NS01 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 495.0 | 17.00 | false | mock |
| NS01_2026-12-05_breakfast | NS01 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 460.0 | 21.00 | false | mock |
| NS01_2026-12-05_lunch | NS01 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 658.0 | 32.00 | false | mock |
| NS01_2026-12-05_dinner | NS01 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 576.9 | 26.07 | false | mock |
| NS01_2026-12-06_breakfast | NS01 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 475.0 | 10.00 | false | mock |
| NS01_2026-12-06_lunch | NS01 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 583.0 | 23.00 | false | mock |
| NS01_2026-12-06_dinner | NS01 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 543.0 | 16.00 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS01_2026-11-30_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-11-30_lunch | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-11-30_dinner | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_breakfast | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_lunch | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-01_dinner | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_lunch | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-02_dinner | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-03_lunch | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-03_dinner | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-04_breakfast | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-04_dinner | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS01_2026-12-05_lunch | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_2 | 0.9 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_5 | 0.9 | estimated | [] | mock |
| NS01_2026-12-05_dinner | slot_6 | 0.9 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_lunch | slot_6 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_2 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_5 | 1.0 | estimated | [] | mock |
| NS01_2026-12-06_dinner | slot_6 | 1.0 | estimated | [] | mock |

### NS02

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS02_2026-11-30_breakfast | NS02 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 325.6 | 9.40 | false | mock |
| NS02_2026-11-30_lunch | NS02 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 290.3 | 6.08 | false | mock |
| NS02_2026-11-30_dinner | NS02 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 454.4 | 10.81 | false | mock |
| NS02_2026-12-01_breakfast | NS02 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 329.8 | 11.47 | false | mock |
| NS02_2026-12-01_lunch | NS02 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 406.0 | 11.96 | false | mock |
| NS02_2026-12-01_dinner | NS02 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 363.0 | 10.36 | false | mock |
| NS02_2026-12-02_breakfast | NS02 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 336.8 | 12.64 | false | mock |
| NS02_2026-12-02_lunch | NS02 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 412.2 | 10.06 | false | mock |
| NS02_2026-12-02_dinner | NS02 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 332.2 | 9.22 | false | mock |
| NS02_2026-12-03_breakfast | NS02 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 376.0 | 15.96 | false | mock |
| NS02_2026-12-03_lunch | NS02 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 399.0 | 11.00 | false | mock |
| NS02_2026-12-03_dinner | NS02 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 349.6 | 9.76 | false | mock |
| NS02_2026-12-04_breakfast | NS02 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 329.8 | 7.40 | false | mock |
| NS02_2026-12-04_lunch | NS02 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 373.6 | 13.37 | false | mock |
| NS02_2026-12-04_dinner | NS02 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 353.6 | 9.09 | false | mock |
| NS02_2026-12-05_breakfast | NS02 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 306.1 | 7.41 | false | mock |
| NS02_2026-12-05_lunch | NS02 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 438.9 | 15.20 | false | mock |
| NS02_2026-12-05_dinner | NS02 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 366.8 | 10.36 | false | mock |
| NS02_2026-12-06_breakfast | NS02 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 327.8 | 6.24 | false | mock |
| NS02_2026-12-06_lunch | NS02 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 332.6 | 9.64 | false | mock |
| NS02_2026-12-06_dinner | NS02 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 397.8 | 9.88 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS02_2026-11-30_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-11-30_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-11-30_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-11-30_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_2 | 0.1 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_3 | 0.1 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_5 | 0.1 | estimated | [] | mock |
| NS02_2026-11-30_lunch | slot_6 | 0.1 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS02_2026-11-30_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS02_2026-12-01_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-01_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-02_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_5 | 0.3 | estimated | [] | mock |
| NS02_2026-12-02_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_2 | 0.1 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_3 | 0.1 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_5 | 0.1 | estimated | [] | mock |
| NS02_2026-12-02_dinner | slot_6 | 0.1 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_2 | 0.4 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_3 | 0.4 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_5 | 0.4 | estimated | [] | mock |
| NS02_2026-12-03_breakfast | slot_6 | 0.4 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-03_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-04_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_2 | 0.1 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_3 | 0.1 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_5 | 0.1 | estimated | [] | mock |
| NS02_2026-12-04_lunch | slot_6 | 0.1 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS02_2026-12-04_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_2 | 0.1 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_3 | 0.1 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_5 | 0.1 | estimated | [] | mock |
| NS02_2026-12-05_breakfast | slot_6 | 0.1 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS02_2026-12-05_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-05_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_1 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_2 | 0.4 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_3 | 0.4 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_4 | 1.0 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_5 | 0.4 | estimated | [] | mock |
| NS02_2026-12-06_dinner | slot_6 | 0.4 | estimated | [] | mock |

### NS03

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS03_2026-11-30_breakfast | NS03 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 296.2 | 14.82 | false | mock |
| NS03_2026-11-30_lunch | NS03 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 265.2 | 7.14 | false | mock |
| NS03_2026-11-30_dinner | NS03 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 387.8 | 10.57 | false | mock |
| NS03_2026-12-01_breakfast | NS03 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 220.1 | 10.71 | false | mock |
| NS03_2026-12-01_lunch | NS03 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 279.4 | 10.82 | false | mock |
| NS03_2026-12-01_dinner | NS03 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 282.9 | 11.97 | false | mock |
| NS03_2026-12-02_breakfast | NS03 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 208.5 | 12.38 | false | mock |
| NS03_2026-12-02_lunch | NS03 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 248.5 | 7.34 | false | mock |
| NS03_2026-12-02_dinner | NS03 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 208.1 | 8.34 | false | mock |
| NS03_2026-12-03_breakfast | NS03 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 199.2 | 10.10 | false | mock |
| NS03_2026-12-03_lunch | NS03 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 208.9 | 8.57 | false | mock |
| NS03_2026-12-03_dinner | NS03 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 191.0 | 7.54 | false | mock |
| NS03_2026-12-04_breakfast | NS03 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 111.4 | 2.89 | false | mock |
| NS03_2026-12-04_lunch | NS03 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 136.8 | 6.78 | false | mock |
| NS03_2026-12-04_dinner | NS03 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 115.1 | 3.47 | false | mock |
| NS03_2026-12-05_breakfast | NS03 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 136.5 | 4.63 | false | mock |
| NS03_2026-12-05_lunch | NS03 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 151.9 | 6.46 | false | mock |
| NS03_2026-12-05_dinner | NS03 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | not_eaten | 0.0 | 0.00 | false | mock |
| NS03_2026-12-06_breakfast | NS03 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 124.2 | 2.61 | false | mock |
| NS03_2026-12-06_lunch | NS03 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 119.8 | 4.15 | false | mock |
| NS03_2026-12-06_dinner | NS03 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 121.3 | 3.16 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS03_2026-11-30_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS03_2026-11-30_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS03_2026-11-30_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-11-30_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_1 | 0.6 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_3 | 0.6 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_3 | 0.6 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-11-30_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_1 | 0.6 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_3 | 0.5 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_3 | 0.5 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_1 | 0.6 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_3 | 0.5 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-01_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_3 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_3 | 0.4 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_4 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_3 | 0.4 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_4 | 0.5 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-02_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_3 | 0.4 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_4 | 0.5 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_3 | 0.4 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_1 | 0.5 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_3 | 0.4 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_4 | 0.4 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-03_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_4 | 0.2 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-04_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_1 | 0.4 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-05_dinner | slot_1 | 0.0 | estimated | [] | staff |
| NS03_2026-12-05_dinner | slot_2 | 0.0 | estimated | [] | staff |
| NS03_2026-12-05_dinner | slot_3 | 0.0 | estimated | [] | staff |
| NS03_2026-12-05_dinner | slot_4 | 0.0 | estimated | [] | staff |
| NS03_2026-12-05_dinner | slot_5 | 0.0 | estimated | [] | staff |
| NS03_2026-12-05_dinner | slot_6 | 0.0 | estimated | [] | staff |
| NS03_2026-12-06_breakfast | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_1 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS03_2026-12-06_dinner | slot_6 | 0.0 | estimated | [] | mock |

### NS04

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS04_2026-11-30_breakfast | NS04 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 265.6 | 8.10 | false | mock |
| NS04_2026-11-30_lunch | NS04 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 252.0 | 5.58 | false | mock |
| NS04_2026-11-30_dinner | NS04 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 368.4 | 8.89 | false | mock |
| NS04_2026-12-01_breakfast | NS04 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 271.0 | 10.14 | false | mock |
| NS04_2026-12-01_lunch | NS04 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 351.4 | 10.18 | false | mock |
| NS04_2026-12-01_dinner | NS04 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 324.9 | 10.96 | false | mock |
| NS04_2026-12-02_breakfast | NS04 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 268.8 | 10.12 | false | mock |
| NS04_2026-12-02_lunch | NS04 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 342.6 | 8.74 | false | mock |
| NS04_2026-12-02_dinner | NS04 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 284.5 | 8.80 | false | mock |
| NS04_2026-12-03_breakfast | NS04 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 289.8 | 11.68 | false | mock |
| NS04_2026-12-03_lunch | NS04 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 326.1 | 9.55 | false | mock |
| NS04_2026-12-03_dinner | NS04 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 301.2 | 9.61 | false | mock |
| NS04_2026-12-04_breakfast | NS04 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 269.8 | 6.25 | false | mock |
| NS04_2026-12-04_lunch | NS04 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 358.8 | 16.39 | false | mock |
| NS04_2026-12-04_dinner | NS04 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 297.2 | 7.18 | false | mock |
| NS04_2026-12-05_breakfast | NS04 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 278.7 | 9.07 | false | mock |
| NS04_2026-12-05_lunch | NS04 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 365.9 | 13.45 | false | mock |
| NS04_2026-12-05_dinner | NS04 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 298.8 | 8.88 | false | mock |
| NS04_2026-12-06_breakfast | NS04 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 294.5 | 5.65 | false | mock |
| NS04_2026-12-06_lunch | NS04 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 296.9 | 9.49 | false | mock |
| NS04_2026-12-06_dinner | NS04 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 307.2 | 7.54 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS04_2026-11-30_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-11-30_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-11-30_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-11-30_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-01_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-01_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-02_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-02_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-03_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-03_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-04_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-04_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS04_2026-12-05_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-05_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS04_2026-12-06_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS04_2026-12-06_dinner | slot_6 | 0.3 | estimated | [] | mock |

### NS05

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS05_2026-11-30_breakfast | NS05 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 403.4 | 19.00 | false | mock |
| NS05_2026-11-30_lunch | NS05 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 439.4 | 11.87 | false | mock |
| NS05_2026-11-30_dinner | NS05 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 593.4 | 15.93 | false | mock |
| NS05_2026-12-01_breakfast | NS05 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 392.0 | 22.52 | false | mock |
| NS05_2026-12-01_lunch | NS05 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 546.1 | 21.92 | false | mock |
| NS05_2026-12-01_dinner | NS05 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 509.6 | 22.22 | false | mock |
| NS05_2026-12-02_breakfast | NS05 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 401.7 | 23.28 | false | mock |
| NS05_2026-12-02_lunch | NS05 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 545.9 | 17.11 | false | mock |
| NS05_2026-12-02_dinner | NS05 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 435.3 | 18.38 | false | mock |
| NS05_2026-12-03_breakfast | NS05 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 413.2 | 22.46 | false | mock |
| NS05_2026-12-03_lunch | NS05 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 122.0 | 4.56 | false | mock |
| NS05_2026-12-03_dinner | NS05 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 313.4 | 13.37 | false | mock |
| NS05_2026-12-04_breakfast | NS05 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 371.3 | 11.05 | false | mock |
| NS05_2026-12-04_lunch | NS05 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 514.2 | 30.26 | false | mock |
| NS05_2026-12-04_dinner | NS05 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 398.3 | 13.67 | false | mock |
| NS05_2026-12-05_breakfast | NS05 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 396.9 | 17.39 | false | mock |
| NS05_2026-12-05_lunch | NS05 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 530.4 | 25.75 | false | mock |
| NS05_2026-12-05_dinner | NS05 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 518.2 | 22.10 | false | mock |
| NS05_2026-12-06_breakfast | NS05 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 409.1 | 8.53 | false | mock |
| NS05_2026-12-06_lunch | NS05 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 525.7 | 21.01 | false | mock |
| NS05_2026-12-06_dinner | NS05 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 464.5 | 13.38 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS05_2026-11-30_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-11-30_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-11-30_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-11-30_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-01_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-02_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-03_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_1 | 0.3 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_4 | 0.0 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS05_2026-12-03_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_1 | 0.6 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_2 | 0.6 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_3 | 0.6 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_5 | 0.6 | estimated | [] | mock |
| NS05_2026-12-03_dinner | slot_6 | 0.6 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_2 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_3 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_5 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_lunch | slot_6 | 0.7 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-04_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS05_2026-12-05_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-05_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS05_2026-12-06_dinner | slot_6 | 0.8 | estimated | [] | mock |

### NS06

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS06_2026-11-30_breakfast | NS06 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 356.6 | 16.70 | false | mock |
| NS06_2026-11-30_lunch | NS06 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 398.5 | 10.81 | false | mock |
| NS06_2026-11-30_dinner | NS06 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 566.4 | 15.43 | false | mock |
| NS06_2026-12-01_breakfast | NS06 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 331.0 | 17.41 | false | mock |
| NS06_2026-12-01_lunch | NS06 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | refused | 0.0 | 0.00 | false | mock |
| NS06_2026-12-01_dinner | NS06 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 422.7 | 19.02 | false | mock |
| NS06_2026-12-02_breakfast | NS06 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 374.7 | 22.78 | false | mock |
| NS06_2026-12-02_lunch | NS06 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 488.0 | 14.58 | false | mock |
| NS06_2026-12-02_dinner | NS06 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 408.3 | 17.88 | false | mock |
| NS06_2026-12-03_breakfast | NS06 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 386.2 | 21.96 | false | mock |
| NS06_2026-12-03_lunch | NS06 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 536.7 | 23.35 | false | mock |
| NS06_2026-12-03_dinner | NS06 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 392.0 | 16.07 | false | mock |
| NS06_2026-12-04_breakfast | NS06 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 342.3 | 10.50 | false | mock |
| NS06_2026-12-04_lunch | NS06 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | refused | 0.0 | 0.00 | false | mock |
| NS06_2026-12-04_dinner | NS06 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 348.8 | 11.97 | false | mock |
| NS06_2026-12-05_breakfast | NS06 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 350.9 | 15.29 | false | mock |
| NS06_2026-12-05_lunch | NS06 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 530.4 | 25.75 | false | mock |
| NS06_2026-12-05_dinner | NS06 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 494.7 | 21.72 | false | mock |
| NS06_2026-12-06_breakfast | NS06 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 382.1 | 8.03 | false | mock |
| NS06_2026-12-06_lunch | NS06 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 472.9 | 18.68 | false | mock |
| NS06_2026-12-06_dinner | NS06 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 464.5 | 13.38 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS06_2026-11-30_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_1 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_lunch | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-11-30_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_lunch | slot_1 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_lunch | slot_2 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_lunch | slot_3 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_lunch | slot_4 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_lunch | slot_5 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_lunch | slot_6 | 0.0 | estimated | [] | staff |
| NS06_2026-12-01_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_dinner | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-01_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-01_dinner | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-02_lunch | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-02_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-03_dinner | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_lunch | slot_1 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_lunch | slot_2 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_lunch | slot_3 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_lunch | slot_4 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_lunch | slot_5 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_lunch | slot_6 | 0.0 | estimated | [] | staff |
| NS06_2026-12-04_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_dinner | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-04_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-04_dinner | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS06_2026-12-05_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS06_2026-12-05_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-05_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS06_2026-12-06_dinner | slot_6 | 0.8 | estimated | [] | mock |

### NS07

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS07_2026-11-30_breakfast | NS07 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 308.0 | 16.90 | false | mock |
| NS07_2026-11-30_lunch | NS07 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 212.0 | 5.45 | false | mock |
| NS07_2026-11-30_dinner | NS07 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 454.0 | 13.10 | false | mock |
| NS07_2026-12-01_breakfast | NS07 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 305.6 | 17.72 | false | mock |
| NS07_2026-12-01_lunch | NS07 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 445.2 | 17.34 | false | mock |
| NS07_2026-12-01_dinner | NS07 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 482.6 | 21.72 | false | mock |
| NS07_2026-12-02_breakfast | NS07 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 345.8 | 22.64 | false | mock |
| NS07_2026-12-02_lunch | NS07 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 442.3 | 13.61 | false | mock |
| NS07_2026-12-02_dinner | NS07 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 408.3 | 17.88 | false | mock |
| NS07_2026-12-03_breakfast | NS07 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 345.9 | 20.35 | false | mock |
| NS07_2026-12-03_lunch | NS07 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 470.7 | 18.85 | false | mock |
| NS07_2026-12-03_dinner | NS07 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 384.0 | 16.38 | false | mock |
| NS07_2026-12-04_breakfast | NS07 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 354.5 | 11.12 | false | mock |
| NS07_2026-12-04_lunch | NS07 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 413.0 | 23.09 | false | mock |
| NS07_2026-12-04_dinner | NS07 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 376.0 | 13.73 | false | mock |
| NS07_2026-12-05_breakfast | NS07 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 369.9 | 16.89 | false | mock |
| NS07_2026-12-05_lunch | NS07 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 463.8 | 20.80 | false | mock |
| NS07_2026-12-05_dinner | NS07 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 450.6 | 20.55 | false | mock |
| NS07_2026-12-06_breakfast | NS07 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 332.5 | 7.00 | false | mock |
| NS07_2026-12-06_lunch | NS07 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 448.0 | 17.58 | false | mock |
| NS07_2026-12-06_dinner | NS07 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 438.1 | 13.12 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS07_2026-11-30_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-11-30_breakfast | slot_2 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS07_2026-11-30_breakfast | slot_4 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_breakfast | slot_5 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_breakfast | slot_6 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_1 | 0.6 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_2 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_3 | 0.5 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_4 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_lunch | slot_6 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_2 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_4 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_5 | 0.0 | estimated | [] | mock |
| NS07_2026-11-30_dinner | slot_6 | 0.0 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_5 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_breakfast | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_3 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_5 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_lunch | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS07_2026-12-01_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_3 | 0.7 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_5 | 0.6 | estimated | [] | mock |
| NS07_2026-12-02_lunch | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS07_2026-12-02_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-03_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_3 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_5 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_lunch | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_4 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_5 | 0.6 | estimated | [] | mock |
| NS07_2026-12-03_dinner | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_2 | 0.5 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_3 | 0.5 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_5 | 0.5 | estimated | [] | mock |
| NS07_2026-12-04_lunch | slot_6 | 0.5 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-04_dinner | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_3 | 0.6 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS07_2026-12-05_lunch | slot_6 | 0.6 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-05_dinner | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_breakfast | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_lunch | slot_6 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_2 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_5 | 0.7 | estimated | [] | mock |
| NS07_2026-12-06_dinner | slot_6 | 0.7 | estimated | [] | mock |

### NS08

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS08_2026-11-30_breakfast | NS08 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 403.4 | 19.00 | false | mock |
| NS08_2026-11-30_lunch | NS08 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 492.1 | 13.27 | false | mock |
| NS08_2026-11-30_dinner | NS08 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 609.2 | 16.61 | false | mock |
| NS08_2026-12-01_breakfast | NS08 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 382.3 | 21.11 | false | mock |
| NS08_2026-12-01_lunch | NS08 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 573.1 | 22.42 | false | mock |
| NS08_2026-12-01_dinner | NS08 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 509.6 | 22.22 | false | mock |
| NS08_2026-12-02_breakfast | NS08 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 401.7 | 23.28 | false | mock |
| NS08_2026-12-02_lunch | NS08 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 572.9 | 17.61 | false | mock |
| NS08_2026-12-02_dinner | NS08 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | not_recorded | NULL | NULL | NULL | NULL | false | mock |
| NS08_2026-12-03_breakfast | NS08 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 441.5 | 25.75 | false | mock |
| NS08_2026-12-03_lunch | NS08 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 577.9 | 25.23 | false | mock |
| NS08_2026-12-03_dinner | NS08 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 443.6 | 18.27 | false | mock |
| NS08_2026-12-04_breakfast | NS08 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 420.2 | 12.55 | false | mock |
| NS08_2026-12-04_lunch | NS08 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 574.8 | 33.83 | false | mock |
| NS08_2026-12-04_dinner | NS08 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 436.6 | 14.98 | false | mock |
| NS08_2026-12-05_breakfast | NS08 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 406.4 | 18.48 | false | mock |
| NS08_2026-12-05_lunch | NS08 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 560.9 | 26.40 | false | mock |
| NS08_2026-12-05_dinner | NS08 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 494.7 | 21.72 | false | mock |
| NS08_2026-12-06_breakfast | NS08 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 409.1 | 8.53 | false | mock |
| NS08_2026-12-06_lunch | NS08 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 506.3 | 19.88 | false | mock |
| NS08_2026-12-06_dinner | NS08 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 504.2 | 15.11 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS08_2026-11-30_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_2 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_5 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_lunch | slot_6 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-11-30_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-01_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-02_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_2 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_5 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_breakfast | slot_6 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-03_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-04_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS08_2026-12-05_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_1 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-05_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_2 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_3 | 1.0 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_5 | 0.9 | estimated | [] | mock |
| NS08_2026-12-06_dinner | slot_6 | 0.9 | estimated | [] | mock |

### NS09

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS09_2026-11-30_breakfast | NS09 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 140.4 | 6.90 | false | mock |
| NS09_2026-11-30_lunch | NS09 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 152.3 | 3.67 | false | mock |
| NS09_2026-11-30_dinner | NS09 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 174.6 | 4.53 | false | mock |
| NS09_2026-12-01_breakfast | NS09 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 142.0 | 5.91 | false | mock |
| NS09_2026-12-01_lunch | NS09 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 229.2 | 8.60 | false | mock |
| NS09_2026-12-01_dinner | NS09 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 177.2 | 6.52 | false | mock |
| NS09_2026-12-02_breakfast | NS09 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 166.2 | 8.90 | false | mock |
| NS09_2026-12-02_lunch | NS09 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 192.4 | 5.16 | false | mock |
| NS09_2026-12-02_dinner | NS09 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 178.5 | 7.10 | false | mock |
| NS09_2026-12-03_breakfast | NS09 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 174.2 | 8.96 | false | mock |
| NS09_2026-12-03_lunch | NS09 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 192.9 | 6.95 | false | mock |
| NS09_2026-12-03_dinner | NS09 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 181.8 | 7.10 | false | mock |
| NS09_2026-12-04_breakfast | NS09 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 173.7 | 5.00 | false | mock |
| NS09_2026-12-04_lunch | NS09 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 203.2 | 10.26 | false | mock |
| NS09_2026-12-04_dinner | NS09 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 175.5 | 5.60 | false | mock |
| NS09_2026-12-05_breakfast | NS09 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 325.8 | 15.46 | false | mock |
| NS09_2026-12-05_lunch | NS09 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 419.0 | 21.23 | false | mock |
| NS09_2026-12-05_dinner | NS09 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 398.9 | 16.82 | false | mock |
| NS09_2026-12-06_breakfast | NS09 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 324.3 | 6.84 | false | mock |
| NS09_2026-12-06_lunch | NS09 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 376.8 | 14.43 | false | mock |
| NS09_2026-12-06_dinner | NS09 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | not_recorded | NULL | NULL | NULL | NULL | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS09_2026-11-30_breakfast | slot_1 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_1 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-11-30_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_breakfast | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_lunch | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-12-01_dinner | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_4 | 0.4 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-12-02_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-02_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_4 | 0.4 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-12-03_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-03_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_breakfast | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_2 | 0.2 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_3 | 0.2 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_4 | 0.4 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_5 | 0.2 | estimated | [] | mock |
| NS09_2026-12-04_lunch | slot_6 | 0.2 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_1 | 0.4 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_2 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_3 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_4 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_5 | 0.3 | estimated | [] | mock |
| NS09_2026-12-04_dinner | slot_6 | 0.3 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_2 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_5 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_breakfast | slot_6 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_1 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_3 | 0.7 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_4 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS09_2026-12-05_lunch | slot_6 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_1 | 0.7 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_2 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_3 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_4 | 0.7 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_5 | 0.6 | estimated | [] | mock |
| NS09_2026-12-05_dinner | slot_6 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_1 | 0.7 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_2 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_3 | 0.7 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_4 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_5 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_breakfast | slot_6 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_1 | 0.7 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_2 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_3 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_4 | 0.7 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_5 | 0.6 | estimated | [] | mock |
| NS09_2026-12-06_lunch | slot_6 | 0.6 | estimated | [] | mock |

### NS10

#### `meal_orders`

| `meal_order_id` | `patient_id` | `meal_plan_id` | `diet_category` | `diet_code` | `order_status` | `order_from` | `order_note` | `record_status` | `post_photo_id` | `staff_zero_reason` | `energy_kcal_est` | `protein_g_est` | `incomplete` | `data_source` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NS10_2026-11-30_breakfast | NS10 | 2026-11-30_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 403.4 | 19.00 | false | mock |
| NS10_2026-11-30_lunch | NS10 | 2026-11-30_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 459.9 | 12.22 | false | mock |
| NS10_2026-11-30_dinner | NS10 | 2026-11-30_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 593.4 | 15.93 | false | mock |
| NS10_2026-12-01_breakfast | NS10 | 2026-12-01_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 432.0 | 24.00 | false | mock |
| NS10_2026-12-01_lunch | NS10 | 2026-12-01_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 573.1 | 22.42 | false | mock |
| NS10_2026-12-01_dinner | NS10 | 2026-12-01_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 526.3 | 23.75 | false | mock |
| NS10_2026-12-02_breakfast | NS10 | 2026-12-02_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 408.7 | 24.42 | false | mock |
| NS10_2026-12-02_lunch | NS10 | 2026-12-02_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 553.3 | 16.58 | false | mock |
| NS10_2026-12-02_dinner | NS10 | 2026-12-02_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 443.9 | 19.21 | false | mock |
| NS10_2026-12-03_breakfast | NS10 | 2026-12-03_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 413.2 | 22.46 | false | mock |
| NS10_2026-12-03_lunch | NS10 | 2026-12-03_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | not_recorded | NULL | NULL | NULL | NULL | false | mock |
| NS10_2026-12-03_dinner | NS10 | 2026-12-03_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 443.6 | 18.27 | false | mock |
| NS10_2026-12-04_breakfast | NS10 | 2026-12-04_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 430.4 | 13.12 | false | mock |
| NS10_2026-12-04_lunch | NS10 | 2026-12-04_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 574.8 | 33.83 | false | mock |
| NS10_2026-12-04_dinner | NS10 | 2026-12-04_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 436.6 | 14.98 | false | mock |
| NS10_2026-12-05_breakfast | NS10 | 2026-12-05_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 396.9 | 17.39 | false | mock |
| NS10_2026-12-05_lunch | NS10 | 2026-12-05_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 581.1 | 28.28 | false | mock |
| NS10_2026-12-05_dinner | NS10 | 2026-12-05_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 521.7 | 22.22 | false | mock |
| NS10_2026-12-06_breakfast | NS10 | 2026-12-06_breakfast_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 409.1 | 8.53 | false | mock |
| NS10_2026-12-06_lunch | NS10 | 2026-12-06_lunch_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 583.0 | 23.00 | false | mock |
| NS10_2026-12-06_dinner | NS10 | 2026-12-06_dinner_general | 상식 | 일반상식 | ordered | 2026-11-30 breakfast | "" | recorded | NULL | NULL | 464.5 | 13.38 | false | mock |

#### `slot_intakes`

| `meal_order_id` | `slot_id` | `intake_fraction_est` | `status` | `quality_issues` | `estimate_basis` |
| --- | --- | --- | --- | --- | --- |
| NS10_2026-11-30_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-11-30_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_1 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_2 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_3 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_4 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_5 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_breakfast | slot_6 | 1.0 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-01_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-02_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-03_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-04_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_3 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_4 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_5 | 0.0 | estimated | [] | mock |
| NS10_2026-12-05_lunch | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-05_dinner | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_breakfast | slot_6 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_1 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_2 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_3 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_4 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_5 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_lunch | slot_6 | 1.0 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_1 | 0.9 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_2 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_3 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_4 | 0.9 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_5 | 0.8 | estimated | [] | mock |
| NS10_2026-12-06_dinner | slot_6 | 0.8 | estimated | [] | mock |

## 7일 요약 · 2026-12-06 기준

2026-11-30~12-06의 아침·점심·저녁 기록을 집계했다. 일별 목표 대비 비율은 기록된 끼니의 섭취 합계에 3을 곱하고 기록 끼니 수와 해당 날짜 목표량으로 나눠 산출했다. 확인된 전량 거부·미섭취는 0으로 포함하고, 금식·취소는 미기록과 별도로 셌다.

팀의 시연용 규칙을 적용했다. 계산 가능한 일별 비율의 7일 평균이 75% 미만이면 주의(`caution`)다. 같은 영양소가 50% 이하인 날이 5일 이상 연속이면 경고(`warning`)가 우선한다. 계산할 수 없는 날은 연속일을 끊는다.

| 환자 | 평균 에너지(%) | 평균 단백질(%) | 에너지 50% 이하 최장 연속일 | 단백질 50% 이하 최장 연속일 | 수준 | 해당 영양소 | 미기록 끼니 | 금식·취소 끼니 |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |
| NS01 | 89.4 | 99.2 | 0 | 0 | none | — | 0 | 1 |
| NS02 | 70.1 | 51.7 | 0 | 1 | caution | 에너지·단백질 | 0 | 0 |
| NS03 | 33.7 | 36.8 | 6 | 5 | warning | 에너지·단백질 | 0 | 0 |
| NS04 | 57.3 | 43.1 | 0 | 7 | warning | 단백질 | 0 | 0 |
| NS05 | 75.5 | 89.5 | 1 | 0 | none | — | 0 | 0 |
| NS06 | 71.9 | 82.0 | 1 | 1 | caution | 에너지 | 0 | 0 |
| NS07 | 78.6 | 89.8 | 0 | 0 | none | — | 0 | 0 |
| NS08 | 78.8 | 91.6 | 0 | 0 | none | — | 1 | 0 |
| NS09 | 46.2 | 53.3 | 5 | 5 | warning | 에너지·단백질 | 1 | 0 |
| NS10 | 80.0 | 90.8 | 0 | 0 | none | — | 1 | 0 |
