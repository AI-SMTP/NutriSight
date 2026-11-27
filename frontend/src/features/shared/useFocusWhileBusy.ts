import { useEffect, useRef } from "react";

/**
 * 요청이 시작되면 패널 제목으로 포커스를 옮긴다(버튼이 막히고 시트가 닫혀도 body로 빠지지 않게).
 * 돌려준 ref를 `tabIndex={-1}`인 제목에 붙인다.
 */
export function useFocusWhileBusy(busy: boolean) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  // 확인 시트가 닫히며 여는 버튼으로 포커스를 돌려주는 정리 함수보다 이 이펙트가 나중에 돈다
  useEffect(() => {
    if (busy) titleRef.current?.focus();
  }, [busy]);
  return titleRef;
}
