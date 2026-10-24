"""Offline Taiwan NBA market ingestion tests; fixture only, not website redistribution."""
import datetime as dt,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
from collect_tw_odds import parse_table,match_espn,numeric

DATE=dt.datetime(2026,10,24,11,45,tzinfo=dt.timezone(dt.timedelta(hours=8))).astimezone(dt.timezone.utc)
def td(side,cls,line,odd):
    return ('<td class="'+cls+'"><div><strong>'+side+
       '</strong><span class="data-wrap"><strong>'+line+
       '</strong><span>, '+odd+'</span></span></div></td>')
def body(*,gameid="2026102531001",settled=False,bad_spread=False,percent=False):
    def betting(side,sp,ml,ou,price_sp):
        return (td(side,"td-bank-bet01",sp,price_sp)
          +td(side,"td-bank-bet03","",ml)
          +td(side,"td-bank-bet02","231.5",ou))
    first_team=('<td rowspan="2" class="td-teaminfo"><table><tr><td>'
       '<a href="/gamesData/teams?teamid=43">熱火</a></td></tr>'
       '<tr><td><a href="/gamesData/teams?teamid=30">黃蜂</a></td></tr></table></td>'
       if settled else '<td class="td-teaminfo"><h3><a href="/gamesData/teams?teamid=43">熱火</a></h3></td>')
    second_team=("" if settled else
       '<td class="td-teaminfo"><h3><a href="/gamesData/teams?teamid=30">黃蜂</a></h3></td>')
    away=('<tr gameid="'+gameid+'"><td rowspan="2" class="td-gameinfo"><h4>AM 06:00</h4></td>'
       +first_team+td("客","td-universal-bet01","","50%")
       +betting("客","-3.5" if not bad_spread else "-4.5","1.48","1.71","1.72")+"</tr>")
    home=('<tr gameid="'+gameid+'">'+second_team+
       betting("主","+3.5","2.17","1.75","1.76")+"</tr>")
    return "<html><table class='predictgame-table'><tbody>"+away+home+"</tbody></table></html>"

class TWTest(unittest.TestCase):
 def test_live_public_markets_and_time(self):
    rows,errors=parse_table(body(),DATE,"https://www.playsport.cc/predict/games?allianceid=3&gameday=tomorrow")
    self.assertEqual(errors,[])
    self.assertEqual(len(rows),1)
    x=rows[0]
    self.assertEqual(x["home"],"CHA")
    self.assertEqual(x["away"],"MIA")
    self.assertEqual(x["layout"],"split_rows")
    self.assertTrue(x["eligible_for_pregame_backtest"])
    self.assertEqual(x["complete_markets"],3)
    self.assertEqual(x["tipoff_utc"],"2026-10-24T22:00:00+00:00")
    self.assertEqual(x["moneyline"]["away_decimal"],1.48)
    self.assertEqual(x["moneyline"]["home_decimal"],2.17)
    self.assertEqual(x["spread"]["home_line"],3.5)
    self.assertEqual(x["spread"]["away_line"],-3.5)
    self.assertEqual(x["total"]["line"],231.5)
    self.assertEqual(x["total"]["over_decimal"],1.71)
    self.assertEqual(x["total"]["under_decimal"],1.75)
 def test_settled_layout_cannot_be_backfilled_as_pregame(self):
    rows,errors=parse_table(body(settled=True),DATE,"https://www.playsport.cc/predict/games?allianceid=3")
    self.assertEqual(len(rows),1)
    self.assertEqual(rows[0]["layout"],"settled_nested")
    self.assertFalse(rows[0]["eligible_for_pregame_backtest"])
 def test_inconsistent_spread_excluded_not_guessed(self):
    rows,errors=parse_table(body(bad_spread=True),DATE,"https://www.playsport.cc")
    self.assertEqual(len(rows),1)
    self.assertIsNone(rows[0]["spread"]["home_line"])
    self.assertEqual(rows[0]["complete_markets"],2)
 def test_team_date_join_requires_unique_event(self):
    rows,_=parse_table(body(),DATE,"https://www.playsport.cc")
    games=[{"id":"ESPN1","date":"2026-10-24T22:00:00Z","home":"CHA","away":"MIA"},
       {"id":"WRONG","date":"2026-10-24T22:00:00Z","home":"CHA","away":"ORL"}]
    result=match_espn(rows,games)
    self.assertEqual(result[0]["event_id"],"ESPN1")
    self.assertEqual(len(result),1)
    self.assertEqual(match_espn(rows,games+[{"id":"DUP","date":"2026-10-24T22:00:00Z","home":"CHA","away":"MIA"}]),[])
 def test_no_fake_prices(self):
    self.assertIsNone(numeric("50%"))
    self.assertIsNone(numeric("逾時"))
    self.assertIsNone(numeric("1.68元"))
    rows,errors=parse_table(body(gameid="oops"),DATE,"https://www.playsport.cc")
    self.assertEqual(rows,[])
 def test_post_start_observed_is_not_pregame(self):
    later=dt.datetime(2026,10,24,23,tzinfo=dt.timezone.utc)
    rows,_=parse_table(body(),later,"https://www.playsport.cc")
    self.assertFalse(rows[0]["eligible_for_pregame_backtest"])
    self.assertEqual(rows[0]["observation_phase"],"post_start_observation")

if __name__=="__main__":unittest.main()
