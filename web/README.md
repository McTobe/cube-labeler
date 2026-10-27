# Cube Labeler web app

The browser version of Cube Labeler, and since 2.0 the main way to use it. It prints to the
PT-P300BT over Bluetooth with the
[Web Serial API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API) and runs
the same Python core as the desktop app inside the browser with [Pyodide](https://pyodide.org),
so labels and printer bytes come out exactly the same. The hosted version is at
<https://print.tobezone.com>.

It has everything the desktop app has:

- **Text labels** with the styling toolbar, fonts, frames, QR codes (with a Wi-Fi helper), a
  picture, tape width, length and the advanced settings, and a tape and print-dot preview.
- **Bin labels** for fasteners and parts, with their drive and part icons or your own picture.
- **The print queue**: several labels as one strip with cut lines; reorder, edit and remove.
- **The icon library** (search, categories, favourites, recently used, a print preview) and the
  **icon editor** (crop, drawing, silhouette or outline, darkness, thickness, clean-up, turn and
  mirror, pencil and eraser touch-ups, kept with the icon so it can be changed again). It can
  also have Gemini, OpenAI or OpenRouter redraw a photo as an icon, with your own API key, which
  stays in the browser and is sent only to that service.
- **Templates**, your own and the starting points, as the desktop app's `.json` files.
- **Backups** as `.cubebackup` files that restore here or in the desktop app, and **Google Drive
  sync** to your own Drive (the newest 3 backups are kept).
- **The printer panel**: connect, status, battery and tape, feed tape. Labels can also be saved
  as a picture.

The label, queue, icons, settings and added fonts are kept in the browser, and after the first
visit the app also starts offline. The layout is tabs on a phone and a sidebar on a wide screen,
in light and dark.

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

Every release tag (`v2.1.2` and so on) makes GitHub Actions build a Docker image and publish
it as `ghcr.io/mctobe/cube-labeler-web` (for amd64 and arm64), tagged `2.1.2`, `2.1`, `latest`
and `next` (`next` also follows pre-release tags such as `v2.2.0-beta.1`; `latest` doesn't). You can also run the "Publish Web Image" workflow by hand from the Actions tab; that
image only gets a commit tag such as `sha-4c256cc`, so `latest` always means the newest release. The image serves
the site with nginx on port 80. Web Serial needs HTTPS, so put it behind a reverse proxy that
handles TLS, such as Nginx Proxy Manager.

With Dockge (or plain Docker Compose), create a stack with this compose file:

```yaml
services:
  cube-labeler-web:
    image: ghcr.io/mctobe/cube-labeler-web:latest
    environment:
      # Optional, keeps people signed in to Google Drive (see below)
      GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET:-}
      PUBLIC_URL: ${PUBLIC_URL:-}
    ports:
      - "8080:80"
    restart: unless-stopped
```

Dockge's **Update** button pulls the newest `latest` image and restarts the container, so
after tagging a release you wait for the "Publish Web Image" workflow to finish and press
Update. To stay on one version instead, use a version tag such as `:2.1`.

**Private package:** the image is a GitHub package with its own visibility, separate from the
repository's, and a package made from a private repository starts out private. Either:

- make the package public (GitHub › your profile › Packages › cube-labeler-web › Package
  settings › Change visibility). The image only holds the
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

**Staying signed in to Google Drive:** set `GOOGLE_CLIENT_SECRET` and `PUBLIC_URL` on the
container (in Dockge, put the secret in the stack's **.env** box), and people sign in once per
device instead of clicking Continue every hour. The
image runs a small helper beside nginx for it. See [docs/google-sign-in.md](../docs/google-sign-in.md)
for the Google Console, Dockge and consent screen steps.

To build the image yourself from a checkout instead: `docker compose up -d --build`.

## How it fits together

| File | What it does |
|---|---|
| `index.html`, `style.css` | The page shell and its look (light and dark). |
| `js/main.js` | Navigation and pages. The pages live in `js/pages/`, shared controls in `js/ui.js`. |
| `js/app.js` | App state and actions: start Python, render, print, keep settings. |
| `js/worker.js`, `js/python.js` | Pyodide runs in a Web Worker so the page stays smooth; `python.js` calls into it. |
| `js/library.js` | The icon library: built-in icons from `icons/library.json` (made by `build.py`) and your own icons, with the desktop app's keys so backups move between the two. |
| `js/storage.js` | Keeps the label, settings and fonts in the browser's IndexedDB. |
| `sw.js` | Offline cache: the app's files, Pyodide, Pillow and qrcode. |
| `vendor/` | [Preact](https://preactjs.com) and [htm](https://github.com/developit/htm), copied in so there is no build step (see `vendor/README.md`). |
| `printer.js` | Web Serial transport and the print flow (status check, job, wait for completion). |
| `cube_web.py` | The Python functions the page calls: render a label, build and read printer bytes. |
| `js/gdrive.js` | Google Drive sync: sign-in, the backups folder, upload and download. |
| `drive_auth.py` | The Docker image's sign-in helper, which keeps people signed in to Google Drive (see `docs/google-sign-in.md`). |
| `about.html`, `privacy.html` | The About page (a plain page that explains the app, the homepage on Google's consent screen) and the privacy policy. |
| `docker/` | The Docker image's nginx config and the script that starts the sign-in helper. |
| `js/version.js` | The version number shown in Settings (`APP_VERSION`), bumped for each release. |
| `serve.py` | Builds the site and serves it on this computer and the local network (`run_web.bat` runs it). |
| `build.py` | Packs the page, the needed `core/` modules, `cube_web.py`, the fonts and the icons into `web/dist/`; the app icons are made from `assets/icon.png`. |
| `fonts/` | Fonts under the SIL Open Font License: Arimo (Arial-compatible; Medium is the bin label font) plus Atkinson Hyperlegible, Barlow Condensed, Inter, JetBrains Mono, Lexend, Nunito and Zilla Slab, each with its licence file. Browsers can't hand system fonts to Python, so the app ships its own; **Add font** loads more. |

The printer bytes come from `core/protocol.py`, which the desktop driver (`core/printer.py`)
uses too.

## Tests

- `python -m unittest tests.test_web_bridge` (from the repository root) checks `cube_web.py`
  on CPython, including that a web print job is byte-for-byte the same as the desktop driver's.
- `python -m unittest tests.test_drive_auth` checks the sign-in helper against a pretend Google.
- `npm install && npm test` (from `web/`) runs `printer.js` against the real Python core in
  Pyodide under Node, with a fake serial port playing the printer.
