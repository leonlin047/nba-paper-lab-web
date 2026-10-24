"""Adversarial tests for traceable, point-in-time NBA matchup evidence."""
import datetime as dt,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from analyst_factors import team_form,matchup_form,parse_made_attempted,extract_four_factors,matchup_box_factors,injuries_by_matchup

DATE="2026-10-25T00:00:00Z"
def score(id,date,home,away,hp,ap):
 return {"id":str(id),"date":date,"home":home,"away":away,"home_score":hp,"away_score":ap}
def matchup():
 return {"id":"future","date":DATE,"home":"MIL","away":"CHI"}
class EvidenceTests(unittest.TestCase):
 def test_rest_form_and_later_game_is_excluded(self):
  samples=[
   score(1,"2026-10-21T00:00:00Z","MIL","CHI",110,100),
   score(2,"2026-10-23T00:00:00Z","CHI","MIL",104,107),
   score(3,"2026-10-26T00:00:00Z","MIL","CHI",200,70)]
  e=matchup_form(matchup(),samples)
  self.assertEqual(e["home"]["n"],2)
  self.assertEqual(e["home"]["avg_scored"],108.5)
  self.assertEqual(e["home"]["rest_hours"],48)
  self.assertEqual(e["h2h"]["n"],2)
  self.assertNotIn("3",e["h2h"]["match_ids"])
 def test_overnight_back_to_back_proxy(self):
  e=team_form([score(1,"2026-10-24T01:00:00Z","MIL","CHI",101,100)],"MIL",dt.datetime.fromisoformat("2026-10-25T00:00:00+00:00"))
  self.assertTrue(e["back_to_back_proxy"])
  self.assertEqual(e["n"],1)
 def test_box_metrics_rejects_malformed_stats(self):
  self.assertEqual(parse_made_attempted("5-20"),(5,20))
  self.assertIsNone(parse_made_attempted("30-5"))
  d={"boxscore":{"teams":[{"team":{"abbreviation":"MIL"},"statistics":[
   {"name":"fieldGoalsMade-fieldGoalsAttempted","displayValue":"40-90"},
   {"name":"threePointFieldGoalsMade-threePointFieldGoalsAttempted","displayValue":"12-34"},
   {"name":"freeThrowsMade-freeThrowsAttempted","displayValue":"20-26"},
   {"name":"offensiveRebounds","displayValue":"10"},
   {"name":"defensiveRebounds","displayValue":"35"},
   {"name":"totalTurnovers","displayValue":"12"}]}]}}
  e=extract_four_factors(d,"42","2026-10-23T20:00:00Z")
  self.assertEqual(len(e),1)
  self.assertEqual(e[0]["estimated_possessions"],103.4)
  self.assertEqual(e[0]["eFG_pct"],51.1)
 def test_box_factors_require_minimum_three_games_before_tip(self):
  x=[{"team":"MIL","date":"2026-10-23T00:00:00Z","game_id":"1","eFG_pct":49,
      "estimated_possessions":102,"three_point_attempt_rate":36,
      "turnover_per_est_poss_pct":13,"free_throw_attempt_rate":24}]
  r=matchup_box_factors(matchup(),x)
  self.assertIsNone(r["home"]["eFG_pct"])
  self.assertEqual(r["home"]["quality"],"insufficient_n")
 def test_injuries_timestamp_gate(self):
  later={"captured_at":"2026-10-25T06:00:00Z","injuries":[
   {"team":"MIL","player":"Example","status":"Out"}],"errors":[]}
  self.assertFalse(injuries_by_matchup(matchup(),later)["available"])
  earlier=dict(later,captured_at="2026-10-24T00:00:00Z")
  found=injuries_by_matchup(matchup(),earlier)
  self.assertEqual(len(found["rows"]),1)
  self.assertFalse(found["official_game_specific"])
  self.assertTrue(found["unknown_impact"])
if __name__=="__main__":unittest.main()
