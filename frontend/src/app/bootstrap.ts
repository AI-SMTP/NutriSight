/**
 * 앱 부트스트랩. 모의 API 모드면 MSW 워커 시작을 기다린 뒤 렌더하고, 실패하면 배너와 함께 렌더한다.
 *
 * - 정본: `docs/specs/frontend-shell-upload.md` '실행 모드'·'워커 실패 배너', '이미지 변환'(`/camera-check`).
 * - `main.tsx`는 이 함수만 부른다. 분기는 모두 여기에 두어 테스트한다.
 * - 모의 코드(`mocks/browser`)는 `VITE_API_MOCK`이 있을 때만 동적 import한다. 기본 빌드에서는
 *   조건이 상수 거짓이 되어 import가 빠지므로 MSW 코드가 번들에 들어가지 않는다.
 */
import { createElement, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";

import { App } from "./App";

/** 모의 API 모듈(`mocks/browser.ts`)에서 부트스트랩이 쓰는 부분 */
export interface MockApiModule {
  startMockApi(): Promise<void>;
}

export type MockApiLoader = () => Promise<MockApiModule>;

export interface BootstrapOptions {
  /** 모의 API 모듈을 불러오는 함수. `null`이면 모의 API를 쓰지 않는다. 기본은 `VITE_API_MOCK`으로 정한다 */
  loadMockApi?: MockApiLoader | null;
}

const DEFAULT_LOADER: MockApiLoader | null = import.meta.env.VITE_API_MOCK
  ? () => import("../mocks/browser")
  : null;

/** 모의 API를 시작한다. 쓰지 않거나 시작했으면 참, 불러오기·시작에 실패했으면 거짓 */
async function startMockApiIfEnabled(load: MockApiLoader | null): Promise<boolean> {
  if (!load) return true;
  try {
    const mockApi = await load();
    await mockApi.startMockApi();
    return true;
  } catch {
    // 보안 컨텍스트가 아니면(HTTP로 접속한 실기기) 서비스 워커 등록이 실패한다.
    // 앱은 그대로 렌더하고 배너로 알린다(참조 문서 '워커 실패 배너'). 원인은 배너 문구로만 보인다.
    return false;
  }
}

/** 모의 API 준비를 기다린 뒤 `container`에 앱을 렌더한다 */
export async function bootstrap(
  container: HTMLElement,
  { loadMockApi = DEFAULT_LOADER }: BootstrapOptions = {},
): Promise<Root> {
  const mockReady = await startMockApiIfEnabled(loadMockApi);
  const root = createRoot(container);
  root.render(createElement(StrictMode, null, createElement(App, { mockUnavailable: !mockReady })));
  return root;
}
