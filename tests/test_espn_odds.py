"""Realistic ESPN NBA scoreboard market shapes, not model-generated prices."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from espn_odds import compact_market,validate_quote
from market_model import build_market

def scoreboard_game():
    return {"id":"401909853","date":"2026-10-24T22:00:00Z","home":"CHA","away":"MIA"}
def source():
    return {
      "provider":{"name":"DraftKings"},"details":"MIA -3.5","spread":3.5,
      "overUnder":231.5,
      "homeTeamOdds":{"favorite":False,"team":{"abbreviation":"CHA"}},
      "awayTeamOdds":{"favorite":True,"team":{"abbreviation":"MIA"}},
      "moneyline":{"home":{"open":{"odds":"+124"},"close":{"odds":"+124"}},
          "away":{"open":{"odds":"-148"},"close":{"odds":"-148"}}},
      "pointSpread":{"home":{"open":{"line":"+3.5","odds":"-110"},
                             "close":{"line":"+3.5","odds":"-110"}},
                     "away":{"open":{"line":"-3.5","odds":"-110"},
                             "close":{"line":"-3.5","odds":"-110"}}},
      "total":{"over":{"open":{"line":"o231.5","odds":"-115"},
                       "close":{"line":"o231.5","odds":"-115"}},
               "under":{"open":{"line":"u231.5","odds":"-105"},
                        "close":{"line":"u231.5","odds":"-105"}}}
    }

class OddsIngestionTests(unittest.TestCase):
 def _parse(self,raw=None):
  game=scoreboard_game()
  quote=compact_market(raw or source(),game["id"],"2026-10-24T02:00:00Z","ESPN scoreboard embedded odds")
  return validate_quote(quote,game["home"],game["away"])
 def test_complete_espn_nested_market(self):
  quote=self._parse()
  self.assertEqual(quote["home_moneyline"],124)
  self.assertEqual(quote["away_moneyline"],-148)
  self.assertEqual(quote["home_spread_verified"],3.5)
  self.assertEqual(quote["home_spread_american"],-110)
  self.assertEqual(quote["away_spread_american"],-110)
  self.assertEqual(quote["over_under"],231.5)
  self.assertEqual(quote["over_american"],-115)
  self.assertEqual(quote["under_american"],-105)
  market=build_market(quote,scoreboard_game(),{"home_win_probability":.45})
  self.assertAlmostEqual(market["moneyline"]["home_decimal"],2.24)
  self.assertEqual(market["spread"]["home_line"],3.5)
  self.assertEqual(market["total"]["line"],231.5)
  self.assertEqual(market["rights_status"],"review")
 def test_team_name_mismatch_rejects_spread(self):
  q=source()
  q["details"]="NY -3.5"
  p=self._parse(q)
  # Opposite side line still verified but impossible named favorite is not validated;
  # source must not become a supposedly confirmed spread.
  self.assertIsNone(p["home_spread_verified"])
 def test_opposite_lines_reject(self):
  q=source()
  q["pointSpread"]["away"]["close"]["line"]="+3.5"
  p=self._parse(q)
  self.assertIsNone(p["home_spread_verified"])
 def test_invalid_prices_not_fabricated(self):
  q=source()
  q["moneyline"]["home"]["close"]["odds"]="EVEN"
  q["moneyline"]["home"]["open"]["odds"]="EVEN"
  p=self._parse(q)
  self.assertIsNone(p["home_moneyline"])
  market=build_market(p,scoreboard_game(),{})
  self.assertIsNone(market["moneyline"]["home_decimal"])
 def test_source_without_any_prices_lines_rejected(self):
  p=compact_market({"provider":{"name":"Demo"}}, "1","2026-10-24T00:00Z","scoreboard")
  self.assertIsNone(p)
 def test_names_and_favorite_flags_not_moneylines(self):
  q=source()
  q.pop("moneyline")
  q["homeTeamOdds"]["favorite"]=True
  p=self._parse(q)
  self.assertIsNone(p["home_moneyline"])
  self.assertIsNone(p["away_moneyline"])
 def test_all_prices_preserve_timestamp(self):
  p=self._parse()
  self.assertEqual(p["captured_at_utc"],"2026-10-24T02:00:00Z")
  self.assertEqual(p["source_endpoint"],"ESPN scoreboard embedded odds")
  self.assertNotIn("licensed",str(p).lower())

if __name__=="__main__":unittest.main()
