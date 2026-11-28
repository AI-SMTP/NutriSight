// jsdom에는 URL.createObjectURL·revokeObjectURL이 없으므로 테스트에서 대역을 붙인다.
// 만든 URL은 "blob:test/1", "blob:test/2" 순서로 돌려준다.

export function stubObjectUrl() {
  let count = 0;
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => {
    count += 1;
    return `blob:test/${count}`;
  });
  const revokeObjectURL = vi.fn<(url: string) => void>();
  const original = {
    create: Object.getOwnPropertyDescriptor(URL, "createObjectURL"),
    revoke: Object.getOwnPropertyDescriptor(URL, "revokeObjectURL"),
  };
  Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });

  // 원래 속성(없었으면 삭제)으로 되돌린다.
  const restore = () => {
    for (const [key, descriptor] of [
      ["createObjectURL", original.create],
      ["revokeObjectURL", original.revoke],
    ] as const) {
      if (descriptor) Object.defineProperty(URL, key, descriptor);
      else Reflect.deleteProperty(URL, key);
    }
  };
  return { createObjectURL, revokeObjectURL, restore };
}

export function makePhoto(name = "tray.jpg", type = "image/jpeg", bytes = 2048): File {
  return new File([new Uint8Array(bytes)], name, { type });
}
