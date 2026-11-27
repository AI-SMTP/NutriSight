/**
 * "사진 없이 기록"(전량 거부·전량 미섭취) 영역의 자리(계획 구현 전제 "화면 ② 작업 분담").
 * Story 17이 버튼·확인 시트·`recordStaffZero` 요청을 여기에 붙인다. 화면 상태 전체를 받으므로
 * 고른 발주(`selectedOrder`), 기록 가능 여부(`recordable`), 요청 진행(`busy`·`submission`), 시연일 상태
 * (`demo`), 재조회·잠금(`query`)을 그대로 쓸 수 있다. 지금은 아무것도 그리지 않는다.
 */
import type { ReactNode } from "react";

import type { PostMealScreen } from "./usePostMealScreen";

export interface StaffZeroSlotProps {
  screen: PostMealScreen;
}

// 자리만 두므로 아직 props를 읽지 않는다. 타입으로 Story 17이 받을 값을 고정해 둔다
export const StaffZeroSlot: (props: StaffZeroSlotProps) => ReactNode = () => null;
