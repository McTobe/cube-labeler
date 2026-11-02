// Tests the network outlet codes in js/outlet-code.js. Run: npm test (from web/).

import assert from 'node:assert/strict';
import { outletParts, outletText, outletPorts, outletStyleSummary, nextFirst, padNumber } from '../js/outlet-code.js';

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const BASE = {
  outlet_building: '', outlet_floor: '', outlet_room: '', outlet_rack: 'DA01', outlet_panel_kind: 'P',
  outlet_panel: '02', outlet_ports: 2, outlet_first: 3, outlet_row: 1, outlet_sep: '', outlet_pair: '/',
  outlet_digits: 0, outlet_lines: 1,
};
const code = (change) => outletText({ ...BASE, ...change });

test('two ports, the usual', () => assert.equal(code({}), 'DA01P02 3/4'));
test('one port', () => assert.equal(code({ outlet_ports: 1 }), 'DA01P02 3'));
test('four ports as a range', () => assert.equal(code({ outlet_ports: 4, outlet_first: 1 }), 'DA01P02 1-4'));
test('panel called M or U', () => {
  assert.equal(code({ outlet_panel_kind: 'M', outlet_first: 7 }), 'DA01M02 7/8');
  assert.equal(code({ outlet_panel_kind: 'U', outlet_panel: '22', outlet_ports: 1, outlet_first: 5 }), 'DA01U22 5');
});
test('pair styles', () => {
  assert.equal(code({ outlet_pair: '-' }), 'DA01P02 3-4');
  assert.equal(code({ outlet_pair: '+' }), 'DA01P02 3+4');
});
test('everything filled in with - between', () => {
  assert.equal(code({ outlet_building: 'B1', outlet_floor: 'F2', outlet_room: 'R204', outlet_sep: '-' }), 'B1-F2-R204-DA01-P02-3/4');
});
test('space and dot between', () => {
  assert.equal(code({ outlet_sep: ' ' }), 'DA01 P02 3/4');
  assert.equal(code({ outlet_sep: '.' }), 'DA01.P02.3/4');
});
test('two lines: where small on top', () => {
  assert.equal(code({ outlet_building: 'B1', outlet_floor: 'F2', outlet_room: 'R204', outlet_lines: 2 }), '-# B1 · F2 · R204\nDA01P02 3/4');
  // Nothing to put on top keeps one line
  assert.equal(code({ outlet_lines: 2 }), 'DA01P02 3/4');
});
test('empty parts are left out', () => {
  assert.equal(code({ outlet_rack: '' }), 'P02 3/4');
  assert.equal(code({ outlet_panel: '' }), 'DA01 3/4');
  assert.equal(code({ outlet_first: '' }), 'DA01P02');
  assert.equal(code({ outlet_rack: '', outlet_panel: '' }), '3/4');
  assert.equal(code({ outlet_rack: '', outlet_panel: '', outlet_first: '' }), '');
});
test('numbers padded', () => {
  assert.equal(code({ outlet_panel: '2', outlet_digits: 2 }), 'DA01P02 03/04');
  assert.equal(code({ outlet_panel: '2', outlet_digits: 3, outlet_ports: 1 }), 'DA01P002 003');
  assert.equal(padNumber('A2', 3), 'A2');
});
test('counts on to the next outlet', () => {
  assert.equal(nextFirst(BASE), 5);
  assert.equal(nextFirst({ ...BASE, outlet_ports: 4 }, 3), 15);
  assert.equal(outletPorts(BASE, nextFirst(BASE, 2)), '7/8');
  assert.equal(nextFirst({ ...BASE, outlet_first: '' }), '');
});
test('style summary', () => {
  assert.equal(outletStyleSummary(BASE), 'DA01P02 3/4, one line');
  assert.equal(outletStyleSummary({ ...BASE, outlet_sep: '-', outlet_lines: 2 }), 'DA01-P02-3/4, two lines');
  assert.equal(outletParts({ ...BASE, outlet_room: 'R1', outlet_lines: 2 }).where, 'R1');
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log(`ok   ${name}`); } catch (err) { failed++; console.log(`FAIL ${name}\n${err.message}`); }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
if (failed) process.exit(1);
