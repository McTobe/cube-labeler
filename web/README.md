# Cube Labeler web app (preview)

A browser version of Cube Labeler that prints to the PT-P300BT over Bluetooth with the
[Web Serial API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API). It runs
the same Python core as the desktop app inside the browser with [Pyodide](https://pyodide.org),
so labels and printer bytes come out exactly the same.

This first version does single text labels: font, tape width, alignment, auto-fit or fixed
size, an optional QR code, cut after printing, printer status and saving the preview as a
picture. Bin labels, icons, the queue and templates are not in it yet.

## Browser support

| Browser | Design labels | Print |
|---|---|---|
| Chrome or Edge on Windows, macOS, Linux | Yes | Yes |
| Chrome on Android | Yes | Yes |
| Firefox, Safari, anything on iPhone or iPad | Yes | No (no Web Serial) |

Pair the printer in the phone's or computer's Bluetooth settings first. **Connect printer**
then opens the browser's device picker, which lists paired devices with the serial port service.

On Android, Chrome also needs the **Nearby devices** permission (Settings › Apps › Chrome ›
Permissions). After granting it, force stop Chrome (Settings › Apps › Chrome › Force stop) and
open it again: until Chrome fully restarts, the picker says "No compatible devices found".

## Running it

On Windows, double-click `run_web.bat` in the repository root. It builds the site, starts a
server, opens the page in your browser and prints the address to open on your phone. The
first time, Windows Firewall may ask about Python: allow it on private networks only.
Close the window (or press Ctrl+C) to stop it.

The same from a terminal, on any system:

```bash
python web/serve.py          # build and serve on port 8000; or: python web/serve.py 8080
```

Or step by step:

```bash
python web/build.py                       # builds web/dist/
python -m http.server 8000 -d web/dist    # then open http://localhost:8000/
```

`web/dist/` is a plain static site, so any host works. The first visit downloads Pyodide,
Pillow and qrcode from the jsDelivr CDN and PyPI (about 15 MB); after that the browser cache
serves them.

Web Serial only works on a secure origin: `https://`, or `http://localhost`. To try it from a
phone on your Wi-Fi without hosting it anywhere:

1. Start `run_web.bat` on your PC and note the phone address it prints (for example `http://192.168.1.20:8000/`).
2. On the phone, open `chrome://flags/#unsafely-treat-insecure-origin-as-secure` in Chrome, add
   `http://192.168.1.20:8000`, enable it and restart Chrome.
3. Open that address on the phone.

## How it fits together

| File | What it does |
|---|---|
| `index.html`, `style.css`, `app.js` | The page and its controls. |
| `printer.js` | Web Serial transport and the print flow (status check, job, wait for completion). |
| `cube_web.py` | The Python functions the page calls: render a label, build and read printer bytes. |
| `serve.py` | Builds the site and serves it on this computer and the local network (`run_web.bat` runs it). |
| `build.py` | Packs the page, the needed `core/` modules, `cube_web.py` and the fonts into `web/dist/`. |
| `fonts/` | Arimo, an Arial-compatible font under the SIL Open Font License (`fonts/OFL.txt`). Browsers can't hand system fonts to Python, so the app ships its own; **Add font** loads more. |

The printer bytes come from `core/protocol.py`, which the desktop driver (`core/printer.py`)
uses too.

## Tests

- `python -m unittest tests.test_web_bridge` (from the repository root) checks `cube_web.py`
  on CPython, including that a web print job is byte-for-byte the same as the desktop driver's.
- `npm install && npm test` (from `web/`) runs `printer.js` against the real Python core in
  Pyodide under Node, with a fake serial port playing the printer.
