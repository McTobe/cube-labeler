// The code on a network outlet label, like DA01P02 3/4: where the outlet is (building, floor,
// room), then the rack, the panel and the ports its cables go to. Empty parts are left out.
// Pure functions, so tests can run them without the app.

// How the rack counts the place of a panel: by panel (P), by M (mått / monteringsplats in the
// Swedish standard SS 455 12 01: whole cm from the top of the rack down to the top edge of the
// panel, like M010) or by rack unit (U)
export const OUTLET_PANEL_KINDS = [['P', 'Panel P'], ['M', 'cm M'], ['U', 'Unit U']];
export const OUTLET_PORTS = [[1, 'One'], [2, 'Two'], [4, 'Four']];
export const OUTLET_SEPARATORS = [['', 'None'], [' ', 'Space'], ['-', '-'], ['.', '.']];
export const OUTLET_PAIRS = [['/', '3/4'], ['-', '3-4'], ['+', '3+4']];
export const OUTLET_DIGITS = [[0, 'As typed'], [2, '01'], [3, '001']];
export const OUTLET_LINES = [[1, 'One line'], [2, 'Two lines']];
// Which way the code is written: one of the two Swedish standards, or the user's own style.
// SS 455 12 01 (the current one) writes +C1B1D1S1M30:24: area, building, distributor (room),
// rack (S), module (M, the panel's place) and the port after a colon. SS 455 12 00 (the old one,
// still the most used) writes AC 01 31C 20: house and floor letters, rack, panel place and jack.
export const OUTLET_STANDARDS = [['ss01', '12 01'], ['ss00', '12 00'], ['own', 'Own style']];
// How SS 455 12 00 counts the panel place: by its height in the rack (31C) or in order (04C)
export const OUTLET_PLACE_KINDS = [['height', 'Height'], ['order', 'Order']];
// The letters SS 455 12 01 puts in front of each part, in the order they are written
export const SS01_PARTS = [['outlet_c', 'C'], ['outlet_b', 'B'], ['outlet_d', 'D'], ['outlet_s', 'S'], ['outlet_m', 'M']];

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

// SS 455 12 01: +C1B1D1 on top on two lines, S1M30:24 the code
function ss01Parts(label, first) {
  const part = ([field, letter]) => {
    const v = clean(label[field]);
    return v ? `${letter}${field === 'outlet_m' ? padNumber(v, label.outlet_digits) : v}` : '';
  };
  const where = SS01_PARTS.slice(0, 3).map(part).join('');
  const kit = SS01_PARTS.slice(3).map(part).join('');
  const ports = outletPorts(label, first);
  const twoLines = Number(label.outlet_lines) === 2 && where && (kit || ports);
  let code = twoLines ? kit : `${where}${kit}`;
  if (ports) code = `${code}:${ports}`;
  // The plus marks the start of a full code; a code split over two lines gets it on top
  if (twoLines) return { where: `+${where}`, code };
  return { where: '', code: code && !code.startsWith(':') ? `+${code}` : code };
}

// SS 455 12 00: house and floor letters together, then rack, panel place and jack, with spaces
function ss00Parts(label, first) {
  const where = `${clean(label.outlet_house)}${clean(label.outlet_storey)}`;
  const kit = [padNumber(label.outlet_cab, label.outlet_digits), clean(label.outlet_place), outletPorts(label, first)].filter(Boolean);
  const twoLines = Number(label.outlet_lines) === 2 && where && kit.length;
  return twoLines ? { where, code: kit.join(' ') } : { where: '', code: [where, ...kit].filter(Boolean).join(' ') };
}

// {where, code}: where is building, floor and room, code the rack, panel and ports
export function outletParts(label, first = label.outlet_first) {
  if (label.outlet_standard === 'ss01') return ss01Parts(label, first);
  if (label.outlet_standard === 'ss00') return ss00Parts(label, first);
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
  const lines = Number(label.outlet_lines) === 2 ? 'two lines' : 'one line';
  if (label.outlet_standard === 'ss01') return `SS 455 12 01, ${lines}`;
  if (label.outlet_standard === 'ss00') return `SS 455 12 00, ${lines}`;
  const example = outletParts({ ...label, outlet_lines: 1, outlet_building: '', outlet_floor: '', outlet_room: '',
    outlet_rack: 'DA01', outlet_panel: '02', outlet_first: 3 }).code;
  return `${example}, ${lines}`;
}

// The first port of the next outlet after `rows` labels of this one
export function nextFirst(label, rows = 1) {
  const start = parseInt(label.outlet_first, 10);
  if (!Number.isFinite(start)) return label.outlet_first;
  return start + (Number(label.outlet_ports) || 1) * rows;
}
