"""Fallback never invents missing quotes or follows off-source references."""
import pathlib,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from core_odds import supplement
NOW=datetime(2026,10,27,18,tzinfo=timezone.utc)
G={'id':'1','date':(NOW+timedelta(hours=12)).isoformat(),'status':'pre','home':'BOS','away':'NY'}
class CoreTests(unittest.TestCase):
    def test_empty_response_is_cached_no_quotes_synthesized(self):
        calls=[]
        def fetch(url):calls.append(url);return {'items':[]}
        with tempfile.TemporaryDirectory()as directory:
            path=pathlib.Path(directory)/'cache.json'
            for time in [NOW,NOW+timedelta(minutes=10)]:self.assertEqual(supplement([G],{},lambda q:0,path,time,fetch),[])
        self.assertEqual(len(calls),1)
    def test_ref_guard_and_event_request_bound(self):
        calls=[]
        def fetch(url):calls.append(url);return {'items':[{'$ref':'https://other.test/private'},{'$ref':'https://sports.core.api.espn.com/v2/other/'}]}
        with tempfile.TemporaryDirectory()as directory:
            self.assertFalse(supplement([{**G,'id':str(i)}for i in range(30)],{},lambda q:0,pathlib.Path(directory)/'cache.json',NOW,fetch))
        self.assertEqual(len(calls),12);self.assertTrue(all('/odds?limit=100' in u for u in calls))
    def test_already_complete_or_undated_games_are_not_requested(self):
        def fetch(url):raise AssertionError('unnecessary request')
        with tempfile.TemporaryDirectory()as directory:
            supplement([G,{**G,'date':'2026-10-28T00:00:00'}],{'q':{'event_id':'1'}},lambda q:3,pathlib.Path(directory)/'c.json',NOW,fetch)
if __name__=='__main__':unittest.main()
