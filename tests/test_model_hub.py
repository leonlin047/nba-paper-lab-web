import copy,sys,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import model_hub as h
class ModelHubTests(unittest.TestCase):
    def test_related_models_do_not_gain_extra_votes(self):
        y=np.array([0.,1.]*20);v={'elo':np.array([.2,.8]*20),'factor':np.array([.8,.2]*20),'gbdt':np.array([.8,.2]*20)}
        w=h.select_weights(v,y,'moneyline');self.assertEqual(w,[1,0,0]);self.assertAlmostEqual(sum(w),1)
        better={**v,'gbdt':np.array([.1,.9]*20)};w=h.select_weights(better,y,'moneyline');self.assertGreater(w[2],0);self.assertGreaterEqual(w[0],.25)

    def test_split_never_shares_calendar_day_and_insufficient_period_fails(self):
        rows=[{'event_id':str(i),'day':f'2025-01-{1+i//4:02d}'}for i in range(40)];a,b=h.split_days(rows,8);self.assertLess(max(r['day']for r in a),min(r['day']for r in b))
        with self.assertRaises(ValueError):h.split_days(rows,100)

    def test_probability_mixture_keeps_push_and_is_not_gaussian_mean_shortcut(self):
        pool={'weights':{'margin':[.5,0,.5]},'profiles':{'margin':{k:{'errors':[-2,-1,0,1,2]}for k in h.KINDS}}};values={'elo':-10,'factor':0,'gbdt':10}
        result=h.mixed_line(values,pool,'margin',0);self.assertAlmostEqual(sum(result.values()),1);self.assertAlmostEqual(result['positive'],result['negative'])
        interval=h.interval(values,pool,'margin');self.assertLess(interval[0],0);self.assertGreater(interval[1],0)

    def test_heldout_labels_do_not_select_pool_weights(self):
        rows=[]
        for season,n,start in [(2025,500,datetime(2024,10,1)),(2026,120,datetime(2025,10,1))]:
            for i in range(n):
                day=(start+timedelta(days=i//2)).date().isoformat();rows.append({'event_id':f'{season}-{i}','day':day,'season':season,'p':.55,'margin_base':2.,'total_base':220.,'side':[0]*4,'total':[0]*3,'y':i%2,'margin_y':5. if i%2 else -5.,'total_y':218.+i%7})
        factors={'models':{t:{'weights':[0]*(3 if t=='total'else 4),'scale':0}for t in h.c.TARGETS}}
        def deterministic(rs,kind,target,*_):return np.array([r['p']if target=='moneyline'else r[target+'_base']for r in rs])
        with patch.object(h,'raw',side_effect=deterministic):
            first=h.development(rows,{},factors)
            for r in rows:
                if r['season']==2026:r.update(y=1-r['y'],margin_y=999.,total_y=999.)
            changed=h.development(rows,{},factors)
        self.assertEqual(first['weights'],changed['weights']);self.assertNotEqual(first['metrics']['candidate']['total']['mae'],changed['metrics']['candidate']['total']['mae'])

    def test_private_unready_models_never_receive_weights(self):
        registry=h.registry({'as_of_utc':'2026-11-02T01:00:00+00:00','apex_eligible_games':0,'online_trained_pairs':46},datetime(2026,11,2,12,tzinfo=timezone.utc))
        enabled=[m['id']for m in registry['models']if m['participates']];self.assertEqual(enabled,list(h.KINDS));self.assertFalse(registry['automatic_promotion']);self.assertFalse(registry['all_models_weighted'])

if __name__=='__main__':unittest.main()
