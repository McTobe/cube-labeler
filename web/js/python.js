// The page's side of worker.js: `py.render_label(options)` and friends return promises.
// printer.js takes this same object, so the print flow awaits every Python call.

export function startPython(onProgress = () => {}) {
  const worker = new Worker(new URL('./worker.js', import.meta.url));
  const pending = new Map();
  let nextId = 1;

  const ready = new Promise((resolve, reject) => {
    worker.onmessage = (event) => {
      const msg = event.data;
      if (msg.type === 'progress') { onProgress(msg.text); return; }
      if (msg.type === 'ready') { resolve(); return; }
      if (msg.type === 'failed') { reject(new Error(msg.error)); return; }
      const call = pending.get(msg.id);
      if (!call) return;
      pending.delete(msg.id);
      if ('error' in msg) call.reject(new Error(msg.error));
      else call.resolve(msg.result);
    };
    worker.onerror = (event) => reject(new Error(event.message || 'The Python worker could not start.'));
  });

  const call = (name, args) => new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, name, args });
  });

  // Any property is a Python function, except `then`, so awaiting `py` itself stays harmless
  const py = new Proxy({}, {
    get(_, name) {
      if (name === 'then' || typeof name !== 'string') return undefined;
      return (...args) => call(name, args);
    },
  });
  return { py, ready };
}
