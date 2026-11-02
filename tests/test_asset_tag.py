"""Tests for asset tags (core/asset_tag.py): numbering, the code and the label they draw as."""

import unittest

from core import asset_tag
from core.label_renderer import LabelConfig, LabelRenderer


class TestNumbering(unittest.TestCase):
    def test_the_number_keeps_its_width(self):
        self.assertEqual(asset_tag.next_number("0042"), "0043")
        self.assertEqual(asset_tag.next_number("0099"), "0100")
        self.assertEqual(asset_tag.next_number("9"), "10")
        self.assertEqual(asset_tag.next_number("0042", 10), "0052")

    def test_letters_around_the_number_stay(self):
        self.assertEqual(asset_tag.next_number("A7"), "A8")
        self.assertEqual(asset_tag.next_number("12B"), "13B")
        self.assertEqual(asset_tag.next_number("none"), "none")

    def test_the_tag_and_link(self):
        self.assertEqual(asset_tag.tag_text(" PC- ", "0042 "), "PC-0042")
        self.assertEqual(asset_tag.link_for("https://x.com/a/{tag}", "PC-1"), "https://x.com/a/PC-1")
        self.assertEqual(asset_tag.link_for("https://x.com/a/", "PC-1"), "https://x.com/a/PC-1")
        self.assertEqual(asset_tag.link_for("  ", "PC-1"), "")


class TestAsTextLabel(unittest.TestCase):
    def config(self, **options):
        base = dict(layout="asset", asset_owner="Tobezone IT", asset_prefix="PC-", asset_number="0042")
        return LabelConfig(**{**base, **options})

    def test_number_big_with_a_barcode_of_the_tag(self):
        text = asset_tag.as_text_label(self.config())
        self.assertEqual(text.layout, "text")
        self.assertEqual(text.text, "# **PC-0042**\nTobezone IT")
        self.assertTrue(text.barcode_enabled)
        self.assertEqual(text.barcode_data, "PC-0042")
        self.assertFalse(text.qr_enabled)

    def test_owner_big_qr_link_on_the_right(self):
        text = asset_tag.as_text_label(self.config(asset_big="owner", asset_code="qr", asset_code_holds="link",
                                                   asset_link="https://x.com/{tag}", asset_code_side="right"))
        self.assertEqual(text.text, "# **Tobezone IT**\nPC-0042")
        self.assertEqual(text.qr_data, "https://x.com/PC-0042")
        self.assertEqual(text.qr_position, "right")
        self.assertFalse(text.barcode_enabled)

    def test_no_code_and_markers_stay_plain(self):
        text = asset_tag.as_text_label(self.config(asset_code="none", asset_owner="**A & B**"))
        self.assertFalse(text.qr_enabled or text.barcode_enabled)
        self.assertEqual(text.text, "# **PC-0042**\n\\*\\*A & B\\*\\*")

    def test_it_draws_like_the_text_label(self):
        renderer = LabelRenderer()
        tag = self.config()
        drawn = renderer.render(tag)[0]
        same = renderer.render(asset_tag.as_text_label(tag))[0]
        self.assertEqual(drawn.tobytes(), same.tobytes())


if __name__ == "__main__":
    unittest.main()
