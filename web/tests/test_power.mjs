// Tests the power outlet codes in js/power-code.js. Run: npm test (from web/).

import assert from 'node:assert/strict';
import { powerParts, powerText, powerGroup, powerStyleSummary, nextGroup } from '../js/power-code.js';

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const BASE = {
  power_building: '', power_floor: '', power_room: '', power_central: 'A1A', power_group_kind: 'Gr.',
  power_group: '13', power_phase: '', power_voltage: '', power_row: 1, power_sep: ' ', power_digits: 0,
  power_lines: 1, power_extra: 'after',
};
const code = (change) => powerText({ ...BASE, ...change });

test('Gr., the usual', () => assert.equal(code({}), 'A1A Gr. 13'));
test('group called F', () => assert.equal(code({ power_group_kind: 'F' }), 'A1A F13'));
test('group with no name and : between', () => assert.equal(code({ power_group_kind: '', power_sep: ':' }), 'A1A:13'));
test('- and . between', () => {
  assert.equal(code({ power_sep: '-', power_group_kind: 'F' }), 'A1A-F13');
  assert.equal(code({ power_sep: '.', power_group_kind: '' }), 'A1A.13');
});
test('phase after the group', () => assert.equal(code({ power_phase: 'L2' }), 'A1A Gr. 13 L2'));
test('phase and voltage after the group get spaces whatever is between', () => {
  assert.equal(code({ power_sep: ':', power_group_kind: '', power_phase: 'L1-L3', power_voltage: '400 V' }), 'A1A:13 L1-L3 400 V');
});
test('phase and voltage on a small line', () => {
  assert.equal(code({ power_group: '21', power_phase: 'L1-L3', power_voltage: '400 V', power_extra: 'below' }), 'A1A Gr. 21\n-# L1-L3 · 400 V');
});
test('the place in the code', () => {
  assert.equal(code({ power_building: 'B1', power_floor: 'F2', power_room: 'R204', power_sep: '-' }), 'B1-F2-R204-A1A-Gr. 13');
});
test('two lines puts the place small on top', () => {
  assert.equal(code({ power_building: 'B1', power_floor: 'F2', power_room: 'R204', power_lines: 2 }), '-# B1 · F2 · R204\nA1A Gr. 13');
});
test('two lines with nothing for the top stays one line', () => assert.equal(code({ power_lines: 2 }), 'A1A Gr. 13'));
test('three lines: place on top, phase and voltage under', () => {
  assert.equal(code({ power_room: 'R204', power_lines: 2, power_voltage: '230 V', power_extra: 'below' }), '-# R204\nA1A Gr. 13\n-# 230 V');
});
test('padded numbers', () => {
  assert.equal(powerGroup({ ...BASE, power_group: '3', power_digits: 2 }), 'Gr. 03');
  assert.equal(powerGroup({ ...BASE, power_group: '3', power_digits: 3, power_group_kind: 'F' }), 'F003');
  assert.equal(powerGroup({ ...BASE, power_group: '3b', power_digits: 2 }), 'Gr. 3b');
});
test('empty parts are left out', () => {
  assert.equal(code({ power_central: '' }), 'Gr. 13');
  assert.equal(code({ power_group: '' }), 'A1A');
  assert.equal(code({ power_central: '', power_group: '' }), '');
  assert.equal(code({ power_central: '', power_group: '', power_voltage: '230 V' }), '230 V');
});
test('parts are trimmed', () => assert.equal(code({ power_central: ' A1A ', power_group: ' 13 ' }), 'A1A Gr. 13'));
test('where and extra parts', () => {
  assert.deepEqual(powerParts({ ...BASE, power_room: 'Kitchen', power_lines: 2, power_phase: 'L1', power_extra: 'below' }),
    { where: 'Kitchen', code: 'A1A Gr. 13', extra: 'L1' });
});
test('style summary', () => {
  assert.equal(powerStyleSummary(BASE), 'A1A Gr. 13, one line');
  assert.equal(powerStyleSummary({ ...BASE, power_group_kind: 'F', power_lines: 2 }), 'A1A F13, two lines');
});
test('next group keeps its zeros', () => {
  assert.equal(nextGroup({ power_group: '13' }), '14');
  assert.equal(nextGroup({ power_group: '09' }), '10');
  assert.equal(nextGroup({ power_group: 'X' }), 'X');
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log(`ok   ${name}`); } catch (err) { failed++; console.log(`FAIL ${name}\n${err.message}`); }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
if (failed) process.exit(1);
