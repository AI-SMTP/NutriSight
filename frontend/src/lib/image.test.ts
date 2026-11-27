// prepareUpload() 테스트. jsdom에는 createImageBitmap과 캔버스 인코딩이 없으므로
// vi.stubGlobal로 비트맵 크기와 인코딩 결과를 주입한다.
import { JPEG_QUALITY, MAX_EDGE_PX, prepareUpload } from "./image";

type FakeBitmap = { width: number; height: number; close: ReturnType<typeof vi.fn> };

function makeFile(bytes = 5000, type = "image/heic"): File {
  return new File([new Uint8Array(bytes)], "tray.heic", { type });
}

function makeBitmap(width: number, height: number): FakeBitmap {
  return { width, height, close: vi.fn() };
}

function jpegBlob(bytes = 1234): Blob {
  return new Blob([new Uint8Array(bytes)], { type: "image/jpeg" });
}

// OffscreenCanvas 대역: 생성 크기, convertToBlob 인자와 호출 시점의 캔버스 크기를 기록한다.
function stubOffscreenCanvas(options: { convertToBlob?: () => Promise<Blob>; context?: unknown }) {
  const drawImage = vi.fn();
  const instances: FakeOffscreenCanvas[] = [];
  const context = options.context === undefined ? { drawImage } : options.context;
  const encode = options.convertToBlob ?? (() => Promise.resolve(jpegBlob()));
  class FakeOffscreenCanvas {
    width: number;
    height: number;
    sizeAtEncode?: { width: number; height: number };
    convertToBlob = vi.fn(() => {
      this.sizeAtEncode = { width: this.width, height: this.height };
      return encode();
    });
    constructor(width: number, height: number) {
      this.width = width;
      this.height = height;
      instances.push(this);
    }
    getContext() {
      return context;
    }
  }
  vi.stubGlobal("OffscreenCanvas", FakeOffscreenCanvas);
  return { drawImage, instances };
}

// canvas 요소 대역: getContext·toBlob을 가로채고 toBlob 호출 시점의 캔버스 크기를 기록한다.
function stubCanvasElement(toBlobResult: Blob | null, options: { context?: unknown } = {}) {
  const drawImage = vi.fn();
  const context = options.context === undefined ? { drawImage } : options.context;
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () => context as CanvasRenderingContext2D | null,
  );
  const sizesAtEncode: { width: number; height: number }[] = [];
  const toBlob = vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (
    this: HTMLCanvasElement,
    callback: BlobCallback,
  ) {
    sizesAtEncode.push({ width: this.width, height: this.height });
    callback(toBlobResult);
  });
  const createElement = vi.spyOn(document, "createElement");
  const createdCanvases = () =>
    createElement.mock.results
      .map((r) => r.value as unknown)
      .filter((v): v is HTMLCanvasElement => v instanceof HTMLCanvasElement);
  return { drawImage, toBlob, sizesAtEncode, createdCanvases };
}

function stubDecode(bitmap: FakeBitmap) {
  const createImageBitmap = vi.fn(() => Promise.resolve(bitmap));
  vi.stubGlobal("createImageBitmap", createImageBitmap);
  return createImageBitmap;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("prepareUpload", () => {
  it("상수는 긴 변 2048px, JPEG 품질 0.9다", () => {
    expect(MAX_EDGE_PX).toBe(2048);
    expect(JPEG_QUALITY).toBe(0.9);
  });

  it("4032×3024 사진을 긴 변 2048px JPEG로 줄인다", async () => {
    const bitmap = makeBitmap(4032, 3024);
    stubDecode(bitmap);
    const out = jpegBlob(4321);
    const { drawImage, instances } = stubOffscreenCanvas({
      convertToBlob: () => Promise.resolve(out),
    });
    const file = makeFile(5000);

    const result = await prepareUpload(file);

    expect(result.converted).toBe(true);
    expect(result.blob).toBe(out);
    expect(result.blob.type).toBe("image/jpeg");
    expect(result.source).toEqual({ type: "image/heic", bytes: 5000, width: 4032, height: 3024 });
    expect(result.output).toEqual({ type: "image/jpeg", bytes: 4321, width: 2048, height: 1536 });
    expect(instances[0]?.sizeAtEncode).toEqual({ width: 2048, height: 1536 });
    // 인코딩이 끝나면 캔버스를 비워 메모리를 반납한다.
    expect(instances[0]?.width).toBe(0);
    expect(instances[0]?.height).toBe(0);
    expect(drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 2048, 1536);
    expect(instances[0]?.convertToBlob).toHaveBeenCalledWith({
      type: "image/jpeg",
      quality: 0.9,
    });
    expect(bitmap.close).toHaveBeenCalledOnce();
  });

  it("세로 사진도 긴 변 기준으로 비율을 유지해 줄인다", async () => {
    stubDecode(makeBitmap(3024, 4032));
    stubOffscreenCanvas({});

    const result = await prepareUpload(makeFile());

    expect(result.output).toMatchObject({ width: 1536, height: 2048 });
  });

  it("1000×750 사진은 크기를 유지하고 JPEG로만 바꾼다", async () => {
    stubDecode(makeBitmap(1000, 750));
    const out = jpegBlob(800);
    stubOffscreenCanvas({ convertToBlob: () => Promise.resolve(out) });
    const file = makeFile(3000, "image/png");

    const result = await prepareUpload(file);

    expect(result.converted).toBe(true);
    expect(result.source).toEqual({
      type: "image/png",
      bytes: file.size,
      width: 1000,
      height: 750,
    });
    expect(result.output).toEqual({
      type: "image/jpeg",
      bytes: out.size,
      width: 1000,
      height: 750,
    });
  });

  it("createImageBitmap을 imageOrientation: from-image로 부른다", async () => {
    const createImageBitmap = stubDecode(makeBitmap(1000, 750));
    stubOffscreenCanvas({});
    const file = makeFile();

    await prepareUpload(file);

    expect(createImageBitmap).toHaveBeenCalledWith(file, { imageOrientation: "from-image" });
  });

  it("디코딩에 실패하면 원본 File을 크기 없이 돌려준다", async () => {
    vi.stubGlobal(
      "createImageBitmap",
      vi.fn(() => Promise.reject(new DOMException("decode failed", "InvalidStateError"))),
    );
    const file = makeFile(7000);

    const result = await prepareUpload(file);

    expect(result.converted).toBe(false);
    expect(result.blob).toBe(file);
    expect(result.source).toEqual({ type: "image/heic", bytes: 7000 });
    expect(result.source).not.toHaveProperty("width");
    expect(result.source).not.toHaveProperty("height");
    expect(result).not.toHaveProperty("output");
  });

  it("createImageBitmap이 없는 브라우저면 디코딩 실패로 처리한다", async () => {
    vi.stubGlobal("createImageBitmap", undefined);
    const file = makeFile();

    const result = await prepareUpload(file);

    expect(result.converted).toBe(false);
    expect(result.blob).toBe(file);
    expect(result).not.toHaveProperty("output");
  });

  it("JPEG 인코딩에 실패하면 원본 File과 디코딩 크기를 돌려준다", async () => {
    const bitmap = makeBitmap(4032, 3024);
    stubDecode(bitmap);
    const { instances } = stubOffscreenCanvas({
      convertToBlob: () => Promise.reject(new Error("encode failed")),
    });
    const file = makeFile(5000);

    const result = await prepareUpload(file);

    expect(result.converted).toBe(false);
    expect(result.blob).toBe(file);
    expect(result.source).toEqual({ type: "image/heic", bytes: 5000, width: 4032, height: 3024 });
    expect(result).not.toHaveProperty("output");
    expect(bitmap.close).toHaveBeenCalledOnce();
    expect(instances[0]?.width).toBe(0);
    expect(instances[0]?.height).toBe(0);
  });

  it("OffscreenCanvas의 2d 컨텍스트가 null이면 canvas 요소로 인코딩한다", async () => {
    const bitmap = makeBitmap(4032, 3024);
    stubDecode(bitmap);
    const { instances } = stubOffscreenCanvas({ context: null });
    const out = jpegBlob(555);
    const { drawImage, toBlob, sizesAtEncode } = stubCanvasElement(out);

    const result = await prepareUpload(makeFile());

    expect(result.converted).toBe(true);
    expect(result.blob).toBe(out);
    expect(result.output).toEqual({ type: "image/jpeg", bytes: 555, width: 2048, height: 1536 });
    expect(drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 2048, 1536);
    expect(toBlob).toHaveBeenCalledOnce();
    expect(sizesAtEncode).toEqual([{ width: 2048, height: 1536 }]);
    expect(instances[0]?.convertToBlob).not.toHaveBeenCalled();
    // 쓰지 못한 OffscreenCanvas도 비운다.
    expect(instances[0]?.width).toBe(0);
    expect(instances[0]?.height).toBe(0);
  });

  it("인코딩 결과가 JPEG가 아니면 변환 실패로 처리한다", async () => {
    stubDecode(makeBitmap(1000, 750));
    stubOffscreenCanvas({
      convertToBlob: () => Promise.resolve(new Blob([new Uint8Array(10)], { type: "image/png" })),
    });
    const file = makeFile();

    const result = await prepareUpload(file);

    expect(result.converted).toBe(false);
    expect(result.blob).toBe(file);
    expect(result).not.toHaveProperty("output");
  });

  describe("OffscreenCanvas가 없으면 canvas 요소를 쓴다", () => {
    beforeEach(() => {
      vi.stubGlobal("OffscreenCanvas", undefined);
    });

    it("toBlob으로 JPEG를 만들고 캔버스를 비운다", async () => {
      const bitmap = makeBitmap(4032, 3024);
      stubDecode(bitmap);
      const out = jpegBlob(999);
      const { drawImage, toBlob, sizesAtEncode, createdCanvases } = stubCanvasElement(out);

      const result = await prepareUpload(makeFile());

      expect(result.converted).toBe(true);
      expect(result.blob).toBe(out);
      expect(result.output).toEqual({ type: "image/jpeg", bytes: 999, width: 2048, height: 1536 });
      expect(drawImage).toHaveBeenCalledWith(bitmap, 0, 0, 2048, 1536);
      expect(toBlob).toHaveBeenCalledWith(expect.any(Function), "image/jpeg", 0.9);
      expect(sizesAtEncode).toEqual([{ width: 2048, height: 1536 }]);
      expect(createdCanvases()).toHaveLength(1);
      expect(createdCanvases()[0]?.width).toBe(0);
      expect(createdCanvases()[0]?.height).toBe(0);
      expect(bitmap.close).toHaveBeenCalledOnce();
    });

    it("toBlob이 null을 주면 원본 File을 돌려주고 캔버스를 비운다", async () => {
      const bitmap = makeBitmap(1000, 750);
      stubDecode(bitmap);
      const { createdCanvases } = stubCanvasElement(null);
      const file = makeFile();

      const result = await prepareUpload(file);

      expect(result.converted).toBe(false);
      expect(result.blob).toBe(file);
      expect(result.source).toMatchObject({ width: 1000, height: 750 });
      expect(result).not.toHaveProperty("output");
      expect(createdCanvases()[0]?.width).toBe(0);
      expect(createdCanvases()[0]?.height).toBe(0);
      expect(bitmap.close).toHaveBeenCalledOnce();
    });

    it("2d 컨텍스트가 null이면 원본 File과 디코딩 크기를 돌려준다", async () => {
      const bitmap = makeBitmap(1000, 750);
      stubDecode(bitmap);
      const { toBlob, createdCanvases } = stubCanvasElement(jpegBlob(), { context: null });
      const file = makeFile();

      const result = await prepareUpload(file);

      expect(result.converted).toBe(false);
      expect(result.blob).toBe(file);
      expect(result.source).toMatchObject({ width: 1000, height: 750 });
      expect(result).not.toHaveProperty("output");
      expect(toBlob).not.toHaveBeenCalled();
      expect(createdCanvases()[0]?.width).toBe(0);
      expect(bitmap.close).toHaveBeenCalledOnce();
    });
  });

  it("OffscreenCanvas와 canvas 요소 모두 2d 컨텍스트가 null이면 원본 File을 돌려준다", async () => {
    stubDecode(makeBitmap(1000, 750));
    stubOffscreenCanvas({ context: null });
    stubCanvasElement(jpegBlob(), { context: null });
    const file = makeFile();

    const result = await prepareUpload(file);

    expect(result.converted).toBe(false);
    expect(result.blob).toBe(file);
    expect(result.source).toMatchObject({ width: 1000, height: 750 });
    expect(result).not.toHaveProperty("output");
  });
});
