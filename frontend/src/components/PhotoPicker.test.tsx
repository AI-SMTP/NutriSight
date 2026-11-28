import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode, useState } from "react";

import { makePhoto, stubObjectUrl } from "../test/objectUrl";
import { PhotoPicker } from "./PhotoPicker";

let urls: ReturnType<typeof stubObjectUrl>;

beforeEach(() => {
  urls = stubObjectUrl();
});

afterEach(() => {
  urls.restore();
});

// 부모가 고른 사진을 들고 있는 실제 사용 형태
function Harness({ disabled, onSelect }: { disabled?: boolean; onSelect?: (f: File) => void }) {
  const [file, setFile] = useState<File | null>(null);
  return (
    <PhotoPicker
      value={file}
      disabled={disabled}
      onSelect={(next) => {
        onSelect?.(next);
        setFile(next);
      }}
    />
  );
}

describe("PhotoPicker", () => {
  it("촬영 입력에는 capture=environment가 있고 앨범 입력에는 없다", () => {
    render(<Harness />);

    const camera = screen.getByLabelText("촬영하기");
    const album = screen.getByLabelText("앨범에서 선택");
    for (const input of [camera, album]) {
      expect(input).toHaveAttribute("type", "file");
      expect(input).toHaveAttribute("accept", "image/*");
    }
    expect(camera).toHaveAttribute("capture", "environment");
    expect(album).not.toHaveAttribute("capture");
  });

  it("사진을 고르면 onSelect를 부르고 원본 object URL로 미리보기를 그린다", async () => {
    const onSelect = vi.fn();
    const photo = makePhoto();
    render(<Harness onSelect={onSelect} />);

    await userEvent.upload(screen.getByLabelText("앨범에서 선택"), photo);

    expect(onSelect).toHaveBeenCalledWith(photo);
    expect(urls.createObjectURL).toHaveBeenCalledWith(photo);
    expect(screen.getByRole("img", { name: "선택한 사진 미리보기" })).toHaveAttribute(
      "src",
      "blob:test/1",
    );
  });

  it("고른 사진이 없으면 미리보기가 없다", () => {
    render(<Harness />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(urls.createObjectURL).not.toHaveBeenCalled();
  });

  it("파일 선택을 취소하면(빈 목록) onSelect를 부르지 않는다", () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);

    fireEvent.change(screen.getByLabelText("촬영하기"), { target: { files: [] } });

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("두 번째 사진을 고르면 첫 URL을 해제하고, 언마운트하면 두 번째 URL을 해제한다", async () => {
    const { unmount } = render(<Harness />);

    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto("a.jpg"));
    expect(urls.revokeObjectURL).not.toHaveBeenCalled();

    await userEvent.upload(screen.getByLabelText("앨범에서 선택"), makePhoto("b.jpg"));
    expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:test/1");
    expect(urls.revokeObjectURL).not.toHaveBeenCalledWith("blob:test/2");
    expect(screen.getByRole("img", { name: "선택한 사진 미리보기" })).toHaveAttribute(
      "src",
      "blob:test/2",
    );

    unmount();
    expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:test/2");
  });

  it("부모가 사진을 지우면 미리보기를 없애고 URL을 해제한다", () => {
    const photo = makePhoto();
    const { rerender } = render(<PhotoPicker value={photo} onSelect={vi.fn()} />);
    expect(screen.getByRole("img")).toHaveAttribute("src", "blob:test/1");

    rerender(<PhotoPicker value={null} onSelect={vi.fn()} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(urls.revokeObjectURL).toHaveBeenCalledWith("blob:test/1");
  });

  it("브라우저가 미리보기를 그리지 못하면 안내 문구를 보이고, 새 사진을 고르면 다시 그린다", async () => {
    render(<Harness />);
    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto("a.heic", "image/heic"));

    fireEvent.error(screen.getByRole("img", { name: "선택한 사진 미리보기" }));

    expect(screen.getByText("미리보기를 표시할 수 없습니다")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();

    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto("b.jpg"));

    expect(screen.queryByText("미리보기를 표시할 수 없습니다")).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "선택한 사진 미리보기" })).toBeInTheDocument();
  });

  it("비활성이면 두 입력이 모두 막힌다", () => {
    render(<Harness disabled />);

    expect(screen.getByLabelText("촬영하기")).toBeDisabled();
    expect(screen.getByLabelText("앨범에서 선택")).toBeDisabled();
  });

  describe("StrictMode(effect 두 번 실행)", () => {
    function lastCreatedUrl(): string {
      const url = urls.createObjectURL.mock.results.at(-1)?.value as string | undefined;
      if (url === undefined) throw new Error("object URL을 만들지 않았습니다");
      return url;
    }

    it("사진을 가진 채 마운트해도 img src는 마지막으로 만든 URL이고 해제되지 않았다", () => {
      render(
        <StrictMode>
          <PhotoPicker value={makePhoto()} onSelect={vi.fn()} />
        </StrictMode>,
      );

      const url = lastCreatedUrl();
      expect(screen.getByRole("img")).toHaveAttribute("src", url);
      expect(urls.revokeObjectURL).not.toHaveBeenCalledWith(url);
    });

    it("사진을 고른 뒤에도 img src는 마지막으로 만든 URL이고 해제되지 않았다", async () => {
      render(
        <StrictMode>
          <Harness />
        </StrictMode>,
      );

      await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto());

      const url = lastCreatedUrl();
      expect(screen.getByRole("img")).toHaveAttribute("src", url);
      expect(urls.revokeObjectURL).not.toHaveBeenCalledWith(url);
    });
  });
});
