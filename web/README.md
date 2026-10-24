# Cube Labeler web app (2.0, in progress)

A browser version of Cube Labeler that prints to the PT-P300BT over Bluetooth with the
[Web Serial API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API). It runs
the same Python core as the desktop app inside the browser with [Pyodide](https://pyodide.org),
so labels and printer bytes come out exactly the same.

It is becoming the main way to use Cube Labeler (version 2.0). Done so far: the app shell
(tabs on a phone, a sidebar on a wide screen), text labels with the styling toolbar, fonts,
frames, QR codes (with a Wi-Fi helper), a picture, tape width, length and the advanced
settings, the tape and print-dot preview, the printer panel (connect, status, feed tape),
saving the label as a picture, and settings. Bin labels (fasteners and parts, with their
drive and part icons or your own picture) and the print queue (one strip with cut lines,
reorder, edit, remove) are in too. The label, queue, settings and added fonts are kept in the
browser, and after the first visit the app also starts offline. Icons, templates, backups and
AI icons follow.

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

## Hosting with Docker

Every release tag (`v1.5.0` and so on) makes GitHub Actions build a Docker image and publish
it as `ghcr.io/mctobe/cube-labeler-web` (for amd64 and arm64), tagged `latest`, `1.5.0` and
`1.5`. You can also run the "Publish Web Image" workflow by hand from the Actions tab; that
image only gets a commit tag such as `sha-4c256cc`, so `latest` always means the newest release. The image serves
the site with nginx on port 80. Web Serial needs HTTPS, so put it behind a reverse proxy that
handles TLS, such as Nginx Proxy Manager.

With Dockge (or plain Docker Compose), create a stack with this compose file:

```yaml
services:
  cube-labeler-web:
    image: ghcr.io/mctobe/cube-labeler-web:latest
    ports:
      - "8080:80"
    restart: unless-stopped
```

Dockge's **Update** button pulls the newest `latest` image and restarts the container, so
after tagging a release you wait for the "Publish Web Image" workflow to finish and press
Update. To stay on one version instead, use a version tag such as `:1.5`.

**Private repository:** the image is a GitHub package with its own visibility, and a new one
starts out private. Either:

- make the package public (GitHub › your profile › Packages › cube-labeler-web › Package
  settings › Change visibility). The repository stays private. The image only holds the
  static site, which anyone opening the page downloads anyway. Or
- keep it private and log in once from the Docker that Dockge uses, with a personal access
  token (classic) that has only the `read:packages` scope:
  `docker exec -it dockge docker login ghcr.io -u <your GitHub user>`.

In Nginx Proxy Manager, add a proxy host for your domain (for example `print.tobezone.com`)
that forwards to `http://<docker host>:8080`, and turn on a Let's Encrypt certificate with
**Force SSL**. If Nginx Proxy Manager runs in Docker on the same host, you can instead put both
containers on one Docker network and forward to `http://cube-labeler-web:80`.

The server tells browsers to check for changes on every load, so phones pick up a new version
straight away. On Android, the first visit still needs Chrome's **Nearby devices** permission
and a force stop of Chrome, as described above; the Chrome flag for insecure origins is not
needed.

To build the image yourself from a checkout instead: `docker compose up -d --build`.

## How it fits together

| File | What it does |
|---|---|
| `index.html`, `style.css` | The page shell and its look (light and dark). |
| `js/main.js` | Navigation and pages. The pages live in `js/pages/`, shared controls in `js/ui.js`. |
| `js/app.js` | App state and actions: start Python, render, print, keep settings. |
| `js/worker.js`, `js/python.js` | Pyodide runs in a Web Worker so the page stays smooth; `python.js` calls into it. |
| `js/storage.js` | Keeps the label, settings and fonts in the browser's IndexedDB. |
| `sw.js` | Offline cache: the app's files, Pyodide, Pillow and qrcode. |
| `vendor/` | [Preact](https://preactjs.com) and [htm](https://github.com/developit/htm), copied in so there is no build step (see `vendor/README.md`). |
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
