// Tests how Google Drive sync merges two devices, in js/syncplan.js. Run: npm test (from web/).

import assert from 'node:assert/strict';
import { planItems, planSettings, baseFor, pruneBackups } from '../js/syncplan.js';

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const same = (side) => ({ l: side, r: side });

test('a change on one side moves to the other', () => {
  const base = same({ shelf: 'a', bin: 'b' });
  assert.deepEqual(planItems({ shelf: 'a', bin: 'b' }, { shelf: 'a2', bin: 'b' }, base), { take: ['shelf'], conflict: [], drop: [] });
  // Changed here only: nothing comes from Drive, the upload takes it there
  assert.deepEqual(planItems({ shelf: 'a2', bin: 'b' }, { shelf: 'a', bin: 'b' }, base), { take: [], conflict: [], drop: [] });
});

test('an edit made while offline is not undone by an older copy in Drive', () => {
  // The phone added an icon meanwhile, so Drive is newer, but it still has the old shelf
  const base = same({ shelf: 'a' });
  const plan = planItems({ shelf: 'a-edited' }, { shelf: 'a', nails: 'n' }, base);
  assert.deepEqual(plan, { take: ['nails'], conflict: [], drop: [] });
});

test('both sides changed the same thing: Drive\'s is kept as a copy', () => {
  const plan = planItems({ shelf: 'mine' }, { shelf: 'theirs' }, same({ shelf: 'a' }));
  assert.deepEqual(plan, { take: [], conflict: ['shelf'], drop: [] });
});

test('deleted on the other device goes here too, unless edited here since', () => {
  const base = same({ screws: 's', nuts: 'n' });
  assert.deepEqual(planItems({ screws: 's', nuts: 'n2' }, {}, base), { take: [], conflict: [], drop: ['screws'] });
});

test('deleted here is not brought back, unless edited there since', () => {
  const base = same({ screws: 's', nuts: 'n' });
  assert.deepEqual(planItems({}, { screws: 's', nuts: 'n2' }, base), { take: ['nuts'], conflict: [], drop: [] });
});

test('new on either side is kept', () => {
  const base = same({});
  assert.deepEqual(planItems({ mine: '1' }, { theirs: '2' }, base), { take: ['theirs'], conflict: [], drop: [] });
});

test('without a last sync nothing is deleted and differences are kept twice', () => {
  const plan = planItems({ screws: 's', shelf: 'a' }, { nails: 'n', shelf: 'b' }, null);
  assert.deepEqual(plan, { take: ['nails'], conflict: ['shelf'], drop: [] });
  assert.deepEqual(planItems({ shelf: 'a' }, { shelf: 'a' }, null), { take: [], conflict: [], drop: [] });
});

test('a fingerprint in another form on the other side is not taken for a change here', () => {
  // r is what Drive held at the last sync, which may be written differently from l
  const base = { l: { shelf: 'local-form' }, r: { shelf: 'drive-form' } };
  assert.deepEqual(planItems({ shelf: 'local-form' }, { shelf: 'drive-form' }, base), { take: [], conflict: [], drop: [] });
  assert.deepEqual(planItems({ shelf: 'local-form' }, { shelf: 'new' }, base), { take: ['shelf'], conflict: [], drop: [] });
});

test('settings merge one by one, and a device joining takes Drive\'s', () => {
  const base = same({ theme: '"dark"', tape: '12' });
  assert.deepEqual(planSettings({ theme: '"light"', tape: '12' }, { theme: '"dark"', tape: '9' }, base), ['tape']);
  assert.deepEqual(planSettings({ theme: '"light"' }, { theme: '"system"' }, base), []);
  assert.deepEqual(planSettings({ theme: '"system"', tape: 'null' }, { theme: '"dark"', tape: '12' }, null), ['theme', 'tape']);
});

const file = (id, parent) => ({ id, createdTime: '2026-10-28T10:00:00Z', appProperties: parent ? { parent } : {} });

test('the base holds when the newest backup was made on top of the last sync, also several uploads later', () => {
  const base = { account: 'a@x' };
  const files = [file('n', 'p'), file('p', 's'), file('s', 'r')];
  assert.deepEqual(baseFor(base, 's', files[0], 'a@x', files), { how: 'kept' });
  assert.deepEqual(baseFor(base, 's', files[1], 'a@x', files), { how: 'kept' });
});

test('two devices that synced at once merge from the backup both started from', () => {
  // This device uploaded a1 on top of a0 while the other uploaded b1 on top of a0
  const files = [file('b1', 'a0'), file('a1', 'a0'), file('a0', 'z')];
  assert.deepEqual(baseFor({ account: 'a@x' }, 'a1', files[0], 'a@x', files), { how: 'parent', id: 'a0' });
  // When that backup is gone, the merge only adds
  assert.deepEqual(baseFor({ account: 'a@x' }, 'a1', files[0], 'a@x', files.slice(0, 2)), { how: 'none' });
});

test('another account or no last sync gives no base', () => {
  const files = [file('n', 's')];
  assert.deepEqual(baseFor({ account: 'a@x' }, 's', files[0], 'b@x', files), { how: 'none' });
  assert.deepEqual(baseFor(null, 's', files[0], 'a@x', files), { how: 'none' });
  assert.deepEqual(baseFor({ account: 'a@x' }, null, files[0], 'a@x', files), { how: 'none' });
  // Backups from older versions say nothing about what they were made on; the base holds as before
  assert.deepEqual(baseFor({ account: 'a@x' }, 's', file('old'), 'a@x', [file('old')]), { how: 'kept' });
});

test('Drive keeps the newest 10 and one a day for two weeks', () => {
  const now = Date.parse('2026-10-28T12:00:00');
  const at = (hoursAgo) => new Date(now - hoursAgo * 3600 * 1000).toISOString();
  // 15 today (newest first), then one every 12 hours for 20 days
  const files = [];
  for (let i = 0; i < 15; i++) files.push({ id: `t${i}`, createdTime: at(i * 0.1) });
  for (let i = 1; i <= 40; i++) files.push({ id: `d${i}`, createdTime: at(12 + i * 12) });
  const gone = new Set(pruneBackups(files, { now }));
  const kept = files.filter((f) => !gone.has(f.id));
  assert.equal(kept.filter((f) => f.id.startsWith('t')).length, 10);
  // One per day for the 13 earlier days within two weeks, nothing older
  const days = new Set(kept.filter((f) => f.id.startsWith('d')).map((f) => new Date(f.createdTime).toDateString()));
  assert.equal(kept.filter((f) => f.id.startsWith('d')).length, days.size);
  assert.ok(days.size >= 13 && days.size <= 14, `${days.size} days kept`);
  assert.ok(kept.every((f) => now - Date.parse(f.createdTime) < 14 * 24 * 3600 * 1000 || files.indexOf(f) < 10));
  assert.deepEqual(pruneBackups(files.slice(0, 3), { now }), []);
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
