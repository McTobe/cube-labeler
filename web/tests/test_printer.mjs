// Tests printer.js against the real Python core running in Pyodide (Node, no browser needed).
// A fake Web Serial port plays the printer: it answers status requests and print commands
// with status packets built by core/ptstatus.py. Run: npm test (from web/).

import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';
import { SerialTransport, queryStatus, printRaster, errorMessage } from '../printer.js';

const WEB_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const CORE_DIR = join(WEB_DIR, '..', 'core');

const STATUS_REQUEST = [0x1b, 0x69, 0x53];  // ESC i S
const PRINT = 0x1a;

const pyodide = await loadPyodide();
pyodide.FS.mkdirTree('/app/core');
for (const name of readdirSync(CORE_DIR).filter((n) => n.endsWith('.py'))) {
  pyodide.FS.writeFile(`/app/core/${name}`, readFileSync(join(CORE_DIR, name)));
}
pyodide.FS.writeFile('/app/cube_web.py', readFileSync(join(WEB_DIR, 'cube_web.py')));
pyodide.runPython(`
import sys
sys.path.insert(0, '/app')
from core.ptstatus import StatusRegister

def status_bytes(status_type=0, err=0, tape_width=12, phase_type=0):
    reg = StatusRegister()
    reg.magic = b"\\x80\\x20B0"
    reg.model = 0x72
    reg.err = err
    reg.tape_width = tape_width
    reg.tape_type = 0x01
    reg.status_type = status_type
    reg.phase_type = phase_type
    reg.tape_bgcolor = 0x01
    reg.tape_fgcolor = 0x08
    return bytes(reg)
`);
const py = pyodide.pyimport('cube_web');
const statusBytes = (opts = {}) => {
  const proxy = pyodide.globals.get('status_bytes').callKwargs(opts);
  const bytes = proxy.toJs();
  proxy.destroy();
  return bytes;
};
const pyBytes = (proxy) => { const b = proxy.toJs(); proxy.destroy(); return b; };

const COVER_OPEN = 1 << 4;

// A Web Serial port that behaves like the PT-P300BT
class FakePrinterPort {
  constructor({ status = {}, afterPrint = [{ status_type: 0x06, phase_type: 1 }, { status_type: 0x01 }],
    silent = false, chunk = 7 } = {}) {
    this.status = status;
    this.afterPrint = afterPrint;
    this.silent = silent;
    this.chunk = chunk;  // replies arrive in small pieces, like Bluetooth does
    this.written = [];
    this.opened = 0;
    this.closed = 0;
  }

  async open({ baudRate }) {
    assert.equal(baudRate, 9600);
    this.opened += 1;
    this.readable = new ReadableStream({ start: (c) => { this.controller = c; } });
    this.writable = new WritableStream({ write: (data) => this._receive(data) });
  }

  _reply(bytes) {
    for (let i = 0; i < bytes.length; i += this.chunk) this.controller.enqueue(bytes.slice(i, i + this.chunk));
  }

  _receive(data) {
    this.written.push(...data);
    if (this.silent) return;
    const tail = Array.from(data.slice(-3));
    if (tail.every((b, i) => b === STATUS_REQUEST[i])) this._reply(statusBytes(this.status));
    if (data.length === 1 && data[0] === PRINT) this.afterPrint.forEach((s) => this._reply(statusBytes(s)));
  }

  async close() {
    this.closed += 1;
    try { this.controller.close(); } catch (err) { /* already closed */ }
  }
}

const RASTER = new Uint8Array([...Array(16).fill(0xff), ...Array(16).fill(0), ...Array.from({ length: 16 }, (_, i) => i)]);

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('prints and waits for completion', async () => {
  const port = new FakePrinterPort();
  const messages = [];
  const result = await printRaster(new SerialTransport(port), py, RASTER,
    { auto_cut: true, required_tape_width_mm: 12 }, (m) => messages.push(m));
  assert.deepEqual(result, { confirmed: true });
  const expected = [
    ...pyBytes(py.status_query()),
    ...pyBytes(py.print_job(statusBytes(), RASTER, { auto_cut: true })),
    PRINT,
    ...pyBytes(py.reset_sequence()),
  ];
  assert.deepEqual(port.written, expected);
  assert.equal(port.closed, 1);
  assert.equal(messages.at(-1), 'Print complete!');
});

test('refuses the wrong tape before printing', async () => {
  const port = new FakePrinterPort({ status: { tape_width: 9 } });
  await assert.rejects(
    printRaster(new SerialTransport(port), py, RASTER, { required_tape_width_mm: 12 }),
    { message: 'This label needs 12mm tape; 9mm is loaded.' },
  );
  assert.ok(!port.written.includes(PRINT));
  assert.equal(port.closed, 1);
});

test('refuses when the cover is open', async () => {
  const port = new FakePrinterPort({ status: { err: COVER_OPEN } });
  await assert.rejects(printRaster(new SerialTransport(port), py, RASTER), /Printer is not ready: .*Cover opened/);
});

test('reports an error during printing', async () => {
  const port = new FakePrinterPort({ afterPrint: [{ status_type: 0x02, err: COVER_OPEN }] });
  await assert.rejects(printRaster(new SerialTransport(port), py, RASTER), /Printer reported an error: .*Cover opened/);
  assert.equal(port.closed, 1);
});

test('reports a missing confirmation', async () => {
  const port = new FakePrinterPort({ afterPrint: [] });
  const fastPy = new Proxy(py, { get: (t, k) => (k === 'completion_timeout' ? () => 0.2 : t[k]) });
  const result = await printRaster(new SerialTransport(port), fastPy, RASTER);
  assert.deepEqual(result, { confirmed: false });
});

test('explains a printer that does not answer', async () => {
  const port = new FakePrinterPort({ silent: true });
  await assert.rejects(queryStatus(new SerialTransport(port), py), /Expected 32 bytes status response, received 0 bytes/);
  assert.equal(port.closed, 1);
});

test('reads the printer status', async () => {
  const status = await queryStatus(new SerialTransport(new FakePrinterPort({ status: { tape_width: 6 } })), py);
  assert.equal(status.tape_width_mm, 6);
  assert.equal(status.is_ready, true);
  assert.deepEqual(status.errors, []);
});

test('a port can be used again after a job', async () => {
  const port = new FakePrinterPort();
  const transport = new SerialTransport(port);
  await queryStatus(transport, py);
  await printRaster(transport, py, RASTER);
  assert.equal(port.opened, 2);
  assert.equal(port.closed, 2);
});

test('errorMessage keeps the last line of a Python traceback', () => {
  const err = new Error('Traceback (most recent call last):\n  File "x", line 1\nRuntimeError: Printer is not ready: Cover opened');
  assert.equal(errorMessage(err), 'Printer is not ready: Cover opened');
  assert.equal(errorMessage(new Error('plain')), 'plain');
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL ${name}\n${err.stack}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
