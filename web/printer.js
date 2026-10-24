// Web Serial transport and print flow for the Brother PT-P300BT.
//
// The bytes come from the Python core (cube_web.py, running in Pyodide); this file only moves
// them over Web Serial and follows the same steps as core/printer.py on the desktop.
//
// `py` is the cube_web module: the app passes its worker bridge, where every call returns a
// promise; the tests pass Pyodide's module directly. Every call is awaited, so both work.

// Serial Port Profile: the Bluetooth Classic service the PT-P300BT exposes
export const SPP_UUID = '00001101-0000-1000-8000-00805f9b34fb';

const BAUD_RATE = 9600;
const STATUS_TIMEOUT_MS = 3000;
const WAKE_RETRY_MS = 1000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class SerialTransport {
  constructor(port) {
    this.port = port;
    this.reader = null;
    this.buffer = new Uint8Array(0);
    this.waiters = [];
    this.readLoop = null;
  }

  static isSupported() {
    return typeof navigator !== 'undefined' && !!navigator.serial
      && typeof navigator.serial.requestPort === 'function';
  }

  // Shows the browser's device picker. No filter: a filter on the SPP service hides paired
  // printers whose services the browser hasn't looked up yet ("No compatible devices found").
  // Allowing the SPP service is what lets the picker list Bluetooth serial devices at all.
  static async request() {
    try {
      return new SerialTransport(await navigator.serial.requestPort({
        allowedBluetoothServiceClassIds: [SPP_UUID],
      }));
    } catch (err) {
      if (err.name !== 'TypeError') throw err;
      // Browsers without Bluetooth serial support list wired serial ports instead
      return new SerialTransport(await navigator.serial.requestPort());
    }
  }

  // A port the user already picked on this site, so reconnecting needs no prompt
  static async remembered() {
    const ports = await navigator.serial.getPorts();
    return ports.length ? new SerialTransport(ports[0]) : null;
  }

  get name() {
    const info = this.port.getInfo ? this.port.getInfo() : {};
    if (info.bluetoothServiceClassId) return 'Bluetooth printer';
    if (info.usbVendorId) return `USB device ${info.usbVendorId.toString(16)}`;
    return 'Serial port';
  }

  // Opens the port, with 1 retry because the printer can be slow to wake from Bluetooth sleep
  async open() {
    try {
      await this.port.open({ baudRate: BAUD_RATE });
    } catch (err) {
      if (err.name === 'InvalidStateError') throw new Error('The printer is already in use by another tab or app.');
      await sleep(WAKE_RETRY_MS);
      await this.port.open({ baudRate: BAUD_RATE });
    }
    this.buffer = new Uint8Array(0);
    this.reader = this.port.readable.getReader();
    this.readLoop = this._pump();
  }

  async _pump() {
    try {
      for (;;) {
        const { value, done } = await this.reader.read();
        if (done) break;
        if (value && value.length) {
          const merged = new Uint8Array(this.buffer.length + value.length);
          merged.set(this.buffer);
          merged.set(value, this.buffer.length);
          this.buffer = merged;
          this._notify();
        }
      }
    } catch (err) {
      // The read loop ends when the port closes or the device disconnects
    } finally {
      this._notify();
    }
  }

  _notify() {
    const waiters = this.waiters;
    this.waiters = [];
    waiters.forEach((wake) => wake());
  }

  async write(bytes) {
    const writer = this.port.writable.getWriter();
    try {
      await writer.write(bytes);
    } finally {
      writer.releaseLock();
    }
  }

  // Reads exactly n bytes, or returns fewer if the timeout passes first (like pyserial)
  async read(n, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (this.buffer.length < n) {
      const left = deadline - Date.now();
      if (left <= 0 || !this.reader) break;
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, left);
        this.waiters.push(() => { clearTimeout(timer); resolve(); });
      });
    }
    const count = Math.min(n, this.buffer.length);
    const out = this.buffer.slice(0, count);
    this.buffer = this.buffer.slice(count);
    return out;
  }

  async close() {
    if (this.reader) {
      try { await this.reader.cancel(); } catch (err) { /* already closed */ }
      try { await this.readLoop; } catch (err) { /* ignored */ }
      this.reader.releaseLock();
      this.reader = null;
    }
    try { await this.port.close(); } catch (err) { /* already closed */ }
  }
}

// Python returns bytes as a proxy; the tests pass plain Uint8Arrays
function toBytes(value) {
  if (value instanceof Uint8Array) return value;
  const bytes = value.toJs();
  if (value.destroy) value.destroy();
  return bytes;
}

function toPlain(value) {
  if (value && typeof value.toJs === 'function') {
    const plain = value.toJs({ dict_converter: Object.fromEntries });
    if (value.destroy) value.destroy();
    return plain;
  }
  return value;
}

// Turns a Python traceback into its last line's message ("Printer is not ready: Cover opened")
export function errorMessage(err) {
  const text = String((err && err.message) || err).trim();
  const lines = text.split('\n').filter((line) => line.trim());
  const last = lines[lines.length - 1] || text;
  const match = last.match(/^\w+(?:Error|Exception): (.*)$/);
  return match ? match[1] : last;
}

async function readStatus(transport, py) {
  const size = await py.status_packet_size();
  const raw = await transport.read(size, STATUS_TIMEOUT_MS);
  if (raw.length !== size) {
    throw new Error(`Expected ${size} bytes status response, received ${raw.length} bytes. `
      + 'Is the printer switched on and paired?');
  }
  return raw;
}

async function withPrinter(transport, py, job) {
  await transport.open();
  try {
    return await job();
  } finally {
    // Like the desktop app: reset the printer before letting go of the port
    try { await transport.write(toBytes(await py.reset_sequence())); } catch (err) { /* ignored */ }
    await transport.close();
  }
}

export async function queryStatus(transport, py) {
  return withPrinter(transport, py, async () => {
    await transport.write(toBytes(await py.status_query()));
    return toPlain(await py.describe_status(await readStatus(transport, py)));
  });
}

// Prints one raster. Resolves to {confirmed: bool}; rejects with a readable error message.
export async function printRaster(transport, py, raster, options = {}, onStatus = () => {}) {
  const lines = await py.raster_lines(raster);
  return withPrinter(transport, py, async () => {
    onStatus('Checking printer status...');
    await transport.write(toBytes(await py.status_query()));
    const status = await readStatus(transport, py);

    let job;
    try {
      job = toBytes(await py.print_job(status, raster, options));
    } catch (err) {
      throw new Error(errorMessage(err));
    }

    onStatus(`Sending ${lines} lines...`);
    await transport.write(job);
    onStatus('Printing label...');
    await transport.write(toBytes(await py.print_command()));

    const deadline = Date.now() + (await py.completion_timeout(lines)) * 1000;
    const size = await py.status_packet_size();
    while (Date.now() < deadline) {
      const raw = await transport.read(size, deadline - Date.now());
      if (raw.length !== size) {
        if (!transport.reader) break;  // the printer disconnected
        continue;
      }
      let state;
      try {
        state = await py.job_state(raw);
      } catch (err) {
        throw new Error(errorMessage(err));
      }
      if (state === 'completed') {
        onStatus('Print complete!');
        return { confirmed: true };
      }
    }
    onStatus('Print sent, but the printer did not confirm completion.');
    return { confirmed: false };
  });
}

// Feeds blank tape so the last label clears the cutter, like the desktop's Feed tape
export async function feedTape(transport, py, lengthMm, onStatus = () => {}) {
  const raster = toBytes(await py.blank_raster(lengthMm));
  return printRaster(transport, py, raster, { compress: false }, (message) => {
    onStatus(message === 'Print complete!' ? 'Tape fed.' : message.replace('Printing label', 'Feeding tape').replace('Print sent', 'Feed sent'));
  });
}
