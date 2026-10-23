"""Chronological ten-season Elo tests: no future results can affect an earlier forecast."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from elo_history import train_and_forecast,win_prob

def final(id,date,season,home="BOS",away="NY",hs=109,as_=100):
 return {"id":str(id),"date":date,"season_end":season,"home":home,"away":away,
         "home_score":hs,"away_score":as_,"phase":"regular"}
def upcoming():
 return {"id":"future","date":"2026-10-25T19:00:00Z",
         "season_year":2027,"season_phase":2,"home":"BOS","away":"NY","status":"pre"}

class EloTests(unittest.TestCase):
 def test_home_advantage(self):
  self.assertGreater(win_prob(1500,1500),0.5)
 def test_chronological_no_future_leakage(self):
  history=[final("1","2025-02-01T01:00:00Z",2025),
           final("2","2026-02-01T01:00:00Z",2026,hs=99,as_=102)]
  baseline,meta=train_and_forecast(history,[upcoming()])
  added,more=train_and_forecast(history+[
    final("future_result","2026-10-26T01:00:00Z",2027,hs=180,as_=60)
  ],[upcoming()])
  self.assertEqual(len(baseline),1)
  self.assertEqual(baseline[0]["home_win_probability"],added[0]["home_win_probability"])
  self.assertEqual(meta["sample_size"],1)
  self.assertFalse(meta["out_of_sample"])
  self.assertIsInstance(meta["brier"],float)
 def test_cannot_train_on_unscored_events(self):
  b,meta=train_and_forecast([{"id":"x","date":"2026-03-01T00:00:00Z","season_end":2026,"home":"BOS","away":"NY","home_score":None,"away_score":None}],[upcoming()])
  self.assertEqual(meta["training_games_through_snapshot"],0)
  self.assertAlmostEqual(b[0]["home_win_probability"],win_prob(1500,1500),places=4)
 def test_preseason_current_not_eligible_for_training(self):
  pre={"id":"preseason","date":"2026-10-20T01:00:00Z","season_year":2027,"season_phase":1,
   "home":"BOS","away":"NY","home_score":180,"away_score":80,"status":"post"}
  baseline,_=train_and_forecast([],[upcoming()])
  filtered,_=train_and_forecast([],[pre,upcoming()])
  self.assertEqual(baseline[0]["home_win_probability"],filtered[0]["home_win_probability"])

if __name__=="__main__":unittest.main()
