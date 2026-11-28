// 디렉토리 안 모든 파일의 상대 경로와 SHA-256을 경로순으로 출력한다(빌드 산출물 보존 확인용).
//   node scripts/hash-dir.mjs <디렉토리>
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const root = process.argv[2];
if (root === undefined) {
  process.stderr.write("사용법: hash-dir.mjs <디렉토리>\n");
  process.exit(2);
}

const files = readdirSync(root, { recursive: true, withFileTypes: true })
  .filter((entry) => entry.isFile())
  .map((entry) =>
    path.relative(root, path.join(entry.parentPath, entry.name)).replaceAll("\\", "/"),
  )
  .sort();

for (const file of files) {
  const digest = createHash("sha256")
    .update(readFileSync(path.join(root, file)))
    .digest("hex");
  process.stdout.write(`${digest}  ${file}\n`);
}
