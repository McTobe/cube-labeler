// Tests the tape counter's sums in js/tape.js. Run: npm test (from web/).

import assert from 'node:assert/strict';
import {
  tapeKey, newRoll, correctRoll, countPrint, mergeRolls, rollLeft, rollUsed, rollPrints, formatTape,
  partLength, planParts, partItems,
} from '../js/tape.js';

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('counts prints down from a full roll', () => {
  let roll = newRoll(8000);
  roll = countPrint(roll, 'pc', 60);
  roll = countPrint(roll, 'phone', 40);
  assert.equal(rollLeft(roll), 7900);
  assert.equal(rollUsed(roll), 100);
  assert.equal(rollPrints(roll), 2);
  assert.equal(rollLeft(countPrint(roll, 'pc', 9000)), 0);
});

test('a corrected count goes on from the new value and keeps the prints so far', () => {
  const roll = correctRoll(countPrint(newRoll(8000), 'pc', 500), 5000);
  assert.equal(rollLeft(roll), 5000);
  assert.equal(rollUsed(roll), 3000);
  assert.equal(rollPrints(roll), 1);
  assert.equal(rollLeft(countPrint(roll, 'pc', 100)), 4900);
});

test('two devices printing on the same roll both count once', () => {
  const start = newRoll(8000);
  const pc = countPrint(countPrint(start, 'pc', 100), 'pc', 100);
  const phone = countPrint(start, 'phone', 50);
  const merged = mergeRolls({ k: pc }, { k: phone }).k;
  assert.equal(rollLeft(merged), 7750);
  // Syncing the same counts again changes nothing
  assert.equal(rollLeft(mergeRolls({ k: merged }, { k: pc }).k), 7750);
  assert.equal(rollLeft(mergeRolls({ k: merged }, { k: merged }).k), 7750);
});

test('the newest roll wins over an older one, and counts per kind of tape stay apart', () => {
  const old = countPrint(newRoll(8000), 'pc', 7000);
  const fresh = { ...newRoll(4000), set_at: old.set_at + 1 };
  assert.equal(mergeRolls({ k: old }, { k: fresh }).k.id, fresh.id);
  assert.equal(mergeRolls({ k: fresh }, { k: old }).k.id, fresh.id);
  const both = mergeRolls({ a: old }, { b: fresh, broken: { id: 3 } });
  assert.deepEqual(Object.keys(both).sort(), ['a', 'b']);
});

test('tape kinds and amounts read well', () => {
  assert.equal(tapeKey({ tape_width_mm: 12, tape_color: 'White', text_color: 'Black' }), '12|White|Black');
  assert.equal(formatTape(5250), '5.2 m');
  assert.equal(formatTape(8000), '8 m');
  assert.equal(formatTape(284), '28 cm');
  assert.equal(formatTape(-5), '0 cm');
});

// Three queue items 50, 100 and 75 mm wide (1 dot = 0.05 mm here), the second printed twice
const lengths = { widths: [1000, 2000, 1500], singles: [1100, 2100, 1600], gap: 100, ends: 100, dot_mm: 0.05, lead_mm: 25, max_mm: 499 };
const owners = [0, 1, 1, 2];

test('part lengths add widths, gaps, ends and one lead', () => {
  assert.equal(partLength(lengths, owners, 0, 0), 80);
  assert.equal(partLength(lengths, owners, 0, 1), 185);
  assert.equal(partLength(lengths, owners, 1, 3), 25 + (100 + 200 + 2000 + 2000 + 1500) * 0.05);
});

test('a queue that fits the roll and the printer is one part', () => {
  assert.deepEqual(planParts(lengths, owners, null, null).map((p) => [p.from, p.to]), [[0, 3]]);
});

test('a short roll splits at a cut line and puts the rest on a new roll', () => {
  const parts = planParts(lengths, owners, 200, 8000);
  assert.deepEqual(parts.map((p) => [p.from, p.to, p.newRoll]), [[0, 1, false], [2, 3, true]]);
  assert.ok(parts[0].mm <= 200);
  // Not even the first label fits: everything goes on the new roll
  assert.deepEqual(planParts(lengths, owners, 50, 8000).map((p) => [p.from, p.to, p.newRoll]), [[0, 3, true]]);
});

test('a queue over the printer limit splits into parts that each fit', () => {
  const long = { ...lengths, widths: [2000, 2000, 2000], singles: [2100, 2100, 2100] };
  const parts = planParts(long, [0, 1, 2, 0, 1, 2], null, null);
  assert.ok(parts.length > 1);
  assert.ok(parts.every((p) => p.mm <= 499 && !p.newRoll));
  assert.equal(parts.at(-1).to, 5);
  // One label longer than the limit cannot be split
  assert.equal(planParts({ ...lengths, singles: [20000, 1, 1] }, [0], null, null), null);
});

test('a part keeps the queue items with the copies it prints', () => {
  const queue = [{ id: 'a', copies: 1 }, { id: 'b', copies: 2 }, { id: 'c', copies: 1 }];
  assert.deepEqual(partItems(queue, owners, 0, 1), [{ id: 'a', copies: 1 }, { id: 'b', copies: 1 }]);
  assert.deepEqual(partItems(queue, owners, 2, 3), [{ id: 'b', copies: 1 }, { id: 'c', copies: 1 }]);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`FAIL ${name}\n${err.stack}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
