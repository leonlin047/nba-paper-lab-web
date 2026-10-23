"""Guard against ESPN schedule entries omitting 'status': scored past games must be included."""
import datetime as dt
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from backfill_history import game,score

def event(*,year=2026,phase=2,date="2026-01-15T02:00:00Z",hs=111,as_=99,status=False):
  e={"id":"401123456","date":date,
     "season":{"year":year},"seasonType":{"type":phase},
     "competitions":[{"competitors":[
         {"homeAway":"home","team":{"abbreviation":"BOS"},"score":{"value":hs}},
         {"homeAway":"away","team":{"abbreviation":"NY"},"score":{"value":as_}}]}]}
  if status:e["status"]={"type":{"state":"post","completed":True}}
  return e

class HistoryTests(unittest.TestCase):
 def test_final_without_status(self):
  e=event()
  parsed=game(e,2026,2)
  self.assertIsNotNone(parsed)
  self.assertEqual(parsed["home_score"],111)
  self.assertEqual(parsed["away_score"],99)
 def test_wrong_season_and_phase_rejected(self):
  self.assertIsNone(game(event(year=2025),2026,2))
  self.assertIsNone(game(event(phase=3),2026,2))
 def test_unscored_and_future_rejected(self):
  self.assertIsNone(game(event(hs=0,as_=0),2026,2))
  future=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=3)).isoformat()
  self.assertIsNone(game(event(date=future),2026,2))
 def test_dict_scores(self):
  self.assertEqual(score({"score":{"value":115,"displayValue":"115"}}),115)
  self.assertIsNone(score({"score":"--"}))
 def test_status_validation_when_present(self):
  self.assertIsNotNone(game(event(status=True),2026,2))

if __name__=="__main__":unittest.main()
