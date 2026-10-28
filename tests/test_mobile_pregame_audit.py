"""Protect the source-backed, dated NBA pregame audit against leakage.

Rows were created from GitHub snapshots saved before tipoff, not inferred
retrospectively by the report generator.
"""
import json
import pathlib
import subprocess
import unittest
from collections import defaultdict
from datetime import datetime, timezone

ROOT=pathlib.Path(__file__).resolve().parents[1]


class TestMobileAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit=json.loads((ROOT/"data/pregame-audit.json").read_text(encoding="utf-8"))

    def test_observed_outcomes_and_strict_60min_freeze(self):
        a=self.audit
        self.assertEqual(a["schema_version"],1)
        self.assertEqual(a["audited_games"],24)
        self.assertEqual(a["eligible_games"],23)
        self.assertEqual(a["excluded_games"],1)
        for r in a["rows"]:
            self.assertTrue(r["date_taiwan"] in ("2026-10-24","2026-10-25","2026-10-28"))
            if r["status"]=="eligible":
                tip=datetime.fromisoformat(r["tipoff_utc"].replace("Z","+00:00"))
                freeze=datetime.fromisoformat(r["freeze_utc"].replace("Z","+00:00"))
                self.assertGreater((tip-freeze).total_seconds(),3600)
                self.assertEqual(r["moneyline"]["hit"],(r["moneyline"]["pick"]=="home")==(
                    r["home_score"]>r["away_score"]))
                self.assertRegex(r["source_commit"],r"^[a-f0-9]{40}$")
                self.assertIsNotNone(r["spread"])
                self.assertIsNotNone(r["total"])
            else:
                self.assertIsNone(r.get("moneyline"))

    def test_today_uses_published_pregame_evidence_not_postgame_recompute(self):
        rows=[r for r in self.audit['rows']if r['date_taiwan']=='2026-10-28']
        self.assertEqual(len(rows),4)
        self.assertTrue(all(r['source_commit']=='9745eaebcf0ff74683f039dbde46613f141bc5f4'for r in rows))
        self.assertTrue(all(datetime.fromisoformat(r['snapshot_generated_at_utc'])<datetime.fromisoformat(r['freeze_utc'].replace('Z','+00:00'))for r in rows))
        self.assertEqual(sum(r['moneyline']['hit']for r in rows),3)
        self.assertEqual(sum(r['spread']['hit']for r in rows),0)
        self.assertEqual(sum(r['total']['hit']for r in rows),1)

    def test_accuracy_recomputes_exactly_from_rows(self):
        a=self.audit
        categories={
            "moneyline":lambda r:r.get("moneyline"),
            "spread":lambda r:r.get("spread"),
            "favorite_spread":lambda r:r.get("spread") if r.get("spread",{}).get("pick_type")=="favorite" else None,
            "underdog_spread":lambda r:r.get("spread") if r.get("spread",{}).get("pick_type")=="underdog" else None,
            "over":lambda r:r.get("total") if r.get("total",{}).get("pick")=="over" else None,
            "under":lambda r:r.get("total") if r.get("total",{}).get("pick")=="under" else None,
            "totals":lambda r:r.get("total"),
        }
        for day,expected in [("all",a["overall"]),*a["by_day"].items()]:
            src=[r for r in a["rows"] if r["status"]=="eligible" and (day=="all" or r["date_taiwan"]==day)]
            for name,pick in categories.items():
                values=[pick(r) for r in src]
                values=[v for v in values if v and isinstance(v.get("hit"),bool)]
                n=len(values);good=sum(v["hit"] for v in values)
                self.assertEqual(expected[name]["games"],n)
                self.assertEqual(expected[name]["correct"],good)
                if n:self.assertAlmostEqual(expected[name]["accuracy_pct"],round(good/n*100,2))
                else:self.assertIsNone(expected[name]["accuracy_pct"])

    def test_public_audit_does_not_redistribute_unreviewed_raw_lines(self):
        a=self.audit
        self.assertEqual(a["required_lead_minutes"],60)
        for r in a["rows"]:
            self.assertNotIn("home_line",str(r))
            self.assertNotIn("reference_line",str(r))
            self.assertNotIn("rights_evidence_url",str(r))

    def test_audit_and_team_page_are_real_interactive_tabs(self):
        html=(ROOT/"research.html").read_text(encoding="utf-8")
        for marker in ('data-target="audit"','id="audit"','id="audit-metrics"',
                       'id="audit-results"','id="audit-day"','id="audit-market"',
                       'id="team-compare"','team-analytics.js','audit-dashboard.js'):
            self.assertIn(marker,html)
        for file in ("audit-dashboard.js","team-analytics.js"):
            result=subprocess.run(["node","--check",str(ROOT/file)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":unittest.main()
