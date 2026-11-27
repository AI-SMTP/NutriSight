import { formatBytes } from "./format";

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [1023, "1023 B"],
    [1024, "1.0 KB"],
    [1536, "1.5 KB"],
    [1_048_575, "1.0 MB"],
    [1_048_576, "1.0 MB"],
    [5_452_595, "5.2 MB"],
  ])("%d바이트를 %s로 표기한다", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  it.each([-1, Number.NaN, Number.POSITIVE_INFINITY])(
    "잘못된 값 %d는 '알 수 없음'이다",
    (bytes) => {
      expect(formatBytes(bytes)).toBe("알 수 없음");
    },
  );
});
