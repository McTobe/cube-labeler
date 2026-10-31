# Vendored libraries

Copied as-is from their npm packages, so the page needs no build step or bundler.
Only the source map comments were removed.

| File | Package | License |
|---|---|---|
| `preact.module.js` | preact 10.29.8 (`dist/preact.module.js`) | MIT, `LICENSE-preact` |
| `preact-hooks.module.js` | preact 10.29.8 (`hooks/dist/hooks.module.js`) | MIT, `LICENSE-preact` |
| `htm.module.js` | htm 3.1.1 (`dist/htm.module.js`) | Apache 2.0, `LICENSE-htm` |

`index.html` maps the bare `preact` and `preact/hooks` imports to these files with an import map.

`arimo-editor.woff2` is Arimo Regular from `web/fonts/Arimo-Regular.ttf` (OFL 1.1, `LICENSE-arimo`),
cut down to Latin, common punctuation, arrows and a few symbols for the label text box (about 10 KB):

```
pyftsubset web/fonts/Arimo-Regular.ttf --unicodes="U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+0160-0161,U+0178,U+017D-017E,U+2013-2014,U+2018-201E,U+2022,U+2026,U+2030,U+2032-2033,U+20AC,U+2122,U+2190-2195,U+2212,U+2264-2265,U+2116,U+03A9,U+03BC,U+0394,U+2126" --flavor=woff2 --layout-features='' --name-IDs='*' --output-file=web/vendor/arimo-editor.woff2
```

The box needs one font with no bold or italic file of its own, so the browser slants the italic
itself and every letter keeps its width (see `web/js/marker-view.js`).
