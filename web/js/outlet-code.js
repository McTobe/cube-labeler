// The code on a network outlet label, like DA01P02 3/4: where the outlet is (building, floor,
// room), then the rack, the panel and the ports its cables go to. Empty parts are left out.
// Pure functions, so tests can run them without the app.

// How the rack counts the place of a panel: by panel (P), by metric position from the top (M)
// or by rack unit (U)
export const OUTLET_PANEL_KINDS = [['P', 'Panel P'], ['M', 'Metric M'], ['U', 'Unit U']];
export const OUTLET_PORTS = [[1, 'One'], [2, 'Two'], [4, 'Four']];
export const OUTLET_SEPARATORS = [['', 'None'], [' ', 'Space'], ['-', '-'], ['.', '.']];
export const OUTLET_PAIRS = [['/', '3/4'], ['-', '3-4'], ['+', '3+4']];
export const OUTLET_DIGITS = [[0, 'As typed'], [2, '01'], [3, '001']];
export const OUTLET_LINES = [[1, 'One line'], [2, 'Two lines']];
// Between building, floor and room on the small top line of a two line label
const WHERE_JOIN = ' · ';

const clean = (v) => String(v ?? '').trim();

// A number padded with zeros to the chosen digits; anything else as typed
export function padNumber(value, digits) {
  const v = clean(value);
  return digits && /^\d+$/.test(v) ? v.padStart(digits, '0') : v;
}

// The ports part: 3, 3/4 (as the pair style says) or 1-4 for four ports
export function outletPorts(label, first = label.outlet_first) {
  const start = parseInt(first, 10);
  if (!Number.isFinite(start)) return '';
  const count = Number(label.outlet_ports) || 1;
  const n = (v) => padNumber(String(v), label.outlet_digits);
  if (count === 1) return n(start);
  if (count === 2) return `${n(start)}${label.outlet_pair || '/'}${n(start + 1)}`;
  return `${n(start)}-${n(start + count - 1)}`;
}

// {where, code}: where is building, floor and room, code the rack, panel and ports
export function outletParts(label, first = label.outlet_first) {
  const sep = label.outlet_sep ?? '';
  const place = [label.outlet_building, label.outlet_floor, label.outlet_room].map(clean).filter(Boolean);
  const panel = clean(label.outlet_panel);
  const kit = [clean(label.outlet_rack), panel ? `${label.outlet_panel_kind || 'P'}${padNumber(panel, label.outlet_digits)}` : '']
    .filter(Boolean);
  const ports = outletPorts(label, first);
  const twoLines = Number(label.outlet_lines) === 2 && place.length > 0;
  const front = twoLines ? kit : [...place, ...kit];
  let code = front.join(sep);
  // With nothing between the parts the ports still get a space, or 02 and 3 would run together
  if (ports) code = code ? `${code}${sep || ' '}${ports}` : ports;
  return { where: twoLines ? place.join(WHERE_JOIN) : '', code };
}

// The label text the renderer draws: the code, with the place small on a line above it
export function outletText(label, first = label.outlet_first) {
  const { where, code } = outletParts(label, first);
  if (!code) return where;
  return where ? `-# ${where}\n${code}` : code;
}

// One line describing the code style, for the folded settings card
export function outletStyleSummary(label) {
  const example = outletParts({ ...label, outlet_lines: 1, outlet_building: '', outlet_floor: '', outlet_room: '',
    outlet_rack: 'DA01', outlet_panel: '02', outlet_first: 3 }).code;
  return `${example}, ${Number(label.outlet_lines) === 2 ? 'two lines' : 'one line'}`;
}

// The first port of the next outlet after `rows` labels of this one
export function nextFirst(label, rows = 1) {
  const start = parseInt(label.outlet_first, 10);
  if (!Number.isFinite(start)) return label.outlet_first;
  return start + (Number(label.outlet_ports) || 1) * rows;
}
