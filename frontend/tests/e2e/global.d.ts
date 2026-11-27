// 앱의 개발 전용 전역(`src/mocks/devGlobal.ts`)을 E2E에서 쓰는 만큼만 선언한다.
// 앱 소스를 E2E 타입 검사에 끌어오지 않으려고 따로 둔다.
export {};

declare global {
  interface Window {
    __nutrisightMock?: {
      reset(): void;
      finishAll(): void;
    };
  }
}
