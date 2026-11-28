import styles from "./SegmentedControl.module.css";

export type SegmentOption<T extends string> = {
  value: T;
  label: string;
};

export type SegmentedControlProps<T extends string> = {
  /** 묶음 이름(화면에는 시각적으로 숨김). 예: "끼니" */
  legend: string;
  /** 라디오 묶음 name */
  name: string;
  options: readonly SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
};

/** 분할 버튼. 라디오 입력과 label로 만들어 모든 선택지를 라벨로 찾을 수 있다. */
export function SegmentedControl<T extends string>({
  legend,
  name,
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedControlProps<T>) {
  return (
    <fieldset className={styles.group} disabled={disabled}>
      <legend className={styles.legend}>{legend}</legend>
      <div className={styles.options}>
        {options.map((option) => (
          <label key={option.value} className={styles.option}>
            <input
              className={styles.input}
              type="radio"
              name={name}
              value={option.value}
              checked={option.value === value}
              onChange={() => onChange(option.value)}
            />
            <span className={styles.text}>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
