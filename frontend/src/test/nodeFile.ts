// Vitest jsdom 환경에서는 전역 `File`이 jsdom 것이라 Node `FormData`가 파일 항목을 만들지 못한다
// (multipart 본문이 비거나 파싱 단언이 실패한다). multipart를 보내는 테스트 묶음에서만 Node `File`로 바꿔 둔다.
// 전역으로 바꾸지 않는 이유: `<input type="file">`의 `FileList`·user-event `upload`는 jsdom `File`만 받는다.
// 브라우저 동작과는 무관한 테스트 환경 우회다.

/** 현재 `describe` 묶음의 각 테스트 동안 전역 `File`을 Node `File`로 바꾼다 */
export function useNodeFileForMultipart(): void {
  beforeEach(async () => {
    const { File: NodeFile } = await import("node:buffer");
    vi.stubGlobal("File", NodeFile);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });
}
