# NS07 · 환자 (patients)

**묶음**: 환자 컬렉션 · [데이터 모델](../../data-model.md) 2절 · 시연용 모의 데이터

## patients

| 필드 | 값 |
| --- | --- |
| `patient_id` | NS07 |
| `display_name` | 환자 NS07 |
| `sex` | female |
| `birth_year` | 1944 (2026-11-23 기준 만 82세) |
| `height_cm` | 154 |
| `default_diet_type` | general (병원 일반식) |
| `conditions` | 고혈압, 퇴행성 무릎관절염 |
| `diet_restrictions` | (없음) — 의료진이 기록한 별도 식이 제한 없음 |
| `ckd_dialysis` | none — 만성콩팥병 없음, 투석 해당 없음 |
| `observation_start` | 2026-11-23 |
| `data_source` | mock |

## patient_weights

| `measured_on` | `weight_kg` |
| --- | --- |
| 2026-10-23 | 52.0 |
| 2026-11-23 | 50.0 |

- BMI: 50.0 / 1.54² ≈ **21.1**
- 체중 감소: 한 달에 2.0 kg (**3.8%**), 의도하지 않은 감소. GLIM의 체중 감소 기준(6개월 내 5% 초과)에는 아직 해당하지 않는다.

## patient_targets

| `effective_from` | `energy_kcal` | `protein_g` | `source` | `note` |
| --- | --- | --- | --- | --- |
| 2026-11-23 | 1,500 | 55 | team_set | 모의 진료팀 설정 |

참고: 시스템 계산값

| 기준 | 에너지 | 단백질 |
| --- | --- | --- |
| ESPEN (체중 50 kg) | 30 kcal/kg → 1,500 kcal | 1.0 g/kg 이상 → 50 g 이상 |
| 2025 한국인 영양소 섭취기준 (여성 75세 이상) | 필요추정량 1,500 kcal | 권장섭취량 50 g |

진료팀 설정값이 있으므로 경고 판정에는 1,500 kcal · 55 g(체중당 1.1 g)을 쓴다.

## patient_assessments

| `assessed_on` | `kind` | `result` | `score` | `note` |
| --- | --- | --- | --- | --- |
| 2026-11-23 | mna_sf | at_risk | 10 | 영양불량 위험 (MNA-SF 8~11점 구간). 모의 평가. [MNA-SF 양식](https://www.mna-elderly.com/sites/default/files/2021-10/MNA-english.pdf) |
| 2026-11-23 | swallowing | no_cough_observed | | 아침 식사 중 사레·기침 관찰 없음. 정식 삼킴 평가는 하지 않음 |
| 2026-11-23 | chewing | denture_discomfort | | 딱딱한 반찬을 씹을 때 틀니가 불편하다고 말함 |
| 2026-11-23 | appetite_assist | reduced_appetite | | 식사 준비 때 포장 개봉 도움이 필요하고 스스로 식사함. 최근 식욕이 줄었다고 말함 |
| 2026-11-23 | pressure_injury | none | | 욕창 없음 |
| 2026-11-23 | refeeding_risk | not_high | | 모의 진료팀 평가에서 고위험 아님 |
