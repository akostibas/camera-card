// Prints a tester's brief (or the answer key) for one prototype run.
// node bin/tester-brief.mjs <variant: alpha|bravo|charlie> <seed 1-3> <run-id> [--key]
import fs from 'fs';
const [variant, seed, run, keyFlag] = process.argv.slice(2);
if (!variant || !seed || !run) { console.error('usage: tester-brief.mjs <variant> <seed> <run-id> [--key]'); process.exit(1); }
globalThis.window = globalThis;
globalThis.location = { search: '?seed=' + seed, pathname: '/x' };
eval(fs.readFileSync(new URL('../proto/harness.js', import.meta.url), 'utf8'));
const { tasks } = PROTO.answerKey;
const order = [1, 4, 3, 'keep', 2, 6, 5];
const list = order.map((uc) => tasks.find((t) => t.uc === uc));
if (keyFlag) { for (const t of list) console.log(`UC${t.uc}: ${t.answer}`); process.exit(0); }
const url = (n) => `http://127.0.0.1:8777/${variant}.html?run=${run}&seed=${seed}&task=${n}`;
// "keep" continues task 3 in the same page, so it has no URL of its own.
let n = 0, out = [];
for (const t of list) {
  if (t.uc === 'keep') { out.push(`   Then, without reopening: ${t.task}`); continue; }
  n++; out.push(`${n}. Open ${url(n)}\n   "${t.task}"`);
}
console.log(out.join('\n'));
