// 두 파일이 바이트 단위로 같은지 확인한다. 다르면 차이 나는 줄을 출력하고 비제로로 끝난다.
//   node scripts/compare-files.mjs <파일 A> <파일 B>
import { readFileSync } from "node:fs";
import process from "node:process";

const [left, right] = process.argv.slice(2);
if (left === undefined || right === undefined) {
  process.stderr.write("사용법: compare-files.mjs <파일 A> <파일 B>\n");
  process.exit(2);
}

const a = readFileSync(left);
const b = readFileSync(right);
if (a.equals(b)) {
  process.stdout.write(`같다: ${left} = ${right}\n`);
} else {
  const aLines = new Set(a.toString("utf8").split("\n"));
  const bLines = new Set(b.toString("utf8").split("\n"));
  for (const line of aLines) if (!bLines.has(line)) process.stderr.write(`- ${line}\n`);
  for (const line of bLines) if (!aLines.has(line)) process.stderr.write(`+ ${line}\n`);
  process.stderr.write(`다르다: ${left} ≠ ${right}\n`);
  process.exitCode = 1;
}
