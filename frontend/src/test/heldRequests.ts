// 끼니 조회 경합 테스트 도우미. `GET /api/meals/{date}/{meal}`을 붙잡아 두고 테스트가 정한 순서·결과로
// 하나씩 끝낸다. 끝낼 때 결과를 주지 않으면 기본 핸들러(그 시점의 모의 상태)로 넘긴다.
// 함께 `/api/` 요청 기록(메서드·경로)을 남겨 "조회만 보냈는지"를 확인한다.
//
// 핸들러 순서 전제: `server.use`는 새 핸들러를 앞에 붙인다. 두 도우미는 결과를 주지 않으면 다음 핸들러로
// 넘기므로, `recordApiRequests()`는 다른 `server.use(...)`(holdMealRequests·errorHandlers 등)를 모두 부른
// 뒤 마지막에 부른다. 먼저 부르면 나중에 얹은 오류 핸들러가 앞에서 응답해 요청이 기록되지 않는다.
import { http, HttpResponse, type JsonBodyType } from "msw";

import type { ApiErrorKind } from "../api/provisional";
import { errorResponse } from "../mocks/errorHandlers";
import { server } from "../mocks/server";

/** 붙잡힌 요청이 끝날 방식 */
type Release =
  { type: "pass" } | { type: "json"; body: JsonBodyType } | { type: "fail"; kind: ApiErrorKind };

export interface HeldRequest {
  /** 요청 경로(`/api/meals/2026-11-27/lunch`) */
  readonly path: string;
  /** 요청의 취소 신호. 클라이언트가 요청을 취소(abort)했는지 확인한다 */
  readonly signal: AbortSignal;
  /** 기본 핸들러로 넘긴다(그 시점의 모의 상태로 응답) */
  pass(): void;
  /** 주어진 본문으로 200 응답한다 */
  respond(body: JsonBodyType): void;
  /** 오류로 끝낸다(`network`는 연결 오류) */
  fail(kind: ApiErrorKind): void;
}

function toResponse(release: Release): Response | undefined {
  if (release.type === "pass") return undefined;
  if (release.type === "json") return HttpResponse.json(release.body);
  return errorResponse(release.kind);
}

/** 이후의 끼니 조회를 모두 붙잡는다. `held`에 도착 순서대로 쌓인다 */
export function holdMealRequests(): { held: readonly HeldRequest[] } {
  const held: HeldRequest[] = [];
  server.use(
    http.get("/api/meals/:date/:meal", async ({ request }) => {
      const release = await new Promise<Release>((resolve) => {
        held.push({
          path: new URL(request.url).pathname,
          signal: request.signal,
          pass: () => resolve({ type: "pass" }),
          respond: (body) => resolve({ type: "json", body }),
          fail: (kind) => resolve({ type: "fail", kind }),
        });
      });
      return toResponse(release);
    }),
  );
  return { held };
}

/** 이후 `/api/` 요청을 `"GET /api/meals/2026-11-27/lunch"` 형태로 기록한다(응답은 다음 핸들러가 한다) */
export function recordApiRequests(): { requests: readonly string[] } {
  const requests: string[] = [];
  server.use(
    http.all("/api/*", ({ request }) => {
      requests.push(`${request.method} ${new URL(request.url).pathname}`);
      return undefined;
    }),
  );
  return { requests };
}
