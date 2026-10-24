// Runs Pyodide and the Cube Labeler Python core off the page's main thread, so typing and
// scrolling stay smooth while a label renders. python.js is the page's side of this.
//
// Messages in:  {id, name, args}  calls cube_web.<name>(...args)
// Messages out: {type: 'progress', text} while starting, {type: 'ready'} once, then
//               {id, result} or {id, error} for each call, in the order they came in.

const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/';
const QRCODE_VERSION = '8.2';  // keep in step with constraints.txt

importScripts(`${PYODIDE_URL}pyodide.js`);

let pyodide = null;
let cubeWeb = null;

const progress = (text) => postMessage({ type: 'progress', text });

async function start() {
  progress('Loading Python...');
  pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

  progress('Loading Pillow and QR codes...');
  await pyodide.loadPackage(['pillow', 'micropip']);
  await pyodide.pyimport('micropip').install(`qrcode==${QRCODE_VERSION}`);

  progress('Loading Cube Labeler...');
  const response = await fetch(new URL('../cube_core.zip', self.location));
  if (!response.ok) throw new Error(`cube_core.zip: HTTP ${response.status}`);
  // The archive holds core/, cube_web.py and the bundled fonts in ~/.fonts
  pyodide.unpackArchive(await response.arrayBuffer(), 'zip', { extractDir: '/home/pyodide' });
  pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  cubeWeb = pyodide.pyimport('cube_web');
}

// Python values back to plain structured-cloneable JavaScript (bytes become Uint8Array)
function toPlain(value) {
  if (value && typeof value.toJs === 'function') {
    const plain = value.toJs({ dict_converter: Object.fromEntries, create_pyproxies: false });
    value.destroy();
    return plain;
  }
  return value;
}

// Pyodide turns JavaScript null into JsNull rather than None; undefined becomes None
function nullsToUndefined(value) {
  if (value === null) return undefined;
  if (Array.isArray(value)) return value.map(nullsToUndefined);
  if (value && value.constructor === Object) {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, nullsToUndefined(v)]));
  }
  return value;
}

function transferables(value, out = []) {
  if (value instanceof Uint8Array) {
    out.push(value.buffer);
  } else if (Array.isArray(value)) {
    value.forEach((v) => transferables(v, out));
  } else if (value && typeof value === 'object') {
    Object.values(value).forEach((v) => transferables(v, out));
  }
  return [...new Set(out)];
}

// Calls run one at a time, in order, like they would on a single Python thread
let queue = Promise.resolve();
const started = start().then(
  () => postMessage({ type: 'ready' }),
  (err) => { postMessage({ type: 'failed', error: String((err && err.message) || err) }); throw err; },
);

self.onmessage = (event) => {
  const { id, name, args } = event.data;
  queue = queue.then(async () => {
    try {
      await started;
      const fn = cubeWeb[name];
      if (typeof fn !== 'function') throw new Error(`cube_web has no function ${name}`);
      let result;
      try {
        result = toPlain(fn(...args.map(nullsToUndefined)));
      } finally {
        fn.destroy();
      }
      postMessage({ id, result }, transferables(result));
    } catch (err) {
      postMessage({ id, error: String((err && err.message) || err) });
    }
  });
};
