# NutriSight 프론트엔드

화면 ①(기준 식전 사진 업로드)·②(식후 사진 업로드)와 역할 선택, 촬영 확인(`/camera-check`)을 담은 Vite + React + TypeScript(strict) 앱이다. 실제 업로드 API와 SSE는 T3이 만든다. 그 전까지는 임시 계약(`src/api/provisional.ts`)과 MSW 모의로 동작한다. 모든 설계는 팀 제안안이다.

- 스펙: `docs/_local/active/frontend-shell-upload/spec.md`
- 계획: `docs/_local/active/frontend-shell-upload/implementation-plan.md`

## 1. 실행 환경과 명령

- Node 24(`.nvmrc`, `engines.node >=24`), pnpm 12.15.0(`package.json`의 `packageManager`).
- 설치: `cd frontend && pnpm install --frozen-lockfile`
- E2E용 브라우저 설치(네트워크 필요, 한 번만): `pnpm exec playwright install chromium`

### 실행 모드

| 명령            | 동작                                                                                                                                                                                    |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm dev`      | Vite 개발 서버. `/api`를 `http://127.0.0.1:8000`(`VITE_API_TARGET`로 변경)으로 프록시한다. 실제 백엔드가 필요하다                                                                       |
| `pnpm dev:mock` | `VITE_API_MOCK=1`. MSW 워커가 임시 계약을 모의한다. 백엔드 없이 동작한다                                                                                                                |
| `pnpm build`    | `tsc -b && vite build`. `frontend/dist`에 빌드한다. `VITE_API_MOCK`이 없으면 MSW 코드는 번들에 들어가지 않는다                                                                          |
| `pnpm gen:api`  | 백엔드 OpenAPI를 `src/api/generated/openapi.json`으로 내보내고(`uv run --frozen --directory ../backend python -m scripts.export_openapi`) `openapi-typescript`로 `schema.d.ts`를 만든다 |
| `pnpm test`     | Vitest(jsdom, MSW node 서버) 한 번 실행. 커버리지는 `pnpm test --coverage`                                                                                                              |
| `pnpm e2e`      | Playwright. `pnpm dev:mock`을 웹 서버로 띄운다                                                                                                                                          |

### 검사 명령

| 명령                | 동작                                  |
| ------------------- | ------------------------------------- |
| `pnpm typecheck`    | `tsc -b --noEmit`                     |
| `pnpm lint`         | `eslint .`                            |
| `pnpm format`       | `prettier --write .`                  |
| `pnpm format:check` | `prettier --check .`                  |
| `pnpm preview`      | 빌드 결과를 Vite 미리보기 서버로 연다 |

### 번들 검사

기본 빌드에 MSW와 `src/mocks/`가 없고 모의 빌드에는 있음을 확인한다. 아래 순서로 실행한다.

1. `pnpm check:bundle` — 기본 빌드를 `frontend/dist`에 만들고 `.build-report/modules.default.json`을 검사한다.
2. `pnpm check:bundle:mock` — `dist`의 해시를 기록하고, 모의 빌드를 `frontend/.build-report/dist-mock/`에 만들어 검사한 뒤, `dist`가 바뀌지 않았는지 비교한다.

`check:bundle:mock`은 1번이 만든 `dist`와 `.build-report/`를 전제로 하므로 1번 뒤에 실행한다. `.build-report/`는 git이 무시한다.

### E2E 설정

`playwright.config.ts` 기준이다.

- 웹 서버: `VITE_MOCK_STEPS=manual pnpm dev:mock --port 5180 --strictPort`. 포트 5180, 기존 서버를 재사용하지 않는다.
- `VITE_MOCK_STEPS=manual`이면 모의 처리가 첫 `analyzing`에서 멈춘다. 테스트가 `window.__nutrisightMock.finishAll()`로 남은 단계를 끝낸다. 각 테스트는 `window.__nutrisightMock.reset()`으로 시작한다. 이 전역은 MSW 모드에서만 생긴다.
- 뷰포트 390×844, Chromium 프로젝트 하나.

### 백엔드가 빌드 결과를 제공하는 방법

`pnpm build`가 만든 `frontend/dist`를 FastAPI가 `/`에서 제공한다.

- `backend/app/config.py`: `Settings.frontend_dist`(환경 변수 `FRONTEND_DIST`)의 기본값이 `<저장소 루트>/frontend/dist`이다. 상대 경로는 저장소 루트 기준으로 해석한다.
- `backend/app/main.py`: `create_app()`이 `/api` 라우트를 모두 등록한 뒤, `frontend_dist/index.html`이 있을 때만 정적 파일을 등록한다. 없으면 정적 제공 없이 시작한다(INFO 로그).
- SPA 대체 응답(`index.html`)은 라우팅 결과가 404이고, 경로가 `/api`로 시작하지 않으며, GET·HEAD 요청이고, `Accept`에 `text/html`이 있을 때만 준다. API의 JSON 404와 405는 그대로 둔다.

## 2. 임시 API 계약과 T3 인계

정본은 스펙 3.3절이다. 아래는 요약이고, 어긋나면 스펙을 따른다. 필드 이름과 상태 값은 `docs/data-model.md`를 따른다. 굵게 쓴 항목은 이 토픽이 제안하는 확장이다.

| 메서드 · 경로                            | 요청                                           | 응답                                                                             | 오류                  |
| ---------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- | --------------------- |
| **`GET /api/meta`**                      | —                                              | `{demo_date}`                                                                    | —                     |
| `GET /api/meals/{date}/{meal}`           | `meal`: `breakfast`·`lunch`·`dinner`           | `{meal_plan_id, date, meal, slots[6], baseline_photo \| null, `**`orders[]`**`}` | 404                   |
| `POST /api/meals/{date}/{meal}/baseline` | multipart `file`                               | 201 `{photo_id, uploaded_at}`                                                    | 404 · 413 · 422       |
| `POST /api/photos`                       | multipart `file`, `patient_id`, `date`, `meal` | 202 `{photo_id, meal_order_id, status}`                                          | 404 · 409 · 413 · 422 |
| `POST /api/meal-orders/{id}/staff-zero`  | JSON `{reason: "refused" \| "not_eaten"}`      | 200 `{meal_order_id, record_status, staff_zero_reason}`                          | 404 · 409             |
| `GET /api/events`                        | —                                              | SSE. 화면 ①②는 `photo.status_changed`만 쓴다                                     | —                     |

- `orders[]`의 각 항목(`MealOrderSummary`)은 `{meal_order_id, patient_id, display_name, room, order_status, record_status, staff_zero_reason, post_photo: {photo_id, status, stage} | null}`이다. 화면 ②는 환자 목록과 업로드 현황을 이 배열 하나로 그린다.
- 화면은 오류 본문의 `detail`이 아니라 상태 코드로 안내 문구를 고른다.
- `photo.status_changed`의 `kind`(`post`·`baseline`)와 기준 사진 이벤트(환자·발주 `null`)는 제안 확장이다. 화면은 `meal_plan_id`만 보고 그 끼니를 다시 읽으므로 `kind`가 없어도 동작한다.

### `provisional.ts`를 T3 API로 교체하는 절차

`src/api/provisional.ts` 머리 주석의 절차를 따른다.

1. T3 라우터가 생기면 `pnpm gen:api`로 `src/api/generated/schema.d.ts`를 다시 만든다.
2. `provisional.ts`의 함수 본문을 `src/api/client.ts`의 `apiClient`(openapi-fetch) 호출로 바꾼다. 함수 이름·인자·반환 타입과 `ApiError` 분류는 그대로 둔다.
3. `provisional.ts`의 타입을 생성 타입의 별칭으로 교체한다.

화면 코드는 바꾸지 않는 것을 목표로 한다. 화면과 훅은 `fetch`를 직접 부르지 않고 이 파일의 함수만 부른다.

### T3 인계 목록(스펙 6절)

1. 3.3절 임시 계약 표(특히 확장 두 가지)를 그대로 받을지, 다르게 정할지.
2. 업로드 크기 상한과 413 처리.
3. 실제 API 연결 뒤 `provisional.ts` 교체와 E2E를 실제 백엔드로 돌리는 일, 실기기 업로드 확인.
4. 업로드·전량 기록 임시 규칙(배지가 "미기록"·"재촬영 필요"인 환자만 가능)을 서버도 지킬지. 처리 중·완료 끼니에 요청이 오면 409로 거절할지. 지금은 화면에서 막는다.
5. ②의 SSE 필터를 끼니(`meal_plan_id`) 단위로 바꾼 점을 `docs/system-architecture.md` 8-1절에 반영하는 문서 수정.
6. 이벤트 데이터 확장(`kind` 필드, 기준 사진 이벤트의 환자·발주 `null`)을 실제 SSE에서도 쓸지. 쓰지 않더라도 기준 사진 저장 직후 그 끼니의 `meal_plan_id`가 담긴 `photo.status_changed`는 보내야 화면 ②의 안내가 갱신된다.
7. 기기 간 갱신(한 기기의 업로드·기준 사진 등록이 다른 기기의 화면 ②에 반영되는지)의 실연동 확인. MSW 모의는 탭 하나 안에서만 상태를 공유한다.
8. 실기기 확인에서 원본(디코딩 실패, 예: HEIC)이 그대로 업로드될 수 있는 경우, 서버가 그 형식을 받아 변환할지(pillow-heif 등) 422로 거절할지. iPhone HEIC가 원본 반환이면 아래 결과 표의 기기·OS·브라우저와 함께 여기에 적는다: 해당 없음(iPhone · iOS Chrome에서 HEIC가 JPEG로 변환됨)
9. 기준 사진 교체 때 분석 중이던 식후 사진을 끝난 뒤 새 기준으로 다시 분석하는 규칙(재분석 예약)을 실제 작업 실행기에서도 같게 할지. 화면 ①의 교체 안내 문구는 이 규칙을 전제로 한다.
10. 재촬영 필요 상태에서 전량 기록할 때 기존 식후 사진의 연결을 끊고 재분석 대상에서 빼는 규칙을 서버에서도 지킬지.

## 3. 실기기 확인

실기기에서 확인하는 범위는 업로드 전 단계(촬영·앨범·미리보기·변환)다. 휴대폰이 PC 주소(HTTP)로 접속하면 보안 컨텍스트가 아니어서 MSW 서비스 워커가 등록되지 않는다. 앱은 "모의 API를 쓸 수 없습니다(보안 컨텍스트 아님)" 배너와 "촬영 확인" 링크를 띄우고, 확인은 API를 쓰지 않는 `/camera-check`에서 한다. 실기기 업로드는 T3 연결 뒤 실제 API로 확인한다.

### 접속 확인 단계

1. PC에서 `cd frontend && pnpm dev:mock --host`를 실행하고, Vite가 출력한 `Network:` LAN 주소(`http://<PC의 LAN IP>:<포트>`)를 확인한다.
2. 같은 와이파이에 연결한 휴대폰 브라우저에서 그 LAN 주소를 연다.
3. 화면 상단에 워커 실패 배너 "모의 API를 쓸 수 없습니다(보안 컨텍스트 아님)"와 "촬영 확인" 링크가 보이는지 확인한다.
4. "촬영 확인" 링크를 눌러 `/camera-check`에 들어간다.

주의: `pnpm dev:mock -- --host`는 `--host`가 Vite에 옵션으로 전달되지 않는다. 항상 `pnpm dev:mock --host`를 쓴다.

### 기기별 확인 항목

- (a) "촬영하기"가 카메라(후면 우선)를 열고, "앨범에서 선택"이 사진 보관함을 연다.
- (b) 그 기기 카메라로 바로 찍은 세로 사진 하나 이상: 미리보기가 바로 서고(세로 방향), "변환됨 · JPEG · 원본 W×H → 변환 W×H · 용량"이 보이며 변환 크기의 긴 변이 2048 이하이고 세로(높이 > 너비)로 표시된다.
- (c) 디코딩되지 않는 입력을 만났을 때: "이 사진은 변환하지 못해 원본 그대로 보냅니다"와 원본 형식·용량이 보이고 화면이 멈추지 않는다(다른 사진을 다시 고를 수 있음). 이런 입력이 생기지 않았으면 "발생 안 함"으로 적는다.
- iPhone HEIC: 앨범의 HEIC 사진 하나로 (b)(변환됨)·(c)(원본 반환) 중 어느 쪽인지 기록한다. (c)이면 T3 인계 목록 8번에 적는다.

합격 기준: 접속 확인 단계 1~4, (a), (b)가 통과해야 "합격"이다. (c)는 발생한 경우에만 통과 여부를 적는다.

### 결과 표

| 기기    | OS               | 브라우저    | 입력 형식                   | 접속   | (a)    | (b)    | (c)        | HEIC 결과 | 합격 여부 | 비고                                                          |
| ------- | ---------------- | ----------- | --------------------------- | ------ | ------ | ------ | ---------- | --------- | --------- | ------------------------------------------------------------- |
| iPhone  | iOS(버전 미기록) | Chrome(iOS) | 카메라 촬영 사진, 앨범 HEIC | 통과   | 통과   | 통과   | 발생 안 함 | 변환됨    | 합격      | 배너 "모의 API를 쓸 수 없습니다" 확인 뒤 "촬영 확인"에서 확인 |
| Android | 미수행           | 미수행      | 미수행                      | 미수행 | 미수행 | 미수행 | 미수행     | 해당 없음 | 미수행    | 확인할 기기가 없어 이번 확인에서 제외                         |

접속 칸에는 배너·링크·`/camera-check` 진입 결과를 적는다.

실기기 확인과 별도로, PC 브라우저의 `pnpm dev:mock`에서 화면 ①②의 페이지 로딩, 사진 업로드, 업로드 뒤 상태 표시가 바뀌는 것을 확인했다.

## 4. 구현 중 정한 사항(제안)과 팀 확인 목록

모두 제안이며 팀 확정 전이다. 출처는 구현 계획의 Story별 구현 메모와 "판단이 필요한 열린 점"이다.

### 화면 문구와 해석

| 화면 | 제안                                                                                                                                                                                                          | 비고                                                                              |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| ①    | 업로드 404 "대상을 찾을 수 없습니다. 목록을 새로 고칩니다", 413 "사진이 너무 큽니다", 422 "사진을 확인할 수 없습니다. 다른 사진을 골라 주세요", 네트워크 오류 "서버에 연결할 수 없습니다. 다시 시도해 주세요" | 스펙에 없는 422·네트워크 문구를 계획이 제안                                       |
| ①    | 409·500 "기준 사진을 올리지 못했습니다. 다시 시도해 주세요"                                                                                                                                                   |                                                                                   |
| ①    | 다시 올리기 시트 제목 "기준 사진을 다시 올릴까요?", 버튼 "다시 올리기"                                                                                                                                        | 본문은 스펙 3.5절 문구                                                            |
| ①    | 등록 상태 "기준 사진 등록됨 (HH:MM, 기기 로컬 시각)", 로딩 "불러오는 중…"                                                                                                                                     |                                                                                   |
| ①    | 촬영 안내 두 줄                                                                                                                                                                                               | "식판 바로 위에서 수직으로 찍어 주세요", "수저나 손이 칸을 가리지 않게 해 주세요" |
| ①    | 미배식 칸은 "미배식"만 표시                                                                                                                                                                                   |                                                                                   |
| ②    | 성공 "<display_name> 식후 사진을 올렸습니다", 실패 "식후 사진을 올리지 못했습니다. 다시 시도해 주세요"                                                                                                        |                                                                                   |
| ②    | 목록 머리글 "업로드 현황", 업로드 영역 "식후 사진 업로드", 환자 미선택 "환자를 고르세요"                                                                                                                      |                                                                                   |
| ②    | 환자 목록과 업로드 현황을 한 목록으로 표시                                                                                                                                                                    | 스펙 3.3절 "배열 하나로"를 따름. 3.5절 2·6번 통합 여부는 팀 확인                  |
| ②    | 배지 색: 금식·취소 회색, 완료 primary, 재촬영 danger, 나머지 accent                                                                                                                                           | 미기록 구분은 팀 확인                                                             |
| ②    | 처리 중·완료 발주는 사진 입력까지 막음(①은 업로드 버튼만 막음)                                                                                                                                                |                                                                                   |
| ②    | 시트 제목 "사진 없이 기록할까요?", 확인 "기록하기"                                                                                                                                                            |                                                                                   |
| ②    | 전량 기록 성공 "<환자> <끼니>을 전량 거부로 기록했습니다"(전량 미섭취도 같은 형식), 실패 "전량 기록을 하지 못했습니다. 다시 시도해 주세요"                                                                    | 413·422는 500과 같은 실패 문구                                                    |
| ②    | 현황 머리글 "완료 x / (ordered 수) · 금식 n". 취소는 분모에서 빼고 따로 적지 않음                                                                                                                             | " · 취소 m"을 붙일지는 팀 확인                                                    |

### 모의 동작과 환경

| 항목                          | 제안                                                                                                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 기본 끼니                     | 10:30 전 아침, 15:30 전 점심, 그 뒤 저녁(경계값은 상수)                                                                                                                          |
| 모의 픽스처                   | 시연일 `2026-11-27`. `NS01`은 세 끼 모두 `npo`(시드는 점심만 `npo`). 아침은 기준 사진 등록·`NS03` 미기록, 점심은 기준 사진 등록·`NS03` 미기록 + 상태 혼합, 저녁은 기준 사진 없음 |
| 취소 발주                     | 기본 픽스처에 두지 않고 테스트에서만 주입                                                                                                                                        |
| 모의 처리 단계                | `uploaded → queued → analyzing(intake → nutrition → alert) → done`. `recommendation`은 생략                                                                                      |
| `finishAll()` 범위            | `uploaded`·`queued`·`analyzing` 어느 시점에 불러도 남은 단계를 끝낸다. 개발 전용 전역                                                                                            |
| 개발 모드의 처리 중 사진      | 점심 `NS04`·`NS09`는 기준 사진을 교체하기 전에는 "처리 중"에 머문다                                                                                                              |
| 실기기 접속 명령              | 스펙 3.2절의 표기는 `--host`가 Vite에 전달되지 않아 쓰지 않고 `pnpm dev:mock --host`를 쓴다. 스펙 표기는 문서 정리 단계에서 고칠 대상                                            |
| 웹 폰트                       | Google Fonts `<link>`(`referrerpolicy="no-referrer"`). 오프라인 시연을 위한 자체 호스팅은 팀 확인                                                                                |
| `public/mockServiceWorker.js` | 정적 파일이라 `dist/`에도 복사된다. 동작에는 영향이 없고, 빼려면 빌드 후 처리가 필요하다                                                                                         |
