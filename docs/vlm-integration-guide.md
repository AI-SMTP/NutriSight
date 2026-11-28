# NutriSight — Claude VLM 백엔드 통합 가이드

## 1. 전달 상태
개인 Fork의 `feature/intake-claude-adapter` 브랜치 작업 기준. 최신 병합 기준 팀 develop `99d388e12b97c1a742ca7767e7ef299b4a240167`. 최종 어댑터 구현 및 독립 단위 검증 완료. 백엔드 전체 통합 검증은 팀 환경에서 수행한다. 팀 기본 FakeEstimator는 유지한다.

## 2. 파일 구성
| 파일(backend 기준) | 역할 |
|---|---|
| app/intake/claude_estimator.py | Claude 호출, 구조화 응답 검증, 공통 타입 변환, 예외 처리 |
| app/intake/image_preprocessing.py | 이미지 경로 및 파일 검증, JPEG 전처리 |
| app/config.py | SecretStr 기반 API 키 설정 |
| app/wiring.py | claude 어댑터 등록 및 클라이언트 생성 |
| pyproject.toml, uv.lock | 의존성 관리 |
| tests/test_claude_estimator.py | VLM 및 통합 테스트 |
| scripts/eval_intake.py | 최종 어댑터 평가 CLI |

## 3. 설치 및 설정
팀 프로젝트의 backend 디렉터리에서:

```bash
uv sync --locked --python 3.12.16
```

`backend/.env` 또는 환경 변수:

```dotenv
INTAKE_ADAPTER=claude
ANTHROPIC_API_KEY=<팀에서 제공한 API 키>
```

키는 Git에 커밋하지 않는다. 기본값은 fake이며, claude 선택 시 키 누락/공백은 ConfigError를 발생시킨다. 이미지 허용 루트는 `storage_paths(settings).photos_dir.resolve()`이다. Python 3.12, anthropic 2.14.0, Pillow 13.0.0, Pydantic 2.14.4 환경에서 검증했다.

## 4. 서비스 호출 및 계약
API 라우터와 Agent는 동일한 분석 실행기/IntakeEstimator 서비스를 사용한다. 모델을 직접 중복 호출하지 않는다.

```python
from pathlib import Path
from app.intake.types import EstimationRequest, SlotSpec

request = EstimationRequest(
    meal_order_id="example-order",
    baseline_image=Path("/example/var/photos/before.jpg"),
    post_image=Path("/example/var/photos/after.jpg"),
    slots=(SlotSpec("slot_1", "잡곡밥", 150.0, "bottom_left"),),
)
result = await estimator.estimate(request)
```

위 경로와 위치는 사용 예시이며 실제 팀 배식 정보로 대체한다. estimator는 팀 Wiring에서 구성한 인스턴스를 사용한다. 미배식 슬롯(served_g=0)은 상위 실행기에서 제외한다. 현재 Claude 어댑터는 빈 요청, 빈 ID, 중복 ID를 거부하며 요청 슬롯 개수는 동적이다. 모든 슬롯이 미배식인 경우에는 상위 실행기에서 호출하지 않는 정책을 팀에서 확인한다.

입력: meal_order_id, baseline_image, post_image, slots(SlotSpec: slot_id, menu_name, served_g, position). Claude에 전송되는 것은 두 이미지와 slot_id, menu_name, position이며 주문 ID와 배식 중량은 전송하지 않는다.

출력: EstimationResult(meal_order_id, slots, image_status, image_issues, estimate_basis, model_id, latency_ms, raw_response). 각 SlotEstimate는 slot_id, intake_fraction_est, status, quality_issues, note를 포함한다. estimate_basis는 `vlm:claude`이다.

- estimated: 0.0~1.0, 0.1 단위. not_determinable: null.
- 품질 코드: blur, occluded, angle, lighting, tray_mismatch. 적절한 코드가 없으면 빈 배열 허용.
- 요청 슬롯만 정확히 한 번씩 반환하고 요청 순서로 정렬한다.
- 이미지 전체 판단 불가 시 모든 슬롯 판단 불가. 부분 판단 불가 슬롯은 상위 집계에서 수치로 대체하지 않는다.
- 1.0은 시각적 잔량이 거의 없음을 의미하며 실제 완전 섭취 보증이 아니다.

## 5. 전처리와 호출 설정
허용 루트 외 경로, 비정상 파일 및 JPEG/PNG 이외 콘텐츠를 거부한다. 파일 크기 10MiB, 원본 최대 변 8192px, 최대 2400만 픽셀 제한 및 Pillow 이미지 폭탄 방어를 적용한다. EXIF 방향 보정, 투명 배경 흰색 합성, RGB, LANCZOS 축소, 최대 긴 변 1536px, JPEG 품질 85를 적용한다. 두 이미지를 모두 검증한 후에만 API를 호출한다.

최종 모델 claude-sonnet-5-5, V3 프롬프트, Schema B, max_tokens=1600, timeout=60초, SDK max_retries=0. Structured output JSON Schema와 Pydantic 검증을 함께 적용한다. 응답 중단 사유가 end_turn이 아니거나 슬롯 계약을 위반하면 결과를 사용하지 않는다.

## 6. 오류 및 운영 로그 연계
| 유형 | 처리 |
|---|---|
| ValueError | 요청/이미지 오류, API 호출 전 차단 가능 |
| ClaudeAPIError | EstimationError 하위 유형. HTTP 상태, 오류 유형/분류/코드, 마스킹 메시지 제공 |
| ClaudeResponseError | EstimationError 하위 유형. 유효하지 않은 응답 거부, model_id/latency_ms/raw_response 제공 |
| not_determinable | 정상적인 판단 불가 결과로 처리, 임의 수치 생성 금지 |

API 예외는 `from None`으로 일반 traceback의 원본 SDK 예외 표시를 억제한다. 메시지 마스킹은 모든 형태의 민감정보 제거를 보증하지 않으므로 원본 응답·로그 접근을 제한한다.

팀 분석 실행기에서 `var/logs/intake.jsonl`에 photo_id와 결과 메타데이터를 연계하고 작업 성공/실패 상태를 관리한다. 입력 이미지, API 키, 인증 헤더를 로그에 남기지 않는다. 실패 시 원본 응답 저장 정책은 팀 규격을 따르되 개인정보 보호를 적용한다. 재시도는 상위 실행기의 팀 정책(자동 재시도 1회)에 맡기며 어댑터는 반복 호출하거나 fake로 자동 대체하지 않는다. 이미지 전체 판단 불가 및 부분 판단 불가의 저장·집계 처리는 팀 규격에 따른다. 운영 로그와 재시도 연결은 아직 통합 검증하지 않았다.

## 7. 클라이언트 종료
`ClaudeIntakeEstimator.aclose()`가 구현되어 있다. 팀 lifespan 종료 시 진행 중인 작업을 종료/대기한 뒤 Claude 클라이언트를 닫도록 연계한다. 시작 실패 시 자원 정리도 고려한다. 팀 공통 runtime/lifespan은 이번 VLM 변경에서 수정하지 않았다.

## 8. 평가 스크립트 실행
backend 디렉터리에서:

```bash
uv run --no-sync python -m scripts.eval_intake --help
uv run --no-sync python -m scripts.eval_intake ../var/intake_eval/request_01.json --image-root ../var/intake_eval/images
```

두 번째 명령은 실제 API를 호출한다. 요청 JSON과 이미지는 별도로 준비해야 하며 현재 팀 브랜치에 실험 사진을 포함하지 않는다. 이미지 경로는 요청 JSON 파일 기준 상대 경로로 해석한다. 요청 예시:

```json
{
  "meal_order_id": "eval-01",
  "baseline_image": "images/before.jpg",
  "post_image": "images/after_01.jpg",
  "slots": [{"slot_id": "slot_1", "menu_name": "잡곡밥", "served_g": 150.0, "position": "bottom_left"}]
}
```

CLI는 팀 공통 결과 JSON을 표준 출력으로 반환하고 비동기 context manager로 SDK 클라이언트를 정리한다. 독립 실험의 버전 비교 및 JSONL 통계 기록 기능은 이 CLI에 이식하지 않았다. CLI help 및 import 검증 완료, 실제 API 실행은 팀 통합 시 확인한다.

## 9. 최종 테스트 결과
- Python 3.12.16, uv lock --check, 패키지 import, Ruff lint/format, git diff --check 통과.
- V3 B 프롬프트 독립 프로젝트와 완전 일치(2529자), API 예외 체인 수정 AST 검증 통과.
- Windows 순수 VLM 독립 단위 테스트 최종 38 passed, 2 skipped, 0 failed (30.02초).
- 팀 공통 conftest 및 app.main이 Unix 전용 fcntl을 import하므로 Windows에서 원본 테스트 수집이 차단됐다. 기존 테스트에서 앱 의존 테스트 및 공통 계약 클래스를 제외한 임시 파일을 생성해 `pytest --noconftest`로 실행하고 삭제했다. 원본 테스트는 보존했다.
- skip 2개는 심볼릭 링크 생성 제한에 따른 경로 탈출 검사다.
- 응답 검증, 동적 슬롯, 이미지 경로/콘텐츠 검증, 이미지 전처리, API 오류 및 마스킹은 실행된 독립 테스트에서 통과했다.
- 전체 회귀 테스트, 공통 계약 테스트, Wiring 및 실제 백엔드 연결은 미검증이다. Linux 팀 환경에서 원본 테스트와 전체 테스트를 실행한다.

```bash
uv run --no-sync pytest tests/test_claude_estimator.py -v
uv run --no-sync pytest --cov=app
```

## 10. 팀 통합 체크리스트
- [ ] Linux에서 원본 VLM 테스트와 전체 회귀 테스트 실행(심볼릭 링크 포함).
- [ ] Claude 선택 및 설정 키/사진 경로 확인, fake 기본 동작 유지 확인.
- [ ] 실제 백엔드 분석 실행기에서 동일 서비스 호출 및 결과 저장 확인.
- [ ] 상위 로그·재시도·판단 불가 처리 연결 확인.
- [ ] 앱 종료 시 aclose 연결 확인.
- [ ] 평가 CLI 또는 실제 시연 경로에서 API 정상 응답 확인.

실측 중량 및 MAE는 팀 합의에 따라 이번 프로젝트 범위에서 제외하며 통합 체크리스트에 포함하지 않는다.
