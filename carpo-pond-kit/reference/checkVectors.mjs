// Прогон эталонного движка по тест-векторам:  node reference/checkVectors.mjs
import { readFileSync } from "node:fs";
import { computePond } from "./progressEngine.js";

const root = new URL("../", import.meta.url);
const config = JSON.parse(readFileSync(new URL("config/progression.json", root), "utf8"));
const vectors = JSON.parse(readFileSync(new URL("config/progress_test_vectors.json", root), "utf8"));

let failed = 0;
for (const c of vectors.cases) {
  const got = computePond(c.input, config, []);
  const exp = c.expected;
  const same =
    got.drops === exp.drops &&
    got.focusDays === exp.focusDays &&
    got.stage === exp.stage &&
    JSON.stringify(got.unlocked) === JSON.stringify(exp.unlocked) &&
    JSON.stringify(got.sessions) === JSON.stringify(exp.sessions);
  console.log(`${same ? "OK  " : "FAIL"} ${c.name}`);
  if (!same) {
    failed++;
    console.log("  expected:", JSON.stringify(exp));
    console.log("  got:     ", JSON.stringify(got));
  }
}
console.log(failed ? `\n${failed} FAILED` : `\nВсе ${vectors.cases.length} векторов пройдены`);
process.exit(failed ? 1 : 0);
