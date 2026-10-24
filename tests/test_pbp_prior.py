"""Contract checks for prior-season true possessions and no fake team efficiency."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from collect_pbp_prior import parse_prior,combine_totals
class PriorTests(unittest.TestCase):
 def setup_data(self):
  results=[]
  totals=[]
  for i in range(30):
   code=f"T{i:02d}"
   results.append({"team_name":code,"team_id":str(i),"ppp":1.1,"spp":14,"ppp_rank":i+1})
   totals.append({"TeamAbbreviation":code,"SecondsPlayed":236160,
      "OffPoss":8100,"DefPoss":8100,"Points":9300,"OpponentPoints":9100,
      "FG2M":2400,"FG3M":1000,"FG2A":4200,"FG3A":3100,"Turnovers":1000,
      "FTA":1700,"OffFGReboundPct":.25})
  return {"results":results},{"multi_row_table_data":totals}
 def test_all_teams_and_real_efficiency(self):
  source,totals=self.setup_data()
  prior=parse_prior(source,"2026-10-24T00:00:00Z")
  full=combine_totals(prior,totals)
  self.assertEqual(full["team_count"],30)
  self.assertEqual(full["possession_total_teams"],30)
  team=full["teams"]["T00"]
  self.assertAlmostEqual(team["offensive_rating_previous_season"],114.81,places=2)
  self.assertAlmostEqual(team["defensive_rating_previous_season"],112.35,places=2)
  self.assertAlmostEqual(team["possessions_per_48_previous_season"],98.78,places=2)
  self.assertTrue(team["not_current_season"])
 def test_reject_incomplete_possession_coverage(self):
  source,totals=self.setup_data()
  prior=parse_prior(source,"2026-10-24T00:00:00Z")
  totals["multi_row_table_data"]=totals["multi_row_table_data"][:1]
  with self.assertRaises(ValueError):combine_totals(prior,totals)
if __name__=="__main__":unittest.main()
