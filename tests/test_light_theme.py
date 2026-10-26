"""Regression checks for bright mobile brand without changing research data."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class MobileBrandTests(unittest.TestCase):
    def test_bright_cobalt_theme_and_meta(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        css=(ROOT/"theme-4456fe.css").read_text(encoding="utf-8")
        self.assertIn('<meta name="theme-color" content="#F8F9FC">',html)
        self.assertIn('href="./theme-4456fe.css?v=20261027"',html)
        self.assertIn('class="site-hero"',html)
        self.assertIn('class="overview-grid"',html)
        self.assertIn("--brand:#4456FE",css)
        self.assertIn("--canvas:#F8F9FC",css)
        self.assertIn("--surface:#FFFFFF",css)
        self.assertIn("--ink:#242836",css)
        self.assertIn("color-scheme:light",css)
        self.assertNotIn("background:#080f20",css)
        self.assertNotIn("background:#0b172a",css)

    def test_no_functionality_lost(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        for pane in ("games","teams","injuries","models","apex-v21",
                     "audit","quality","research","news"):
            self.assertIn('data-target="'+pane+'"',html)
            self.assertIn('id="'+pane+'"',html)
        for contract in ('id="apex-v21-terminal"','id="audit-metrics"',
                         'id="team-compare"','id="pl-predictions"',
                         'id="check"','id="open-research"'):
            self.assertIn(contract,html)
        for script in ("apex-dashboard.js","audit-dashboard.js","team-analytics.js",
                       "game-details.js","research-dashboard.js","news.js","injuries.js"):
            self.assertIn('src="./'+script+'"',html)
            check=subprocess.run(["node","--check",str(ROOT/script)],
                                 capture_output=True,text=True)
            self.assertEqual(check.returncode,0,script+": "+check.stderr)

    def test_all_data_stays_external_and_unchanged(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        css=(ROOT/"theme-4456fe.css").read_text(encoding="utf-8")
        # Theme should not hardcode odds, injuries, forecasts or hit rates.
        for key in ("api_key","access_token","authorization: bearer",
                    "home_win_probability_proxy:0.","win_rate:0."):
            self.assertNotIn(key,css.lower())
        self.assertIn("data-target=\"apex-v21\"",html)

if __name__=="__main__":
    unittest.main()
