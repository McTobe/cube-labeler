#!/usr/bin/env python3
"""
Unit and integration tests for Cube Labeler.
"""

import os
import sys
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Font shipped with the tests so font handling can be checked on any OS
TEST_FONTS_DIR = os.path.join(BASE_DIR, "tests", "fonts")

from core.ptcbp import (
    serialize_control,
    serialize_data,
    Opcode,
    CommandSet,
    _encode_rle,
    _decode_rle,
)
from core.ptstatus import (
    StatusRegister,
    unpack_status,
    parse_printer_status,
)
from core.font_manager import FontManager, font_manager
from core.label_renderer import LabelRenderer, LabelConfig
from core.printer import MockBrotherPrinter, list_serial_ports
from ui.templates import (
    BUILTIN_PRESETS,
    load_preset,
    export_config_to_json,
    import_config_from_json,
)


class TestPTCBP(unittest.TestCase):
    def test_packbits_roundtrip(self):
        sample = b"AAAAABBBBBCCCCCCDDDDDEEEEEFFFFFF1234567890\x00\x00\x00\x00"
        compressed = _encode_rle(sample)
        decompressed = _decode_rle(compressed)
        self.assertEqual(decompressed, sample)

    def test_serialize_reset_and_command_set(self):
        reset_bytes = serialize_control('reset')
        self.assertEqual(reset_bytes, b"\x1b@")

        cmd_set_bytes = serialize_control('use_command_set', CommandSet.ptcbp)
        self.assertEqual(cmd_set_bytes, b"\x1bia\x01")

    def test_serialize_zerofill_and_data(self):
        zf = serialize_control('zerofill')
        self.assertEqual(zf, b"Z")

        sample_data = bytes([0xFF] * 16)
        data_packet = serialize_data(sample_data, compress='none')
        self.assertTrue(data_packet.startswith(b"G"))


class TestPTStatus(unittest.TestCase):
    def test_status_unpacking(self):
        reg = StatusRegister()
        reg.magic = b"\x80\x20B0"
        reg.model = 0x72  # PT-P300BT
        reg.country = 0x00
        reg._power = 0    # Battery full
        reg.err = 0       # No errors
        reg.tape_width = 12
        reg.tape_type = 0x01  # Laminated
        reg.tape_bgcolor = 0x01  # White
        reg.tape_fgcolor = 0x08  # Black
        reg.status_type = 0x00
        reg.phase_type = 0x00
        reg.phase = 0x0000

        raw_bytes = bytes(reg)
        self.assertEqual(len(raw_bytes), 32)

        unpacked = unpack_status(raw_bytes)
        status = parse_printer_status(unpacked)

        self.assertEqual(status.model_name, "PT-P300BT")
        self.assertEqual(status.tape_width_mm, 12)
        self.assertEqual(status.bg_color_name, "White")
        self.assertEqual(status.fg_color_name, "Black")
        self.assertTrue(status.is_ready)
        self.assertTrue(status.tape_loaded)


def _font_manager_without_fonts():
    """A FontManager that found no installed fonts, like a bare Linux box."""
    mgr = object.__new__(FontManager)
    mgr._font_cache = {}
    mgr._loaded_fonts = {}
    return mgr


class TestFontManager(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Arial is only guaranteed on Windows")
    def test_font_discovery(self):
        names = font_manager.get_font_names()
        self.assertGreater(len(names), 0)
        self.assertIn("Arial", names)

    def test_font_dir_scan(self):
        mgr = _font_manager_without_fonts()
        mgr.scan_font_dir(TEST_FONTS_DIR)
        self.assertIn("Roboto", mgr.get_font_names())
        self.assertEqual(
            mgr.resolve_font_path("roboto"), os.path.join(TEST_FONTS_DIR, "Roboto-Regular.ttf")
        )

    def test_font_loading(self):
        font = font_manager.load_font("Arial", 24)
        self.assertIsNotNone(font)

    def test_missing_font_still_scales(self):
        mgr = _font_manager_without_fonts()
        small = mgr.load_font("No Such Font", 10)
        large = mgr.load_font("No Such Font", 60)
        self.assertGreater(large.getbbox("Hg")[3], small.getbbox("Hg")[3] * 3)

    def test_auto_fit_without_installed_fonts(self):
        with patch("core.label_renderer.font_manager", _font_manager_without_fonts()):
            config = LabelConfig(text="Line 1\nLine 2", auto_fit_font=True, tape_width_mm=12)
            _, _, _, metrics = LabelRenderer().render(config)
        self.assertGreater(metrics.effective_font_size, 20)


class TestLabelRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def test_text_render(self):
        config = LabelConfig(
            text="TEST LABEL",
            font_name="Arial",
            auto_fit_font=True,
            tape_width_mm=12,
        )
        prev, rast, rbytes, metrics = self.renderer.render(config)

        self.assertIsNotNone(prev)
        self.assertEqual(rast.size[0], 128)  # Printhead 128 dots
        self.assertEqual(len(rbytes), 128 * rast.size[1] // 8)
        self.assertGreater(metrics.print_length_mm, 0)
        self.assertGreater(metrics.effective_font_size, 0)

    def test_multiline_and_qr_render(self):
        config = LabelConfig(
            text="Line 1\nLine 2\nLine 3",
            font_name="Arial",
            auto_fit_font=True,
            qr_enabled=True,
            qr_data="https://github.com/Ircama/PT-P300BT",
            tape_width_mm=12,
        )
        prev, rast, rbytes, metrics = self.renderer.render(config)

        self.assertIsNotNone(prev)
        self.assertEqual(rast.size[0], 128)
        self.assertGreater(metrics.print_length_mm, 20.0)

    def test_tape_widths(self):
        for width in [12, 9, 6]:
            config = LabelConfig(text="WIDTH TEST", tape_width_mm=width)
            prev, rast, rbytes, metrics = self.renderer.render(config)
            self.assertEqual(rast.size[0], 128)

    def test_single_label_has_own_cut_lines_by_default(self):
        config = LabelConfig(text="CUT TEST")
        self.assertFalse(config.auto_cut_hardware)
        _, rast, rbytes, _ = self.renderer.render(config)
        line = LabelRenderer.PRINTHEAD_DOTS // 8
        # The first raster line is the cut line; the end stops at the cutter, so it has none
        self.assertTrue(any(rbytes[:line]))
        self.assertFalse(any(rbytes[-line:]))
        _, _, plain, _ = self.renderer.render(LabelConfig(text="CUT TEST", cut_line=False))
        self.assertFalse(any(plain[:line]))

    def test_cut_marks_leave_the_middle_blank(self):
        # Ticks mark only the edges of the printable area, so a slightly-off cut leaves no shadow
        line = LabelRenderer.PRINTHEAD_DOTS // 8
        for rbytes in (
            self.renderer.render(LabelConfig(text="CUT TEST"))[2],
            self.renderer.render_batch([LabelConfig(text="A"), LabelConfig(text="B")])[2],
        ):
            first = rbytes[:line]
            self.assertTrue(any(first))
            self.assertFalse(any(first[line // 2 - 2 : line // 2 + 2]))

    def test_cut_line_rendering(self):
        config = LabelConfig(
            text="CUT TEST",
            cut_line=True,
            cut_line_style="dotted",
            cut_line_position="both",
        )
        prev, rast, rbytes, metrics = self.renderer.render(config)
        self.assertIsNotNone(prev)
        self.assertGreater(len(rbytes), 0)

    def test_unicode_and_styling(self):
        config = LabelConfig(
            text="🏷 Специи & Kaßler 100% ☕",
            font_name="Arial",
            stroke_width=1,
            alignment="right",
            fixed_width_mm=60.0,
        )
        prev, rast, rbytes, metrics = self.renderer.render(config)
        self.assertIsNotNone(prev)
        self.assertGreaterEqual(metrics.print_length_mm, 59.0)

    def test_fixed_length_is_exact(self):
        # A length shorter than the content is kept, and the end is cut off with a note
        long_text = LabelConfig(text="A long label that needs more than 20 mm", fixed_width_mm=20.0)
        _, _, _, natural = self.renderer.render(LabelConfig(text=long_text.text))
        self.assertGreater(natural.print_length_mm, 30.0)
        _, _, _, metrics = self.renderer.render(long_text)
        self.assertAlmostEqual(metrics.print_length_mm, 20.0, delta=0.2)
        self.assertIn("cut off", metrics.warning)
        _, _, _, roomy = self.renderer.render(LabelConfig(text="Hi", fixed_width_mm=40.0))
        self.assertAlmostEqual(roomy.print_length_mm, 40.0, delta=0.2)
        self.assertIsNone(roomy.warning)

    def test_image_merge(self):
        import tempfile
        from PIL import Image as PILImage
        # Create a small test image
        tmp_img = PILImage.new("RGB", (30, 30), "black")
        tmp_path = os.path.join(BASE_DIR, "tests", "temp_icon.png")
        tmp_img.save(tmp_path)

        try:
            config = LabelConfig(
                text="IMAGE TEST",
                image_path=tmp_path,
                image_position="left",
                image_scale=0.8,
            )
            prev, rast, rbytes, metrics = self.renderer.render(config)
            self.assertIsNotNone(prev)
            self.assertGreater(metrics.print_length_mm, 10.0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_render_batch(self):
        c1 = LabelConfig(text="LABEL 1", tape_width_mm=12)
        c2 = LabelConfig(text="LABEL 2", tape_width_mm=12)
        c3 = LabelConfig(text="LABEL 3", tape_width_mm=12)

        # Batch of 3 labels
        prev, rast, rbytes, metrics = self.renderer.render_batch([c1, c2, c3])
        self.assertIsNotNone(prev)
        self.assertEqual(rast.size[0], 128)
        self.assertEqual(metrics.label_count, 3)
        self.assertEqual(metrics.tape_saved_mm, 50.0)  # 25mm * (3 - 1)
        self.assertGreater(metrics.print_length_mm, 30.0)

        # Batch of 1 label fallback
        prev1, rast1, rbytes1, metrics1 = self.renderer.render_batch([c1])
        self.assertEqual(metrics1.label_count, 1)
        self.assertEqual(metrics1.tape_saved_mm, 0.0)


class TestMockPrinter(unittest.TestCase):
    def test_mock_flow(self):
        mock = MockBrotherPrinter()
        status = mock.get_status()
        self.assertEqual(status.model_name, "PT-P300BT")
        self.assertTrue(status.is_ready)

        dummy_raster = bytes([0x00] * 16 * 20)  # 20 lines
        progress_calls = []

        final_status = mock.print_raster_data(
            dummy_raster,
            progress_callback=lambda c, t: progress_calls.append((c, t)),
        )
        self.assertTrue(final_status.is_ready)
        self.assertGreater(len(progress_calls), 0)

    def test_mock_feed_tape(self):
        mock = MockBrotherPrinter()
        status_msgs = []
        status = mock.feed_tape(25.0, status_callback=lambda m: status_msgs.append(m))
        self.assertTrue(status.is_ready)
        self.assertGreater(len(status_msgs), 0)
        self.assertTrue(any("25.0mm" in m for m in status_msgs))


class TestQueueLogic(unittest.TestCase):
    def test_queue_lifecycle(self):
        import copy
        renderer = LabelRenderer()
        queue = []

        # Add 3 items
        c1 = LabelConfig(text="Spice: Paprika")
        c2 = LabelConfig(text="Spice: Cumin")
        c3 = LabelConfig(text="Spice: Oregano")

        queue.append(copy.deepcopy(c1))
        queue.append(copy.deepcopy(c2))
        queue.append(copy.deepcopy(c3))
        self.assertEqual(len(queue), 3)

        # Move item down
        queue[0], queue[1] = queue[1], queue[0]
        self.assertEqual(queue[0].text, "Spice: Cumin")
        self.assertEqual(queue[1].text, "Spice: Paprika")

        # Delete item
        del queue[2]
        self.assertEqual(len(queue), 2)

        # Render remaining batch
        prev, rast, rbytes, metrics = renderer.render_batch(queue)
        self.assertEqual(metrics.label_count, 2)
        self.assertEqual(metrics.tape_saved_mm, 25.0)

    def test_padding_alias(self):
        cfg = LabelConfig(h_padding=14)
        self.assertEqual(cfg.h_padding, 14)
        self.assertEqual(cfg.h_padding_dots, 14)
        cfg.h_padding_dots = 20
        self.assertEqual(cfg.h_padding, 20)


class TestTemplates(unittest.TestCase):
    def test_presets_exist(self):
        self.assertIn("Storage Box", BUILTIN_PRESETS)
        self.assertIn("WiFi Guest Access", BUILTIN_PRESETS)
        self.assertIsNotNone(load_preset("Storage Box"))

    def test_json_export_import(self):
        tmp_path = os.path.join(BASE_DIR, "tests", "test_template.json")
        cfg = LabelConfig(text="SAVE TEST", font_name="Arial", qr_enabled=True, qr_data="test123")
        ok = export_config_to_json(cfg, tmp_path)
        self.assertTrue(ok)

        loaded = import_config_from_json(tmp_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.text, "SAVE TEST")
        self.assertTrue(loaded.qr_enabled)

        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
