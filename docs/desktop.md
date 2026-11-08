# Cube Labeler desktop app (legacy)

> **The Windows desktop app is no longer developed.** Its last version is **2.4.0**, and it gets no new features or fixes. Cube Labeler lives on as a web app at **<https://print.tobezone.com>**, which runs in Chrome or Edge on Android, Windows, macOS and Linux, needs nothing installed and has more kinds of label than the desktop app. See the [main README](../README.md) to get started.

The desktop app is a single portable `CubeLabeler.exe` for 64-bit Windows 10 or 11 with Bluetooth. It keeps working with the printer, and its `.cubebackup` files restore in the web version, so you can move your icons, templates and settings across (Settings → Backups).

## Download

**[Download CubeLabeler.exe (v2.4.0)](https://github.com/McTobe/cube-labeler/releases/download/v2.4.0/CubeLabeler.exe)** · [release page](https://github.com/McTobe/cube-labeler/releases/tag/v2.4.0) · [source code at v2.4.0](https://github.com/McTobe/cube-labeler/tree/v2.4.0)

Put it anywhere you like and double-click it. There is nothing to install. Windows SmartScreen may warn you the first time because the file is not code-signed. Choose **More info**, then **Run anyway**.

## Connecting the printer

1. Turn the printer on. The power LED turns green.
2. In Windows, open **Settings → Bluetooth & devices → Add device**, choose **Bluetooth** and pick **PT-P300BT**. Windows creates a serial (COM) port for it.
3. In Cube Labeler, click the **printer chip** at the top right. Turn **Simulation** off, choose **Scan ports** and select the printer's port (for example `COM3`).
4. Choose **Check status**. The chip shows the model, loaded tape and battery when the printer is ready.

## Usage

The window has a **left rail** for switching views, the **tape preview** in the middle and the **printer chip** at the top right.

| View | What it's for |
|---|---|
| **Text label** | Type text under the preview. Font, QR code, icon, length and advanced options are in the panel on the right. |
| **Bin label** | Labels for fastener or parts bins. Pick *Fasteners* or *Parts* under *Label for*; fields are listed in the order they appear on the label. |
| **Queue** | Labels added with **Add to queue** print as one strip. Reorder, edit or remove them before printing. |
| **Templates** | Ready-made labels and your own saved templates. |
| **Icons** | The icon library: browse, search, import, make, edit and back up icons. Your own icons are in `~/.printlabel/icons/`. |
| **Settings** | Bin label language, AI service (Gemini, OpenAI or OpenRouter) with its API key and model, backups (including automatic backups to a folder that Google Drive, OneDrive or Dropbox syncs) and simulation mode. |

Label text uses the same style markers as the web version (`**bold**`, `[3.5mm] `, `---` and so on; see the [main README](../README.md#styling-label-text)). The preview can show the whole label (**Fit**) or zoom to 100–300%. The **•••** menu next to **Print** has *Export PNG* and *Feed tape*.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+P` | Print |
| `Ctrl+Enter` | Add to queue |
| `Ctrl+S` | Export PNG |
| `Ctrl+B`, `Ctrl+I`, `Ctrl+U` | Bold, italic, underline in the label text |
| `Esc` | Close the printer panel |

### Command line

Run `CubeLabeler.exe` with arguments to use it without the window:

```powershell
CubeLabeler.exe --ports                       # list serial ports and find the printer
CubeLabeler.exe COM4 --status                 # battery, tape and errors
CubeLabeler.exe COM4 "Storage Box #42"        # print a label
CubeLabeler.exe COM4 "Line one\nLine two"     # two-line label
CubeLabeler.exe COM4 --feed                   # feed 25 mm of tape
CubeLabeler.exe --virtual "Test" --preview --save-png test.png  # no printer needed
```

`CubeLabeler.exe --help` lists every option, including `--font`, `--font-size`, `--width`, `--image`, `--no-cut-guide` and `--auto-cut`.

## Building it from source

The desktop code was removed from the main branch after 2.4.0. It is kept at the `v2.4.0` tag:

```powershell
git clone --branch v2.4.0 https://github.com/McTobe/cube-labeler.git
cd cube-labeler
pip install -r requirements.txt -c constraints.txt
python main.py                                 # run the app
pip install pyinstaller -c constraints.txt
python build.py                                # build dist\CubeLabeler.exe
```

Issues and pull requests for the desktop app are no longer taken.
