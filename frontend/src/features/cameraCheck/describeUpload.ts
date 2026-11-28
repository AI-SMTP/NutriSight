// /camera-check 결과 문구(`docs/specs/frontend-shell-upload.md` '이미지 변환'). 값은 모두 prepareUpload()의 PreparedUpload에서 읽는다.
import { formatBytes } from "../../lib/format";
import type { PreparedUpload } from "../../lib/image";

const UNKNOWN_TYPE = "형식 알 수 없음";

/** 변환 결과를 한 줄 문구로 만든다. 성공이면 원본→변환 크기·용량, 실패면 원본 형식·용량. */
export function describeUpload({ converted, source, output }: PreparedUpload): string {
  if (converted && output) {
    const sourceSize = `${source.width ?? "?"}×${source.height ?? "?"}`;
    return (
      `변환됨 · JPEG · 원본 ${sourceSize}, ${formatBytes(source.bytes)}` +
      ` → 변환 ${output.width}×${output.height}, ${formatBytes(output.bytes)}`
    );
  }
  const type = source.type || UNKNOWN_TYPE;
  return `이 사진은 변환하지 못해 원본 그대로 보냅니다 · ${type}, ${formatBytes(source.bytes)}`;
}
