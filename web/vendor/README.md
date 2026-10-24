# Vendored libraries

Copied as-is from their npm packages, so the page needs no build step or bundler.
Only the source map comments were removed.

| File | Package | License |
|---|---|---|
| `preact.module.js` | preact 10.29.8 (`dist/preact.module.js`) | MIT, `LICENSE-preact` |
| `preact-hooks.module.js` | preact 10.29.8 (`hooks/dist/hooks.module.js`) | MIT, `LICENSE-preact` |
| `htm.module.js` | htm 3.1.1 (`dist/htm.module.js`) | Apache 2.0, `LICENSE-htm` |

`index.html` maps the bare `preact` and `preact/hooks` imports to these files with an import map.
