// Date labels for the freezer, the fridge and opened jars: what is in it, the day it was made
// and the day to use it by. The label is ordinary label text, worked out here from the date
// fields, so the queue, templates and history treat it like any text label. No imports, so
// tests run it in Node.

// How long food keeps: [id, name, amount, unit]
export const KEEPS = [
  ['3d', '3 days', 3, 'day'], ['1w', '1 week', 7, 'day'], ['2w', '2 weeks', 14, 'day'],
  ['1m', '1 month', 1, 'month'], ['3m', '3 months', 3, 'month'], ['6m', '6 months', 6, 'month'],
];

// Names to tap, two rows of four
export const DATE_NAMES = ['Soup', 'Chili', 'Bread', 'Leftovers', 'Sauce', 'Stock', 'Berries', 'Meat'];

// Which dates go on the label
export const DATE_SHOWS = [['both', 'Both dates'], ['use', 'Use by'], ['made', 'Made']];

// How dates are written
export const DATE_STYLES = ['words', 'dots', 'iso'];

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const pad = (n) => String(n).padStart(2, '0');

// A day as YYYY-MM-DD, in local time (what a date field holds)
export const isoDay = (day) => `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;

export function parseDay(text) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text || '');
  if (!m) return null;
  const day = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return day.getMonth() === Number(m[2]) - 1 ? day : null;
}

const startOfDay = (day) => new Date(day.getFullYear(), day.getMonth(), day.getDate());

// The day it was made: "today" and "yesterday" follow the calendar, so a saved date label or
// template prints today's date when it is used again; a picked day stays as it is
export function madeDay(made, today = new Date()) {
  const base = startOfDay(today);
  if (made === 'yesterday') return new Date(base.getFullYear(), base.getMonth(), base.getDate() - 1);
  return parseDay(made) || base;
}

// The use-by day. A month on from 31 January is the last day of February.
export function useByDay(made, keeps) {
  const [, , amount, unit] = KEEPS.find(([id]) => id === keeps) || KEEPS[4];
  if (unit === 'day') return new Date(made.getFullYear(), made.getMonth(), made.getDate() + amount);
  const month = made.getMonth() + amount;
  const last = new Date(made.getFullYear(), month + 1, 0).getDate();
  return new Date(made.getFullYear(), month, Math.min(made.getDate(), last));
}

// 2 Nov 2026, 02.11.26 or 2026-11-02
export function formatDay(day, style = 'words') {
  if (style === 'dots') return `${pad(day.getDate())}.${pad(day.getMonth() + 1)}.${pad(day.getFullYear() % 100)}`;
  if (style === 'iso') return isoDay(day);
  return `${day.getDate()} ${MONTHS[day.getMonth()]} ${day.getFullYear()}`;
}

// Typed text prints as typed: a * or # in a name is not styling
const plain = (text) => text.replace(/[\\*_=#<>\-[]/g, (ch) => `\\${ch}`);

// The label text: the name in bold and a size larger, with the portions after it, and the
// dates on a line under it
export function dateText(label, today = new Date()) {
  const made = madeDay(label.date_made, today);
  const style = label.date_style;
  const show = label.date_show || 'both';
  const dates = [];
  if (show !== 'use') dates.push(`Made ${formatDay(made, style)}`);
  if (show !== 'made') dates.push(`Use by ${formatDay(useByDay(made, label.date_keeps), style)}`);
  const name = (label.date_name || '').trim();
  const portions = String(label.date_portions || '').trim();
  const head = [name && `**${plain(name)}**`, portions && plain(portions)].filter(Boolean).join(' · ');
  return [head && `## ${head}`, dates.join(' · ')].filter(Boolean).join('\n');
}
