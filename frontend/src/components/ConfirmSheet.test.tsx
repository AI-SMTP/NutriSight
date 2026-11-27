import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { ConfirmSheet } from "./ConfirmSheet";

function renderSheet(props: { open?: boolean; busy?: boolean } = {}) {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmSheet
      open={props.open ?? true}
      title="전량 거부 기록"
      message="NS03 점심을 전량 거부로 기록합니다"
      confirmLabel="기록"
      onConfirm={onConfirm}
      onCancel={onCancel}
      busy={props.busy}
    />,
  );
  return { onConfirm, onCancel };
}

describe("ConfirmSheet", () => {
  it("열리면 제목으로 이름 붙은 dialog와 안내 문구를 보여 준다", () => {
    renderSheet();

    const dialog = screen.getByRole("dialog", { name: "전량 거부 기록" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("NS03 점심을 전량 거부로 기록합니다");
  });

  it("닫혀 있으면 아무것도 그리지 않는다", () => {
    renderSheet({ open: false });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("확인 버튼은 onConfirm, 취소 버튼은 onCancel을 부른다", async () => {
    const { onConfirm, onCancel } = renderSheet();

    await userEvent.click(screen.getByRole("button", { name: "기록" }));
    await userEvent.click(screen.getByRole("button", { name: "취소" }));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("Escape 키는 취소로 처리한다", async () => {
    const { onCancel } = renderSheet();

    await userEvent.keyboard("{Escape}");

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("처리 중이면 두 버튼이 모두 막히고 Escape도 무시한다", async () => {
    const { onConfirm, onCancel } = renderSheet({ busy: true });

    expect(screen.getByRole("button", { name: "기록" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    await userEvent.keyboard("{Escape}");

    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("안내 문구를 dialog 설명(aria-describedby)으로 연결한다", () => {
    renderSheet();

    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(
      "NS03 점심을 전량 거부로 기록합니다",
    );
  });
});

// 버튼으로 시트를 여닫는 실제 사용 형태
function SheetHarness({ busy = false }: { busy?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        전량 거부
      </button>
      <button type="button">시트 밖 버튼</button>
      <ConfirmSheet
        open={open}
        title="전량 거부 기록"
        message="NS03 점심을 전량 거부로 기록합니다"
        confirmLabel="기록"
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
        busy={busy}
      />
    </>
  );
}

describe("ConfirmSheet 포커스", () => {
  it("열리면 취소 버튼에 포커스가 간다", async () => {
    render(<SheetHarness />);

    await userEvent.click(screen.getByRole("button", { name: "전량 거부" }));

    expect(screen.getByRole("button", { name: "취소" })).toHaveFocus();
  });

  it("Tab·Shift+Tab이 시트 안의 버튼 사이에서만 돈다", async () => {
    render(<SheetHarness />);
    await userEvent.click(screen.getByRole("button", { name: "전량 거부" }));
    const cancel = screen.getByRole("button", { name: "취소" });
    const confirm = screen.getByRole("button", { name: "기록" });

    await userEvent.tab();
    expect(confirm).toHaveFocus();
    await userEvent.tab();
    expect(cancel).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(confirm).toHaveFocus();
  });

  it("포커스가 시트 밖으로 나가 있어도 Tab을 누르면 시트 안으로 돌아온다", async () => {
    render(<SheetHarness />);
    await userEvent.click(screen.getByRole("button", { name: "전량 거부" }));
    // 문서 순서상 다음 요소가 시트 밖 버튼인 위치로 포커스를 옮겨 둔다.
    screen.getByRole("button", { name: "전량 거부" }).focus();

    await userEvent.tab();

    expect(screen.getByRole("button", { name: "취소" })).toHaveFocus();
  });

  it.each([
    ["취소", "취소"],
    ["확인", "기록"],
  ])("%s로 닫히면 시트를 연 버튼으로 포커스를 돌려준다", async (_case, label) => {
    render(<SheetHarness />);
    const opener = screen.getByRole("button", { name: "전량 거부" });
    await userEvent.click(opener);

    await userEvent.click(screen.getByRole("button", { name: label }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("Escape로 닫혀도 시트를 연 버튼으로 포커스를 돌려준다", async () => {
    render(<SheetHarness />);
    const opener = screen.getByRole("button", { name: "전량 거부" });
    await userEvent.click(opener);

    await userEvent.keyboard("{Escape}");

    expect(opener).toHaveFocus();
  });

  it("처리 중이면 포커스가 body로 빠지지 않고 시트에 머문다", async () => {
    const { rerender } = render(<SheetHarness />);
    await userEvent.click(screen.getByRole("button", { name: "전량 거부" }));

    rerender(<SheetHarness busy />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveFocus();
    await userEvent.tab();
    expect(dialog).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(dialog).toHaveFocus();
  });
});
