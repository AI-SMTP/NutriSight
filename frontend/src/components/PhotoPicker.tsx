import { useEffect, useRef, useState, type ChangeEvent } from "react";

import styles from "./PhotoPicker.module.css";

export type PhotoPickerProps = {
  /** 고른 사진. 부모가 들고 있고 null이면 미리보기를 지운다 */
  value: File | null;
  onSelect: (file: File) => void;
  disabled?: boolean;
};

const PREVIEW_FAILED = "미리보기를 표시할 수 없습니다";

// 촬영 입력만 후면 카메라 힌트(capture)를 준다.
const SOURCES = [
  { label: "촬영하기", capture: "environment" },
  { label: "앨범에서 선택", capture: undefined },
] as const;

// 고른 사진의 object URL을 img에 직접 붙인다. 사진이 바뀌거나 언마운트되면 이전 URL을 해제한다.
// URL을 state에 두지 않아 StrictMode의 effect 재실행에서도 해제된 URL을 쓰지 않는다.
function usePreviewSource(file: File | null) {
  const imageRef = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const image = imageRef.current;
    if (!file || !image) return;
    const url = URL.createObjectURL(file);
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return imageRef;
}

/** 촬영(후면 카메라 힌트)과 앨범 선택 두 입력, 원본 미리보기를 둔 사진 입력. */
export function PhotoPicker({ value, onSelect, disabled = false }: PhotoPickerProps) {
  const imageRef = usePreviewSource(value);
  const [failedFile, setFailedFile] = useState<File | null>(null);
  const previewFailed = value !== null && failedFile === value;

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // 같은 사진을 다시 골라도 change가 오도록 입력을 비운다.
    event.target.value = "";
    if (file) onSelect(file);
  };

  return (
    <div className={styles.picker}>
      <div className={styles.inputs}>
        {SOURCES.map(({ label, capture }) => (
          <label key={label} className={styles.pickerLabel} data-disabled={disabled || undefined}>
            {label}
            <input
              className={styles.fileInput}
              type="file"
              accept="image/*"
              capture={capture}
              disabled={disabled}
              onChange={handleChange}
            />
          </label>
        ))}
      </div>
      {value !== null && (
        <div className={styles.preview}>
          <img
            ref={imageRef}
            className={styles.image}
            alt="선택한 사진 미리보기"
            hidden={previewFailed}
            onError={() => setFailedFile(value)}
          />
          {previewFailed && <p className={styles.previewFailed}>{PREVIEW_FAILED}</p>}
        </div>
      )}
    </div>
  );
}
