// 임시 계약 호출 테스트 공용 도우미: 작은 JPEG 본문과 ApiError 단언.
import { ApiError, type ApiErrorKind } from "../api/provisional";

/** JPEG 시그니처만 담은 작은 본문 */
export function jpegBlob(): Blob {
  return new Blob([new Uint8Array([0xff, 0xd8, 0xff])], { type: "image/jpeg" });
}

/** 실패해야 하는 호출의 ApiError(kind·status)를 확인한다 */
export async function expectApiError(
  promise: Promise<unknown>,
  kind: ApiErrorKind,
  status?: number,
): Promise<void> {
  const error = await promise.then(
    () => {
      throw new Error("예외가 나야 한다");
    },
    (err: unknown) => err,
  );
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ kind, status });
}
