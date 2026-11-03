// The code on a power outlet label, like A1A Gr. 13: where the outlet is (building, floor,
// room), the central (distribution board) and the group (fuse) that feeds it, and if wanted its
// phase and voltage. Empty parts are left out. Pure functions, so tests can run them without the
// app. The network outlet's codes are in outlet-code.js.
import { padNumber } from './outlet-code.js';

// How the group is written: Gr. 13, F13 or just 13
export const POWER_GROUP_KINDS = [['Gr.', 'Gr.'], ['F', 'F'], ['', 'None']];
export const POWER_PHASES = [['', 'None'], ['L1', 'L1'], ['L2', 'L2'], ['L3', 'L3'], ['L1-L3', 'All']];
export const POWER_VOLTAGES = [['', 'None'], ['230 V', '230 V'], ['400 V', '400 V']];
export const POWER_SEPARATORS = [[' ', 'Space'], [':', ':'], ['-', '-'], ['.', '.']];
export const POWER_DIGITS = [[0, 'As typed'], [2, '01'], [3, '001']];
export const POWER_LINES = [[1, 'One line'], [2, 'Two lines']];
// Phase and voltage after the group, or on a small line under the code
export const POWER_EXTRAS = [['after', 'After the group'], ['below', 'Small line']];
// Between building, floor and room, and between phase and voltage, on a small line
const SMALL_JOIN = ' · ';

const clean = (v) => String(v ?? '').trim();

// The group part: Gr. 13 (with a space, as it is written), F13, or 13
export function powerGroup(label, group = label.power_group) {
  const number = padNumber(group, label.power_digits);
  if (!number) return '';
  const kind = label.power_group_kind ?? 'Gr.';
  if (!kind) return number;
  return kind.endsWith('.') ? `${kind} ${number}` : `${kind}${number}`;
}

// {where, code, extra}: where is building, floor and room when they go on their own line, extra
// the phase and voltage when they go on a small line under the code
export function powerParts(label, group = label.power_group) {
  const sep = label.power_sep ?? ' ';
  const place = [label.power_building, label.power_floor, label.power_room].map(clean).filter(Boolean);
  const extras = [label.power_phase, label.power_voltage].map(clean).filter(Boolean);
  const twoLines = Number(label.power_lines) === 2 && place.length > 0;
  const below = label.power_extra === 'below';
  const front = [...(twoLines ? [] : place), clean(label.power_central), powerGroup(label, group)].filter(Boolean);
  let code = front.join(sep);
  // After the group they always get a space: A1A:13 L2 reads better than A1A:13:L2
  if (!below && extras.length) code = [code, ...extras].filter(Boolean).join(' ');
  return { where: twoLines ? place.join(SMALL_JOIN) : '', code, extra: below ? extras.join(SMALL_JOIN) : '' };
}

// The label text the renderer draws: the code, with the place small above it and the phase and
// voltage small under it
export function powerText(label, group = label.power_group) {
  const { where, code, extra } = powerParts(label, group);
  if (!code) return [where, extra].filter(Boolean).join('\n');
  return [where && `-# ${where}`, code, extra && `-# ${extra}`].filter(Boolean).join('\n');
}

// One line describing the code style, for the folded settings card
export function powerStyleSummary(label) {
  const example = powerParts({ ...label, power_lines: 1, power_building: '', power_floor: '', power_room: '',
    power_phase: '', power_voltage: '', power_central: 'A1A', power_group: '13' }).code;
  return `${example}, ${Number(label.power_lines) === 2 ? 'two lines' : 'one line'}`;
}

// The next group after this one, keeping its zeros (09 becomes 10); anything not a number stays
export function nextGroup(label) {
  const g = clean(label.power_group);
  if (!/^\d+$/.test(g)) return label.power_group;
  return String(parseInt(g, 10) + 1).padStart(g.length, '0');
}
