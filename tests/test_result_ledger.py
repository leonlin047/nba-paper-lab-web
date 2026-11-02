import copy,json,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import result_ledger as r
import collect_scoreboard as s
NOW=datetime(2026,11,2,12,tzinfo=timezone.utc)
def game():return {'id':'1','date':(NOW-timedelta(hours=3)).isoformat(),'home':'GS','away':'LAC','status':'pre','season_phase':2,'season_year':2027,'home_score':0,'away_score':0}
def forecast(tip=None):return {'event_id':'1','date':tip or(NOW+timedelta(hours=3)).isoformat(),'home':'GS','away':'LAC','generated_at_utc':NOW.isoformat(),'frozen_at_utc':NOW.isoformat(),'model_version':'v1','home_win_probability':.6,'baseline':{'home_win_probability':.55},'market':{'provider':'test','captured_at_utc':NOW.isoformat(),'home_line':-3.5,'total_line':220.5},'cover':{'positive':.6,'negative':.4,'push':0},'totals':{'positive':.4,'negative':.6,'push':0}}
class ResultLedgerTests(unittest.TestCase):
    def test_strict_score_identity_no_legacy_team_only_join(self):
        g=game();board={'captured_at':NOW.isoformat(),'games':[{'event_id':'1','date':g['date'],'home':'GSW','away':'LAC','status':'已結束','home_score':124,'away_score':112,'provider':'ESPN'}]};public={'games':[g]}
        for field,value in [('event_id','2'),('date',(NOW-timedelta(days=1)).isoformat()),('home','BOS')]:
            wrong=copy.deepcopy(board);wrong['games'][0][field]=value;self.assertEqual(r.reconcile_games(copy.deepcopy(public),wrong,NOW),0)
        legacy=copy.deepcopy(board);legacy['games'][0].pop('date');self.assertEqual(r.reconcile_games(copy.deepcopy(public),legacy,NOW),0)
        self.assertEqual(r.reconcile_games(public,board,NOW),1);self.assertEqual(g['status'],'post');self.assertEqual(g['home_score'],124)
        self.assertEqual(r.reconcile_games(public,board,NOW),0)

    def test_old_snapshot_and_duplicate_identity_are_rejected(self):
        g=game();board={'captured_at':(NOW-timedelta(hours=7)).isoformat(),'games':[{'event_id':'1','date':g['date'],'home':'GS','away':'LAC','status':'已結束','home_score':120,'away_score':110,'provider':'ESPN'}]}
        self.assertEqual(r.reconcile_games({'games':[g]},board,NOW),0)
        board['captured_at']=NOW.isoformat();self.assertEqual(r.reconcile_games({'games':[g,copy.deepcopy(g)]},board,NOW),0)

    def test_missing_early_market_can_freeze_later_without_changing_moneyline(self):
        first=forecast();first.update(cover=None,totals=None);first['market'].update(home_line=None,total_line=None,captured_at_utc=None);original=copy.deepcopy(first);markets=[]
        self.assertEqual(r.seed_and_freeze_markets(markets,{'gbdt':[first]},{},NOW),0)
        later=forecast();later['generated_at_utc']=(NOW+timedelta(minutes=10)).isoformat();later['market']['captured_at_utc']=later['generated_at_utc']
        self.assertEqual(r.seed_and_freeze_markets(markets,{}, {'gbdt':[later]},NOW+timedelta(minutes=10)),2)
        before=copy.deepcopy(markets);later['model_version']='v2';later['market']['home_line']=-4.5
        self.assertEqual(r.seed_and_freeze_markets(markets,{}, {'gbdt':[later]},NOW+timedelta(minutes=20)),0);self.assertEqual(before,markets);self.assertEqual(first,original)

    def test_historical_import_requires_real_pregame_line_not_a_later_price(self):
        f=forecast();f['frozen_at_utc']=(NOW-timedelta(hours=2)).isoformat();f['generated_at_utc']=f['frozen_at_utc'];markets=[]
        self.assertEqual(r.seed_and_freeze_markets(markets,{'gbdt':[f]},{},NOW),0)
        f['market']['captured_at_utc']=f['frozen_at_utc'];self.assertEqual(r.seed_and_freeze_markets(markets,{'gbdt':[f]},{},NOW),2)
        post=forecast((NOW-timedelta(minutes=10)).isoformat());self.assertEqual(r.seed_and_freeze_markets([],{}, {'gbdt':[post]},NOW),0)

    def test_score_correction_keeps_predictions_and_previous_settlement(self):
        g={**game(),'status':'post','home_score':124,'away_score':112};f=forecast(g['date']);f['generated_at_utc']=(NOW-timedelta(hours=5)).isoformat();f['frozen_at_utc']=f['generated_at_utc'];before=copy.deepcopy(f)
        self.assertTrue(r.settle(f,g,NOW));self.assertFalse(r.settle(f,g,NOW+timedelta(minutes=1)))
        self.assertTrue(r.settle(f,{**g,'home_score':123},NOW+timedelta(minutes=2)));self.assertEqual(len(f['settlement_revisions']),1)
        for k,v in before.items():self.assertEqual(f[k],v)
        self.assertFalse(r.settle(f,{**g,'away':'BOS'},NOW))

    def test_quote_date_teams_age_and_posttip_gate(self):
        f=forecast();quote={'event_id':'1','date':f['date'],'home':'GSW','away':'LAC','captured_at_utc':NOW.isoformat(),'spread':{'home_line':-3.5}}
        self.assertTrue(r.quote_ok(quote,f,NOW));self.assertIsNone(r.choose_quote([{**quote,'home':'BOS'}],f,NOW));self.assertFalse(r.quote_ok({**quote,'captured_at_utc':(NOW-timedelta(hours=7)).isoformat()},f,NOW))

    def test_first_window_and_freshness(self):
        f=forecast();rows=[];self.assertEqual(r.freeze_first(rows,[f],NOW,NOW.isoformat()),1);self.assertEqual(r.freeze_first(rows,[{**f,'model_version':'v2'}],NOW,NOW.isoformat()),0)
        self.assertEqual(r.freeze_first([], [f],NOW,(NOW-timedelta(hours=7)).isoformat()),0)
        self.assertEqual(r.freeze_first([], [forecast((NOW+timedelta(days=2)).isoformat())],NOW,NOW.isoformat()),0)

    def test_provider_normalization_keeps_id_and_tip(self):
        raw={'events':[{'id':'1','date':game()['date'],'status':{'type':{'state':'post'}},'competitions':[{'competitors':[{'homeAway':'home','team':{'abbreviation':'GSW'},'score':'124'},{'homeAway':'away','team':{'abbreviation':'LAC'},'score':'112'}]}]}]}
        n=s.normalize_espn(raw)[0];self.assertEqual(n['event_id'],'1');self.assertEqual(n['home'],'GS');self.assertEqual(n['date'],game()['date'])
        with tempfile.TemporaryDirectory()as folder:
            root=Path(folder);r.write(root/'scoreboard.json',{'old':True})
            def unavailable(_):raise OSError('unavailable')
            self.assertIsNone(s.run(root,NOW,unavailable));self.assertEqual(r.read(root/'scoreboard.json',{}),{'old':True})

if __name__=='__main__':unittest.main()
