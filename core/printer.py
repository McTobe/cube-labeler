#!/usr/bin/env python3
"""
Printer driver and communication manager for Brother PT-P300BT.
Supports both physical Bluetooth serial connections and simulated virtual mode.
"""

import time
import threading
from typing import Callable, List, Optional, Tuple
import serial
from serial.tools import list_ports

from core.ptcbp import (
    serialize_control,
    serialize_control_obj,
    serialize_data,
    CommandSet,
    PrintParameters,
    PrintParameterField,
    PageMode,
    PageModeAdvanced,
    CompressionType,
)
from core.ptstatus import (
    StatusRegister,
    PrinterStatus,
    unpack_status,
    parse_printer_status,
)


from dataclasses import dataclass


@dataclass
class PortOption:
    device: str
    label: str
    is_brother: bool
    is_incoming: bool
    is_preferred: bool

    def __iter__(self):
        # Support tuple unpacking (device, label) for backwards compatibility
        return iter((self.device, self.label))


def list_serial_ports() -> List[PortOption]:
    """
    Returns list of available serial ports classified by role (Brother, Incoming, etc.)
    sorted with preferred printer ports first.
    """
    ports = []
    for p in list_ports.comports():
        hwid = (p.hwid or "").upper()
        desc = (p.description or "").lower()

        # Detect Brother printer Vendor ID (0430 / VID&00020430) or naming
        is_brother = ("0430" in hwid) or ("brother" in desc) or ("pt-" in desc) or ("cube" in desc)
        # Detect Bluetooth Incoming port (waiting for incoming connection)
        is_incoming = ("LOCALMFG" in hwid) or ("000000000000" in hwid) or ("incoming" in desc)

        if is_brother and not is_incoming:
            label = f"{p.device} [Brother PT-P300BT]"
            is_preferred = True
        elif is_brother and is_incoming:
            label = f"{p.device} [Brother Incoming Port]"
            is_preferred = False
        elif is_incoming:
            label = f"{p.device} [Bluetooth Incoming - Listen]"
            is_preferred = False
        else:
            label = f"{p.device} ({p.description or 'Serial Port'})"
            is_preferred = False

        ports.append(PortOption(
            device=p.device,
            label=label,
            is_brother=is_brother,
            is_incoming=is_incoming,
            is_preferred=is_preferred,
        ))

    # Sort so preferred Brother ports appear first, then outgoing, then incoming
    def _sort_key(item: PortOption):
        if item.is_preferred:
            return (0, item.device)
        elif not item.is_incoming:
            return (1, item.device)
        else:
            return (2, item.device)

    ports.sort(key=_sort_key)
    return ports


class BrotherPrinter:
    """Manages serial communication with a physical Brother PT-P300BT label printer."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None

    def connect(self) -> None:
        """Opens the serial connection, with 1 retry for Bluetooth sleep wakeup."""
        if self._ser and self._ser.is_open:
            return
        last_err = None
        for attempt in range(2):
            try:
                self._ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=self.timeout)
                return
            except (serial.SerialException, OSError) as e:
                last_err = e
                if attempt == 0:
                    time.sleep(1.0)
        if last_err:
            raise last_err

    def disconnect(self) -> None:
        """Closes the serial connection."""
        if self._ser and self._ser.is_open:
            try:
                self.reset()
            except Exception:
                pass
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def reset(self) -> None:
        """Flushes buffer and initializes printer into PTCBP raster graphics mode."""
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Printer is not connected.")
        # 64 null bytes to flush print buffer
        self._ser.write(b"\x00" * 64)
        # ESC @ Initialize
        self._ser.write(serialize_control('reset'))
        # ESC i a 1 : Select PTCBP raster graphics command set
        self._ser.write(serialize_control('use_command_set', CommandSet.ptcbp))
        self._ser.flush()

    def get_status(self) -> PrinterStatus:
        """Queries the 32-byte hardware status register from the printer."""
        was_open = self._ser is not None and self._ser.is_open
        if not was_open:
            self.connect()

        try:
            self.reset()
            # ESC i S : Request status
            self._ser.write(serialize_control('get_status'))
            self._ser.flush()

            raw_bytes = self._ser.read(32)
            if len(raw_bytes) != 32:
                raise TimeoutError(f"Expected 32 bytes status response, received {len(raw_bytes)} bytes.")

            raw_reg = unpack_status(raw_bytes)
            return parse_printer_status(raw_reg)
        finally:
            if not was_open:
                self.disconnect()

    def configure_printer(
        self,
        raster_lines: int,
        tape_dim: Tuple[int, int, int],
        compress: bool = True,
        chaining: bool = False,
        auto_cut: bool = False,
        end_margin: int = 0,
    ) -> None:
        """Sends printer configuration packet (dimensions, margins, compression)."""
        type_, width, length = tape_dim

        # Set media parameters
        active_f = (
            PrintParameterField.width
            | PrintParameterField.quality
            | PrintParameterField.recovery
        )
        params = PrintParameters(
            active_fields=active_f,
            media_type=type_,
            width_mm=width,
            length_mm=length,
            length_px=raster_lines,
            is_follow_up=0,
            sbz=0,
        )
        self._ser.write(serialize_control_obj('set_print_parameters', params))

        # Advanced page mode (chaining)
        pm2 = 0
        if not chaining:
            pm2 |= PageModeAdvanced.no_page_chaining
        self._ser.write(serialize_control('set_page_mode_advanced', pm2))

        # Page mode (auto cut)
        pm = 0
        if auto_cut:
            pm |= PageMode.auto_cut
        self._ser.write(serialize_control('set_page_mode', pm))

        # Margin
        self._ser.write(serialize_control('set_page_margin', end_margin))

        # Compression mode: TIFF RLE
        ctype = CompressionType.rle if compress else CompressionType.none
        self._ser.write(serialize_control('compression', ctype))
        self._ser.flush()

    def print_raster_data(
        self,
        raster_data: bytes,
        no_feed: bool = False,
        auto_cut: bool = False,
        end_margin: int = 0,
        nocomp: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PrinterStatus:
        """
        Executes a complete print job:
        1. Checks status
        2. Configures media parameters
        3. Streams 128-dot raster lines
        4. Triggers print and returns final status
        """
        if status_callback:
            status_callback("Connecting to printer...")
        self.connect()

        try:
            if status_callback:
                status_callback("Querying printer status...")
            self.reset()
            self._ser.write(serialize_control('get_status'))
            self._ser.flush()
            initial_bytes = self._ser.read(32)
            if len(initial_bytes) != 32:
                raise RuntimeError("Failed to receive status from printer.")
            status = parse_printer_status(unpack_status(initial_bytes))

            if not status.is_ready:
                err_msg = ", ".join(status.errors) if status.errors else status.phase_name
                raise RuntimeError(f"Printer is not ready: {err_msg}")

            raster_lines = len(raster_data) // 16
            if status_callback:
                status_callback(f"Configuring printer ({raster_lines} lines)...")

            self.configure_printer(
                raster_lines=raster_lines,
                tape_dim=(
                    status.raw_status.tape_type,
                    status.raw_status.tape_width,
                    status.raw_status.tape_length,
                ),
                compress=not nocomp,
                chaining=no_feed,
                auto_cut=auto_cut,
                end_margin=end_margin,
            )

            # Stream raster lines (128 px = 16 bytes per line)
            chunk_size = 16
            zero_chunk = bytearray(b"\x00" * chunk_size)
            total_chunks = len(raster_data) // chunk_size

            if status_callback:
                status_callback("Sending raster image data...")

            for i in range(0, len(raster_data), chunk_size):
                chunk = raster_data[i : i + chunk_size]
                if chunk == zero_chunk:
                    line = serialize_control('zerofill')
                else:
                    line = serialize_data(chunk, 'none' if nocomp else 'rle')
                self._ser.write(line)

                chunk_idx = (i // chunk_size) + 1
                if progress_callback and (chunk_idx % 5 == 0 or chunk_idx == total_chunks):
                    progress_callback(chunk_idx, total_chunks)

            self._ser.flush()

            if status_callback:
                status_callback("Printing label...")

            # Send Print command
            self._ser.write(serialize_control('print'))
            self._ser.flush()

            # Read completion status
            done_bytes = self._ser.read(32)
            if len(done_bytes) == 32:
                final_status = parse_printer_status(unpack_status(done_bytes))
            else:
                final_status = status

            if status_callback:
                status_callback("Print complete!")

            return final_status
        finally:
            try:
                self.reset()
            except Exception:
                pass
            self.disconnect()

    def feed_tape(
        self,
        length_mm: float = 25.0,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PrinterStatus:
        """Advances tape by length_mm so the label emerges past the manual cutter blade."""
        if status_callback:
            status_callback("Connecting to printer to feed tape...")
        self.connect()
        try:
            if status_callback:
                status_callback("Checking printer status...")
            self.reset()
            self._ser.write(serialize_control('get_status'))
            self._ser.flush()
            raw_bytes = self._ser.read(32)
            if len(raw_bytes) != 32:
                raise RuntimeError("Failed to receive status from printer.")
            status = parse_printer_status(unpack_status(raw_bytes))

            # 0.149mm per dot -> dots needed for feed
            dots_to_feed = max(int(round(length_mm / 0.149)), 60)

            if status_callback:
                status_callback(f"Feeding {length_mm:.1f}mm of tape...")

            self.configure_printer(
                raster_lines=dots_to_feed,
                tape_dim=(
                    status.raw_status.tape_type,
                    status.raw_status.tape_width,
                    status.raw_status.tape_length,
                ),
                compress=False,
                chaining=False,
                auto_cut=False,
                end_margin=0,
            )

            # Send zerofill lines to advance tape
            zero_line = serialize_control('zerofill')
            for _ in range(dots_to_feed):
                self._ser.write(zero_line)
            self._ser.flush()

            self._ser.write(serialize_control('print'))
            self._ser.flush()

            done_bytes = self._ser.read(32)
            if len(done_bytes) == 32:
                final_status = parse_printer_status(unpack_status(done_bytes))
            else:
                final_status = status

            if status_callback:
                status_callback("Tape fed successfully to cutter!")
            return final_status
        finally:
            try:
                self.reset()
            except Exception:
                pass
            self.disconnect()


class MockBrotherPrinter:
    """Virtual / Simulated printer for testing, UI previewing, and development without hardware."""

    def __init__(self, port: str = "VIRTUAL_COM1"):
        self.port = port
        self.is_connected = False

    def connect(self) -> None:
        self.is_connected = True

    def disconnect(self) -> None:
        self.is_connected = False

    def reset(self) -> None:
        pass

    def get_status(self) -> PrinterStatus:
        """Returns realistic simulated status (PT-P300BT with 12mm White/Black tape, Battery full)."""
        reg = StatusRegister()
        reg.magic = b"\x80\x20B0"
        reg.model = 0x72  # PT-P300BT
        reg.country = 0x00
        reg._power = 0    # Battery full
        reg.err = 0       # No errors
        reg.tape_width = 12
        reg.tape_type = 0x01  # Laminated (TZexxx)
        reg.status_type = 0x00
        reg.phase_type = 0x00
        reg.phase = 0x0000
        reg.tape_bgcolor = 0x01  # White
        reg.tape_fgcolor = 0x08  # Black
        return parse_printer_status(reg)

    def print_raster_data(
        self,
        raster_data: bytes,
        no_feed: bool = False,
        auto_cut: bool = False,
        end_margin: int = 0,
        nocomp: bool = False,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PrinterStatus:
        """Simulates printing with realistic progress feedback."""
        if status_callback:
            status_callback("[Virtual] Connecting to simulated PT-P300BT...")
        time.sleep(0.3)

        chunk_size = 16
        total_chunks = max(len(raster_data) // chunk_size, 1)

        if status_callback:
            status_callback(f"[Virtual] Streaming {total_chunks} raster lines...")

        # Step through chunks smoothly
        steps = min(total_chunks, 40)
        for step in range(1, steps + 1):
            time.sleep(0.02)
            cur = int(step * (total_chunks / steps))
            if progress_callback:
                progress_callback(cur, total_chunks)

        if status_callback:
            status_callback("[Virtual] Thermal printhead active (simulated print)...")
        time.sleep(0.6)

        if status_callback:
            status_callback("[Virtual] Label printed successfully!")

        return self.get_status()

    def feed_tape(
        self,
        length_mm: float = 25.0,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PrinterStatus:
        """Simulates feeding tape."""
        if status_callback:
            status_callback(f"[Virtual] Feeding {length_mm:.1f}mm of tape...")
        time.sleep(0.4)
        if status_callback:
            status_callback("[Virtual] Tape fed successfully to cutter!")
        return self.get_status()
