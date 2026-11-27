import { http, HttpResponse } from "msw";

import { server } from "../mocks/server";
import { getHealth } from "./client";

describe("getHealth", () => {
  it("공용 MSW 서버의 응답을 생성 타입으로 돌려준다", async () => {
    server.use(http.get("/api/health", () => HttpResponse.json({ status: "ok" })));

    await expect(getHealth()).resolves.toEqual({ status: "ok" });
  });

  it("서버 오류면 예외를 던진다", async () => {
    server.use(http.get("/api/health", () => new HttpResponse(null, { status: 500 })));

    await expect(getHealth()).rejects.toThrow("HTTP 500");
  });
});
