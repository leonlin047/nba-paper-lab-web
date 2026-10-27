"""Leakage, immutable first freezes, cache idempotency and real-line safeguards."""
import copy,json,pathlib,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import factor_scorecard as f
NOW=datetime(2026,10,27,18,tzinfo=timezone.utc)

def row(season=2026,i=0):
    return {'event_id':str(i),'date':(NOW+timedelta(hours=12)).isoformat(),'day':'2026-10-28','season':season,'home':'BOS','away':'NY','p':.6,'margin_base':3.,'total_base':220.,'side':[1,1,None,0],'total':[1,0,None],'evidence':{},'last_input_game':'2026-10-26T00:00:00Z','y':i%2,'margin_y':5 if i%2 else -5,'total_y':218+i%7}
def fit():
    return {'models':{t:{'weights':[1]*len(rules),'scale':.1 if t=='moneyline' else 1,'rules':[{'id':a,'label':b,'group':c,'weight':1}for a,b,c in rules]} for t,rules in f.RULES.items()},'sigmas':{'margin':14,'total':20},'train_n':1000,'validation_n':500,'test_n':500,'metrics':{}}

class ScorecardTests(unittest.TestCase):
    def test_group_cap_missing_distinct_and_push_probability(self):
        self.assertEqual(f.score([1,1,None,0],[2,2,2,2],f.SIDE),2)
        parts=f.contributions(row(),'moneyline',fit()['models']['moneyline'])
        self.assertIsNone(parts['parts'][2]['points']);self.assertEqual(parts['parts'][3]['points'],0)
        for total,line in [(False,-3),(False,-3.5),(True,220),(True,220.5)]:
            p=f.probabilities(220 if total else 3,20,line,total)
            self.assertAlmostEqual(sum(p.values()),1);self.assertTrue(all(0<=v<=1 for v in p.values()))
            self.assertEqual(p['push']>0,float(line).is_integer())
        self.assertIsNone(f.probabilities(1,10,None))

    def test_held_out_labels_do_not_select_weights_or_scales(self):
        rows=[row(season,i)for season in (2023,2024,2025,2026)for i in range(500)]
        a=f.fit_models(rows)
        for r in rows:
            if r['season']==2026:r.update(y=1-r['y'],margin_y=999,total_y=999)
        b=f.fit_models(rows)
        self.assertEqual(a['models'],b['models']);self.assertEqual(a['sigmas'],b['sigmas'])
        self.assertTrue(all(type(w)is int and -2<=w<=2 for m in a['models'].values()for w in m['weights']))

    def test_same_day_and_future_labels_do_not_change_earlier_predictions(self):
        history=[]
        for i in range(65):
            history.append({'id':str(i),'date':(NOW-timedelta(days=70-i)).isoformat(),'home':'BOS','away':'NY','home_score':110+i%5,'away_score':100,'season_end':2026})
        early={'id':'early','date':'2026-10-27T00:00:00Z','home':'BOS','away':'NY','home_score':100,'away_score':90,'season_end':2027}
        later={**early,'id':'later','date':'2026-10-27T04:00:00Z'}
        future={**early,'id':'future','date':'2026-10-27T12:00:00Z'}
        a=f.build_records(history+[early,later,future],[],NOW)
        early['home_score']=200;future['home_score']=200
        b=f.build_records(history+[early,later,future],[],NOW)
        ar=next(r for r in a if r['event_id']=='later');br=next(r for r in b if r['event_id']=='later')
        for key in ['p','margin_base','total_base','side','total','last_input_game']:self.assertEqual(ar[key],br[key])
        self.assertLess(f.day_of(ar['last_input_game']),ar['day'])

    def test_first_freeze_and_cache_are_idempotent_and_no_posttip_backfill(self):
        future=row();future.update(y=None,margin_y=None,total_y=None)
        with tempfile.TemporaryDirectory()as directory:
            root=pathlib.Path(directory)
            with patch.object(f,'build_records',return_value=[future]),patch.object(f,'fit_models',return_value=fit())as fitter:
                a=f.run(root,NOW);before=json.loads((root/'factor-pregame-ledger.json').read_text())['records']
                b=f.run(root,NOW+timedelta(minutes=10));after=json.loads((root/'factor-pregame-ledger.json').read_text())['records']
                self.assertEqual(fitter.call_count,1);self.assertEqual(before,after);self.assertTrue(b['cache']['fit_reused']);self.assertEqual(b['cache']['old_samples_refit'],0)
                self.assertEqual(a['prospective']['new_frozen'],1);self.assertEqual(b['prospective']['new_frozen'],0)
                self.assertGreaterEqual(len(a['forecasts'][0]['report_zh']),200)
        with tempfile.TemporaryDirectory()as directory:
            with patch.object(f,'build_records',return_value=[future]),patch.object(f,'fit_models',return_value=fit()):
                result=f.run(pathlib.Path(directory),NOW+timedelta(hours=13))
                self.assertEqual(result['prospective']['new_frozen'],0)

    def test_archived_line_requires_verified_match_and_hour_before_tip(self):
        r=row();q={'join_verified':True,'eligible_for_pregame_backtest':True,'observed_at_utc':(NOW-timedelta(minutes=1)).isoformat(),'home':'BOS','away':'NY','spread':{'home_line':-3.5},'total':{'line':220.5}}
        archive={'games':{'0':{'first':q}}}
        self.assertEqual(len(f.odds_replay([r],fit(),archive,NOW)['rows']),1)
        for change in [{'home':'MIA'},{'join_verified':False},{'observed_at_utc':r['date']},{'observed_at_utc':(NOW+timedelta(minutes=1)).isoformat()}]:
            bad=copy.deepcopy(archive);bad['games']['0']['first'].update(change)
            self.assertFalse(f.odds_replay([r],fit(),bad,NOW)['rows'])

if __name__=='__main__':unittest.main()
