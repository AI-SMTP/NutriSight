import { formatBytes, formatClock } from "./format";

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

describe("formatClock", () => {
  it.each([
    [new Date(2026, 10, 27, 7, 5), "07:05"],
    [new Date(2026, 10, 27, 17, 20), "17:20"],
    [new Date(2026, 10, 27, 0, 0), "00:00"],
  ])("ISO 시각 %s를 기기 로컬 시각 %s로 표기한다", (date, expected) => {
    expect(formatClock(date.toISOString())).toBe(expected);
  });

  it.each(["", "not-a-date"])("해석할 수 없는 값 '%s'는 '--:--'다", (value) => {
    expect(formatClock(value)).toBe("--:--");
  });
});
