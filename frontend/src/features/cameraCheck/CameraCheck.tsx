import { useRef, useState } from "react";

import { PhotoPicker } from "../../components/PhotoPicker";
import { prepareUpload, type PreparedUpload } from "../../lib/image";
import styles from "./CameraCheck.module.css";
import { describeUpload } from "./describeUpload";

type Prepare = (file: File) => Promise<PreparedUpload>;

export type CameraCheckProps = {
  /** 변환 함수. 테스트에서 결과를 주입할 때만 바꾼다 */
  prepare?: Prepare;
};

// 변환 함수가 예외를 던져도(주입한 함수 등) 원본을 보내는 것으로 보고 실패 문구를 보인다.
async function prepareOrOriginal(prepare: Prepare, file: File): Promise<PreparedUpload> {
  try {
    return await prepare(file);
  } catch {
    return { blob: file, converted: false, source: { type: file.type, bytes: file.size } };
  }
}

type Result = { status: "idle" } | { status: "converting" } | { status: "done"; text: string };

/**
 * 촬영 확인(/camera-check). API 없이 사진 입력·미리보기·업로드 전 변환 결과만 보여 준다.
 * 업로드·조회 요청과 SSE 구독을 하지 않는다(`docs/specs/frontend-shell-upload.md` '이미지 변환').
 */
export function CameraCheck({ prepare = prepareUpload }: CameraCheckProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<Result>({ status: "idle" });
  // 마지막으로 고른 사진. 앞서 고른 사진의 변환이 늦게 끝나면 그 결과는 버린다.
  const latestFile = useRef<File | null>(null);

  const handleSelect = async (selected: File) => {
    latestFile.current = selected;
    setFile(selected);
    setResult({ status: "converting" });
    const prepared = await prepareOrOriginal(prepare, selected);
    if (latestFile.current !== selected) return;
    setResult({ status: "done", text: describeUpload(prepared) });
  };

  return (
    <section className={styles.screen}>
      <p className={styles.intro}>
        사진을 고르면 업로드 전에 변환한 결과를 보여 줍니다. 사진은 서버로 보내지 않습니다.
      </p>
      <PhotoPicker value={file} onSelect={(selected) => void handleSelect(selected)} />
      <p className={styles.result} role="status">
        {result.status === "converting" && "변환 중…"}
        {result.status === "done" && result.text}
      </p>
    </section>
  );
}
