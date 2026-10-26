"""Private research-learning status has safe public provenance and honest freshness."""
import json
import unittest
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class LearningStatusTests(unittest.TestCase):
    def test_public_summary_contains_aggregate_only(self):
        text=(ROOT/"data/learning-status.json").read_text(encoding="utf-8")
        d=json.loads(text)
        self.assertEqual(d["schema_version"],1)
        self.assertTrue(d["status_snapshot_only"])
        self.assertFalse(d["automatic_champion_promotion"])
        self.assertIn("manual",d["public_update_frequency"])
        self.assertGreaterEqual(d["frozen_pregame_games"],d["labeled_pregame_games"])
        self.assertTrue(d["frozen_pregame_games"]>=0)
        self.assertEqual(d["incumbent"],"elo")
        datetime.fromisoformat(d["as_of_utc"])
        self.assertIn("research-snapshots/learning_loop.json",d["private_report_url"])
        for forbidden in ("api_key","bearer","home_score","visitor_team_score",
                          "pregame_features","medical_note","access_token"):
            self.assertNotIn(forbidden,text.lower())

    def test_public_status_explicitly_denies_live_sync_and_automatic_upgrade(self):
        js=(ROOT/"audit-dashboard.js").read_text(encoding="utf-8")
        for word in ("learning-status.json","私人資料不會自動同步",
                     "人工審核","未具備可證明超越 Elo"):
            self.assertIn(word,js)


if __name__=="__main__":unittest.main()
