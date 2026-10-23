#!/usr/bin/env python3
"""
Printer driver and communication manager for Brother PT-P300BT.
Supports both physical Bluetooth serial connections and simulated virtual mode.
"""

import time
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
import serial
from serial.tools import list_ports

from core import protocol
from core.ptstatus import PrinterStatus, StatusRegister, parse_printer_status
from core.specs import PRINTHEAD_DOTS, format_tape_width, tape_width_from_status


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


class PrinterBusyError(RuntimeError):
    """Raised when another job is already using the printer's serial port."""


_port_locks: Dict[str, threading.Lock] = {}
_port_locks_guard = threading.Lock()


def _get_port_lock(port: str) -> threading.Lock:
    """Returns the process-wide lock that serializes access to one serial port."""
    key = (port or "").upper()
    with _port_locks_guard:
        lock = _port_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _port_locks[key] = lock
        return lock


class BrotherPrinter:
    """Manages serial communication with a physical Brother PT-P300BT label printer."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._lock = _get_port_lock(port)

    def _acquire(self, wait_sec: float) -> None:
        if wait_sec <= 0:
            acquired = self._lock.acquire(blocking=False)
        else:
            acquired = self._lock.acquire(timeout=wait_sec)
        if not acquired:
            raise PrinterBusyError(f"Printer on {self.port} is busy with another job.")

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
        """Resets the printer and closes the serial connection."""
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
        self._ser.write(protocol.init_sequence())
        self._ser.flush()

    def _query_status(self) -> PrinterStatus:
        """Resets the printer and reads one status packet. Requires an open connection."""
        self.reset()
        self._ser.write(protocol.status_request())
        self._ser.flush()
        raw_bytes = self._ser.read(protocol.STATUS_PACKET_SIZE)
        if len(raw_bytes) != protocol.STATUS_PACKET_SIZE:
            raise TimeoutError(
                f"Expected 32 bytes status response, received {len(raw_bytes)} bytes. "
                "Is the printer switched on and paired?"
            )
        return protocol.parse_status(raw_bytes)

    def _wait_for_completion(self, timeout_sec: float, fallback: PrinterStatus) -> PrinterStatus:
        """
        Reads status packets until the printer reports completion or an error.
        Phase-change and notification packets are skipped. Raises on a reported error;
        returns the last status with completion_confirmed=False if the timeout expires.
        """
        deadline = time.monotonic() + timeout_sec
        last_status = fallback
        while time.monotonic() < deadline:
            raw = self._ser.read(protocol.STATUS_PACKET_SIZE)
            if len(raw) != protocol.STATUS_PACKET_SIZE:
                continue
            try:
                status = protocol.parse_status(raw)
            except ValueError:
                continue
            last_status = status
            protocol.raise_if_error(status)
            if protocol.is_completed(status):
                return status
        last_status.completion_confirmed = False
        return last_status

    def _completion_timeout(self, raster_lines: int) -> float:
        return protocol.completion_timeout(raster_lines)

    def get_status(self) -> PrinterStatus:
        """Queries the 32-byte hardware status register from the printer."""
        # Status queries never wait: if a print is running, report busy instead of blocking it
        self._acquire(wait_sec=0)
        try:
            was_open = self._ser is not None and self._ser.is_open
            if not was_open:
                self.connect()
            try:
                return self._query_status()
            finally:
                if not was_open:
                    self.disconnect()
        finally:
            self._lock.release()

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
        self._ser.write(protocol.job_configuration(
            raster_lines, tape_dim, compress=compress, chaining=chaining,
            auto_cut=auto_cut, end_margin=end_margin,
        ))
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
        required_tape_width_mm: Optional[float] = None,
    ) -> PrinterStatus:
        """
        Executes a complete print job:
        1. Checks status (and the loaded tape width, if required_tape_width_mm is given)
        2. Configures media parameters
        3. Streams 128-dot raster lines
        4. Triggers print and waits for the printer to confirm completion
        """
        raster_lines = protocol.validate_raster(raster_data)
        chunk_size = protocol.LINE_BYTES

        self._acquire(wait_sec=5.0)
        try:
            if status_callback:
                status_callback("Connecting to printer...")
            self.connect()

            try:
                if status_callback:
                    status_callback("Querying printer status...")
                status = self._query_status()

                protocol.check_ready(status, required_tape_width_mm)

                if status_callback:
                    status_callback(f"Configuring printer ({raster_lines} lines)...")

                self.configure_printer(
                    raster_lines=raster_lines,
                    tape_dim=protocol.tape_dim(status),
                    compress=not nocomp,
                    chaining=no_feed,
                    auto_cut=auto_cut,
                    end_margin=end_margin,
                )

                # Stream raster lines (128 px = 16 bytes per line)
                if status_callback:
                    status_callback("Sending raster image data...")

                for i in range(0, len(raster_data), chunk_size):
                    self._ser.write(protocol.raster_line(raster_data[i : i + chunk_size], not nocomp))

                    chunk_idx = (i // chunk_size) + 1
                    if progress_callback and (chunk_idx % 5 == 0 or chunk_idx == raster_lines):
                        progress_callback(chunk_idx, raster_lines)

                self._ser.flush()

                if status_callback:
                    status_callback("Printing label...")

                # Send Print command
                self._ser.write(protocol.PRINT_COMMAND)
                self._ser.flush()

                final_status = self._wait_for_completion(
                    self._completion_timeout(raster_lines), fallback=status
                )

                if status_callback:
                    if final_status.completion_confirmed:
                        status_callback("Print complete!")
                    else:
                        status_callback("Print sent, but the printer did not confirm completion.")

                return final_status
            finally:
                self.disconnect()
        finally:
            self._lock.release()

    def feed_tape(
        self,
        length_mm: float = 25.0,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> PrinterStatus:
        """Advances tape by length_mm so the label emerges past the manual cutter blade."""
        self._acquire(wait_sec=5.0)
        try:
            if status_callback:
                status_callback("Connecting to printer to feed tape...")
            self.connect()
            try:
                if status_callback:
                    status_callback("Checking printer status...")
                status = self._query_status()

                protocol.check_ready(status)

                dots_to_feed = protocol.feed_dots(length_mm)

                if status_callback:
                    status_callback(f"Feeding {length_mm:.1f}mm of tape...")

                self.configure_printer(
                    raster_lines=dots_to_feed,
                    tape_dim=protocol.tape_dim(status),
                    compress=False,
                    chaining=False,
                    auto_cut=False,
                    end_margin=0,
                )

                # Send zerofill lines to advance tape
                self._ser.write(protocol.raster_lines(bytes(protocol.LINE_BYTES * dots_to_feed), compress=False))
                self._ser.flush()

                self._ser.write(protocol.PRINT_COMMAND)
                self._ser.flush()

                final_status = self._wait_for_completion(
                    self._completion_timeout(dots_to_feed), fallback=status
                )

                if status_callback:
                    status_callback("Tape fed successfully to cutter!")
                return final_status
            finally:
                self.disconnect()
        finally:
            self._lock.release()


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
        required_tape_width_mm: Optional[float] = None,
    ) -> PrinterStatus:
        """Simulates printing with realistic progress feedback."""
        if status_callback:
            status_callback("[Virtual] Connecting to simulated PT-P300BT...")
        time.sleep(0.3)

        status = self.get_status()
        if required_tape_width_mm is not None:
            loaded = tape_width_from_status(status.tape_width_mm)
            if loaded != float(required_tape_width_mm):
                raise RuntimeError(
                    f"This label needs {format_tape_width(required_tape_width_mm)} tape; "
                    f"{format_tape_width(loaded)} is loaded."
                )

        chunk_size = PRINTHEAD_DOTS // 8
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

        return status

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
