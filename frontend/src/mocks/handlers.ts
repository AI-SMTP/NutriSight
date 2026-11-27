import type { HttpHandler } from "msw";

/** 모의 API 기본 핸들러. 브라우저 워커와 Vitest node 서버가 함께 쓴다(Story 9에서 채운다). */
export const handlers: HttpHandler[] = [];
