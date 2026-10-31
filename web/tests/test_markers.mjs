// The styled view of the label text box (js/marker-view.js) reads the markers like
// core/rich_text.py does. Run with: node tests/test_markers.mjs
import assert from 'node:assert/strict';
import { textParts, markerHtml, stylesAt } from '../js/marker-view.js';

const words = (text) => textParts(text).filter((p) => !p.mark && !p.newline)
  .map((p) => [p.text, ['bold', 'italic', 'underline', 'invert'].filter((s) => p[s]).join('+')]);
const marks = (text) => textParts(text).filter((p) => p.mark).map((p) => p.text);

// Every character of the text stays in the layer, in order, so the caret lines up
for (const text of ['# **Workshop**', '-# Drawer 4 · __screws__\n---\n==M3== and *M4*', 'a\\*b', 'x\\ny', '', '**open']) {
  assert.equal(textParts(text).map((p) => p.text).join(''), text);
}

assert.deepEqual(words('# **Workshop**'), [['Workshop', 'bold']]);
assert.deepEqual(marks('# **Workshop**'), ['# ', '**', '**']);
assert.deepEqual(words('==M3== and *M4*'), [['M3', 'invert'], [' and ', ''], ['M4', 'italic']]);
// The markers of a style carry it, so an inverted run is one dark box
assert.ok(textParts('==M3==').every((p) => p.invert));
// Size and alignment, in either order, then a column line
assert.deepEqual(marks('>> ## Right'), ['>> ', '## ']);
assert.equal(textParts('---')[0].column, true);
// Markers that don't open a style are plain text, like on the label
assert.deepEqual(words('**open'), [['**open', '']]);
assert.deepEqual(words('M3 * 8 * 2'), [['M3 * 8 * 2', '']]);
assert.deepEqual(words('a\\*b'), [['a', ''], ['*b', '']]);
// Bold inside italic
assert.deepEqual(words('*a **b** c*'), [['a ', 'italic'], ['b', 'bold+italic'], [' c', 'italic']]);
// A typed "\n" starts a new line on the label, so a size marker after it counts
assert.deepEqual(marks('a\\n# b'), ['\\n', '# ']);

assert.equal(markerHtml('<b>&'), '&lt;b&gt;&amp;​');
assert.ok(markerHtml('**x**').includes('<span class="st-bold">x</span>'));

assert.equal(stylesAt('==M3== and *M4*', 15).italic, true);
assert.equal(stylesAt('==M3== and *M4*', 9).italic, false);
assert.equal(stylesAt('==M3== and *M4*', 4).invert, true);
assert.equal(stylesAt('**a**\nb', 6).bold, false);

console.log('marker view: ok');
