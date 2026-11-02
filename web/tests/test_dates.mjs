// Tests the date label's sums and text in js/dates.js. Run: npm test (from web/).

import assert from 'node:assert/strict';
import { madeDay, useByDay, formatDay, dateText, parseDay, isoDay } from '../js/dates.js';

const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const day = (y, m, d) => new Date(y, m - 1, d);
const NOV_2 = day(2026, 11, 2);

test('today and yesterday follow the calendar, a picked day stays', () => {
  assert.equal(isoDay(madeDay('today', NOV_2)), '2026-11-02');
  assert.equal(isoDay(madeDay('yesterday', NOV_2)), '2026-11-01');
  assert.equal(isoDay(madeDay('yesterday', day(2026, 1, 1))), '2025-12-31');
  assert.equal(isoDay(madeDay('2026-10-28', NOV_2)), '2026-10-28');
  // Something that is not a day counts as today
  assert.equal(isoDay(madeDay('2026-02-31', NOV_2)), '2026-11-02');
  assert.equal(parseDay('nonsense'), null);
});

test('use-by adds days, weeks and months', () => {
  assert.equal(isoDay(useByDay(NOV_2, '3d')), '2026-11-05');
  assert.equal(isoDay(useByDay(NOV_2, '1w')), '2026-11-09');
  assert.equal(isoDay(useByDay(day(2026, 12, 25), '2w')), '2027-01-08');
  assert.equal(isoDay(useByDay(NOV_2, '3m')), '2027-02-02');
  assert.equal(isoDay(useByDay(NOV_2, '6m')), '2027-05-02');
});

test('a month on from the 31st is the last day of a shorter month', () => {
  assert.equal(isoDay(useByDay(day(2027, 1, 31), '1m')), '2027-02-28');
  assert.equal(isoDay(useByDay(day(2028, 1, 31), '1m')), '2028-02-29');
  assert.equal(isoDay(useByDay(day(2026, 8, 31), '3m')), '2026-11-30');
});

test('dates in three styles', () => {
  assert.equal(formatDay(NOV_2, 'words'), '2 Nov 2026');
  assert.equal(formatDay(NOV_2, 'dots'), '02.11.26');
  assert.equal(formatDay(NOV_2, 'iso'), '2026-11-02');
});

test('the label text: name and portions, then the dates', () => {
  const label = { date_name: 'Chili con carne', date_portions: '2', date_made: 'today', date_keeps: '3m', date_show: 'both', date_style: 'words' };
  assert.equal(dateText(label, NOV_2), '## **Chili con carne** · 2\nMade 2 Nov 2026 · Use by 2 Feb 2027');
  assert.equal(dateText({ ...label, date_show: 'use' }, NOV_2), '## **Chili con carne** · 2\nUse by 2 Feb 2027');
  assert.equal(dateText({ ...label, date_show: 'made', date_style: 'dots' }, NOV_2), '## **Chili con carne** · 2\nMade 02.11.26');
  assert.equal(dateText({ ...label, date_portions: '' }, NOV_2), '## **Chili con carne**\nMade 2 Nov 2026 · Use by 2 Feb 2027');
  assert.equal(dateText({ ...label, date_name: ' ', date_portions: '' }, NOV_2), 'Made 2 Nov 2026 · Use by 2 Feb 2027');
});

test('typed markers print as typed', () => {
  const label = { date_name: '**Soup** #1', date_portions: '', date_made: 'today', date_keeps: '3d', date_show: 'made' };
  assert.equal(dateText(label, NOV_2), '## **\\*\\*Soup\\*\\* \\#1**\nMade 2 Nov 2026');
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`FAIL ${name}\n${err.stack}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
