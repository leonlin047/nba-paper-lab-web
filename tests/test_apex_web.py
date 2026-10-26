"""Public mobile APEX v2.1 is a real clickable research tab, never fake data."""
import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class ApexWebTests(unittest.TestCase):
    def test_apex_model_tab_and_script(self):
        html=(ROOT/"index.html").read_text(encoding="utf-8")
        script=(ROOT/"apex-dashboard.js").read_text(encoding="utf-8")
        for item in ('data-target="apex-v21"','id="apex-v21"','id="apex-v21-terminal"',
                     '<script src="./apex-dashboard.js" defer></script>'):
            self.assertIn(item,html)
        self.assertIn("data/apex-v21-status.json",script)
        self.assertIn('addEventListener("click"',script)
        self.assertIn('aria-pressed',script)
        self.assertNotIn("innerHTML",script)
        self.assertNotIn("eval(",script)

    def test_private_research_is_not_mislabeled_as_proven(self):
        status=json.loads((ROOT/"data/apex-v21-status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["model_id"],"apex_v21_genuinely_frozen_shadow")
        self.assertEqual(status["release_status"],"merged_private_main")
        self.assertEqual(status["official_model"],"elo")
        self.assertTrue(status["research_only"])
        self.assertFalse(status["champion_auto_promotion"])
        self.assertFalse(status["raw_data_published"])
        self.assertEqual(status["report_status"],"insufficient_data")
        self.assertEqual(status["eligible_paired_games"],0)
        self.assertEqual(status["new_shadow_snapshots"],0)
        self.assertEqual(status["authorized_public_forecasts"],[])
        self.assertEqual(status["minimum_evaluated_games"],100)
        self.assertEqual(status["public_update_method"],"manual_sanitized_snapshot")
        text=(ROOT/"data/apex-v21-status.json").read_text(encoding="utf-8").lower()
        for secret in ("api_key","access_token","raw_game_json","private_store/observations.sqlite",
                       "home_score","away_score","observed_prices"):
            self.assertNotIn(secret,text)


if __name__=="__main__":
    unittest.main()
