# Brother P-touch Cube (PT-P300BT) Label Studio

A modern, responsive desktop GUI application for printing to Brother P-touch Cube PT-P300BT label printers over Bluetooth from a computer.

Based on the [Ircama/PT-P300BT](https://github.com/Ircama/PT-P300BT) Python utility.

---

## ✨ Features

- **Batch Queue System & Tape Waste Reduction**:
  - Queue multiple label designs and print them as a single continuous chain
  - Automatically eliminates the ~25mm wasted tape between consecutive prints
  - Saves $(N - 1) \times 25.0\text{ mm}$ of expensive TZe tape (e.g. 5 labels saves 100mm / 4 inches of tape!)
  - Reorder, edit, or delete queued items with live batch length and tape savings counters
  - WYSIWYG batch preview of the full stitched tape strip
- **Cut Guide Lines**:
  - Printed cut guide lines (dotted, tick marks, solid) placed precisely between queued labels and at margins
  - Easy manual cutting with scissors without guesswork
- **Manual Tape Feed**:
  - Feed 25 mm of tape past the cutter blade from the "•••" menu next to Print
- **Real-Time WYSIWYG Tape Preview**: Interactive canvas that accurately previews the printed label on realistic tape cartridge simulations (White, Yellow, Red, Blue, Green, Black, Clear, Gold).
- **Auto-Fit Font Sizing**: Automatically maximizes text font size to fill the tape printable height (64 dots for 12mm tape) while respecting multi-line baselines.
- **Rich Typography**:
  - System font discoverer (Arial, Segoe UI, Consolas, Calibri, Impact, etc.)
  - Custom `.ttf` / `.otf` font file importer
  - Font scaling, line spacing multiplier, text alignment (Left, Center, Right), text outline/stroke
- **QR Codes**:
  - Generate crisp QR codes for URLs, inventory IDs, or plain text
  - Dedicated **WiFi Guest Login** QR code generator (`WIFI:S:...;P:...;;`)
  - Adjustable position (left/right) and scale
- **Image & Icon Merging**:
  - Import custom graphics (PNG, JPG, BMP)
  - Automatic whitespace background cropping and contrast binarization slider
- **Physical Metrics & Estimations**:
  - Exact printed label length in mm, cm, and inches
  - Total tape used (including lead-in margin)
  - Estimated print duration in seconds
  - Tape saved badge in queue
  - Maximum tape length warnings (>49.9 cm)
- **Hardware Telemetry & Connection Management**:
  - Auto-scans Bluetooth serial COM ports
  - Real-time battery status (Full, Half, Low, AC Adapter)
  - Tape width detection (12mm, 9mm, 6mm, 3.5mm) and loaded tape color detection
  - Hardware error reporting (Cover open, cutter jammed, low battery, tape out)
- **Built-in Virtual / Simulation Mode**:
  - Test and design labels even when the printer is turned off or not yet paired
  - Full simulated raster streaming and progress bar feedback
- **Template Library**:
  - Ready-made text label starting points in the **Templates** view: *Storage Box / Shelf*, *Cable Wrap / Wire Flag*, *WiFi Guest QR Login*, *Kitchen Spice Jar*, *Equipment Asset Tag*, *Name Badge / Shipping*
  - Save the current label as a JSON template and open it again later
- **📚 Built-in Icon Library & Gallery Browser**:
  - Over 30+ curated monochrome vector/line-art icons across 5 dedicated categories: *Fasteners*, *Engineering*, *Electronics*, *Tools*, and *Symbols*, plus persistent *My Icons*
  - Fast instant keyword search (Torx, Bearing, Gear, Socket, Wrench, Fuse, etc.) and category filtering
  - One-click icon assignment for both text labels and bin labels
  - Persistent user icon storage in `~/.printlabel/icons/` with direct "Open Custom Folder" integration
- **✨ Gemini AI Wireframe Generator & Line-Art Studio**:
  - **Photo to Technical Wireframe**: Convert photos of workshop items/parts into pure black-and-white vector wireframes using Google Gemini multimodal AI (`gemini-2.5-flash-image`, `gemini-3.1-flash-image`)
  - **Text Prompt to Wireframe**: Generate clean technical silhouettes directly from descriptive text prompts
  - **Clean & Import Tool**: Auto-crops whitespace borders, removes background, strictly binarizes to 1-bit thermal monochrome, and centers imported web images or screenshots
  - **Reverse / Invert Colors**: 1-click black-and-white color flip to instantly correct inverted or white-on-black graphics
  - **Thermal Printhead Line-Thickening**: Morphological line thickness controls (Normal, Bold, Extra Bold, Heavy) optimized specifically for Brother thermal printheads (64-dot height) so strokes never fade or break
- **🔩 Bin Labels for Hardware Storage**:
  - A dedicated **Bin label** editor (12 mm tape) with two kinds of label, picked under *Label for*:
    - **Fasteners**: a solid black size block (`M3`, `M5`, or your own text such as `1/4"` or `#6-32`), a free-text name (with suggestions like *Screws*, *Nuts*, *Washers*, *Bolts*), **One / Two / Four** bins with length boxes laid out like the bins, and a drive icon
    - **Parts**: a name banner, part number, an optional note and an icon (*Bearing*, *WAGO*, *Fuse*, or your own)
  - Fields are listed in the same order they appear on the printed label
  - Plain numbers in the length boxes print as `x30`; anything else prints as typed
  - **Drive** dropdown: *Allen*, *Hex*, *PH*, *PZ*, *Torx*, *Slot* or *None*, drawn from the icon library; tick **Simple icon** for bold drawn shapes instead
  - **Library…** and **File…** buttons next to the drive or part icon let you use your own icon (the dropdown then reads *Custom*)
  - Set the **Label length** in mm to match your bin (38 mm by default, 10 mm minimum)
  - The last bin label you made is remembered between sessions, so the next one starts from it
  - Bin labels go into the same zero-waste batch print queue as text labels
- **Exporting**:
  - Export high-resolution PNGs of your label designs

---

## 🚀 Quick Start

### 1. Requirements

Ensure you have Python 3.10+ installed. Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 2. Launch the Application

Double-click `run.bat` (on Windows) or run:

```bash
python main.py
```

---

## 🔌 Connecting Your PT-P300BT

1. **Turn on the printer** (press the power button; the LED should turn green).
2. **Pair via Windows Bluetooth**:
   - Go to Windows Settings → *Bluetooth & devices* → *Add device*.
   - Select your **PT-P300BT** printer and pair it.
   - Windows will create an outgoing Serial Port (COMx).
3. **In the App**:
   - Click the **printer chip** at the top right to open the printer panel.
   - Turn off **Simulation** if it is on, and choose **Scan ports**.
   - Select your printer's COM port (e.g. `COM3` or `COM7`).
   - Choose **Check status**; the chip shows the model, loaded tape and battery.
   - Click **Print** (or press `Ctrl+P`).

### Finding your way around

The window has three parts: a **left rail** for switching views, the **tape preview** in the middle, and a **header** with the **printer chip** at the top right.

- **Printer chip**: shows whether the printer is ready, has a problem, is connecting, is offline, or is in simulation, along with the model, loaded tape and battery. Click it to open the printer panel with the port list, **Scan ports**, **Check status** and the **Simulation** switch.
- **Left rail**:
  - **Text label**: type your text under the preview; font, QR code, icon, length and advanced options are in the panel on the right.
  - **Bin label**: the bin label editor for fasteners and parts (see *Bin Labels* above).
  - **Queue**: labels you add with **Add to queue** (`Ctrl+Enter`) print as one strip, saving about 25 mm of tape per extra label.
  - **Templates**: ready-made starting points, plus saving and opening your own templates.
  - **Settings** (at the bottom of the rail): bin label language (English or Swedish), Gemini API key, and simulation mode.
- **Print** is the main button below the preview, next to **Add to queue**. The "•••" menu beside it has Export PNG (`Ctrl+S`) and Feed tape.

---

## 📁 Project Structure

```
printlabel-ui/
├── core/
│   ├── ptcbp.py              # PTCBP protocol serializer & TIFF PackBits RLE codec
│   ├── ptstatus.py           # 32-byte printer status register unpacker & tables
│   ├── font_manager.py       # Windows font registry discovery & TTF loader
│   ├── label_renderer.py     # PIL rendering engine, auto-fit, QR codes & rasterization
│   ├── inventory_renderer.py # Bin label procedural vector label generator
│   ├── label_language.py     # Bin label text in English / Swedish and the default bin labels
│   ├── specs.py              # Dot pitch, tape sizes and other printer constants
│   ├── icon_manager.py       # Curated icon library manager, search index & user storage
│   ├── ai_generator.py       # Gemini AI multimodal wireframe & thermal post-processing engine
│   ├── config.py             # User persistent config (API keys, preferences)
│   ├── printer.py            # Thread-safe serial communication driver & virtual mock
│   └── cli.py                # Command-line interface driver
├── ui/
│   ├── app.py                # Main window: rail, views, text label panel, queue & printing
│   ├── widgets.py            # Collapsible sections, labelled sliders and the left rail
│   ├── printer_chip.py       # Header printer chip and its connection panel
│   ├── templates_view.py     # Template cards with preview pictures
│   ├── settings_view.py      # Settings: label language, Gemini key, simulation
│   ├── tape_preview.py       # Preview canvas with tape strip, zoom & metrics
│   ├── inventory_tab.py      # Bin label editor
│   ├── icon_browser.py       # Icon Library modal gallery browser & search dialog
│   ├── ai_generator_dialog.py# Gemini AI wireframe & Clean and Import dialog
│   └── templates.py          # Built-in presets & JSON template import/export
├── assets/
│   ├── icons/                # Curated monochrome icon library (Fasteners, Engineering, etc.)
│   └── icon.ico              # Application desktop icon
├── tests/
│   ├── test_all.py           # Core printing & serialization unit tests
│   ├── test_inventory.py     # Hardware inventory procedural engine unit tests
│   ├── test_icons_and_ai.py  # Icon library discovery, search & AI processing tests
│   ├── test_gui_inventory.py # Headless GUI test for the bin label editor
│   └── test_gui_queue.py     # Headless GUI test for text labels, the queue and views
├── main.py                   # Main entry point (launches GUI or CLI depending on args)
├── build.py                  # Automated PyInstaller build script for single portable .exe
├── printlabel.spec           # PyInstaller spec bundling all assets & dependencies
├── run.bat                   # Windows one-click launcher
└── requirements.txt          # Python dependencies
```

---

## 📦 Standalone Portable Executable (.exe)

`PrintLabel` can be compiled into a single, completely self-contained portable `.exe` that runs on any 64-bit Windows PC with **no Python installation required**:

- **Pre-compiled Single Executable**: `dist\PrintLabel.exe` (~20 MB)
- **GUI Mode**: Double-click `PrintLabel.exe` or run without arguments to launch the modern desktop UI.
- **CLI Mode**: Run from Command Prompt or PowerShell with standard `printlabel` arguments:
  ```powershell
  # Show command-line help
  PrintLabel.exe --help

  # List available COM ports & detected Brother printers
  PrintLabel.exe --ports

  # Check printer telemetry (battery, loaded tape width & color)
  PrintLabel.exe COM4 --status

  # Print a label directly from the terminal
  PrintLabel.exe COM4 "Storage Box #42"

  # Feed tape by 25mm
  PrintLabel.exe COM4 --feed

  # Name the port with --port, or try a label without hardware using --virtual
  PrintLabel.exe --port COM4 "Storage Box #42"
  PrintLabel.exe --virtual "Test Label" --preview --save-png test.png
  ```

### 🔨 Compiling From Source
To compile your own portable single `.exe` file:
1. Double-click `build.bat` **or** run:
   ```powershell
   python build.py
   ```
2. The executable will be generated at `dist\PrintLabel.exe`.

---

## 🧪 Testing

Run the automated test suite:

```bash
python -m unittest discover tests
```

The suite also runs on macOS and Linux. There, fonts are found in the standard font folders (falling back to Pillow's built-in font), and the GUI tests are skipped when Python has no tkinter.
