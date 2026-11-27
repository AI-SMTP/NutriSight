import { describeUpload } from "./describeUpload";

describe("describeUpload", () => {
  it("변환에 성공하면 원본·변환 크기와 용량을 보여 준다", () => {
    const text = describeUpload({
      blob: new Blob(),
      converted: true,
      source: { type: "image/heic", bytes: 5_242_880, width: 4032, height: 3024 },
      output: { type: "image/jpeg", bytes: 627_000, width: 2048, height: 1536 },
    });

    expect(text).toBe("변환됨 · JPEG · 원본 4032×3024, 5.0 MB → 변환 2048×1536, 612.3 KB");
  });

  it("변환에 실패하면 원본 형식과 용량을 보여 준다", () => {
    const text = describeUpload({
      blob: new Blob(),
      converted: false,
      source: { type: "image/heic", bytes: 3_145_728 },
    });

    expect(text).toBe("이 사진은 변환하지 못해 원본 그대로 보냅니다 · image/heic, 3.0 MB");
  });

  it("브라우저가 형식을 알려 주지 않으면 '형식 알 수 없음'으로 적는다", () => {
    const text = describeUpload({
      blob: new Blob(),
      converted: false,
      source: { type: "", bytes: 10 },
    });

    expect(text).toBe("이 사진은 변환하지 못해 원본 그대로 보냅니다 · 형식 알 수 없음, 10 B");
  });
});
