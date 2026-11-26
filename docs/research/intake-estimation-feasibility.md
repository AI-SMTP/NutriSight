# 식전·식후 사진 기반 섭취량 판단 가능성 검토 (OpenCV · VLM)

**작성일**: 2026-11-26 · **관련 문서**: [기획안](../proposal.md), [서비스 워크플로우](../workflow.md)

## 결론 요약

- **판단은 가능하다.** 단, 목표를 "메뉴별 섭취 그램"이 아니라 **"칸별 섭취 비율(0~100%)"**로 잡을 때 그렇다. 일반식은 배식 계획에 메뉴별 급여량이 있으므로, 비율만 맞으면 열량·영양소로 환산할 수 있다.
- **현실적인 정확도 목표는 사람의 눈대중 수준**이다. 현장에서 쓰는 4분위 눈대중(0·25·50·75·100%)은 저울 실측과 높은 일치도가 검증된 방법이다. 반면 간호 기록지는 저울과 60.8%만 일치했다. 메뉴별 섭취율 평균 절대오차 **10~15%p 이내**면 기존 기록보다 나은 수준이다.
- **권장 구성은 OpenCV를 주 추정기로, VLM을 보조로 쓰는 방식이다.**
  - OpenCV: 식판 검출·펴기, 칸 분리, 남은 음식 면적 비율 계산
  - VLM: 사진 품질 검사, 메뉴 확인, 4분위 판정을 비교 기준으로 제공
- VLM 단독으로 그램을 추정하는 방식은 오차가 커서(음식당 35~50%) 숫자를 기록하는 용도로는 부족하다. 다만 메뉴 이름과 같은 맥락을 주고 비율이나 4분위로 판정하게 하면 쓸 만한 비교 기준이 된다.

## 1. 문제를 어떻게 정의하느냐가 핵심이다

| 정의 | 난이도 | 이유 |
| --- | --- | --- |
| 사진 한 장에서 음식 그램 추정 | 높음 | 카메라 거리와 각도를 모르면 실제 크기를 알 수 없고, 높이(부피)도 보이지 않는다. |
| 식전·식후 사진에서 칸별 **남은 비율** 추정 | **중간** | 같은 식판, 같은 칸을 비교하므로 크기 기준이 상쇄된다. 식판 칸 구조가 위치를 알려준다. |
| 칸별 **4분위 판정** (0·25·50·75·100%) | 낮음 | 현장의 눈대중 기준과 같다. 대부분의 음식은 "다 먹음, 한두 입 먹음, 안 먹음"에 몰린다. |

NutriSight는 다음 조건 때문에 두 번째와 세 번째 정의에 해당한다. 그래서 일반적인 "AI 칼로리 측정"보다 쉬운 문제다.
- 대상은 일반식이다.
- 칸이 나뉜 식판을 쓴다.
- 식전 사진이 있다.
- 배식 계획에 급여량이 있다.

## 2. 선행 사례로 본 정확도 수준

| 사례 | 방식 | 결과 |
| --- | --- | --- |
| 저울 대비 4분위 눈대중 (학교 급식 748개 식판) | 사람 눈대중 | 87%의 음식이 저울과 상당 이상 일치 (weighted κ) |
| 디지털 사진 눈대중 (Williamson 2003) | 사람이 사진을 보고 판정 | 저울과 r = 0.92 |
| 이탈리아 병원 파일럿 (2025, 362끼) | Mask R-CNN + 면적→중량 회귀, 고정 카메라 | MAE 약 40 g (식판 무게의 약 10%). 간호 기록지는 저울과 60.8% 일치 |
| 인도네시아 병원 식사 (2025) | Mask R-CNN + 단안 깊이 추정, 통제 환경 | 잔반 비율 MAE 약 10.5% |
| 장기요양시설 (Pfisterer 2022) | RGB-D 카메라 + 분할 | 평균 섭취 오차 −4.2% |
| 한국 식판 (Applied Sciences 2023) | Mask R-CNN + **식판 기준 호모그래피 보정** | 다른 각도로 찍은 식후 사진을 식전 구도로 맞춤. 국은 면적 변화가 작아 섭취량을 과소 추정 |
| GPT-4V 섭취량 추정 (2023) | VLM 단독 | MAE 54.6 g (영양사 눈대중 43.6 g), r = 0.78 |
| GPT-4o 잔반 추정 (2025) | VLM + 메뉴 이름 제공 | 저울과 r = 0.87. 메뉴 이름을 주면 정확도가 오르고, 재료별 양까지 주면 오히려 떨어짐 |
| 오픈소스 VLM 벤치마크 (2026) | VLM 단독, 그램 추정 | 오픈 모델은 상용 모델보다 낮음. 상용 최고(GPT-4o) MAE 35 g |
| 최신 대형 VLM 비교 (2026, Nutrition5k) | VLM 단독, 음식별 그램 | 음식별 MAE 24~36 g (상대오차 35~53%). 작은 전용 추정 모듈을 붙이면 16.5 g |
| 휴대 촬영 3D 복원 (CVPR 2026 챌린지) | 단안 3D 복원으로 부피 차이 계산 | 섭취 부피 MAPE 54%. "전후 차이는 두 추정 오차가 더해져 커진다" |

**읽는 법**
- 높은 정확도를 낸 사례는 대부분 **고정 카메라나 깊이 카메라**를 썼다. 개인 기기로 찍는 NutriSight에서는 같은 수준을 기대하기 어렵다.
- 휴대 촬영으로 부피를 직접 복원하는 방식은 오차가 크다. 비율 비교로 문제를 좁히는 것이 맞다.
- VLM은 사람 눈대중과 비슷한 수준이지만 더 낫지는 않다. 메뉴 이름 같은 맥락을 주면 좋아진다.

## 3. OpenCV 방식 검토

### 처리 흐름

1. **식판 검출** — 식판 외곽선(사각형)을 찾는다. 식판 색이 단색이면 색 기준 이진화와 윤곽선 검출로 충분하다.
2. **원근 보정** — 식판 네 꼭짓점으로 호모그래피를 구해 정면에서 본 직사각형으로 편다. 식전·식후 사진이 같은 좌표계로 맞춰진다. 한국 식판 선행연구와 같은 방법이다.
3. **칸 분리** — 식판 규격이 고정되어 있으므로, 칸 위치를 템플릿(정규화 좌표)으로 미리 정해 둔다. 학습이 필요 없다.
4. **음식 영역 추출** — 칸마다 "빈 칸 색"과 다른 픽셀을 음식으로 본다. 빈 식판 사진을 기준으로 쓰면 안정적이다 (HSV 거리, 적응형 임계값, 형태학 연산).
5. **남은 비율** — `식후 음식 면적 ÷ 식전 음식 면적`. 메뉴별 보정 계수(선형회귀)를 저울 실측으로 맞춘다.

### 장점
- 학습 데이터 없이 바로 동작한다. 금요일 필수 목표(반찬 1종 이상)를 달성하는 데 적합하다.
- 결과가 결정적이고 설명 가능하다. 칸별 마스크를 화면에 겹쳐 보여줄 수 있다.
- 로컬에서 돌아가 환자 사진을 외부로 보내지 않는다.

### 한계와 대응

| 한계 | 영향 | 대응 |
| --- | --- | --- |
| 면적은 부피가 아니다 | 밥처럼 쌓인 음식은 위만 먹어도 면적이 그대로다 | 메뉴별 면적→섭취율 보정 곡선. 밥·국은 VLM 판정과 비교 |
| 국그릇 | 그릇 벽이 경사져 수위가 내려가도 면적 변화가 작다 | 국은 별도 처리(수면 타원 크기 또는 VLM 판정), 파일럿 1단계에서는 제외 검토 |
| 양념·국물 자국 | 빈 칸이 음식으로 잡힌다 | 면적 하한, 채도·질감 기준 추가. 빈 식판 기준 사진과 비교 |
| 조명·화이트밸런스 차이 | 색 기준 분할이 흔들린다 | 식판 흰 영역으로 색 정규화, LAB 색공간 사용 |
| 식판 일부가 잘림 또는 손·수저가 가림 | 호모그래피 실패 | 업로드 시 품질 검사 후 재촬영 요청 |
| 섞어 먹음 (밥에 반찬을 올림) | 칸 단위 가정이 깨짐 | 칸 기준으로만 기록하고, 이상치는 경고 대신 "확인 필요"로 표시 |

### 학습 기반 분할을 붙인다면
- 칸별로 점 하나를 프롬프트로 주는 SAM 계열 분할을 쓰면, 학습 없이 음식 경계를 더 잘 잡을 수 있다. 색 기준 분할이 흔들릴 때의 대안이다.
- 단안 깊이 추정(Depth Anything 등)은 밥 높이 변화를 보강할 수 있다. 하지만 휴대 촬영에서는 오차가 커서 선택 사항이다.

## 4. VLM 방식 검토

### 할 수 있는 것
- **4분위·비율 판정**: 식전·식후 사진 두 장과 칸별 메뉴 이름을 주고 "칸별 남은 비율을 0·25·50·75·100% 중 하나로" 답하게 한다. 사람 눈대중 수준이 기대된다.
- **사진 품질 검사**: 식판 전체가 나왔는지, 가려진 칸은 없는지, 식전·식후가 같은 식판인지 판정한다.
- **메뉴 확인**: 배식 계획의 메뉴와 사진 속 음식이 맞는지 확인한다.
- **결과 설명**: 의료진 화면에 "단백질 반찬을 3끼 연속 남김" 같은 요약을 만든다.

### 한계

| 한계 | 내용 |
| --- | --- |
| 정밀 수치 | 그램 단위 추정은 음식당 35~50% 오차. 영양소 기록의 주 근거로 쓰기 어렵다 |
| 재현성 | 같은 입력에도 답이 달라질 수 있다. 의료 기록으로 남기려면 온도 0, 다회 판정 다수결이 필요하다 |
| 개인정보 | 실제 환자 사진을 외부 API로 보내려면 병원의 동의·보안 검토가 필요하다. 파일럿은 모의 식판만 쓰므로 문제없다. 실제 운영은 로컬 오픈소스 모델(Qwen2.5-VL 7B 등)을 검토해야 하는데, 이 모델들은 상용 모델보다 정확도가 낮다 |
| 비용·지연 | 끼니당 API 호출 비용과 수 초의 지연이 든다. 파일럿 규모에서는 문제없다 |
| 프롬프트 민감도 | 단위나 맥락 제공 방식에 따라 결과가 크게 바뀐다 (선행연구: 재료별 양을 주면 오히려 악화) |

## 5. 권장 구성

```
업로드(식전/식후)
   │
   ├─▶ [VLM] 사진 품질 검사 ── 실패 ─▶ 재촬영 요청
   │
   ▼
[OpenCV] 식판 검출 → 원근 보정 → 칸 분리 → 음식 영역 → 칸별 남은 비율
   │
   ├─▶ [보정] 메뉴별 면적→섭취율 보정 (저울 실측으로 학습)
   │
   ├─▶ [VLM] 칸별 4분위 판정 (비교·교차검증)
   │        └─ OpenCV 결과와 크게 어긋나면 status = "확인 필요"
   ▼
섭취율 × 배식 계획 급여량 → 열량·영양소 섭취량
```

- **주 추정기는 OpenCV**다. 결정적이고 설명 가능하며 로컬에서 동작한다.
- **VLM은 품질 검사와 교차검증**에 쓴다. 두 방식이 어긋나는 칸을 "확인 필요"로 표시하면, 의료진이 신뢰할 수 있는 결과만 경고에 반영된다.
- 기획안의 "면적비 또는 선형회귀를 비교 기준으로" 계획과 이어진다. MLP는 보정 데이터가 충분히 모인 뒤의 선택 사항으로 둔다.

## 6. 검증 실험 제안 (모의 식판)

| 항목 | 내용 |
| --- | --- |
| 정답값 | 칸별 저울 실측 배식량과 잔반량에서 구한 섭취율 |
| 비교 대상 | ① OpenCV 면적비 ② OpenCV + 메뉴별 보정 ③ VLM 4분위 ④ 팀원 눈대중(4분위) |
| 지표 | 칸별 섭취율 MAE(%p), 4분위 일치율·weighted κ, 메뉴 유형별 오차(밥·국·반찬) |
| 촬영 조건 | 개인 기기, 같은 식판을 각도·거리·조명을 바꿔 촬영 (실사용 조건 재현) |
| 합격선 (제안) | 반찬 섭취율 MAE ≤ 15%p, 팀원 눈대중과 비슷하거나 나은 수준 |

## 7. 남은 확인 사항

1. **식판 규격** — 실제로 쓸 식판의 모양, 칸 수, 색, 국그릇이 식판에 포함되는지. 칸 템플릿과 국 처리 방식이 여기서 정해진다.
2. **국 처리** — 파일럿 1단계에서 국을 포함할지.
3. **VLM 사용 범위** — 파일럿에서 외부 API를 써도 되는지(모의 데이터만 사용), 실제 운영을 위해 로컬 모델까지 검토할지.

## 참고 문헌

- Hoy et al. (2013). Visual inspection of cafeteria waste by quarter servings rivals the accuracy of weighing. *JNEB*. https://www.jneb.org/article/S1499-4046(13)00304-7/fulltext
- Getts et al. (2017). Validity and interrater reliability of the visual quarter-waste method. https://pmc.ncbi.nlm.nih.gov/articles/PMC7261231/
- Martin et al. (2013). Measuring food intake with digital photography. https://pmc.ncbi.nlm.nih.gov/articles/PMC4138603/
- Favaretto et al. (2026). Enhancing hospital nutrition assessment through AI: a prospective tray-level pilot study. https://pmc.ncbi.nlm.nih.gov/articles/PMC13118341/
- Rizaluddin et al. (2025). From pixels to portions: segmentation and depth estimation for measuring food leftovers in hospital meals. https://doi.org/10.1109/icdsg67714.2025.11381375
- Pfisterer et al. (2022). Automated food intake tracking requires depth-refined semantic segmentation in long-term care. https://pmc.ncbi.nlm.nih.gov/articles/PMC8742067/
- Papathanail et al. (2021). Evaluation of a novel AI system to monitor energy and macronutrient intake in hospitalised older patients. https://www.mdpi.com/2072-6643/13/12/4539
- Food classification and meal intake amount estimation through deep learning (2023). *Applied Sciences* 13(9):5742. https://www.mdpi.com/2076-3417/13/9/5742
- Kwon et al. (2024). Amount estimation method for food intake based on color and depth images. *Sensors* 24(7):2044. https://www.mdpi.com/1424-8220/24/7/2044
- Dietary assessment with multimodal ChatGPT (GPT-4V) (2023). https://arxiv.org/pdf/2312.08592v1.pdf
- Morren et al. (2025). AI to the rescue: a novel approach to measure plate leftovers. https://doi.org/10.2139/ssrn.5107665
- Marchetti et al. (2026). Benchmarking open-source VLMs for food image recognition and portion size estimation. https://pmc.ncbi.nlm.nih.gov/articles/PMC13764829/
- Liao & Li (2026). Geometry-enhanced portion estimation for multimodal LLMs. https://arxiv.org/abs/2607.16514
- PerBite (2026). A curated diagnostic workflow for bite-aware food volume estimation. https://arxiv.org/html/2606.02021
- 누비랩 (2022). 영상 기반 급식 잔반량 추정을 위한 신규 음식 대응형 영상 분할 기술 개발. https://scienceon.kisti.re.kr/srch/selectPORSrchReport.do?cn=TRKO202400004576
