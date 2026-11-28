// 서비스 워커 사용 가능 여부 대역. jsdom에는 `isSecureContext`와 `navigator.serviceWorker`가 없다.
// `isSecureContext`는 vi.stubGlobal로 바꾸므로 vi.unstubAllGlobals()가 되돌리고,
// `navigator.serviceWorker`는 restoreServiceWorkerSupport()로 지운다.

export function stubServiceWorkerSupport({
  secure,
  serviceWorker,
}: {
  secure: boolean;
  serviceWorker: boolean;
}): void {
  vi.stubGlobal("isSecureContext", secure);
  Reflect.deleteProperty(navigator, "serviceWorker");
  if (serviceWorker) {
    Object.defineProperty(navigator, "serviceWorker", { value: {}, configurable: true });
  }
}

export function restoreServiceWorkerSupport(): void {
  Reflect.deleteProperty(navigator, "serviceWorker");
}
