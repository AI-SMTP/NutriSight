/**
 * 생성 타입(`generated/schema.d.ts`)을 쓰는 openapi-fetch 클라이언트.
 *
 * 지금 백엔드 OpenAPI에는 `/api/health`뿐이다. 화면 ①②가 쓰는 엔드포인트는 T3이 라우터를 만들 때까지
 * `provisional.ts`(임시 계약)에 둔다. T3 연결 뒤 `pnpm gen:api`로 타입을 다시 만들고 이 클라이언트로 옮긴다.
 */
import createClient from "openapi-fetch";

import type { operations, paths } from "./generated/schema";

// `baseUrl`은 현재 출처다. openapi-fetch는 `new Request(baseUrl + path)`를 만드는데, jsdom(Node)의
// `Request`는 상대 URL을 받지 않는다. 브라우저·Vite 프록시·MSW 워커에서는 같은 출처라 그대로 맞는다.
// `location`이 없는 순수 Node 환경은 쓰지 않는다.
// `fetch`는 호출할 때마다 전역에서 찾는다. 클라이언트 생성 시점에 붙잡으면 MSW가 나중에 바꾼
// `fetch`(Vitest node 서버, 브라우저 워커 시작 뒤)를 쓰지 못한다.
export const apiClient = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  fetch: (request) => globalThis.fetch(request),
});

/** 생성 타입에서 꺼낸 `GET /api/health` 200 응답 본문. */
export type HealthResponse =
  operations["health_api_health_get"]["responses"][200]["content"]["application/json"];

/** `GET /api/health`. 서버가 응답하지 않거나 오류면 예외를 던진다. */
export async function getHealth(): Promise<HealthResponse> {
  // 생성 타입에 오류 응답이 정의돼 있지 않아 `error`는 never다. 상태 코드와 본문으로 판정한다.
  const { data, response } = await apiClient.GET("/api/health");
  if (!response.ok || data === undefined) {
    throw new Error(`헬스체크 실패: HTTP ${response.status}`);
  }
  return data;
}
