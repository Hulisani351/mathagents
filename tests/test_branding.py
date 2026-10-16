"""Offline asset, configuration and colour-contrast checks."""
from pathlib import Path
import ast
import struct
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


def luminance(colour):
    rgb = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


class BrandingTests(unittest.TestCase):
    def test_theme_contrast_and_light_base(self):
        theme = tomllib.loads((ROOT / '.streamlit/config.toml').read_text())['theme']
        self.assertEqual(theme['base'], 'light')
        self.assertEqual(theme['primaryColor'], '#A63C00')
        self.assertGreaterEqual(1.05 / (luminance(theme['primaryColor']) + .05), 4.5)
        self.assertGreaterEqual(1.05 / (luminance(theme['textColor']) + .05), 4.5)

    def test_logo_is_a_square_png(self):
        data = (ROOT / 'assets/uj-logo.png').read_bytes()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        width, height = struct.unpack('>II', data[16:24])
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 100)

    def test_source_and_single_stylesheet(self):
        source = (ROOT / 'streamlit_app.py').read_text(encoding='utf-8')
        ast.parse(source)
        self.assertEqual(source.count('<style>'), 1)
        self.assertIn('Student project by Hulisani Rambau', source)
        self.assertNotIn('not an official', source.lower())
        css = (ROOT / 'assets/workspace.css').read_text()
        self.assertIn('prefers-reduced-motion', css)
        self.assertIn('focus-visible', css)
        self.assertNotIn('url(http', css)


if __name__ == '__main__':
    unittest.main()
