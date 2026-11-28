// prepareUpload() 대역 공용 도우미. jsdom에는 createImageBitmap과 캔버스 인코딩이 없으므로
// vi.stubGlobal로 비트맵 크기와 인코딩 결과를 주입한다(lib/image.test.ts, app/bootstrap.test.ts).

export type FakeBitmap = { width: number; height: number; close: ReturnType<typeof vi.fn> };

export function makeBitmap(width: number, height: number): FakeBitmap {
  return { width, height, close: vi.fn() };
}

export function jpegBlob(bytes = 1234): Blob {
  return new Blob([new Uint8Array(bytes)], { type: "image/jpeg" });
}

// OffscreenCanvas 대역: 생성 크기, convertToBlob 인자와 호출 시점의 캔버스 크기를 기록한다.
export function stubOffscreenCanvas(options: {
  convertToBlob?: () => Promise<Blob>;
  context?: unknown;
}) {
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

export function stubDecode(bitmap: FakeBitmap) {
  const createImageBitmap = vi.fn(() => Promise.resolve(bitmap));
  vi.stubGlobal("createImageBitmap", createImageBitmap);
  return createImageBitmap;
}
