// 오류 시나리오 핸들러. 테스트가 `server.use(errorHandlers.postUpload("conflict"))`처럼 기본 핸들러 위에 얹는다.
// 화면은 상태 코드로만 안내를 고르므로(스펙 3.3절) 본문은 FastAPI 기본 형태(`{detail}`)만 맞춘다.
import { http, HttpResponse, type HttpHandler } from "msw";

import type { ApiErrorKind } from "../api/provisional";

/** `ApiErrorKind`별 응답 상태 코드와 `detail` 문구. `network`는 응답 없이 연결 오류로 끝낸다 */
const KIND_RESPONSES: Readonly<
  Record<Exclude<ApiErrorKind, "network">, { status: number; message: string }>
> = {
  not_found: { status: 404, message: "모의 오류: 대상을 찾을 수 없습니다" },
  conflict: { status: 409, message: "모의 오류: 지금 기록할 수 없습니다" },
  too_large: { status: 413, message: "모의 오류: 사진이 너무 큽니다" },
  invalid: { status: 422, message: "모의 오류: 요청 형식이 올바르지 않습니다" },
  server: { status: 500, message: "모의 오류: 서버 오류" },
};

/** FastAPI 기본 오류 본문(`{detail}`) 응답. 기본 핸들러도 같은 형태로 쓴다 */
export function detailResponse(status: number, message: string): Response {
  return HttpResponse.json({ detail: message }, { status });
}

function errorResponse(kind: ApiErrorKind): Response {
  if (kind === "network") return HttpResponse.error();
  const { status, message } = KIND_RESPONSES[kind];
  return detailResponse(status, message);
}

function errorHandler(method: "get" | "post", path: string) {
  return (kind: ApiErrorKind): HttpHandler => http[method](path, () => errorResponse(kind));
}

/** 엔드포인트별 오류 핸들러 생성기 */
export const errorHandlers = {
  meta: errorHandler("get", "/api/meta"),
  meal: errorHandler("get", "/api/meals/:date/:meal"),
  baselineUpload: errorHandler("post", "/api/meals/:date/:meal/baseline"),
  postUpload: errorHandler("post", "/api/photos"),
  staffZero: errorHandler("post", "/api/meal-orders/:id/staff-zero"),
} as const;
