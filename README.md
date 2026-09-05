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
- **Manual Tape Feed (`✂ Feed Tape`)**:
  - 1-click on-demand tape advance (25mm) to feed printed tape past the cutter blade
- **Real-Time WYSIWYG Tape Preview**: Interactive canvas that accurately previews the printed label on realistic tape cartridge simulations (White, Yellow, Red, Blue, Green, Black, Clear, Gold).
- **Auto-Fit Font Sizing**: Automatically maximizes text font size to fill the tape printable height (64 dots for 12mm tape) while respecting multi-line baselines.
- **Rich Typography**:
  - System font discoverer (Arial, Segoe UI, Consolas, Calibri, Impact, etc.)
  - Custom `.ttf` / `.otf` font file importer
  - Font scaling, line spacing multiplier, text alignment (Left, Center, Right), text outline/stroke
- **QR Code & Barcode Integration**:
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
  - 1-click presets: *Storage Box*, *Cable Wrap / Flag*, *WiFi Guest QR*, *Kitchen Spice Jar*, *Asset Tag*, *Name Badge*
- **🔩 Hardware & Bins Inventory Design System (V2)**:
  - Professional procedural thermal label generator built according to the modular hardware inventory design standard
  - **Archetype A (Threaded Fasteners)**: Solid black inverted size anchor block (`M3`, `M5`), upper category header (`SKRUV`, `MUTTER`, `BRICKOR`), 4 compartment modes (Single Size, 2-Bin Dual, 4-Bin 2×2 Grid, Assortment Text), and tool drive badges with geometric vector icons (`⬢` internal hex, `⬡` external wrench, `◉` washer, `✶` Torx, `✚` Phillips)
  - **Archetype B (Discrete Components & Electrical)**: Inverted 38% category banner strip, spacious spec & rating zone, and dedicated 25% square right icon frame (`◎` ball bearing, `⧉` WAGO splicing clip, `⊷` inline fuse)
  - **8 Pre-loaded Catalog Presets**: Instant loading for standard workshop drawer configs (DIN 912, countersunk DIN 7991, hex nuts DIN 934, washers DIN 125, 608ZZ bearings, WAGO 221, inline fuses)
  - Seamless integration with the zero-waste batch print queue
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
   - Uncheck **Simulation Mode** in the top bar.
   - Click the **🔄** button to scan ports.
   - Select your printer's COM port (e.g. `COM3` or `COM7`).
   - Click **Check Status** to verify connection and read tape details.
   - Click **PRINT LABEL** (or press `Ctrl+P`) to print!

---

## 📁 Project Structure

```
printlabel-ui/
├── core/
│   ├── ptcbp.py           # PTCBP protocol serializer & TIFF PackBits RLE codec
│   ├── ptstatus.py        # 32-byte printer status register unpacker & tables
│   ├── font_manager.py    # Windows font registry discovery & TTF loader
│   ├── label_renderer.py  # PIL rendering engine, auto-fit, QR codes & rasterization
│   └── printer.py         # Thread-safe serial communication driver & virtual mock
├── ui/
│   ├── app.py             # CustomTkinter main application window & event wiring
│   ├── tape_preview.py    # Interactive WYSIWYG canvas widget with zoom & metrics
│   └── templates.py       # Built-in presets & JSON template import/export
├── tests/
│   └── test_all.py        # Automated test suite (14 unit tests)
├── assets/                # Sample label outputs & icons
├── main.py                # Main launch script
├── run.bat                # Windows one-click launcher
└── requirements.txt       # Dependencies
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
