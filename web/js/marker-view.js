// The styled view of the label text box: a layer behind the (see-through) text box shows the same
// characters, with the words bold, italic, underlined or inverted and the markers in pale grey.
//
// The text box itself stays a plain textarea, so phone keyboards, autocorrect and undo behave as
// usual. For its caret to sit on the right letter every character in the layer must keep the width
// it has in the box: one font with no bold or italic file (vendor/arimo-editor.woff2), so italic is
// slanted by the browser, bold is drawn with an outline, and no size changes. Kerning and
// ligatures are off in both, since they would differ where a style starts or ends.
//
// The reading of the markers follows core/rich_text.py (parse, _split_prefixes, parse_inline),
// which draws the label; keep the two in step.

const SIZE_PREFIXES = [['## ', 'medium'], ['# ', 'large'], ['-# ', 'small']];
const ALIGN_PREFIXES = [['<< ', 'left'], ['>< ', 'center'], ['>> ', 'right']];
const COLUMN_BREAK = '---';
// Longest first, so "**" is read as bold and not as two italic markers
const INLINE_MARKERS = [['**', 'bold'], ['__', 'underline'], ['==', 'invert'], ['*', 'italic']];
const ESCAPABLE = '\\*_=#<>-';
const STYLES = ['bold', 'italic', 'underline', 'invert'];

// A marker opens a style only if text follows it and the same marker closes it later
function opens(text, start, marker) {
  if (start >= text.length || text[start] === ' ') return false;
  let idx = text.indexOf(marker, start + 1);
  while (idx !== -1) {
    if (text[idx - 1] !== ' ' && text[idx - 1] !== '\\') return true;
    idx = text.indexOf(marker, idx + 1);
  }
  return false;
}

// One line (no line breaks) as pieces: {text, mark, bold, italic, underline, invert}. A marker
// that opens a style carries that style, and so does the one that closes it, so a run of
// inverted text is one dark box with its markers inside.
function lineParts(line, out) {
  if (line.trim() === COLUMN_BREAK) {
    out.push({ text: line, mark: true, column: true });
    return;
  }
  // Size and alignment at the start, in either order
  let rest = line;
  let size = null;
  let align = null;
  let found = true;
  while (found) {
    found = false;
    if (!size) {
      for (const [prefix] of SIZE_PREFIXES) {
        if (rest.startsWith(prefix)) { size = prefix; rest = rest.slice(prefix.length); found = true; out.push({ text: prefix, mark: true }); break; }
      }
    }
    if (!align) {
      for (const [prefix] of ALIGN_PREFIXES) {
        if (rest.startsWith(prefix)) { align = prefix; rest = rest.slice(prefix.length); found = true; out.push({ text: prefix, mark: true }); break; }
      }
    }
  }

  const state = { bold: false, italic: false, underline: false, invert: false };
  const push = (text, mark) => {
    const last = out[out.length - 1];
    const piece = { text, mark, ...state };
    if (last && !last.column && last.mark === mark && STYLES.every((s) => last[s] === state[s])) last.text += text;
    else out.push(piece);
  };
  let i = 0;
  while (i < rest.length) {
    const ch = rest[i];
    if (ch === '\\' && i + 1 < rest.length && ESCAPABLE.includes(rest[i + 1])) {
      push('\\', true);
      push(rest[i + 1], false);
      i += 2;
      continue;
    }
    let matched = false;
    for (const [marker, attr] of INLINE_MARKERS) {
      if (!rest.startsWith(marker, i)) continue;
      const end = i + marker.length;
      if (state[attr] && i > 0 && rest[i - 1] !== ' ') {
        push(marker, true);
        state[attr] = false;
      } else if (!state[attr] && opens(rest, end, marker)) {
        state[attr] = true;
        push(marker, true);
      } else {
        continue;
      }
      i = end;
      matched = true;
      break;
    }
    if (!matched) {
      push(ch, false);
      i += 1;
    }
  }
}

// The whole text as pieces, with the line breaks as pieces of their own. A typed "\n" is a line
// break on the label too, so it shows as a marker and the text after it starts a new line.
export function textParts(text) {
  const out = [];
  text.split('\n').forEach((line, n) => {
    if (n > 0) out.push({ text: '\n', mark: false, newline: true });
    line.split('\\n').forEach((part, m) => {
      if (m > 0) out.push({ text: '\\n', mark: true });
      lineParts(part, out);
    });
  });
  return out;
}

const escapeHtml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// The layer's HTML for the text
export function markerHtml(text) {
  let html = '';
  for (const p of textParts(text)) {
    if (p.newline) { html += '\n'; continue; }
    const cls = [p.mark ? 'mk' : '', p.column ? 'mk-col' : '', ...STYLES.filter((s) => p[s]).map((s) => `st-${s}`)]
      .filter(Boolean).join(' ');
    html += cls ? `<span class="${cls}">${escapeHtml(p.text)}</span>` : escapeHtml(p.text);
  }
  // A last empty line needs something in it to have a height, as it has in the text box
  return `${html}​`;
}

// The styles the text has at a spot (the letter just before it, or the first letter of the
// line), for lighting up the toolbar buttons
export function stylesAt(text, pos) {
  const none = { bold: false, italic: false, underline: false, invert: false };
  const at = pos > 0 && text[pos - 1] !== '\n' ? pos - 1 : pos;
  if (at >= text.length || text[at] === '\n') return none;
  let offset = 0;
  for (const p of textParts(text)) {
    if (at < offset + p.text.length) {
      return p.newline || p.column ? none : { bold: p.bold, italic: p.italic, underline: p.underline, invert: p.invert };
    }
    offset += p.text.length;
  }
  return none;
}
