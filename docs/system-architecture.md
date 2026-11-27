# 하루 파일럿 시스템 구조 (팀 제안안)

**상태**: 팀 제안안 — 팀 회의에서 확정 전 · **작성일**: 2026-11-27
**관련 문서**: [데이터 모델](data-model.md) · [하루 파일럿 설계 전 검토](pilot-design-review.md) · [서비스 워크플로우](workflow.md) · [기획안](proposal.md)

[설계 전 검토](pilot-design-review.md)에서 정한 화면 4개, 기술 구성, 경고 규칙을 실제로 돌아가는 구조로 옮긴 안이다. 테이블과 필드는 [데이터 모델](data-model.md)에 정리했고, 이 문서의 ID·상태 값·필드 이름은 데이터 모델을 따른다. API의 요청·응답 스키마는 다음 단계에서 정한다.

## 1. 전제

| 항목 | 전제 |
| --- | --- |
| 목적 | 시연용 파일럿. 흐름이 처음부터 끝까지 동작하는지 검증한다. |
| 접근 제어 | **없음.** 로그인·권한·사용자 계정을 두지 않는다. 화면에서 역할(영양사·요양보호사·의사)을 고르는 것은 화면 구분일 뿐 권한이 아니다. |
| 실행 환경 | 대표자 PC 한 대. 프로세스 하나(FastAPI)가 API, 화면 정적 파일, 분석 작업, 이벤트 전달을 모두 맡는다. |
| 데이터 | 모의 환자와 팀이 직접 찍은 모의 식판만 쓴다. 그래서 외부 API(VLM, Claude)로 사진과 기록을 보내도 된다. |
| VLM | 모델은 테스트로 정한다. 이 문서는 **입출력 인터페이스**만 정의하고, 모델별 구현은 그 인터페이스를 따르는 어댑터로 둔다. |

## 2. 구성 요소

```mermaid
flowchart LR
  UI["브라우저 React 화면 4개"]

  subgraph server["FastAPI 프로세스 (대표자 PC)"]
    API["HTTP API (REST)"]
    STREAM["SSE 스트림"]
    BUS["이벤트 버스"]
    JOB["분석 작업 실행기"]
    INT["섭취 추정 IntakeEstimator"]
    NUT["영양 계산 · 경고"]
    REC["처방 추천 에이전트"]
    RAG["가이드라인 검색"]
  end

  subgraph storage["로컬 저장소"]
    DB[("app.db")]
    CK[("checkpoints.db")]
    FS["사진 폴더"]
    DOCS["RAG 문서"]
  end

  VLM(["VLM API"])
  CLAUDE(["Claude API"])

  UI -->|"업로드 · 조회 · 확정 · 질문"| API
  STREAM -->|"상태 · 경고 · 추천 · 대화 토큰"| UI
  API --> JOB
  JOB --> INT
  INT --> VLM
  JOB --> NUT
  NUT --> REC
  API --> REC
  REC --> CLAUDE
  REC --> RAG
  RAG --> DOCS
  REC --> CK
  JOB --> BUS
  NUT --> BUS
  REC --> BUS
  BUS --> STREAM
  API --> DB
  JOB --> DB
  NUT --> DB
  REC --> DB
  API --> FS
  JOB --> FS
```

| 구성 요소 | 하는 일 |
| --- | --- |
| 브라우저 화면 | ① 기준 식전 업로드(모바일), ② 식후 업로드(모바일), ③ 의사 대시보드 + 대화(PC), ④ 처리 상태 대시보드(PC). |
| HTTP API | 업로드, 조회, 처방 확정 같은 요청을 받는다. 화면 4개가 같은 API를 쓴다. |
| SSE | 서버가 화면으로 보내는 두 종류의 스트림. ① 시스템 이벤트(사진 처리 상태, 경고, 추천 카드), ② 대화 응답(토큰, 도구 호출). |
| 이벤트 버스 | 프로세스 안의 발행·구독 통로. 분석·경고·추천 모듈이 상태 변화를 발행하면, 연결된 SSE 구독자 모두에게 전달한다. |
| 분석 작업 실행기 | 업로드된 식후 사진을 `asyncio` 백그라운드 작업으로 분석한다. 동시 VLM 호출 수를 세마포어로 제한한다. |
| 섭취 추정 | `IntakeEstimator` 인터페이스. VLM 어댑터를 바꿔 끼워 모델을 비교한다. |
| 영양 계산·경고 | 칸별 섭취 비율 → 영양소 섭취량 → 일별 집계 → 주의/경고 판정. 외부 호출이 없는 순수 함수로 둔다. |
| 처방 추천 에이전트 | `create_agent` + Claude. 경고가 생기면 추천 카드를 만들고, 의사의 대화에 답한다. 대화 기록은 체크포인터(`checkpoints.db`)에 둔다. |
| VLM API | 섭취 추정에 쓰는 외부 모델. 테스트로 정한다. |
| 가이드라인 검색 | RAG 문서(`docs/research/rag-sources/`)에서 근거 구절을 찾는다. |

## 3. 핵심 흐름

### 3-1. 기준 식전 사진 (영양사)

1. 화면 ①이 날짜·끼니와 사진을 `POST /api/meals/{date}/{meal}/baseline`으로 보낸다.
2. 서버는 사진 내용을 검증(`PIL.Image.verify()`)하고, 서버가 만든 이름으로 사진 폴더에 저장한다. `photos`에 `kind=baseline`으로 기록하고 그 끼니의 `meal_plans.baseline_photo_id`에 연결한다. 파일럿은 식사 종류가 일반식(`general`) 하나뿐이라 날짜·끼니로 `meal_plans`를 찾는다.
3. 그 끼니에 **기준 사진을 기다리던 식후 사진**(`waiting_baseline`)이 있으면 분석 대기열에 다시 넣는다.
4. `photo.status_changed` 이벤트를 발행한다.

같은 끼니에 기준 사진을 다시 올리면 새 사진 행을 만들어 `baseline_photo_id`를 바꾸고(이전 사진 행은 남긴다), 그 끼니의 식후 분석을 모두 다시 실행한다 (결정). 이어서 일별 %와 경고를 다시 계산한다. 이미 확정된 처방은 확정 시점의 판단 기록이므로 바꾸지 않고, 추천은 자동 생성 규칙(경고 수준이 오를 때만)을 따른다. 기준 사진은 따로 검증하지 않고 저장만 한다 (결정).

### 3-2. 식후 사진 → 분석 → 경고 → 추천

```mermaid
sequenceDiagram
  participant C as ② 요양보호사 화면
  participant A as HTTP API
  participant J as 분석 작업 실행기
  participant I as IntakeEstimator
  participant N as 영양 계산·경고
  participant R as 처방 추천 에이전트
  participant E as 이벤트 버스 → SSE
  participant D as ③④ 의사·상태 화면

  C->>A: POST 식후 사진 (환자, 날짜·끼니)
  A->>A: 발주 확인 · 검증 · 저장 · status=uploaded
  A-->>C: 202 Accepted (photo_id)
  A->>J: 작업 등록
  J->>E: photo.status_changed (queued → analyzing, stage=intake)
  E-->>D: 상태 표시
  J->>I: estimate(기준 사진, 식후 사진, 칸 배치)
  I-->>J: 칸별 섭취 비율 · 상태
  J->>N: 끼니 영양소 섭취량 · 일별 집계 (stage=nutrition)
  J->>N: 경고 재판정 (stage=alert)
  N->>E: intake.updated · alert.changed
  E-->>D: 추이 · 경고 갱신
  alt 경고 수준이 올라감 (없음→주의, 주의→경고 등)
    N->>R: 추천 생성 요청 (환자 ID, stage=recommendation)
    R->>E: recommendation.created
    E-->>D: 추천 카드 표시
  end
  J->>E: photo.status_changed (done, outcome)
  E-->>D: 상태 표시
```

- 업로드 응답은 분석을 기다리지 않는다(`202`). 결과는 SSE로 받는다.
- 서버는 `meal_orders`에서 그 환자·끼니의 발주를 찾는다. 발주가 없거나 `order_status`가 `ordered`가 아니면(금식·취소) `409`로 거절한다. 받은 사진은 `photos`에 `kind=post`로 기록하고 `meal_orders.post_photo_id`에 연결한다. 재촬영하면 새 사진 행을 만들고 `post_photo_id`를 바꾼다.
- 칸별 추정은 `slot_intakes`에, 끼니 합계(`energy_kcal_est`·`protein_g_est`·`incomplete`)는 `meal_orders`에 저장한다. 사진 상태가 바뀔 때마다 `meal_orders.record_status`를 함께 바꾼다 (4절 표).
- 기준 사진이 없는 끼니의 식후 사진은 `waiting_baseline`으로 두고 분석하지 않는다.
- **전량 거부·전량 미섭취**: 요양보호사가 사진 대신 `POST /api/meal-orders/{id}/staff-zero`를 보내면, 사진·VLM 없이 모든 칸을 0%(`estimate_basis = "staff"`)로 저장한다. `meal_orders.staff_zero_reason`을 남기고 `record_status = recorded`로 바꾼 뒤, 영양 계산과 경고 평가(위 그림의 `N` 이후)를 같은 순서로 실행한다. 발주가 `ordered`가 아니면 `409`다.
- 추천은 **경고 수준이 올라갈 때만** 자동으로 만든다 (결정). 같은 수준이 이어지면 기존 카드를 유지하고, 의사가 고친 카드를 자동으로 덮어쓰지 않는다. 의사는 카드의 "다시 만들기"로 최신 데이터 기준 카드를 다시 만들 수 있다(이전 카드는 `superseded`).

### 3-3. 처방 대화 (의사)

1. 의사가 환자를 고르면 화면 ③이 그 환자의 스레드 목록과 최근 스레드를 불러온다.
2. 질문은 `POST /api/threads/{thread_id}/messages`로 보내고, 응답 본문을 **SSE 스트림**으로 받는다. `EventSource`는 GET만 지원하므로 화면은 `fetch` 스트림으로 읽는다.
3. 에이전트가 "처방 초안 작성" 도구로 추천 카드를 고치면 `recommendation.updated` 이벤트가 시스템 스트림으로도 나가, 왼쪽 추천 카드가 함께 바뀐다.

### 3-4. 처방 확정 (의사)

0. (선택) 의사가 추천 카드에서 처방 유형을 골라 항목을 추가하거나 기존 항목을 고친다 (`PATCH /api/recommendations/{id}`, `recommendation.updated` 이벤트). 추천 카드가 없는 환자에게는 `POST /api/patients/{id}/prescriptions`로 처방을 직접 작성해 확정한다.
1. 의사가 추천 카드에서 항목을 고르고 `POST /api/recommendations/{id}/confirm`을 보낸다.
2. 서버는 처방(`status=confirmed`)을 만들고 원래 추천과 연결한다. 에이전트는 이 API를 호출할 수 없다. 확정은 화면의 의사 조작으로만 일어난다.
3. `prescription.confirmed` 이벤트를 발행하고, 섭취 추이 그래프에 처방 시점이 표시된다.

## 4. 사진 처리 상태

```mermaid
stateDiagram-v2
  [*] --> uploaded
  uploaded --> waiting_baseline: 기준 사진 없음
  waiting_baseline --> queued: 기준 사진 업로드됨
  uploaded --> queued
  queued --> analyzing
  analyzing --> done: 4단계 완료
  analyzing --> not_determinable: 사진 전체를 판단할 수 없음
  analyzing --> failed: VLM 호출 실패 · 시간 초과 · 단계 오류
  failed --> queued: 재시도
  done --> queued: 기준 사진 교체
  not_determinable --> queued: 기준 사진 교체
  not_determinable --> [*]
  done --> [*]
```

사진 상태는 `photos.status`에, 처리 단계는 `photos.stage`에, 결과는 `photos.outcome`에 둔다 ([데이터 모델](data-model.md) 5절). 아래 표는 식후 사진 기준이다.

| `status` | 뜻 | `meal_orders.record_status` | 화면 ④ 표시 |
| --- | --- | --- | --- |
| `uploaded` | 저장됨, 작업 등록 전 | `pending` | 업로드됨 |
| `waiting_baseline` | 그 끼니의 기준 사진이 없어 보류 | `pending` | 기준 사진 대기 |
| `queued` | 분석 대기열에 있음 | `pending` | 대기 중 |
| `analyzing` | 처리 중. `stage`가 지금 단계를 나타낸다: `intake`(섭취 추정) → `nutrition`(영양 계산) → `alert`(경고 평가) → `recommendation`(처방 추천, 경고 수준이 올라갈 때만) | `pending` | 단계별 진행 표시 |
| `done` | 4단계 완료. 일부 칸이 판단 불가여도 `done`이다. `outcome`에 결과(`no_change` / `alert_changed` / `warning_raised`)를 남긴다. | `recorded` | 완료 (판단 불가 칸 수, `outcome`) |
| `not_determinable` | 사진 전체가 판단 불가 (식판이 아님, 심하게 흐림 등). 섭취 추정 단계에서 끝난다. | `not_determinable` | 판단 불가 · 재촬영 요청 |
| `failed` | 외부 호출 실패, 시간 초과, 단계 처리 오류. `error`에 단계 이름과 사유를 붙인다 (예: `intake: VLM timeout`). | `failed` | 실패 (단계·사유) · 재시도 버튼 |

- **칸 단위 판단 불가**와 **사진 단위 판단 불가**를 나눈다. 칸 하나가 가려졌다면 사진은 `done`이고, 그 칸만 `slot_intakes.status = not_determinable`이다.
- 식후 사진이 없는 발주는 `record_status = not_recorded`다.
- **추천 생성 실패는 사진을 `failed`로 만들지 않는다.** 섭취 기록과 경고는 이미 저장됐으므로 사진은 `done`으로 끝내고, `recommendations.status = failed`로 기록해 카드 자리에 실패를 표시한다 (12절).
- 재시도는 섭취 추정 단계부터 다시 한다.
- 기준 식전 사진은 분석하지 않으므로 `stage`·`outcome`을 쓰지 않는다.
- 서버를 다시 켜면 `queued`·`analyzing`으로 남은 사진을 대기열에 다시 넣는다.

## 5. 섭취 추정 인터페이스 (VLM 무관)

분석 작업 실행기는 아래 인터페이스만 안다. 모델마다 어댑터를 하나씩 만들고, 설정값으로 어떤 어댑터를 쓸지 고른다. 저울 실측 평가 스크립트도 같은 인터페이스로 여러 어댑터를 돌려 비교한다.

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str          # 칸 ID (예: "slot_3"). meal_plan_slots.slot_id
    menu_name: str        # 예: "두부조림"
    served_g: float       # 표준 배식량
    position: str         # 식판 안 위치 설명 (예: "윗줄 1 (왼쪽 끝)"). meal_plan_slots.position. 좌표를 쓰는 모델은 무시해도 된다.


@dataclass(frozen=True)
class EstimationRequest:
    meal_order_id: str    # 환자의 한 끼 (예: "NS07_2026-11-23_lunch")
    baseline_image: Path  # 끼니의 기준 식전 사진
    post_image: Path      # 환자의 식후 사진
    slots: tuple[SlotSpec, ...]  # 미배식 칸(served_g = 0)은 넣지 않는다


class SlotStatus(StrEnum):
    ESTIMATED = "estimated"
    NOT_DETERMINABLE = "not_determinable"


class QualityIssue(StrEnum):
    BLUR = "blur"
    OCCLUDED = "occluded"            # 손·수저 등이 칸을 가림
    ANGLE = "angle"                  # 기준 사진과 각도 차이가 큼
    LIGHTING = "lighting"
    TRAY_MISMATCH = "tray_mismatch"  # 기준 사진과 다른 식판·배치로 보임


@dataclass(frozen=True)
class SlotEstimate:
    slot_id: str
    intake_fraction_est: float | None  # 0~1, 0.1 단위. 판단 불가면 None
    status: SlotStatus
    quality_issues: tuple[QualityIssue, ...] = ()
    note: str = ""                     # 모델이 남긴 짧은 근거 (분석 로그·평가용)


@dataclass(frozen=True)
class EstimationResult:
    meal_order_id: str
    slots: tuple[SlotEstimate, ...]
    image_status: SlotStatus           # 사진 전체 판단 가능 여부
    image_issues: tuple[QualityIssue, ...]
    estimate_basis: str                # "vlm:<어댑터 이름>"
    model_id: str                      # 실제 호출한 모델 ID
    latency_ms: int
    raw_response: str                  # 평가·디버깅용 원문


class EstimationError(Exception):
    """외부 호출 실패·시간 초과. 사진 처리 상태를 failed로 만든다."""


class IntakeEstimator(Protocol):
    name: str

    async def estimate(self, request: EstimationRequest) -> EstimationResult: ...
```

- **도메인 실패는 값으로, 외부 실패는 예외로** 나눈다. 판단 불가는 `status`로 돌려주고, 네트워크·시간 초과는 `EstimationError`로 던진다.
- **확신도는 두지 않는다.** 모델이 확신하지 못하는 칸은 `not_determinable`로 돌리고 이유를 `quality_issues`에 남기도록 프롬프트에서 기준을 정한다.
- 결과의 `slots`에는 요청한 칸이 **빠짐없이 한 번씩** 있어야 한다. 실행기는 칸 ID가 빠지거나 남는 응답, 범위를 벗어난 비율을 검증해 `failed`로 처리한다.
- 출력 필드는 기존 계약(`intake_fraction_est`, `estimate_basis`, `status`)을 따른다. `estimate_basis`는 어댑터 이름까지 담아 모델 비교 결과를 기록에 남긴다.
- 반복 호출로 결과를 안정화할지(열린 문제)는 어댑터 안에서 정한다. 인터페이스는 바뀌지 않는다.

**결과 저장 (데이터 모델과의 대응)**

| 인터페이스 출력 | 저장 위치 |
| --- | --- |
| `SlotEstimate`의 `slot_id` · `intake_fraction_est` · `status` · `quality_issues` | `slot_intakes`의 같은 이름 필드 |
| `EstimationResult.estimate_basis` | 칸마다 `slot_intakes.estimate_basis`에 복사 (`vlm:<어댑터>`) |
| `image_status = not_determinable` | `photos.status`와 `meal_orders.record_status`를 `not_determinable`로 (칸 행은 만들지 않는다) |
| `image_issues` | 저장 위치 미정 (13절 4번) |
| `model_id` · `latency_ms` · `raw_response` · `note` | DB에 두지 않고 분석 로그(`var/logs/intake.jsonl`, `photo_id`와 함께)에 남긴다 |

`slot_intakes.estimate_basis`의 나머지 값은 이 인터페이스를 거치지 않는다. `staff`는 요양보호사의 전량 거부·전량 미섭취 확인(9절 `staff-zero`)이고, `mock`은 시드 데이터다.

## 6. 영양 계산·경고 모듈

외부 호출이 없는 순수 함수로 둔다. 테스트가 가장 쉬운 부분이므로 경계값을 테스트로 고정한다.

| 함수 | 입력 → 출력 |
| --- | --- |
| `meal_nutrients` | 칸별 섭취(`slot_intakes`) + 배식 계획(`meal_plan_slots`의 칸별 영양성분) → 끼니 에너지·단백질 섭취량(`energy_kcal_est`·`protein_g_est`), 불완전 여부(`incomplete`) |
| `daily_target` | 목표 이력(`patient_targets`) · 체중(`patient_weights`) · 성별·나이 + 날짜 → 그날 적용된 하루 목표 에너지·단백질과 출처(`team_set` / `espen_weight` / `kdri`) |
| `daily_intake` | 환자의 그날 발주·끼니 기록 + 그날 목표 → `daily_intakes` 한 행: 섭취량 합계, 목표 대비 %(기록된 끼니로 3끼 환산), 기록된 끼니 수, 미기록 끼니 수, 금식·취소 끼니 수 |
| `evaluate_alert` | 일별 섭취 이력(`daily_intakes`) + 규칙 설정 → `none` / `caution` / `warning`, 근거 기간, 근거 수치, 미기록 수 |

- 규칙의 임계값(75%, 50%)과 기간(7일, 연속 5일)은 설정값이다.
- **목표를 정하는 순서**: 진료팀이 설정한 목표(`team_set`)가 있으면 그것을 쓴다. 없으면 체중이 있을 때 ESPEN(30 kcal/kg, 단백질 1.0 g/kg), 체중이 없을 때 2025 한국인 영양소 섭취기준(성별·연령)으로 계산한다. 하루 %와 경고는 그날 적용된 목표를 분모로 쓰고, 목표가 바뀌어도 과거 날짜는 다시 계산하지 않는다 ([데이터 모델](data-model.md) 2절).
- 판단 불가 칸은 그 칸을 섭취량 합계에서 빼고 `meal_orders.incomplete`를 켠다.
- 끼니 처리 규칙은 [데이터 모델](data-model.md) 4절을 따른다. `recorded`는 포함(전량 거부·전량 미섭취는 0 섭취로 포함), `not_recorded`·`not_determinable`·`failed`는 평균에서 빼고 미기록으로 세며, `pending`은 아직 집계하지 않는다. 금식·취소는 평균에서 빼되 미기록으로 세지 않는다(`npo_meals`).
- 하루 % = 기록된 끼니 섭취 합계 × (3 ÷ 기록된 끼니 수) ÷ 그날 목표. 간식은 빼고 3끼 기준이다. 기록된 끼니가 없는 날은 NULL이다 ([데이터 모델](data-model.md) 6절).
- 경고 수준이 바뀌면 `alert.changed` 이벤트를 발행하고, 올라갔으면 추천 생성을 요청한다.

## 7. 처방 추천 에이전트

| 항목 | 제안 |
| --- | --- |
| 실행 | `langchain.agents.create_agent` + Claude. 추천 카드 생성과 대화가 같은 에이전트·같은 도구를 쓴다. |
| 추천 카드 | 같은 에이전트를 구조화 출력(카드 스키마)으로 한 번 실행해 저장한다. 구조화 출력 방식은 오전 검증 결과로 정한다 ([설계 전 검토](pilot-design-review.md) 4-2절의 기술 위험). |
| 대화 기록 | 체크포인터(`SqliteSaver` 계열)를 `checkpoints.db`에 둔다. `thread_id`는 스레드 ID이고, 스레드는 한 환자에게만 속한다. |
| 환자 범위 고정 | 도구는 요청마다 **선택한 환자 ID를 미리 묶어서** 만든다. 모델이 환자 ID를 인자로 고를 수 없으므로 다른 환자의 기록을 조회할 수 없다. 접근 제어가 아니라 맥락이 섞이지 않게 하는 장치다. |
| 확정 | 에이전트에는 처방 확정 도구를 주지 않는다. 초안 작성까지만 한다. |

**도구 (후보)**

| 도구 | 하는 일 |
| --- | --- |
| `get_intake_summary(days)` | 묶인 환자의 최근 섭취 추이, 경고 수준, 자주 남긴 메뉴 |
| `search_guidelines(query)` | 가이드라인 근거 구절 검색 → 문서 ID, 절, 본문, 출처 링크 |
| `draft_prescription(items)` | 묶인 환자의 추천 카드를 고친다. `recommendation.updated` 이벤트를 발행한다. |

**가이드라인 검색**: 문서가 4건(약 90쪽)뿐이라 처음에는 절 단위로 나눈 본문을 BM25로 검색한다. 한국어 문서 검색 품질이 부족하면 다국어 임베딩으로 바꾼다. 인터페이스(`search_guidelines`)는 그대로 둔다.

## 8. SSE 설계

### 8-1. 시스템 이벤트 스트림

`GET /api/events` — 화면 ③④가 `EventSource`로 구독한다. 화면 ①②는 자기가 올린 사진 상태만 보면 되므로 같은 스트림을 구독하고 자기 `photo_id`만 골라 쓴다.

```
event: photo.status_changed
id: 1042
data: {"photo_id": "p_81", "patient_id": "NS07", "meal_plan_id": "2026-11-27_lunch_general", "meal_order_id": "NS07_2026-11-27_lunch", "status": "analyzing", "stage": "intake", "at": "2026-11-27T12:31:05+09:00"}
```

| 이벤트 | 발행 시점 | 화면 |
| --- | --- | --- |
| `photo.status_changed` | 사진 처리 상태가 바뀔 때 | ①②④ |
| `intake.updated` | 끼니 섭취량이 새로 계산될 때 | ③④ |
| `alert.changed` | 환자의 경고 수준이 바뀔 때 | ③④ |
| `recommendation.created` · `recommendation.updated` | 추천 카드가 생기거나 고쳐질 때 | ③④ |
| `prescription.confirmed` | 처방이 확정될 때 | ③④ |

- 이벤트는 **"무엇이 바뀌었는지"만** 알린다. 화면은 이벤트를 받으면 해당 REST API로 최신 상태를 다시 읽는다. 그래서 이벤트를 놓쳐도 다음 조회에서 맞춰진다.
- 연결이 끊겼다가 다시 붙으면 화면은 보고 있던 데이터를 한 번 다시 읽는다. 놓친 이벤트를 다시 보내는 기능(`Last-Event-ID` 재전송)은 만들지 않는다.
- 연결 유지를 위해 15초마다 주석 줄(`: ping`)을 보낸다.

### 8-2. 대화 스트림

`POST /api/threads/{thread_id}/messages` — 응답이 `text/event-stream`이다. 에이전트의 스트림 출력을 아래 이벤트로 바꿔 보낸다.

| 이벤트 | 내용 |
| --- | --- |
| `token` | 답변 텍스트 조각 |
| `tool_start` | 도구 이름 (화면에 "섭취 요약 조회" 같은 표시) |
| `tool_end` | 도구 이름, 결과 요약 |
| `card_updated` | 이 대화로 추천 카드가 고쳐짐 (카드 ID) |
| `done` | 답변 끝 |
| `error` | 실패 사유 (화면 표시용 문장) |

## 9. HTTP API (초안)

| 메서드 · 경로 | 화면 | 하는 일 |
| --- | --- | --- |
| `GET /api/meals/{date}/{meal}` | ①② | 그 끼니의 배식 계획(칸 배치), 기준 사진 여부. 파일럿은 식사 종류가 `general` 하나라 경로에 두지 않는다. |
| `POST /api/meals/{date}/{meal}/baseline` | ① | 기준 식전 사진 업로드 |
| `GET /api/patients` | ②③ | 환자 목록과 경고 수준 |
| `GET /api/patients/{id}` | ③ | 환자 요약 카드: 기본 정보, 최근 체중과 변화, 현재 목표와 출처, 최근 평가 |
| `POST /api/photos` | ② | 식후 사진 업로드 (환자, 날짜·끼니) → `202`. 그 끼니의 발주가 없거나 `ordered`가 아니면(금식·취소) `409` |
| `GET /api/photos?date=&meal=` | ④ | 사진별 처리 상태(`status`·`stage`·`outcome`·`error`) |
| `POST /api/photos/{id}/retry` | ④ | `failed` 사진 재분석 |
| `POST /api/meal-orders/{id}/staff-zero` | ② | 전량 거부·전량 미섭취 확인 (`reason`: `refused` / `not_eaten`) → 모든 칸 0%, 근거 `staff` |
| `GET /api/patients/{id}/intake?days=14` | ③ | 일별 섭취 추이, 그날 목표, 기록·미기록·금식 끼니 수, 처방 시점 |
| `GET /api/patients/{id}/alert` | ③ | 현재 경고 수준과 근거 |
| `GET /api/patients/{id}/recommendation` | ③ | 현재 추천 카드 |
| `PATCH /api/recommendations/{id}` | ③ | 의사가 추천 항목을 추가·수정 (`added_by`·`last_modified_by = "doctor"`) |
| `POST /api/recommendations/{id}/confirm` | ③ | 고른 항목으로 처방 확정 |
| `POST /api/patients/{id}/recommendation/regenerate` | ③ | 추천 "다시 만들기": 최신 데이터로 새 카드를 만들고 이전 카드는 `superseded` |
| `POST /api/patients/{id}/prescriptions` | ③ | 추천 없이 의사가 처방을 직접 작성해 확정 |
| `GET /api/patients/{id}/prescriptions` | ③ | 처방 이력 |
| `GET /api/patients/{id}/threads` · `POST` | ③ | 환자의 스레드 목록 · 새 대화 |
| `GET /api/threads/{id}/messages` | ③ | 스레드의 지난 메시지 |
| `POST /api/threads/{id}/messages` | ③ | 질문 → 대화 스트림 (SSE) |
| `GET /api/events` | ①~④ | 시스템 이벤트 스트림 (SSE) |

리셋은 HTTP API로 두지 않는다(제안). 시드 상태로 되돌릴 때는 앱을 끈 상태에서 `uv run python -m scripts.seed`로 리셋한 뒤 앱을 다시 시작한다. 앱이 실행 중이면 리셋 명령은 `var/app.lock` 때문에 실행을 거절한다.

## 10. 저장소

| 위치 | 내용 |
| --- | --- |
| `var/app.db` | 업무 데이터: 환자, 예정 식단(칸·배식량·영양성분), 실제 발주된 식사(칸별 섭취), 사진, 일별 섭취, 경고, 추천, 처방, 스레드 목록. 환자·발주·사진 행에 데이터 출처(`data_source`: `mock` / `upload`)를 두고, 칸별 섭취는 `estimate_basis`로 출처를 구분한다. |
| `var/checkpoints.db` | 에이전트 체크포인터 (대화 상태). 업무 DB와 나눠 리셋을 쉽게 한다. |
| `var/photos/` | 사진 파일. 이름은 서버가 만든다 (`<photo_id>.jpg`). |
| `var/logs/intake.jsonl` | 섭취 추정 분석 로그: 사진 ID, 모델 ID, 응답 시간, 칸별 근거(`note`), 원문. 어댑터 비교와 디버깅용 |
| `data/seed/` | 모의 환자 10명, 배식 계획, 발주(특이사항 포함), 7일 모의 섭취 이력. 배식 계획과 발주는 화면에서 입력하지 않고 여기서만 넣는다. 날짜는 시연일 기준 상대 날짜(D-7~D-1, 시연일 D는 배식 계획과 발주)로 넣는다 ([시연 환자 구성](samples/README.md)). |
| `docs/research/rag-sources/` | RAG 문서 원본 |

테이블과 필드는 [데이터 모델](data-model.md)에 정리했다. 데이터는 환자, 예정 식단, 실제 발주된 식사의 세 묶음으로 나눈다. 리셋은 행 단위로 업로드분을 골라 지우지 않고 DB를 시드로 다시 만든다. 리셋은 앱을 끈 상태에서 CLI로만 하고, 임시 파일에 새 DB를 만든 뒤 기존 `app.db`를 원자적으로 교체한다(제안). 그래서 일별 섭취·경고·추천·처방·스레드에는 출처 필드를 두지 않는다.

## 11. 코드 구성 (제안)

```
backend/
  app/
    main.py            FastAPI 앱, 정적 파일, 시작 시 미완료 작업 복구
    config.py          설정 (어댑터 선택, 임계값, 동시 호출 수, 경로)
    api/               라우터: meals, photos, patients, recommendations, threads, events
    events/            이벤트 버스, SSE 직렬화
    jobs/              분석 작업 실행기 (대기열, 세마포어, 상태 전이)
    intake/            IntakeEstimator 인터페이스, VLM 어댑터들, 응답 검증
    nutrition/         목표량, 섭취량 환산, 일별 집계, 경고 규칙
    recommender/       에이전트, 도구, 카드 스키마, 가이드라인 검색
    storage/           SQLite 접근, 사진 저장
  tests/
  scripts/
    seed.py            모의 데이터 넣기
    eval_intake.py     저울 실측 식판으로 어댑터 비교
frontend/              React (Vite). 빌드 결과를 FastAPI가 제공
data/seed/
var/                   실행 중 생기는 파일 (git 제외)
```

모듈 담당([설계 전 검토](pilot-design-review.md) 7절)과 이렇게 맞춘다: 섭취 추정 → `intake/`·`eval_intake.py`, 영양 계산·경고 → `nutrition/`·`seed.py`, 백엔드·화면 → `api/`·`events/`·`jobs/`·`storage/`·`frontend/`, 처방 추천 → `recommender/`.

## 12. 실패 처리

| 상황 | 처리 |
| --- | --- |
| VLM 호출 실패·시간 초과 | 사진 `failed`, 화면 ④에 재시도 버튼. 자동 재시도는 1회. |
| VLM 응답이 형식에 맞지 않음 | `failed`로 처리하고 원문을 분석 로그(`var/logs/intake.jsonl`)에 남긴다. |
| 영양 계산·경고 평가 중 오류 | 사진 `failed`, `error`에 단계 이름을 붙인다 (예: `nutrition: ...`). |
| 기준 사진 없음 | `waiting_baseline`. 기준 사진이 올라오면 자동으로 분석한다. |
| 추천 생성 실패 | 사진은 `done`으로 끝내고 `recommendations.status = failed`로 기록한다. 경고는 그대로 표시하고 카드 자리에 "추천 생성 실패 · 다시 만들기"를 둔다. |
| 대화 중 실패 | 대화 스트림에 `error` 이벤트를 보내고, 스레드는 이어서 쓸 수 있게 둔다. |
| 서버 재시작 | 미완료 분석을 대기열에 다시 넣는다. 대화는 체크포인터에서 이어진다. |

## 13. 열린 문제

1. **VLM 선정** — 저울 실측 식판으로 어댑터를 비교해 정한다. 반복 호출로 결과를 안정화할지도 함께 정한다.
2. **추천 카드 구조화 출력** — `create_agent` + Claude에서 어떤 방식이 동작하는지 오전에 확인한다.
3. **가이드라인 검색 품질** — BM25로 한국어·영어 혼합 문서에서 근거를 잘 찾는지 확인하고, 부족하면 임베딩으로 바꾼다.
4. **사진 단위 품질 문제 저장** — 사진 전체가 판단 불가일 때의 `image_issues`를 화면 ④에 보여 줄 칸이 데이터 모델에 없다. `photos`에 `quality_issues`를 더할지 데이터 모델에서 정한다.
