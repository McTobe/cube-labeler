// The tape counter's sums: how much is left on a roll, how counts from two devices come
// together, and how a queue splits into parts that fit. Plain functions; app.js keeps the state.
//
// A roll (settings.tape_rolls[key], one per kind of tape) looks like
//   {id, length_mm, loaded, set_at, start_mm, used: {device: mm}, prints: {device: n},
//    used_before, prints_before}
// Each device only ever adds to its own entry in used and prints, so two devices' counts merge
// by taking the larger entry per device, and none is lost or counted twice. A new roll or a
// corrected count starts a new id; then the newest one wins.

export const ROLL_LENGTHS_MM = [8000, 4000];
export const LOW_TAPE_MM = 300;

// One count per kind of tape: width and colours, as the printer reports them
export const tapeKey = (info) => `${info.tape_width_mm}|${info.tape_color}|${info.text_color}`;

// "12 mm white", for the roll box
export const tapeName = (info) => `${info.tape_width_mm} mm ${String(info.tape_color || '').toLowerCase()}`.trim();

const sum = (counts) => Object.values(counts || {}).reduce((total, n) => total + n, 0);

export const rollLeft = (roll) => Math.max(0, roll.start_mm - sum(roll.used));
export const rollUsed = (roll) => (roll.used_before || 0) + sum(roll.used);
export const rollPrints = (roll) => (roll.prints_before || 0) + sum(roll.prints);

// "5.2 m" or "28 cm"
export function formatTape(mm) {
  if (mm >= 1000) return `${(Math.floor(mm / 100) / 10).toLocaleString(undefined, { maximumFractionDigits: 1 })} m`;
  return `${Math.max(0, Math.round(mm / 10))} cm`;
}

const newId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export function newRoll(lengthMm) {
  return {
    id: newId(), length_mm: lengthMm, loaded: new Date().toISOString(), set_at: Date.now(),
    start_mm: lengthMm, used: {}, prints: {}, used_before: 0, prints_before: 0,
  };
}

// The same roll with leftMm left: the prints so far are kept for the summary
export function correctRoll(roll, leftMm) {
  return {
    ...roll, id: newId(), set_at: Date.now(), start_mm: leftMm, used: {}, prints: {},
    used_before: Math.max(0, roll.length_mm - leftMm), prints_before: rollPrints(roll),
  };
}

export function countPrint(roll, device, mm) {
  return {
    ...roll,
    used: { ...roll.used, [device]: (roll.used[device] || 0) + mm },
    prints: { ...roll.prints, [device]: (roll.prints[device] || 0) + 1 },
  };
}

const looksLikeRoll = (roll) => roll && typeof roll === 'object' && typeof roll.id === 'string'
  && Number(roll.start_mm) >= 0 && Number(roll.length_mm) > 0;

function largest(a = {}, b = {}) {
  const out = { ...a };
  for (const [device, n] of Object.entries(b)) out[device] = Math.max(out[device] || 0, Number(n) || 0);
  return out;
}

// This device's rolls and another device's (from a Drive backup), together
export function mergeRolls(mine = {}, theirs = {}) {
  const out = { ...mine };
  for (const [key, roll] of Object.entries(theirs || {})) {
    if (!looksLikeRoll(roll)) continue;
    const own = out[key];
    if (!own || (own.id !== roll.id && roll.set_at > own.set_at)) out[key] = roll;
    else if (own.id === roll.id) out[key] = { ...own, used: largest(own.used, roll.used), prints: largest(own.prints, roll.prints) };
  }
  return out;
}

// --- Printing a queue in parts ---------------------------------------------------------------

// How much tape printed labels from..to (indexes into the printed labels, copies counted)
// use as one print. lengths comes from Python's queue_lengths; owners maps each printed label
// to its queue item.
export function partLength(lengths, owners, from, to) {
  const toMm = (dots) => dots * lengths.dot_mm + lengths.lead_mm;
  if (from === to) return toMm(lengths.singles[owners[from]]);
  let dots = lengths.ends + lengths.gap * (to - from);
  for (let n = from; n <= to; n++) dots += lengths.widths[owners[n]];
  return toMm(dots);
}

// Splits the printed labels into parts: each fits the printer's limit, and while the roll is
// counted each fits what is left on it, with a new roll (of the same length) before the part
// that would not. A part never cuts a label. Returns null when one label alone is too long.
// Each part: {from, to, mm, newRoll}.
export function planParts(lengths, owners, left, rollLength) {
  const parts = [];
  let from = 0;
  let onRoll = left;  // null when the roll is not counted
  let newRoll = false;
  while (from < owners.length) {
    const room = Math.min(lengths.max_mm, onRoll ?? Infinity);
    let to = from - 1;
    while (to + 1 < owners.length && partLength(lengths, owners, from, to + 1) <= room) to++;
    if (to < from) {
      if (partLength(lengths, owners, from, from) > lengths.max_mm) return null;
      if (newRoll || onRoll === null) return null;  // cannot happen: a fresh roll holds any label
      // Not even the next label fits on what is left: it goes on a new roll
      onRoll = rollLength;
      newRoll = true;
      continue;
    }
    const mm = partLength(lengths, owners, from, to);
    parts.push({ from, to, mm, newRoll });
    if (onRoll !== null) onRoll -= mm;
    newRoll = false;
    from = to + 1;
  }
  return parts;
}

// The queue items with their copies for printed labels from..to
export function partItems(queue, owners, from, to) {
  const items = [];
  for (let n = from; n <= to; n++) {
    const last = items[items.length - 1];
    if (last && last.index === owners[n]) last.copies++;
    else items.push({ index: owners[n], copies: 1 });
  }
  return items.map(({ index, copies }) => ({ ...queue[index], copies }));
}
