import { useEffect, type RefObject } from "react";

/**
 * 요청이 시작되면 패널 제목으로 포커스를 옮긴다(버튼이 막히고 시트가 닫혀도 body로 빠지지 않게).
 * `titleRef`는 `tabIndex={-1}`인 제목에 붙인 ref다. 화면이 확인 시트의 대체 포커스로도 함께 쓴다.
 */
export function useFocusWhileBusy(
  busy: boolean,
  titleRef: RefObject<HTMLHeadingElement | null>,
): void {
  // 확인 시트가 닫히며 여는 버튼으로 포커스를 돌려주는 정리 함수보다 이 이펙트가 나중에 돈다
  useEffect(() => {
    if (busy) titleRef.current?.focus();
  }, [busy, titleRef]);
}
