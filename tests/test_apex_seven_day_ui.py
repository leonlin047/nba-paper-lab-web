"""APEX v2.1 private historical replay is never presented as prospective proof."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class TestSevenDayReplayUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/"data/apex-seven-day-replay.json").read_text())

    def test_distinguish_retrospective_from_frozen_model(self):
        d=self.data
        self.assertEqual(d["kind"],"retrospective_simulated_asof_replay")
        self.assertEqual(d["real_frozen_apex_predictions_for_window"],0)
        self.assertEqual(d["completed_games"],43)
        self.assertEqual(d["apex"]["correct"],27)
        self.assertEqual(d["elo"]["correct"],25)
        self.assertEqual(d["apex"]["n"],43)
        self.assertEqual(d["elo"]["n"],43)
        self.assertEqual(sum(x["games"] for x in d["by_day"]),43)
        self.assertEqual(sum(x["apex_hits"] for x in d["by_day"]),27)
        self.assertEqual(sum(x["elo_hits"] for x in d["by_day"]),25)
        self.assertGreater(d["apex"]["brier"],d["elo"]["brier"])
        self.assertIn("downloaded after games",d["simulation_assumption"])

    def test_market_validation_is_not_invented(self):
        market=self.data["market_result"]
        self.assertIn("not_evaluable",market["spread"])
        self.assertIn("not_evaluable",market["over_under"])

    def test_apex_replay_tab_and_source(self):
        js=(ROOT/"apex-dashboard.js").read_text()
        self.assertIn('["replay","七日模擬回測"]',js)
        self.assertIn("apex-seven-day-replay.json",js)
        self.assertIn("不構成模型升級證據",js)
        self.assertIn("這不是當時真正提前封存",js)
        p=subprocess.run(["node","--check",str(ROOT/"apex-dashboard.js")],
                         capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)


if __name__=="__main__":
    unittest.main()
