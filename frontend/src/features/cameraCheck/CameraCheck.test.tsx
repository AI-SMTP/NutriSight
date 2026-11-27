import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { PreparedUpload } from "../../lib/image";
import { makePhoto, stubObjectUrl } from "../../test/objectUrl";
import { renderRoute } from "../../test/renderRoute";
import { CameraCheck } from "./CameraCheck";

let urls: ReturnType<typeof stubObjectUrl>;

beforeEach(() => {
  urls = stubObjectUrl();
});

afterEach(() => {
  urls.restore();
  vi.unstubAllGlobals();
});

const CONVERTED: PreparedUpload = {
  blob: new Blob([], { type: "image/jpeg" }),
  converted: true,
  source: { type: "image/jpeg", bytes: 4_194_304, width: 4032, height: 3024 },
  output: { type: "image/jpeg", bytes: 524_288, width: 2048, height: 1536 },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("CameraCheck", () => {
  it("변환에 성공하면 원본·변환 크기와 용량을 보여 준다", async () => {
    const prepare = vi.fn(() => Promise.resolve(CONVERTED));
    const photo = makePhoto();
    render(<CameraCheck prepare={prepare} />);

    await userEvent.upload(screen.getByLabelText("촬영하기"), photo);

    expect(prepare).toHaveBeenCalledWith(photo);
    expect(
      await screen.findByText("변환됨 · JPEG · 원본 4032×3024, 4.0 MB → 변환 2048×1536, 512.0 KB"),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "선택한 사진 미리보기" })).toBeInTheDocument();
  });

  it("실제 prepareUpload가 디코딩하지 못하면(jsdom) 원본을 보낸다는 문구를 보여 준다", async () => {
    render(<CameraCheck />);

    await userEvent.upload(
      screen.getByLabelText("앨범에서 선택"),
      makePhoto("a.heic", "image/heic", 3_145_728),
    );

    expect(
      await screen.findByText("이 사진은 변환하지 못해 원본 그대로 보냅니다 · image/heic, 3.0 MB"),
    ).toBeInTheDocument();
  });

  it("주입한 변환 함수가 reject하면 원본을 보낸다는 문구를 보여 준다", async () => {
    const prepare = vi.fn(() => Promise.reject(new Error("unexpected")));
    render(<CameraCheck prepare={prepare} />);

    await userEvent.upload(
      screen.getByLabelText("촬영하기"),
      makePhoto("a.png", "image/png", 2048),
    );

    expect(
      await screen.findByText("이 사진은 변환하지 못해 원본 그대로 보냅니다 · image/png, 2.0 KB"),
    ).toBeInTheDocument();
  });

  it("사진을 고르기 전에도 결과 영역(status)이 접근성 트리에 있다", () => {
    render(<CameraCheck />);

    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("변환하는 동안 '변환 중'을 보인다", async () => {
    const pending = deferred<PreparedUpload>();
    render(<CameraCheck prepare={() => pending.promise} />);

    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto());

    expect(screen.getByRole("status")).toHaveTextContent("변환 중");
    pending.resolve(CONVERTED);
    expect(await screen.findByText(/^변환됨/)).toBeInTheDocument();
  });

  it("앞서 고른 사진의 결과가 늦게 와도 마지막 사진의 결과만 보인다", async () => {
    const first = deferred<PreparedUpload>();
    const second = deferred<PreparedUpload>();
    const prepare = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    render(<CameraCheck prepare={prepare} />);

    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto("a.jpg"));
    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto("b.jpg"));
    second.resolve(CONVERTED);
    expect(await screen.findByText(/^변환됨/)).toBeInTheDocument();

    // 늦게 끝난 첫 변환의 상태 갱신까지 모두 반영시킨 뒤 확인한다.
    await act(async () => {
      first.resolve({
        blob: new Blob(),
        converted: false,
        source: { type: "image/png", bytes: 1 },
      });
      await first.promise;
    });

    expect(screen.queryByText(/변환하지 못해/)).not.toBeInTheDocument();
    expect(screen.getByText(/^변환됨/)).toBeInTheDocument();
  });

  it("/camera-check는 렌더와 사진 선택 동안 fetch·EventSource를 한 번도 부르지 않는다", async () => {
    const fetch = vi.fn();
    const EventSource = vi.fn();
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("EventSource", EventSource);
    renderRoute("/camera-check");

    await userEvent.upload(screen.getByLabelText("촬영하기"), makePhoto());
    expect(await screen.findByText(/변환하지 못해/)).toBeInTheDocument();

    expect(fetch).not.toHaveBeenCalled();
    expect(EventSource).not.toHaveBeenCalled();
  });
});
