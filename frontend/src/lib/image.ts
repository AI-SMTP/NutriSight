// 업로드 전 사진 변환(스펙 3.6절). 긴 변을 MAX_EDGE_PX 이하로 줄여 JPEG로 만들고,
// 디코딩이나 변환이 실패하면 원본 File을 그대로 돌려준다(검증은 서버에 맡긴다).
// - imageOrientation 옵션을 지원하지 않는 엔진은 디코딩 실패로 처리되어 원본을 보낸다.
// - 원본 해상도 그대로 디코딩하므로 아주 큰 사진(48MP 등)의 메모리 사용은 실기기 확인 대상이다.

export const MAX_EDGE_PX = 2048;
export const JPEG_QUALITY = 0.9;

const OUTPUT_TYPE = "image/jpeg";

export type PreparedUpload = {
  blob: Blob;
  converted: boolean;
  source: { type: string; bytes: number; width?: number; height?: number };
  output?: { type: string; bytes: number; width: number; height: number };
};

type Size = { width: number; height: number };

// 긴 변이 MAX_EDGE_PX보다 크면 비율을 유지해 줄인다. 작으면 그대로 둔다.
function fitWithin({ width, height }: Size): Size {
  const longEdge = Math.max(width, height);
  if (longEdge <= MAX_EDGE_PX) return { width, height };
  const scale = MAX_EDGE_PX / longEdge;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

type Canvas = HTMLCanvasElement | OffscreenCanvas;

// iOS는 캔버스 메모리를 늦게 반납하므로 다 쓴 캔버스는 크기를 0으로 줄여 비운다.
function releaseCanvas(canvas: Canvas): void {
  canvas.width = 0;
  canvas.height = 0;
}

// OffscreenCanvas로 인코딩한다. 2d 컨텍스트를 얻지 못하면 null을 돌려 canvas 요소로 넘긴다.
async function encodeWithOffscreen(bitmap: ImageBitmap, size: Size): Promise<Blob | null> {
  const canvas = new OffscreenCanvas(size.width, size.height);
  try {
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(bitmap, 0, 0, size.width, size.height);
    return await canvas.convertToBlob({ type: OUTPUT_TYPE, quality: JPEG_QUALITY });
  } finally {
    releaseCanvas(canvas);
  }
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("JPEG 인코딩 실패"))),
      OUTPUT_TYPE,
      JPEG_QUALITY,
    );
  });
}

async function encodeWithElement(bitmap: ImageBitmap, size: Size): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  try {
    const context = canvas.getContext("2d");
    if (!context) throw new Error("2d 컨텍스트를 얻지 못했습니다");
    context.drawImage(bitmap, 0, 0, size.width, size.height);
    return await canvasToBlob(canvas);
  } finally {
    releaseCanvas(canvas);
  }
}

// OffscreenCanvas를 우선 쓰고, 없거나 컨텍스트를 못 얻으면(구형 Safari 등) canvas 요소로 대신한다.
async function encodeJpeg(bitmap: ImageBitmap, size: Size): Promise<Blob> {
  const offscreen =
    typeof OffscreenCanvas === "function" ? await encodeWithOffscreen(bitmap, size) : null;
  const blob = offscreen ?? (await encodeWithElement(bitmap, size));
  // JPEG를 지원하지 않는 브라우저는 PNG로 대신 인코딩하므로 실패로 본다.
  if (blob.type !== OUTPUT_TYPE) throw new Error(`JPEG가 아닌 결과: ${blob.type}`);
  return blob;
}

async function decode(file: File): Promise<ImageBitmap | null> {
  try {
    return await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    // 지원하지 않는 형식이거나 createImageBitmap이 없는 브라우저: 원본을 보낸다.
    return null;
  }
}

export async function prepareUpload(file: File): Promise<PreparedUpload> {
  const source = { type: file.type, bytes: file.size };
  const bitmap = await decode(file);
  if (!bitmap) return { blob: file, converted: false, source };

  const decoded = { ...source, width: bitmap.width, height: bitmap.height };
  try {
    const size = fitWithin(bitmap);
    const blob = await encodeJpeg(bitmap, size);
    return {
      blob,
      converted: true,
      source: decoded,
      output: { type: blob.type, bytes: blob.size, ...size },
    };
  } catch {
    // 그리기·인코딩 실패: 디코딩 크기만 남기고 원본을 보낸다.
    return { blob: file, converted: false, source: decoded };
  } finally {
    bitmap.close();
  }
}
