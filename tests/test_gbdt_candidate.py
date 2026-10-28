"""Chronology, persisted offsets, quote identity, first publication and cache safety."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import gbdt_candidate as c

NOW=datetime(2026,10,28,18,tzinfo=timezone.utc)
SMALL=[{'num_leaves':3,'min_data_in_leaf':5,'rounds':8}]
def row(i,start=datetime(2020,1,1,tzinfo=timezone.utc),p=.8):
    dt=start+timedelta(days=i)
    return {'event_id':str(i),'date':dt.isoformat(),'day':c.day_of(dt.isoformat()),'season':2020,'home':'NY','away':'DET','p':p,'margin_base':6.,'total_base':220.,'side':[0,0,1,-1],'total':[1,0,0], 'evidence':{'home_gap_hours':48.,'away_gap_hours':24.,'home_games_7d':2,'away_games_7d':3,'home_recent_n':12,'away_recent_n':12},'last_input_game':(dt-timedelta(days=1)).isoformat(),'y':i%2,'margin_y':10. if i%2 else -8.,'total_y':215.+i%9}

def forecast(event='a',hours=2):
    return {'event_id':event,'date':(NOW+timedelta(hours=hours)).isoformat(),'home':'NY','away':'DET','model_version':'v1','home_win_probability':.6,'baseline':{'home_win_probability':.55},'market':{'home_line':-2.5,'total_line':220.,'home_no_vig_probability':.58},'cover':{'positive':.6,'negative':.4},'totals':{'positive':.4,'negative':.5},'selection':{'moneyline':True,'quality_reasons':[]}}

class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=[row(i)for i in range(180)]
        cls.bundle=c.fit_bundle(cls.rows[:80],cls.rows[80:120],cls.rows[120:],SMALL)

    def test_features_cannot_read_labels_or_future_observations(self):
        a=row(1);b=copy.deepcopy(a);b.update(y=0,margin_y=999,total_y=999,market={'future':True},lineup={'future':True})
        np.testing.assert_equal(c.feature_vector(a),c.feature_vector(b));self.assertEqual(len(c.feature_vector(a)),20)
        b['evidence']['home_gap_hours']=None;self.assertTrue(np.isnan(c.feature_vector(b)[3]))

    def test_periods_reject_shared_days_and_duplicate_ids(self):
        a=row(1);b=row(2);b['day']=a['day']
        with self.assertRaises(ValueError):c.assert_periods([a],[b])
        with self.assertRaises(ValueError):c.assert_periods([a,a],[row(3)])

    def test_native_serialization_keeps_explicit_elo_offset(self):
        model=c.train_tree(self.rows[:80],'moneyline',SMALL[0]);rs=self.rows[80:84]
        delta=c.correction(model,rs);booster=c.lgb.Booster(model_str=model)
        np.testing.assert_allclose(delta,booster.predict(c.matrix(rs),raw_score=True,num_threads=1))
        restored=c.sigmoid(c.logit(c.base(rs,'moneyline'))+delta)
        self.assertTrue(np.all(np.abs(restored-c.sigmoid(delta))>.1))
        np.testing.assert_allclose(c.correction(booster.model_to_string(),rs),delta)

    def test_predictions_ignore_heldout_labels_and_bundle_has_disjoint_calibration(self):
        a=[row(181)];b=copy.deepcopy(a);b[0].update(y=1-a[0]['y'],margin_y=500,total_y=600)
        for target in c.TARGETS:np.testing.assert_equal(c.predict(a,self.bundle)[target],c.predict(b,self.bundle)[target])
        periods=self.bundle['periods'];self.assertLess(periods['train'][1],periods['validation'][0]);self.assertLess(periods['validation'][1],periods['calibration'][0])

    def test_per_target_fixed_architecture(self):
        specs={t:[{**SMALL[0],'rounds':i+2}]for i,t in enumerate(c.TARGETS)}
        b=c.fit_bundle(self.rows[:80],self.rows[80:120],self.rows[120:],configs_by_target=specs)
        for t in c.TARGETS:self.assertEqual(b['models'][t]['config'],specs[t][0])

    def test_calibration_has_valid_ordered_probability_and_rejects_bad_labels(self):
        raw=np.array([-2.,-1.,0.,1.,2.]*20);y=np.array([0,0,1,1,1]*20)
        fit=c.fit_platt(raw,y);p=c.platt(np.array([-2.,0.,2.]),fit)
        self.assertTrue(np.all((p>0)&(p<1)));self.assertTrue(np.all(np.diff(p)>0))
        with self.assertRaises(ValueError):c.fit_platt([1.],[2.])

    def test_integer_halfpoint_push_and_unsupported_quarter_lines(self):
        errors=[-2.,-1.,0.,1.,2.]
        for line in (-2.,-2.5,0.,.5):
            p=c.line_probabilities(0,errors,line);self.assertAlmostEqual(p['positive']+p['negative']+p['push'],1.)
        self.assertGreater(c.line_probabilities(0,errors,0.)['push'],0)
        self.assertEqual(c.line_probabilities(0,errors,.5)['push'],0)
        self.assertIsNone(c.line_probabilities(0,errors,.25))
        self.assertIsNone(c.line_probabilities(0,errors,True))

    def test_quotes_require_same_event_teams_date_and_observation_before_prediction(self):
        f=forecast();m={'event_id':'a','home':'NYK','away':'DET','date':f['date'],'captured_at_utc':(NOW-timedelta(minutes=1)).isoformat()}
        self.assertTrue(c.valid_market(m,f,NOW))
        for changes in ({'event_id':'b'},{'home':'BOS'},{'date':(NOW+timedelta(days=1)).isoformat()},{'captured_at_utc':(NOW+timedelta(seconds=1)).isoformat()}):self.assertFalse(c.valid_market({**m,**changes},f,NOW))
        self.assertIsNone(c.observed_market([{**m,'home':'BOS'}],f,NOW))

    def test_lineup_gate_requires_fresh_matching_timestamped_observation(self):
        f=forecast();ctx={'event_id':'a','date':f['date'],'home':'NY','away':'DET','generated_at_utc':NOW.isoformat(),'lineup':{'injury_snapshot_at_utc':NOW.isoformat(),'home':{'snapshot_usable':True},'away':{'snapshot_usable':True}}}
        self.assertTrue(c.valid_context(ctx,f,NOW))
        for changes in ({'home':'BOS'},{'generated_at_utc':(NOW-timedelta(hours=7)).isoformat()},{'generated_at_utc':(NOW+timedelta(minutes=1)).isoformat()}):self.assertFalse(c.valid_context({**ctx,**changes},f,NOW))

    def test_first_freeze_is_immutable_across_model_versions_no_retroactive_entry(self):
        ledger=[];self.assertEqual(c.freeze_forecasts(ledger,[forecast()],NOW),1);first=copy.deepcopy(ledger)
        self.assertEqual(c.freeze_forecasts(ledger,[{**forecast(),'model_version':'v2','home_win_probability':.9}],NOW),0);self.assertEqual(ledger,first)
        self.assertEqual(c.freeze_forecasts(ledger,[forecast('past',-1),forecast('late',.5),forecast('early',25)],NOW),0)
        stale=forecast('stale');stale['selection']['quality_reasons']=['schedule_or_results_snapshot_stale'];self.assertEqual(c.freeze_forecasts(ledger,[stale],NOW),0)

    def test_settlement_identity_push_and_paired_sample(self):
        f=forecast();ledger=[];c.freeze_forecasts(ledger,[f],NOW);r=ledger[0]
        game={'id':'a','date':f['date'],'home':'NY','away':'DET','status':'post','season_phase':2,'home_score':112,'away_score':108}
        # Source validation is independently tested in analyst_factors; test ledger guards here.
        with patch.object(c,'valid_final',return_value=True):
            c.settle(r,{**game,'home':'BOS'},NOW+timedelta(hours=5));self.assertIsNone(r['settlement'])
            c.settle(r,game,NOW+timedelta(hours=5))
        self.assertTrue(r['settlement']['total']['push']);self.assertTrue(r['settlement']['spread']['hit'])
        stats=c.prospective_stats(ledger);self.assertEqual(stats['all']['market_paired_n'],1);self.assertEqual(stats['all']['total'],{'n':0,'correct':0,'push':1})
        self.assertEqual(stats['selected']['n'],stats['all']['n'])

    def test_results_memory_survives_rolling_window_and_accepts_only_same_identity_corrections(self):
        game={'id':'a','date':(NOW-timedelta(days=1)).isoformat(),'home':'NY','away':'DET','status':'post','season_phase':2,'season_year':2027,'home_score':110,'away_score':100}
        archive,ingest=c.accumulate_results({},[game],NOW);self.assertEqual(ingest['new_results'],1)
        archive2,ingest=c.accumulate_results(archive,[],NOW+timedelta(days=30));self.assertEqual(archive2,archive)
        same,ingest=c.accumulate_results(archive,[game,game],NOW);self.assertEqual(ingest['new_results'],0);self.assertEqual(same,archive)
        changed,ingest=c.accumulate_results(archive,[{**game,'home_score':111}],NOW);self.assertEqual(ingest['corrected_results'],1);self.assertEqual(changed['games'][0]['home_score'],111)
        wrong,ingest=c.accumulate_results(archive,[{**game,'home':'BOS'}],NOW);self.assertEqual(wrong,archive)
        self.assertEqual(changed['games'][0]['first_observed_at_utc'],archive['games'][0]['first_observed_at_utc'])

    def test_weekly_cache_only_refits_for_new_labels_or_consumed_corrections(self):
        rows=[row(i)for i in range(2100)];now=datetime(2026,10,28,tzinfo=timezone.utc)
        chosen={'models':{t:{'config':SMALL[0]}for t in c.TARGETS}}
        fake={'train_n':1100,'validation_n':500,'calibration_n':500}
        with patch.object(c,'fit_bundle',return_value=fake)as fit:
            first,reused,_=c.live_fit(rows,chosen,{},'code',now);self.assertFalse(reused)
            cache={'code':'code','live':first};rows.append(row(2100))
            second,reused,new=c.live_fit(rows,chosen,cache,'code',now+timedelta(days=1));self.assertTrue(reused);self.assertEqual(new,1);self.assertEqual(fit.call_count,1)
            _,reused,_=c.live_fit(rows,chosen,cache,'code',now+timedelta(days=7));self.assertFalse(reused)
            _,reused,_=c.live_fit(rows[:-1],chosen,cache,'code',now+timedelta(days=7));self.assertTrue(reused)
            rows[0]['margin_y']+=1
            _,reused,_=c.live_fit(rows,chosen,cache,'code',now);self.assertFalse(reused)

if __name__=='__main__':unittest.main()
