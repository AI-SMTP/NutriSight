/// <reference types="vite/client" />

// 앱이 읽는 Vite 환경 변수(`docs/specs/frontend-shell-upload.md` '실행 모드'). 값이 없으면 `undefined`다.
interface ImportMetaEnv {
  /** 있으면 MSW 워커로 임시 계약을 모의한다(`pnpm dev:mock`) */
  readonly VITE_API_MOCK?: string;
  /** `manual`이면 모의 처리가 첫 analyzing에서 멈춘다(E2E 단계 제어) */
  readonly VITE_MOCK_STEPS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
