import { setupServer } from "msw/node";

import { handlers } from "./handlers";

/** Vitest용 MSW node 서버. 테스트는 `server.use(...)`로 테스트별 핸들러를 얹는다. */
export const server = setupServer(...handlers);
