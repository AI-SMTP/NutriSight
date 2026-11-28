# 프론트엔드 골격과 업로드 화면

> `frontend/` Vite + React 골격, OpenAPI 타입 생성, 화면 ①②가 쓰는 임시 API 계약(`provisional.ts`)과 MSW 모의, 기준 식전·식후 사진 업로드 화면, 빌드 결과의 FastAPI 정적 제공 (팀 제안안 기준).

## 개요

`frontend/`는 pnpm · Vite · React · TypeScript(strict) 프로젝트다. 화면 ①(영양사, 기준 식전 사진 업로드)과 ②(요양보호사, 식후 사진 업로드와 업로드 현황), 역할 선택(`/`), API 없이 동작하는 촬영 확인(`/camera-check`)을 담는다.

실제 업로드·조회 API와 `GET /api/events` SSE는 아직 백엔드에 없다(후속 구현 토픽 T3). 그래서 화면이 쓰는 API의 요청·응답 모양을 `src/api/provisional.ts` 한 파일에 임시 계약으로 두고, 개발 모드에서는 MSW(Mock Service Worker)가 이 계약을 메모리 상태로 모의한다. 화면 코드는 `fetch`를 직접 부르지 않고 이 파일의 함수만 부른다. T3이 실제 라우터를 만들면 이 파일의 함수 본문과 타입만 바꿔 연결한다.

백엔드는 `pnpm build` 결과(`frontend/dist`)를 `/`에서 정적 파일로 제공하고, API 경로가 아닌 화면 주소의 HTML 요청에는 `index.html`을 돌려준다. 개발 중에는 Vite 개발 서버가 `/api`를 백엔드로 프록시한다.

이 문서가 다루는 범위 밖: 실제 업로드·조회 API, SSE 서버, 사진 저장·검증, 업로드 크기 상한(T3), 화면 ③(의사)·④(처리 상태)와 재시도 버튼(T7), 디자인 후보 선택, 로그인·권한. 이 문서의 설계 결정은 모두 팀 확정이 아니라 제안이다.

## 구조 / 스키마

### 파일 구성

```
frontend/
  package.json · pnpm-lock.yaml · .nvmrc(24) · tsconfig*.json · vite.config.ts
  eslint.config.js · .prettierrc · playwright.config.ts · index.html · README.md
  public/mockServiceWorker.js       MSW 워커 (msw init으로 생성, 커밋)
  src/
    main.tsx                        bootstrap()만 부른다
    app/                            bootstrap.ts · App.tsx · routes.tsx · screens.ts · AppLayout.tsx
                                    RoleSelect.tsx · MockUnavailableBanner.tsx
    styles/                         tokens.css · global.css
    api/
      generated/openapi.json        백엔드에서 내보낸 OpenAPI (커밋)
      generated/schema.d.ts         openapi-typescript 결과 (커밋)
      client.ts                     openapi-fetch 클라이언트 (생성 타입용, 지금은 /api/health만)
      provisional.ts                화면 ①② 임시 계약: 타입 + 호출 함수 + ApiError
      events.tsx                    EventSource 구독 Provider · useSystemEvents 훅
    lib/                            image.ts · mealStatus.ts · format.ts
    components/                     Button · SegmentedControl · Badge · PhotoPicker · ConfirmSheet
    features/
      shared/                       useDemoDate · useMealQuery(+mealQueryState) · useSubmission
                                    useUploadFlow · defaultMeal · meals · messages · MealScreenParts
      baseline/                     화면 ① (BaselinePage · useBaselineScreen · TrayLayout · messages)
      postMeal/                     화면 ② (PostMealPage · usePostMealScreen · useStaffZero
                                    OrderList · StaffZeroSlot · messages)
      cameraCheck/                  촬영 확인 (CameraCheck · describeUpload)
    mocks/                          MSW 모의 (브라우저·Vitest 공용)
      fixtures.ts · scenarios.ts · types.ts   픽스처와 모의 상태 타입
      state.ts · operations.ts                메모리 상태, 상태 전이 순수 함수
      pipeline.ts · runtime.ts · eventBus.ts  처리 단계, 타이머 런타임, 이벤트 버스
      handlers.ts · errorHandlers.ts          REST 핸들러, 오류 시나리오 핸들러
      sseHandler.ts · browser.ts · devGlobal.ts · server.ts
    test/                           Vitest setup과 테스트 도우미
  scripts/                          check-bundle.mjs · hash-dir.mjs · compare-files.mjs
  tests/e2e/                        baseline.spec.ts · postMeal.spec.ts · helpers.ts · fixtures/tray.jpg
backend/
  app/config.py                     Settings.frontend_dist
  app/main.py                       frontend_dist가 있으면 app.frontend() + 404 처리기 등록
  scripts/export_openapi.py         create_app().openapi() → JSON 파일
  tests/test_frontend_static.py · test_export_openapi.py
```

- 단위 테스트는 `src/**/*.test.{ts,tsx}`에 대상 옆에 둔다. E2E만 `tests/e2e/`에 둔다.
- 루트 `.gitignore`의 `lib/` 패턴이 `frontend/src/lib/`까지 무시하므로 `!frontend/src/lib/` 예외를 둔다. `frontend/.build-report/`(번들 검사 산출물)도 무시 대상이다.
- TypeScript 5.9.3, `strict`와 `noUncheckedIndexedAccess`를 켠다. 의존성 버전은 정확한 값으로 고정한다. Node 24(`.nvmrc`, `engines.node >=24`), pnpm 12.15.0(`packageManager`).

### 실행 모드

| 명령 | 동작 |
| --- | --- |
| `pnpm dev` | Vite 개발 서버. `/api`를 `http://127.0.0.1:8000`(`VITE_API_TARGET`로 변경)으로 프록시한다. 실제 백엔드가 필요하다 |
| `pnpm dev:mock` | `VITE_API_MOCK=1 vite`. MSW 워커가 임시 계약을 모의한다. 백엔드 없이 동작한다 |
| `pnpm dev:mock --host` | 같은 와이파이의 휴대폰이 PC 주소로 접속할 때 쓴다. `pnpm dev:mock -- --host`는 `--host`가 Vite 옵션으로 넘어가지 않는다 |
| `pnpm build` | `tsc -b && vite build`. `frontend/dist`에 만든다. `VITE_API_MOCK`이 없으면 MSW와 `src/mocks/`는 번들에 들어가지 않는다 |
| `pnpm preview` | 빌드 결과를 Vite 미리보기 서버로 연다 |
| `pnpm gen:api` | 백엔드 OpenAPI를 `src/api/generated/openapi.json`으로 내보내고 `openapi-typescript`로 `schema.d.ts`를 만든다 |
| `pnpm test` | Vitest 한 번 실행(jsdom, MSW node 서버). 커버리지는 `pnpm test --coverage` |
| `pnpm e2e` | Playwright. `VITE_MOCK_STEPS=manual pnpm dev:mock --port 5180 --strictPort`를 웹 서버로 띄운다 |
| `pnpm typecheck` · `lint` · `format` · `format:check` | `tsc -b --noEmit` · `eslint .` · `prettier --write .` · `prettier --check .` |
| `pnpm check:bundle` · `check:bundle:mock` | 기본 빌드에 MSW·`src/mocks/`가 없는지, 모의 빌드에는 있는지 확인한다 |

환경 변수: `VITE_API_MOCK`(모의 API 사용), `VITE_MOCK_STEPS`(`manual`이면 모의 처리가 첫 `analyzing`에서 멈춤), `VITE_API_TARGET`(프록시 대상), 백엔드의 `FRONTEND_DIST`(빌드 결과 위치).

### 임시 API 계약

`src/api/provisional.ts`가 정의하는 엔드포인트다. 굵게 쓴 항목은 `docs/system-architecture.md` 9절 초안에 없는 이 토픽의 **제안 확장**이다. 이 표가 T3의 입력이다.

| 메서드 · 경로 | 요청 | 응답 | 오류 |
| --- | --- | --- | --- |
| **`GET /api/meta`** | — | `{demo_date: "YYYY-MM-DD"}` (T2 `seed_meta.demo_date`) | — |
| `GET /api/meals/{date}/{meal}` | `meal`: `breakfast`·`lunch`·`dinner` | `{meal_plan_id, date, meal, slots: Slot[], baseline_photo: {photo_id, uploaded_at} \| null, `**`orders: MealOrderSummary[]`**`}` | 404 배식 계획 없음 |
| `POST /api/meals/{date}/{meal}/baseline` | multipart `file` | 201 `{photo_id, uploaded_at}` | 404 · 413 · 422 |
| `POST /api/photos` | multipart `file`, `patient_id`, `date`, `meal` | 202 `{photo_id, meal_order_id, status}` | 404 배식 계획·환자 없음 · 409 발주 없음·금식·취소 또는 이미 기록 중·기록된 끼니 · 413 · 422 |
| `POST /api/meal-orders/{id}/staff-zero` | JSON `{reason: "refused" \| "not_eaten"}` | 200 `{meal_order_id, record_status: "recorded", staff_zero_reason}` | 404 발주 ID 없음 · 409 금식·취소 또는 이미 기록 중·기록된 끼니 |
| `GET /api/events` | — | SSE. 이벤트 이름 `photo.status_changed`. 화면 ①②가 쓰는 이벤트는 이것뿐이다 | — |

- 오류 본문은 FastAPI 기본(`{"detail": ...}`)을 가정한다. 화면은 `detail`이 아니라 상태 코드로 안내 문구를 고른다.
- 상태 코드와 `ApiError.kind`의 대응: 404 `not_found`, 409 `conflict`, 413 `too_large`, 422 `invalid`, 연결 실패 `network`, 그 밖의 실패 응답 `server`. 성공 본문에 계약 필드가 없거나 끼니 조회의 `slots`·`orders`가 배열이 아니면 `server`다. 경로 조각이 `.`·`..`이면 요청을 보내지 않고 `invalid`를 던진다.
- 업로드 요청의 파일 이름은 사용자 기기의 원래 이름이 아니라 JPEG이면 `photo.jpg`, 아니면 `photo`다.
- 409와 404의 구분은 엔드포인트별이다. 식후 업로드는 배식 계획이나 환자가 없으면 404, 둘은 있지만 그 끼니의 발주가 없으면 409다. 전량 기록은 지정한 발주 ID가 없으면 404다. 오류 코드 필드는 두지 않는다.
- `GET /api/events`의 경로(`EVENTS_PATH`)와 이벤트 이름(`PHOTO_STATUS_CHANGED_EVENT`)은 `provisional.ts`의 상수다.

### 데이터 형식

필드 이름과 값 집합은 `docs/data-model.md`를 따른다.

| 타입 | 필드 |
| --- | --- |
| `Slot` | `slot_id`, `position`, `dish_type`, `menu_name`(`string \| null`), `served_g`, `energy_kcal`, `protein_g`. 미배식 칸은 `menu_name = null`, `served_g = 0` |
| `MealOrderSummary` (제안 확장) | `meal_order_id`, `patient_id`, `display_name`, `room`, `order_status`(`ordered`·`npo`·`cancelled`), `record_status`(`not_recorded`·`pending`·`recorded`·`not_determinable`·`failed`), `staff_zero_reason`(`refused`·`not_eaten`·`null`), `post_photo: {photo_id, status, stage} \| null` |
| `PhotoStatusChangedEvent` | `photo_id`, `kind?`(`post`·`baseline`, 제안 확장), `patient_id`, `meal_plan_id`, `meal_order_id`, `status`, `stage`, `outcome?`(`done` 이벤트에만), `at`. 기준 사진 이벤트는 `patient_id`·`meal_order_id`가 `null`이다 |

사진 상태는 `uploaded`·`waiting_baseline`·`queued`·`analyzing`·`done`·`not_determinable`·`failed`, 처리 단계는 `intake`·`nutrition`·`alert`·`recommendation`이다. 화면 ②는 환자 목록과 업로드 현황을 `orders` 배열 하나로 그린다. 그래서 `GET /api/patients`(경고 수준 포함)는 쓰지 않는다.

### 라우트

| 경로 | 화면 |
| --- | --- |
| `/` | 역할 선택. 영양사(→ `/baseline`), 요양보호사(→ `/post-meal`). 의사·처리 상태는 "준비 중"으로 비활성. 아래쪽에 "촬영 확인" 링크. 고른 역할은 저장하지 않는다(URL이 곧 화면, 접근 제어 없음) |
| `/baseline` | ① 기준 식전 사진 |
| `/post-meal` | ② 식후 사진 |
| `/camera-check` | 촬영 확인. API를 부르지 않는다 |
| 그 밖 | `/`로 이동 |

모든 화면이 `AppLayout`(서비스 이름 "NutriSight", 화면 제목, 역할 배지)을 공유한다. `/baseline`과 `/post-meal`은 그 안의 `MealScreensLayout`(SSE Provider)을 한 번 더 공유한다.

### 디자인 토큰

`src/styles/tokens.css`의 CSS 변수다. 값은 샘플 캔버스 "화면 초안"에서 옮겼고, 디자인 후보가 정해지면 이 파일만 바꾼다. 컴포넌트는 CSS Modules를 쓰며 색·모서리·글꼴은 변수만 참조한다.

| 분류 | 변수 = 값 |
| --- | --- |
| 주색 | `--color-primary` `#0f766e`, `--color-primary-strong` `#115e59`, `--color-primary-soft` `#e6f4f1` |
| 배경·표면 | `--color-bg` `#f6f7f9`, `--color-surface` `#ffffff` |
| 선 | `--color-line` `#e3e6eb`, `--color-line-strong` `#cdd3db` |
| 글자 | `--color-text` `#1b2430`, `--color-text-muted` `#4a5565`, `--color-text-subtle` `#5b6575` |
| 위험 | `--color-danger` `#991b1b`, `--color-danger-soft` `#fdecec` |
| 보조 | `--color-accent` `#3730a3`, `--color-accent-soft` `#eef2ff` |
| 모서리 | `--radius-sm` 8px, `--radius-md` 10px, `--radius-lg` 12px, `--radius-xl` 14px |
| 글꼴 | `--font-sans` = `"Noto Sans KR"`(Google Fonts) 뒤에 `system-ui` 계열 대체 |
| 레이아웃 | `--touch-min` 44px(누를 수 있는 요소의 최소 크기), `--layout-max-width` 480px |

### 배지 규칙

`lib/mealStatus.ts`의 `orderBadge()`가 발주 하나의 배지를 정한다(`docs/data-model.md` 5절 "② 요양보호사 화면" 열). 순수 함수이고 React·네트워크·`api/`를 import하지 않는다. 표를 위에서부터 보고 처음 맞는 행을 쓴다.

| 순서 | 조건 | 배지 (`kind`) | 선택 |
| --- | --- | --- | --- |
| 1 | `order_status` = `npo` / `cancelled` | 금식 / 취소 (`npo` / `cancelled`, 회색) | 불가 |
| 2 | `record_status` = `recorded` | 완료 (`done`). `staff_zero_reason`이 있으면 "완료 · 전량 거부" / "완료 · 전량 미섭취" | 가능 |
| 3 | `record_status` = `not_determinable` 또는 사진 `not_determinable` | 재촬영 필요 (`retake`) | 가능 |
| 4 | 사진 `waiting_baseline` | 처리 중 · 기준 사진 대기 (`waiting_baseline`) | 가능 |
| 5 | 사진 `uploaded`·`queued`·`analyzing`·`failed`, 또는 `record_status` `pending`·`failed` | 처리 중 (`processing`) | 가능 |
| 6 | 그 밖 | 미기록 (`not_recorded`) | 가능 |

- `canRecord(badge)`는 `not_recorded`와 `retake`일 때만 참이다. 식후 업로드와 전량 기록이 이 함수를 함께 쓴다.
- `summarizeOrders(orders)`가 현황 머리글 "완료 x / y · 금식 n"을 만든다. `y`는 `order_status = ordered` 수, `x`는 그중 `recorded` 수, `n`은 `npo` 수다. `cancelled`는 분모에서 빼고 머리글에 적지 않는다(제안).
- 배지 색(제안): 금식·취소 회색(`neutral`), 완료 `primary`, 재촬영 필요 `danger`, 나머지 `accent`. 미기록과 처리 중은 색으로 구분하지 않는다.
- `failed`의 재시도 버튼은 화면 ②에 없다(화면 ④ 범위).

## 동작

### 정적 제공과 SPA 대체 응답

`Settings.frontend_dist`(환경 변수 `FRONTEND_DIST`, 기본값 `<저장소 루트>/frontend/dist`)가 빌드 결과 위치다. `~`는 펼치고 상대 경로는 실행 위치가 아니라 저장소 루트 기준으로 해석한다.

`create_app()`은 모든 `/api` 라우트를 등록한 뒤 `_register_frontend()`를 부른다. `frontend_dist/index.html`이 없으면 INFO 로그만 남기고 정적 제공을 등록하지 않으며 앱은 그대로 시작한다. 있으면 두 가지를 등록한다.

- `app.frontend("/", directory=dist, fallback=None)`: 정적 파일을 대체 응답 없이 제공한다. 기본값 `"auto"`는 대체 응답을 켜므로 `None`을 명시한다. 일반 라우트가 먼저 맞고, 맞는 라우트가 없을 때만 정적 파일을 확인한다. 파일 경로 검사(`dist` 밖 접근 차단)는 Starlette `StaticFiles`가 한다.
- 404 처리기: 앱 전역 `StarletteHTTPException` 처리기다. 404일 때만 아래 조건을 검사하고, 조건이 맞으면 `index.html`을 돌려준다. 조건이 맞지 않거나 404가 아니면 기본 HTTP 오류 응답(JSON)을 그대로 돌려준다.

대체 응답 조건은 네 가지가 모두 맞는 경우다.

1. 라우팅·정적 파일 결과가 404다.
2. 경로가 `/api`이거나 `/api/`로 시작하지 않는다.
3. 메서드가 GET 또는 HEAD다.
4. `Accept` 헤더에 `text/html` 문자열이 들어 있다(q값은 해석하지 않는다).

FastAPI 내장 `fallback`은 HTML 요청이면 `/api` 경로에도 `index.html`을 주고, `/api` 404 포괄 라우트는 POST 전용 경로의 GET 405를 404로 바꾼다. 둘 다 쓰지 않고 위 방식을 택하므로 API의 JSON 404와 405가 보존된다. 정적 제공·대체 응답용 경로는 OpenAPI `paths`에 들어가지 않는다.

| 요청 | 응답 |
| --- | --- |
| `GET /` (`Accept: */*`, `text/html` 모두) | 200 `index.html` |
| `GET /post-meal`, `GET /baseline/extra` (`Accept: text/html`) | 200 `index.html` |
| `GET /post-meal` (`Accept: */*`) | 404 JSON `{"detail": "Not Found"}` |
| `HEAD /post-meal` (`Accept: text/html`) | 200, 본문 없음 |
| `POST /post-meal` (`Accept: text/html`) | 404 JSON (대체 응답 없음) |
| `GET /assets/app.js`, `GET /favicon.ico` (있는 파일) | 200 파일 본문 |
| `GET /assets/missing.js` (`Accept: */*`) | 404 JSON |
| `GET /api/missing` (`Accept: text/html`, `*/*` 모두) | 404 JSON |
| `GET /api/_probe`(POST 전용 라우트, `Accept: text/html`) | 405, `Allow: POST` |
| `POST /api/health` | 405, `Allow: GET` |
| `GET /api/health` | 200 `{"status": "ok"}` |
| `dist` 밖을 가리키는 경로·심볼릭 링크 (`..%2F` 등) | 비밀 파일 내용을 돌려주지 않는다(`Accept: */*`는 404 JSON, `text/html`은 `index.html`) |

- `assets/` 디렉토리가 없고 `index.html`만 있는 `dist`도 시작되며 `GET /`와 화면 주소는 200이다.
- 시작한 뒤 `index.html`이 사라지면(다시 빌드하는 중 등) 대체 응답 대신 기본 JSON 404를 돌려준다.
- 이 응답 표는 `backend/tests/test_frontend_static.py`가 `tmp_path`의 가짜 `dist`와 테스트용 POST 전용 `/api/_probe` 라우트로 검증한다. `tests/conftest.py`의 `SETTING_ENV_DEFAULTS`가 `FRONTEND_DIST`를 존재하지 않는 경로로 두어, 다른 테스트가 저장소의 `dist`에 영향받지 않는다.

### OpenAPI 내보내기와 생성 타입

`backend/scripts/export_openapi.py`(`python -m scripts.export_openapi [--out PATH]`)가 서버를 띄우지 않고 `create_app().openapi()`를 JSON 파일로 쓴다. lifespan(앱 잠금·자동 시드)은 실행하지 않는다. `--out`을 주지 않으면 `frontend/src/api/generated/openapi.json`에 쓰고, 상대 경로는 현재 디렉토리 기준이다. 키를 정렬하고 들여쓰기 2칸, 끝 줄바꿈 하나로 써서 다시 내보내도 바이트가 같다. 설정 오류(`ConfigError`)는 한국어 안내와 종료 코드 1로 바꾼다.

`pnpm gen:api`는 `uv run --frozen --directory ../backend python -m scripts.export_openapi --out ../frontend/src/api/generated/openapi.json`을 실행한 뒤 `openapi-typescript`로 `schema.d.ts`를 만든다. `--frozen`이라 `backend/uv.lock`을 바꾸지 않고, 백엔드 디렉토리에서 모듈로 실행하므로 `--out`은 그 디렉토리 기준이다. 두 생성 파일은 커밋하며 Prettier·ESLint 대상에서 뺀다. 다시 생성해도 커밋본과 차이가 없어야 한다.

`api/client.ts`의 `openapi-fetch` 클라이언트는 `createClient<paths>`로 만들며 기준 URL은 현재 출처다. `fetch`는 호출마다 전역에서 찾아(MSW가 바꾼 `fetch`를 쓰기 위해) 부른다. 지금 생성 타입의 `paths`에는 `/api/health`뿐이다.

### 임시 계약과 T3 교체 절차

임시 계약은 `api/provisional.ts` 한 파일이다. 화면과 훅은 이 파일의 함수(`getMeta`, `getMeal`, `uploadBaseline`, `uploadPostPhoto`, `recordStaffZero`)와 `ApiError`·`mealPlanId`만 부른다. `getMeal`은 취소 신호(`signal`)를 받으며 취소된 요청의 예외는 `ApiError`로 바꾸지 않고 그대로 던진다.

`mealPlanId(date, meal)`은 `"<date>_<meal>_general"`(`docs/data-model.md` 3절 ID 규칙, 파일럿은 일반식 하나)이다.

T3이 실제 라우터를 만들면 다음 순서로 연결한다.

1. `pnpm gen:api`로 `schema.d.ts`를 다시 만든다.
2. `provisional.ts`의 함수 본문을 `client.ts`의 `apiClient`(openapi-fetch) 호출로 바꾼다. 함수 이름·인자·반환 타입과 `ApiError` 분류는 그대로 둔다.
3. `provisional.ts`의 타입을 생성 타입의 별칭으로 교체한다.
4. MSW 없이 `pnpm dev`(실제 백엔드)로 화면 ①②와 E2E를 실제 API에 대해 확인한다.

화면 코드는 바꾸지 않는 것을 목표로 한다.

### 시연일 초기화

화면 ①②는 들어오면 먼저 `GET /api/meta`로 시연일을 읽고(`useDemoDate`), 성공한 뒤에 끼니 조회를 시작한다. 상태는 `loading`·`ready(date)`·`error`다.

- 시연일 조회가 실패하면(네트워크 오류·서버 오류 모두) 본문 대신 "시연일을 불러오지 못했습니다"와 "다시 시도"를 보이고, 날짜·끼니·환자 선택과 사진 입력·제출을 모두 막는다. 이 동안 끼니 조회는 한 건도 나가지 않는다.
- "다시 시도"는 시연일 조회부터 다시 한다. 성공하면 끼니 조회가 시작된다.
- 화면을 떠난 뒤 도착한 응답은 반영하지 않는다.
- `/`와 `/camera-check`는 시연일을 읽지 않는다.

기본 끼니는 화면에 들어온 순간의 기기 로컬 시각으로 정한다(`defaultMeal`): 10:30 전 아침, 15:30 전 점심, 그 뒤 저녁. 경계값은 `BREAKFAST_END = "10:30"`, `LUNCH_END = "15:30"` 상수다. 화면 ①의 날짜 기본값은 시연일이고 화면 ②의 날짜는 늘 시연일이다.

### 끼니 조회 순서 규칙

끼니 조회(`GET /api/meals/{date}/{meal}`)는 최초 조회, SSE 이벤트로 인한 재조회, SSE `open`으로 인한 재조회, 제출 뒤 재조회, "다시 시도" 모두 `useMealQuery`의 `refetch()` 하나로 보낸다.

1. **번호**: `refetch()`는 보낼 때마다 번호를 올린다. 응답은 성공이든 실패든 가장 마지막으로 보낸 요청의 응답일 때만 화면에 반영한다. 앞서 보낸 요청의 응답은 늦게 도착해도 버린다. 최신 요청이 아직 대기 중이면 화면은 이전에 반영한 상태를 그대로 둔다. 화면을 떠나면 진행 중인 조회를 취소하고 응답을 버린다.
2. **끼니 전환**: 날짜·끼니를 바꾸면 이전 끼니 데이터(배식 계획·발주·현황)를 같은 렌더에서 지운다. 새 끼니 조회가 성공할 때까지 환자 선택과 제출은 막힌다.
3. **404**: 조회가 404이면 서버가 정상 응답한 것이므로 아래 (가)·(나)보다 먼저 적용한다. "이 날짜·끼니의 배식 계획이 없습니다"를 보이고, 날짜·끼니 선택은 그대로 두어 다른 끼니로 바꿀 수 있게 하며, 사진 입력·환자 선택·제출은 막는다. 이미 데이터를 보여 주던 중의 404도 같다(데이터를 지운다).
4. **(가)**: 최초 조회나 끼니 전환 직후 조회가 404가 아닌 이유로 실패해 보여 줄 데이터가 없으면, 본문 대신 "서버에 연결할 수 없습니다"와 "다시 시도"를 보이고 사진 입력과 제출을 막는다.
5. **(나)**: 이미 보여 주던 데이터가 있는데 재조회가 실패하면, 데이터를 그대로 두고 현황 위에 "목록을 새로 고치지 못했습니다"와 "다시 시도"를 띄운다.
6. "다시 시도"는 조회만 다시 보낸다. 제출 요청을 다시 보내지 않는다.

`view` 값은 `loading`·`ready`·`no_plan`·`unreachable`이고, (나)는 `view = ready`에 `refreshError = true`로 표현한다. 시연일이 준비되지 않았거나 `enabled`가 거짓이면 조회를 보내지 않으며, 그때 온 SSE `open`의 재조회도 아무것도 하지 않는다. 상태 전이 규칙은 `features/shared/mealQueryState.ts`의 순수 함수에 있다.

### 제출과 잠금 규칙

**요청 대상 고정**: 제출할 때 대상(날짜·끼니, ②는 환자와 `meal_order_id`)과 고른 사진을 얼린 요청 객체에 고정한다(`useSubmission`). 요청 중에는 날짜·끼니·환자 선택, 사진 입력, 다른 제출 버튼을 막고 새 제출을 받지 않는다. 요청마다 번호를 두어, 화면을 떠난 뒤 도착한 성공·실패 응답은 상태도 바꾸지 않고 콜백도 부르지 않는다. 요청이 없을 때 날짜·끼니·환자를 바꾸면 고른 사진과 오류 메시지를 지운다(`useUploadFlow.changeSelection`). 요청 중에는 "사진 올리기" 제목이 포커스를 받는다.

**성공 처리**: 제출이 성공하면(① 201, ② 202·200) 다음을 이 순서로 한다.

1. 성공 안내를 남기고 그 대상을 **로컬 제출 완료**로 표시한다(`markSubmitted`). 대상 키는 ①이 `meal_plan_id`, ②가 `meal_order_id`다. 표시한 순간의 마지막 조회 번호를 함께 기록한다.
2. 그 끼니를 다시 읽는다(`refetch`).
3. 고른 사진을 비운다.

**잠금 해제**: 같은 선택에서 표시한 번호보다 뒤에 보낸 조회가 성공해 반영될 때만 로컬 제출 완료 표시를 지운다. 제출 전에 보낸 조회가 늦게 성공해도 표시를 지우지 못하고(최신이 아니면 버려지고, 최신이어도 번호가 제출 전이면 표시를 유지한다), 조회 실패는 표시를 지우지 않는다. 그래서 재조회가 실패하거나 제출 전 조회가 늦게 오는 경우에도 같은 대상을 다시 제출할 수 없다.

**성공 안내**: 성공 안내는 끼니를 바꿔도 지우지 않고 조회 실패 (가)·(나)에도 유지한다. 다만 안내를 남긴 끼니(`meal_plan_id`)를 보고 있을 때만 보여 준다. 다시 제출을 시작하면 이전 안내를 지운다.

**실패 처리**: 실패하면 입력(고른 사진)을 유지하고 오류 분류별 한국어 안내를 보인다. 404는 ①②가 모두, 409는 ②만(업로드·전량 기록 모두) 그 끼니를 다시 읽는다.

**업로드·전량 기록 임시 규칙**: 배지가 "미기록" 또는 "재촬영 필요"인 환자만 사진 업로드와 전량 거부·미섭취를 할 수 있다. "처리 중"·"완료"인 환자를 고르면 두 동작과 사진 입력을 막고 "이미 기록 중이거나 기록된 끼니입니다"를 보인다. 로컬 제출 완료인 발주도 같다. 재촬영 필요에서 다시 올리면 새 사진이 이전 사진을 대신한다. 완료된 끼니를 고치는 기능은 없다. 서버가 같은 규칙을 409로 지킬지는 T3이 정한다.

### 오류 안내 문구

문구는 상태 코드 분류로 고른다(`features/shared/messages.ts`, 화면별 `messages.ts`). 모두 제안이며 팀 확인 전이다.

| 분류 | ① 기준 사진 업로드 | ② 식후 사진 업로드 | ② 전량 기록 |
| --- | --- | --- | --- |
| 404 | 대상을 찾을 수 없습니다. 목록을 새로 고칩니다 | 같음 | 같음 |
| 409 | 기준 사진을 올리지 못했습니다. 다시 시도해 주세요 | 이 끼니는 지금 기록할 수 없습니다(식사가 나가지 않거나 이미 기록 중·기록됨). 목록을 확인하세요 | 같음 |
| 413 | 사진이 너무 큽니다 | 같음 | 전량 기록을 하지 못했습니다. 다시 시도해 주세요 |
| 422 | 사진을 확인할 수 없습니다. 다른 사진을 골라 주세요 | 같음 | 전량 기록을 하지 못했습니다. 다시 시도해 주세요 |
| 네트워크 | 서버에 연결할 수 없습니다. 다시 시도해 주세요 | 같음 | 같음 |
| 500 등 | 기준 사진을 올리지 못했습니다. 다시 시도해 주세요 | 식후 사진을 올리지 못했습니다. 다시 시도해 주세요 | 전량 기록을 하지 못했습니다. 다시 시도해 주세요 |

조회 상태 안내(`VIEW_MESSAGES`): "시연일을 불러오지 못했습니다", "이 날짜·끼니의 배식 계획이 없습니다", "서버에 연결할 수 없습니다", "목록을 새로 고치지 못했습니다", "불러오는 중…", "다시 시도". 업로드와 전량 기록은 `submission` 하나를 공유하므로 ②는 마지막으로 보낸 요청의 종류를 기억해 실패 안내를 업로드 영역과 전량 기록 영역 중 해당 쪽에만 보인다.

### SSE 구독

`api/events.tsx`의 `SystemEventsProvider`가 `/baseline`·`/post-meal`을 감싸는 레이아웃에서 `EventSource("/api/events")` 하나를 연다. `/`와 `/camera-check`에서는 구독하지 않는다. 두 화면 사이를 오가도 연결은 유지되고, 레이아웃을 벗어나면 `close()`한다. 개발 모드의 StrictMode에서는 이펙트가 두 번 실행되어 첫 연결이 바로 닫힌다.

- 화면은 `useSystemEvents({onPhotoStatusChanged, onOpen})`로 구독한다. 콜백은 늘 마지막 렌더의 것이 불린다.
- 메시지 데이터를 JSON으로 읽고 `meal_plan_id`·`photo_id`가 문자열이 아니면(JSON 오류 포함) 버린다. `kind`는 보지 않고 그대로 넘긴다.
- 화면은 선택한 날짜·끼니로 자기 `meal_plan_id`를 계산한다. 이벤트의 `meal_plan_id`가 같으면 그 끼니를 다시 읽는다. 식후 사진과 기준 사진 이벤트를 구별하지 않으므로, T3이 `kind`를 두지 않아도 갱신은 동작한다. 사진 ID가 아니라 끼니 단위로 거르므로 다른 사용자의 업로드도 반영된다(실제 서버 연결 뒤). 이는 `docs/system-architecture.md` 8-1절의 "자기 `photo_id`만 골라 쓴다"와 다른 제안이다.
- 조회가 진행 중일 때 이벤트가 와도 새 조회를 보낸다(번호가 커지고 이전 응답은 버려진다). 끼니를 바꾼 직후 응답을 기다리는 동안 온 새 끼니의 이벤트도 놓치지 않는다.
- `open`은 첫 연결이든 재연결이든 올 때마다 현재 끼니를 한 번 다시 읽는다. 최초 조회를 보낸 뒤 첫 `open` 전에 일어난 변경(이벤트로 받지 못한 변경)도 첫 `open` 뒤 재조회로 반영된다. `Last-Event-ID` 재전송은 쓰지 않는다.
- 재연결은 브라우저 `EventSource`의 자동 재연결에 맡긴다.
- 연결 함수는 주입할 수 있다(`connect` prop, 기본 `new EventSource(EVENTS_PATH)`). Vitest(jsdom/node)에는 `EventSource`가 없으므로 모의 이벤트 버스를 발행기로 쓰는 연결(`src/test/mockConnect.ts`)을 넣는다.

### 이미지 변환

`lib/image.ts`의 `prepareUpload(file): Promise<PreparedUpload>`가 업로드 전에 사진을 변환한다. `PreparedUpload = {blob, converted, source: {type, bytes, width?, height?}, output?: {type, bytes, width, height}}`다. 상수는 파일 상단의 `MAX_EDGE_PX = 2048`, `JPEG_QUALITY = 0.9`다.

1. `createImageBitmap(file, {imageOrientation: "from-image"})`로 디코딩한다. `source.type`·`bytes`는 입력 `File`의 `type`·`size`, `source.width`·`height`는 방향을 보정한 비트맵 크기다.
2. 긴 변이 2048보다 크면 비율을 유지해 줄이고(반올림, 최소 1px), 작거나 같으면 그대로 둔다.
3. 캔버스에 그려 `image/jpeg`로 인코딩한다. `OffscreenCanvas`를 우선 쓰고, 없거나 2d 컨텍스트를 못 얻으면 canvas 요소로 대신한다. 결과 `type`이 `image/jpeg`가 아니면(PNG 대체 인코딩 등) 실패로 본다. 다 쓴 캔버스는 크기를 0으로 줄여 비우고 비트맵은 `close()`한다.
4. 성공하면 `converted: true`, `blob`은 JPEG, `output`은 변환 결과 `Blob`의 `type`·`size`와 그린 크기다. 4032×3024 입력은 `output` 2048×1536, 1000×750 입력은 1000×750이다.

실패는 원본 `File`을 `converted: false`로 그대로 돌려준다(서버 검증에 맡긴다). 디코딩 실패면 `source`에 형식·용량만 있고 `output`이 없다. 디코딩 뒤 그리기·인코딩 실패면 `source`에 디코딩 크기도 있고 `output`이 없다. 디코딩 가능 여부는 브라우저와 입력 형식에 달려 있어 모든 입력의 변환을 보장하지 않는다. `imageOrientation` 옵션을 지원하지 않는 엔진은 디코딩 실패로 처리되어 원본을 보낸다.

`/camera-check`는 `PhotoPicker`로 촬영·앨범 선택, 원본 object URL 미리보기(그리지 못하면 "미리보기를 표시할 수 없습니다"), `prepareUpload()` 결과를 보인다. 결과 문구는 `PreparedUpload` 값에서만 읽는다.

- 성공: `변환됨 · JPEG · 원본 W×H, <용량> → 변환 W×H, <용량>`
- 실패: `이 사진은 변환하지 못해 원본 그대로 보냅니다 · <source.type>, <용량>` (형식이 비어 있으면 "형식 알 수 없음")
- 용량은 `formatBytes`가 B·KB·MB로 표기한다(KB·MB는 소수 첫째 자리).

변환 중에는 "변환 중…"을 보이고, 앞서 고른 사진의 변환이 늦게 끝나면 그 결과는 버린다. 이 화면은 업로드·조회 요청과 SSE 구독을 하지 않는다.

### 기준 사진 화면

화면 ①(`features/baseline/`)은 영양사가 날짜·끼니를 고르고 배식 계획과 등록 상태를 보며 기준 식전 사진을 올린다.

1. 날짜(`<input type="date">`, 기본값은 시연일)와 끼니(아침·점심·저녁 분할 버튼)를 고른다.
2. 배식 계획 6칸을 식판 배치대로 메뉴명과 배식량(`served_g`+`g`)으로 보인다. 윗줄은 칸 3~6, 아랫줄은 칸 1~2다. 미배식 칸(`menu_name = null`)은 "미배식"만 보인다.
3. 끼니의 등록 상태 표시(`data-testid="baseline-status"`)는 기준 사진이 있으면 "등록됨 (HH:MM)"(기기 로컬 시각), 없으면 "아직 없음"이다. 업로드 성공 직후의 일시 안내 "기준 사진 등록됨"(`role="status"` 영역)과는 별개의 요소다.
4. 사진 입력은 "촬영하기"(`accept="image/*" capture="environment"`)와 "앨범에서 선택"(`capture` 없음) 두 라벨이다. 고른 사진은 미리보기로 보인다. 촬영 안내 두 줄: "식판 바로 위에서 수직으로 찍어 주세요", "수저나 손이 칸을 가리지 않게 해 주세요".
5. "기준 사진 업로드"는 `prepareUpload()` → `POST .../baseline`을 보낸다. 진행 중에는 날짜·끼니·사진 입력·제출을 막는다. 성공하면 그 끼니를 로컬 제출 완료로 잠그고(업로드 버튼만 막는다) 다시 읽는다.
6. 기준 사진이 이미 있는 끼니에서 올리면 확인 시트를 먼저 띄운다. 제목 "기준 사진을 다시 올릴까요?", 본문 "다시 올리면 이 끼니의 식후 사진을 모두 새 기준으로 다시 분석합니다(분석 중인 사진은 끝난 뒤 다시 분석). 사진 없이 기록한 끼니는 그대로입니다", 버튼 "다시 올리기"·"취소"다. 본문은 모의 동작(기준 사진 교체와 재분석 예약)과 같은 내용이다. 확인할 때 제출 가능 여부를 다시 검사하고, 그 사이 조회 결과가 바뀌어 제출할 수 없으면 요청 없이 시트를 닫는다.

### 식후 사진 화면

화면 ②(`features/postMeal/`)는 요양보호사가 시연일의 세 끼("오늘 아침/점심/저녁") 중 하나와 환자를 고르고 식후 사진을 올리거나 사진 없이 기록하며, 그 끼니의 업로드 현황을 본다.

1. 날짜 입력은 없다. 끼니를 바꾸면 고른 환자도 지운다.
2. 기준 사진 안내는 `baseline_photo` 유무로 바뀐다(`role="status"`, `data-testid="baseline-guide"`): "기준 사진 등록됨" / "기준 사진이 아직 없어요. 지금 올려도 기준 사진이 등록되면 자동으로 분석해요."
3. 환자 목록과 업로드 현황은 한 목록이다(제목 "업로드 현황"). 항목은 `room · display_name`과 배지이고, 금식·취소는 회색 배지로 비활성이라 고를 수 없다. 머리글은 `summarizeOrders` 문자열(`data-testid="order-summary"`)이다. 고른 환자가 이후 조회에서 없어지거나 금식·취소로 바뀌면 선택이 없는 것으로 본다.
4. 환자를 고르기 전에는 "환자를 고르세요"를 보인다. 고른 환자를 기록할 수 없으면 "이미 기록 중이거나 기록된 끼니입니다"를 보이고 사진 입력·업로드·전량 기록 버튼을 막는다.
5. 사진 입력은 화면 ①과 같은 두 라벨이다. 업로드 버튼은 "<display_name> 식후 사진 업로드"(환자를 고르기 전에는 "식후 사진 업로드")이고 `prepareUpload()` → `POST /api/photos`를 보낸다. 성공하면 "<display_name> 식후 사진을 올렸습니다"를 보이고, 202를 받자마자 그 끼니를 다시 읽는다. 기준 사진이 없는 끼니면 배지가 "처리 중 · 기준 사진 대기", 있으면 "처리 중"이 된다. 이후 변화는 SSE 이벤트를 받을 때마다 다시 읽어 반영한다.
6. "사진 없이 기록" 영역에 "전량 거부"·"전량 미섭취" 버튼이 있다. 버튼은 확인 시트(제목 "사진 없이 기록할까요?", 본문 "NS03 점심을 전량 거부로 기록합니다", 버튼 "기록하기"·"취소")를 열고, 시트를 열 때 대상(발주·사유)을 고정한다. 확인하면 시트를 바로 닫고, 그 사이 조회 결과가 바뀌어 기록할 수 없으면 요청하지 않는다. 기록할 수 있으면 `POST /api/meal-orders/{id}/staff-zero`를 보낸다. 200을 받으면 "<환자> <끼니>을 전량 거부로 기록했습니다"(전량 미섭취도 같은 형식)를 보이고 곧바로 다시 읽어 배지가 "완료 · 전량 거부"(또는 "완료 · 전량 미섭취")가 된다. 전량 기록은 사진 이벤트를 만들지 않으므로 SSE를 기다리지 않는다.
7. 로컬 제출 완료인 발주는 사진 입력까지 막는다(화면 ①은 업로드 버튼만 막는다).

### MSW 픽스처

`mocks/fixtures.ts`와 `scenarios.ts`가 시연일 D(고정 `2026-11-27`)의 모의 초기 상태를 만든다. `createInitialState({overrides})`는 매번 새 객체를 돌려주며, 테스트는 `overrides`로 발주(`null`이면 그 발주 제거)·사진·배식 계획을 덮어쓴다. 픽스처에 없는 ID를 덮어쓰면 던진다.

- 배식 계획: 아침·점심·저녁 각 6칸. 메뉴·배식량·열량·단백질은 `data/seed/demo_seed.json` D0 값이고 칸 위치 표기도 시드를 따른다. 칸 순서가 `slot_1`~`slot_6`이다.
- 환자 10명(`NS01`~`NS10`)과 끼니별 발주 30건. `NS01`은 세 끼 모두 `npo`다(시드는 점심만 `npo`). `cancelled` 발주는 기본값에 두지 않고 테스트가 주입한다.
- 끼니별 분포(제안):

| 끼니 | 기준 사진 | 환자별 상태 |
| --- | --- | --- |
| 아침 | 있음 | `NS03` 미기록, 나머지(금식 제외)는 완료 |
| 점심 | 있음 | 미기록 `NS03`·`NS08`, 처리 중 `NS04`(`analyzing`)·`NS09`(`queued`), 완료 `NS02`·`NS07`·`NS10`, 재촬영 필요 `NS05`, 완료 · 전량 거부 `NS06`, 금식 `NS01` |
| 저녁 | 없음 | 금식 `NS01` 외 모두 미기록 |

- 모의 상태(`mockState`)는 메모리 하나다. 핸들러와 런타임은 `update`로 새 상태 객체를 넣고, 상태 전이(`operations.ts`)는 받은 상태를 고치지 않는 순수 함수다.
- 모의 REST 핸들러(`handlers.ts`)는 임시 계약 표의 모든 엔드포인트를 구현한다. 없는 날짜·끼니의 조회는 404, 업로드 본문을 읽을 수 없거나 필수 필드(`file`, `patient_id`, `date`, `meal`, 올바른 `reason`)가 없으면 422다. 크기 상한은 모의하지 않는다. 식후 업로드는 배식 계획·환자 없음 404, 그 끼니의 발주 없음·금식·취소·이미 기록 중·기록됨 409다. 전량 기록은 발주 ID 없음 404, 금식·취소·이미 기록 중·기록됨 409다. 기록할 수 있는지는 `orderBadge`·`canRecord`를 재사용해 판정한다.
- 재촬영 필요 발주에 새 사진을 올리면 새 사진이 발주의 현재 사진 연결(`post_photo_id`)을 대신하고 이전 사진 행은 남는다. 재촬영 필요 발주에 전량 기록하면 사진 행은 남기고 `post_photo_id`를 끊는다.
- 오류 시나리오: `errorHandlers.{meta, meal, baselineUpload, postUpload, staffZero}(kind)`가 `not_found`·`conflict`·`too_large`·`invalid`·`server`(각각 404·409·413·422·500, 본문 `{detail}`)와 `network`(연결 오류) 핸들러를 만든다. 테스트가 `server.use(...)`로 기본 핸들러 위에 얹는다.

### MSW 처리 단계

식후 사진을 받으면 `mocks/runtime.ts`의 런타임이 `uploaded → queued → analyzing(intake) → analyzing(nutrition) → analyzing(alert) → done` 순서로 단계를 진행한다. `recommendation` 단계는 생략한다. 단계마다 사진 상태를 바꾸고, 그 사진이 지금 연결된 발주의 `record_status`를 함께 바꾸며(`uploaded`·`waiting_baseline`·`queued`·`analyzing` → `pending`, `done` → `recorded`, `not_determinable` → `not_determinable`, `failed` → `failed`), `photo.status_changed`를 모의 이벤트 버스에 발행한다. `done` 이벤트에는 `outcome: "no_change"`가 붙는다.

- 단계 간격은 기본 800ms다. `VITE_MOCK_STEPS=manual`이면(`manualSteps`) 처리마다 첫 `analyzing(intake)`에서 멈추고 `finishAll()`이 남은 단계를 끝낸다.
- 기준 사진이 없는 끼니의 식후 사진은 `waiting_baseline`에서 멈추고 발주는 `pending`이다. 그 끼니에 기준 사진이 처음 등록되면 대기 사진을 `queued`부터 이어서 처리한다.
- 결과를 `not_determinable`·`failed`로 끝내는 주입 지점(`resolveResult`)은 테스트용이다. 이 경우 `intake` 단계에서 끝난다.
- 기준 사진을 저장한 직후(최초·교체 모두) 이벤트 `{photo_id, kind: "baseline", meal_plan_id, patient_id: null, meal_order_id: null, status: "uploaded", stage: null, at}`를 발행한다. 대기 사진이 없는 끼니에서도 발행하므로, 같은 모의 상태를 보는 화면 ②가 기준 사진 안내를 갱신한다(`docs/system-architecture.md` 3-1절 4단계).
- 브라우저에서는 `sseHandler.ts`가 `GET /api/events`를 `msw/sse`로 모의한다. 연결 직후 `retry: 2000` 프레임을 먼저 보내고(첫 덩어리가 와야 응답이 열린다), 이후 이벤트 버스의 이벤트를 `event: photo.status_changed` 메시지(JSON 데이터)로 보낸다. 요청이 중단되면 버스 구독을 끊는다. Vitest 공용 서버에는 이 핸들러를 넣지 않는다.

### 기준 사진 교체와 재분석 예약

이미 기준 사진이 있는 끼니에 다시 등록하면(교체) 그 끼니에서 전량 기록(`staff_zero_reason`)이 없고 현재 연결된 식후 사진(`post_photo_id`)이 있는 발주의 사진만 대상이다.

| 사진 상태 | 처리 |
| --- | --- |
| `done`·`not_determinable`·`failed`·`waiting_baseline` | 즉시 `queued`부터 다시 처리한다. `photo.status_changed`를 발행하고 발주의 `record_status`는 `pending`이 된다 |
| `queued`·`analyzing` | 지금 처리를 이어 가되 **재분석 예약**을 남긴다. 처리가 끝나면(`done`·`not_determinable`·`failed`) 곧바로 `queued`부터 새 기준으로 한 번 더 처리한다 |

이렇게 해서 시스템 구조 3-1절의 "그 끼니의 식후 분석을 모두 다시 실행한다"와 결과가 같다. 사진 없이 전량 기록한 발주와, 재촬영 필요 상태에서 전량 기록해 사진 연결이 끊긴 발주는 바뀌지 않는다("완료 · 전량 거부"로 남는다). 화면 ②는 다시 처리되는 환자를 "처리 중"으로 보인다. 개발 모드에서 점심 `NS04`·`NS09`는 런타임이 가진 작업이 아니라 픽스처 상태라서 기준 사진을 교체하기 전에는 "처리 중"에 머물고, 교체하면 런타임이 이어받아 재처리까지 끝낸다.

### finishAll과 reset

`window.__nutrisightMock = {reset, finishAll}`은 개발 전용 전역이며 MSW 모드에서 워커 시작에 성공한 뒤에만 만든다.

- `finishAll()`은 호출 시점에 런타임이 가진 식후 사진 작업 전부를, 정지 지점에 도달했는지와 무관하게(`uploaded`·`queued`·`analyzing` 어느 단계든) 종료 상태까지 진행해 이벤트를 보낸다. 단계마다 걸린 타이머를 먼저 취소해 같은 단계 이벤트가 두 번 나가지 않으며, 호출 뒤 타이머를 흘려도 추가 이벤트가 없다. 재분석 예약이 걸린 작업은 예약된 재처리까지 끝낸다. `waiting_baseline` 사진은 시작되지 않은 작업이므로 건드리지 않는다. 호출 시점과 무관하게 결과가 같아서 E2E가 단계 타이머와 경쟁하지 않는다.
- `reset()`은 런타임의 타이머와 작업을 모두 취소한 뒤 모의 상태를 픽스처 초기값으로 되돌린다(사진 번호 `mock_photo_N`도 다시 1부터다). 각 E2E 테스트는 시작할 때 이 함수를 부른다.
- Vitest 공용 설정(`src/test/setup.ts`)은 테스트마다 단계 간격을 `setTimeout` 최댓값으로 둔 런타임을 설치해 단계가 스스로 진행하지 않게 하고, `afterEach`에서 `reset()`한다. 완료까지 보는 테스트는 자기 런타임을 설치한다.

### 워커 실패 배너

`app/bootstrap.ts`의 `bootstrap(container)`는 `VITE_API_MOCK`이 있을 때만 `mocks/browser`를 동적 import해 `startMockApi()`를 기다린 뒤 앱을 렌더한다. 기본 빌드에서는 조건이 상수 거짓이라 import가 빠진다. 불러오기·시작에 실패해도 앱은 렌더한다.

`startMockApi()`는 워커를 만들기 전에 `isSecureContext`와 `navigator.serviceWorker`를 직접 확인하고, 없으면 `MockApiUnavailableError`를 던진다. MSW 3의 `worker.start()`는 서비스 워커를 쓸 수 없어도 예외 없이 fetch 가로채기로 대신 동작하기 때문이다. 확인을 통과하면 SSE 핸들러를 포함해 워커를 시작하고(`onUnhandledFrame: "bypass"`), 런타임을 설치한 뒤 전역을 만든다.

실패하면 모든 화면 상단에 배너 "모의 API를 쓸 수 없습니다(보안 컨텍스트 아님)"와 `/camera-check` 링크("촬영 확인")를 띄운다. 이 상태에서 화면 ①②는 첫 요청인 `GET /api/meta`가 실패하므로 "시연일을 불러오지 못했습니다"를 보이고, 실기기 확인은 `/camera-check`에서 한다.

### 번들 검사

`vite.config.ts`의 `bundleModuleReport` 플러그인이 빌드마다 출력 청크별로 실제 들어간 모듈 ID를 `frontend/.build-report/modules.<default|mock>.json`에 쓴다(`dist/` 밖이라 정적 제공 대상이 아니다). `scripts/check-bundle.mjs --report <경로> [--expect-mock]`가 보고서를 읽는다.

- 기본 검사: 어느 청크든 모듈 ID에 `/node_modules/msw/` 또는 `/src/mocks/`가 있으면 해당 청크·모듈을 출력하고 비제로로 끝난다.
- `--expect-mock`: 반대로 두 패턴이 모두 하나 이상 있어야 통과한다.

`pnpm check:bundle`은 기본 빌드를 `frontend/dist`에 만들고 `modules.default.json`을 검사한다. `pnpm check:bundle:mock`은 `scripts/hash-dir.mjs dist`로 `dist`의 파일 목록·SHA-256을 기록하고, 모의 빌드를 `frontend/.build-report/dist-mock/`(`--outDir`로 분리)에 만들어 `modules.mock.json`을 검사한 뒤, `scripts/compare-files.mjs`로 `dist`가 바뀌지 않았는지 바이트 단위로 비교한다. 그래서 `check:bundle:mock`은 `check:bundle`이 만든 `dist`와 `.build-report/`를 전제로 하며 그 뒤에 실행한다.

### 테스트와 E2E

**Vitest**(jsdom, MSW node 서버): `src/**/*.test.{ts,tsx}`. 공용 설정이 `server.listen({onUnhandledFrame: "error"})`, 테스트마다 `resetHandlers`·모의 상태 `reset()`·`cleanup()`을 한다. 커버리지(`v8`)는 `src/`를 대상으로 하며 `src/api/generated/`, `src/mocks/`, `src/test/`, 테스트 파일, `*.d.ts`, `src/main.tsx`를 뺀다. 줄 커버리지 80% 미만이면 실패한다. 스타일 테스트가 `tokens.css`의 글자·배경 조합 대비 4.5:1 이상과, 모듈 CSS에 색·모서리·글꼴 리터럴이 없고 누를 수 있는 요소가 `var(--touch-min)`을 쓰는지 확인한다. jsdom은 레이아웃을 계산하지 않아 44px 실측은 E2E가 맡는다.

화면 테스트가 확인하는 규칙은 다음과 같다.

- 시연일 조회 실패 시 입력 차단과 끼니 조회 0건, 다시 시도 뒤 조회 시작
- 404·(가)·(나) 분류와 제출 성공 뒤 재조회 실패 시 성공 안내 유지·재제출 불가
- 늦게 도착한 앞선 응답 무시, 끼니 전환 직후 이벤트의 재조회와 늦은 응답 버림, 제출 전 조회의 늦은 성공이 잠금을 풀지 못함
- 첫 `open` 전에 등록된 기준 사진이 첫 `open` 뒤 재조회로 반영됨
- 제출 중 화면 이탈 뒤 늦은 응답 무시
- 업로드·전량 기록 오류(404·409·413·422·네트워크)별 안내와 입력 유지
- 같은 모의 상태를 공유하는 화면 ①②의 연동(기준 사진 등록 이벤트 → 화면 ② 안내 갱신, 기준 사진 교체 뒤 재분석과 전량 거부 보존)
- `/camera-check`가 워커 시작 실패 상태에서도 렌더되고 `fetch`·`EventSource`를 한 번도 부르지 않음
- 라우트 전환 시 SSE 연결 수(`/baseline`·`/post-meal`에서만 1회, 둘 사이 이동은 유지, `/`·`/camera-check`로 이동하면 `close()`)

**Playwright E2E**(`pnpm e2e`): Chromium 하나, 뷰포트 390×844, 포트 5180, 기존 서버를 재사용하지 않는다. 각 테스트는 `/baseline` 또는 `/post-meal`로 이동한 뒤 `reset()`을 부르고, 끼니는 시각 규칙에 기대지 않고 명시적으로 고른다.

- 화면 ①: 날짜 `2026-11-27`을 직접 입력, "저녁" 선택 → 윗줄 4칸·아랫줄 2칸 → 등록 상태 "아직 없음" → 사진 선택·업로드 → `role="status"`에 "기준 사진 등록됨", 등록 상태가 `/^등록됨 \(/`.
- 화면 ②: "오늘 점심"·`NS03` → 전량 거부 확인 시트를 열어 취소하고 기록되지 않음을 확인 → 사진 선택·업로드 → 배지 "처리 중" → `finishAll()` → "완료".
- 두 흐름 모두 날짜·끼니·환자 항목·사진 입력 라벨·업로드 버튼(②는 전량 기록 버튼과 확인 시트 버튼 포함)이 44×44px 이상인지 `boundingBox()`로 확인한다.
- 합성 식판 이미지(`tests/e2e/fixtures/tray.jpg`, 단색 도형)를 쓴다. 실제 사진이 아니다.

**백엔드**: `test_frontend_static.py`(정적 제공 응답 표), `test_export_openapi.py`(두 번 내보낸 결과가 바이트 단위로 같음, `paths`에 `/api/health`, 키 정렬).

## 제약사항

- **실제 백엔드 라우터 없음**: `/api/health`를 뺀 임시 계약의 엔드포인트는 MSW 모의로만 응답한다. `pnpm dev`(실제 백엔드 프록시)로 화면 ①②를 열면 `GET /api/meta`가 실패해 "시연일을 불러오지 못했습니다"를 보인다. 임시 계약은 제안일 뿐이며 실제 모양은 T3이 정한다.
- **MSW 모의 상태는 브라우저 탭 하나 안의 메모리**: 기기·탭 사이에 공유되지 않는다. 한 기기의 업로드나 기준 사진 등록이 다른 기기의 화면 ②에 반영되는지는 T3 실연동에서만 확인할 수 있다. 같은 탭 안의 화면 ①②는 같은 모의 상태와 이벤트 버스를 쓴다.
- **실기기는 `/camera-check`에서만 확인**: 휴대폰이 PC 주소(HTTP)로 접속하면 보안 컨텍스트가 아니라 서비스 워커(MSW)가 등록되지 않는다. 그래서 `pnpm dev:mock --host`로 접속한 실기기에서 화면 ①②의 업로드는 확인하지 못하고(워커 실패 배너가 뜬다), 업로드 전 단계(촬영·앨범·미리보기·변환)만 확인한다. 자체 서명 HTTPS나 USB 포트 포워딩은 쓰지 않는다. 실기기 업로드는 T3 연결 뒤 실제 API로 확인한다.
- **실기기 확인 결과**(2026-11-28, 합격 기준은 접속 확인·(a) 촬영·앨범 진입·(b) 디코딩되는 세로 사진의 변환 표시):

| 기기 | OS · 브라우저 | 입력 형식 | 접속 | (a) | (b) | (c) | HEIC | 결과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| iPhone | iOS(버전 미기록) · Chrome(iOS) | 카메라 촬영 사진, 앨범 HEIC | 통과 | 통과 | 통과 | 발생 안 함 | 변환됨 | 합격 |
| Android | 미수행 | 미수행 | 미수행 | 미수행 | 미수행 | 미수행 | 해당 없음 | 미수행(확인할 기기가 없음) |

  (c)는 디코딩되지 않는 입력을 만났을 때 "이 사진은 변환하지 못해 원본 그대로 보냅니다"와 원본 형식·용량이 보이고 화면이 멈추지 않는 것이다. iPhone에서는 HEIC가 JPEG로 변환되어 원본 반환 경로를 거치지 않았다. Android 확인과 다른 iOS·브라우저 조합은 이 결과에 포함되지 않는다.
- **팀 확인 전 제안 문구와 해석**: 오류 안내 문구 표의 대부분(설계 단계에서 정한 404·413 문구와 ② 409 공통 안내 제외), 촬영 안내 두 줄, 재업로드 시트의 제목·버튼, 전량 기록 시트의 제목·확인 버튼과 성공·실패 안내, "<환자> 식후 사진을 올렸습니다", "업로드 현황", "환자를 고르세요", "불러오는 중…", 등록 상태의 "등록됨 (HH:MM)" 표기가 해당한다. 환자 목록과 업로드 현황을 한 목록으로 합친 구성, 배지 색(미기록과 처리 중을 색으로 구분하지 않음), 현황 머리글에 " · 취소 m"을 붙이지 않는 것, 모의 픽스처 분포(`NS01`이 세 끼 모두 금식)도 제안이다.
- **웹 폰트의 외부 요청**: `index.html`이 Google Fonts(`Noto Sans KR`)를 `<link>`로 불러온다(`referrerpolicy="no-referrer"`). 오프라인 환경에서는 `system-ui` 대체 글꼴로 표시된다. 오프라인 시연을 위한 자체 호스팅은 하지 않았다.
- **`public/mockServiceWorker.js`가 `dist/`에 복사된다**: 정적 파일이라 기본 빌드 결과에도 들어간다. 동작에는 영향이 없다(`VITE_API_MOCK` 없이는 등록되지 않는다). 번들 검사는 청크 모듈만 보므로 이 파일은 대상이 아니다. 빼려면 빌드 뒤 처리가 필요하다.
- **SSE는 200이 아닌 응답 뒤 재연결하지 않는다**: 서버가 200이 아니거나 `text/event-stream`이 아닌 응답을 주면 브라우저가 연결을 닫고 다시 연결하지 않는다. 수동 재연결은 두지 않는다. 연결이 한 번 열린 뒤의 끊김은 `EventSource`가 자동 재연결하고, 다시 `open`이 오면 현재 끼니를 한 번 다시 읽는다.
- **`Accept`가 `text/html`인 누락 자산 요청은 `index.html`을 받는다**: `GET /assets/missing.js`에 `Accept: text/html`이 붙으면 대체 응답 조건에 맞아 `index.html`(200)이 나간다. `Accept: */*`이면 404 JSON이다.
- **`index.html`이 시작 시점에 없으면 정적 제공이 꺼진다**: 앱을 시작한 뒤 `pnpm build`로 `dist`를 처음 만들어도 재시작 전에는 등록되지 않는다.
- **큰 사진의 메모리**: `prepareUpload`는 원본 해상도 그대로 디코딩한다. 아주 큰 사진(48MP 등)의 메모리 사용은 실기기에서 확인되지 않았다. 변환에 실패하면 원본 파일이 그대로 업로드 대상이 되며, 그 검증은 서버(T3) 몫이다.
- **T3이 정하는 사항**: 이 토픽은 아래를 제안만 하고 결정하지 않는다.
  - 임시 계약 표(특히 확장 두 가지: `GET /api/meta`와 끼니 조회의 `orders`)를 그대로 받을지
  - 업로드 크기 상한과 413 처리
  - 처리 중·완료 끼니에 업로드·전량 기록이 오면 409로 거절할지(지금은 화면에서 막는다)
  - 끼니 단위 SSE 필터를 `docs/system-architecture.md` 8-1절에 반영하는 문서 수정
  - 이벤트 데이터 확장(`kind` 필드, 기준 사진 이벤트의 환자·발주 `null`)을 실제 SSE에서도 쓸지. 쓰지 않더라도 기준 사진 저장 직후 그 끼니의 `meal_plan_id`가 담긴 `photo.status_changed`는 보내야 화면 ②의 안내가 갱신된다
  - 디코딩되지 않아 원본으로 올라오는 형식(예: HEIC)을 서버가 받아 변환할지(pillow-heif 등) 422로 거절할지
  - 기준 사진 교체 때 분석 중이던 식후 사진을 끝난 뒤 다시 분석하는 규칙(재분석 예약)과, 재촬영 필요 상태에서 전량 기록할 때 기존 사진 연결을 끊고 재분석 대상에서 빼는 규칙을 실제 작업 실행기에서도 같게 할지
