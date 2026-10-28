"""Context integration: provenance, unknown availability, cache and frozen labels."""
import copy,json,pathlib,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import context_factors as c
NOW=datetime(2026,10,27,18,tzinfo=timezone.utc)
GAME={'id':'next','date':(NOW+timedelta(hours=6)).isoformat(),'status':'pre','season_phase':2,'home':'BOS','away':'NY'}

def fixtures(n=4):
    out={}
    for i in range(n):
        date=(NOW-timedelta(days=6-i)).isoformat();event={'id':str(i),'date':date,'home':'BOS','away':'NY','home_score':110,'away_score':100,'season_year':2027}
        players={t:[{'name':t+str(j),'minutes':30.,'athlete_id':str(j+1),'position':'C' if j==0 else 'G','points':10,'rebounds':3,'assists':2}for j in range(8)]for t in('BOS','NY')}
        teams=[{'team':t,'game_id':str(i),'estimated_possessions':100,'eFG_pct':55 if t=='BOS'else 50,'turnover_per_est_poss_pct':12,'free_throw_attempt_rate':25,'three_point_attempt_rate':42,'oreb_pct':25}for t in('BOS','NY')]
        out[str(i)]=c.archive_event(event,players,teams,(NOW-timedelta(minutes=30)).isoformat(),48)
    return {'events':out}

def injury(player='BOS0',status='Out'):
    return {'captured_at':(NOW-timedelta(minutes=20)).isoformat(),'source':'fixture','errors':[],'injuries':[{'team':'BOS','player':player,'status':status,'date':(NOW-timedelta(hours=1)).isoformat()}]}

class ContextTests(unittest.TestCase):
    def test_known_role_is_not_ability_loss_and_unreported_not_cleared(self):
        r=c.observe(GAME,fixtures(),injury(),NOW)
        self.assertEqual(r['lineup']['home']['matched_out_role_minutes'],30)
        self.assertEqual(r['lineup']['away']['explicit_available'],[])
        self.assertIsNone(r['lineup']['home']['replacement_ability']);self.assertIsNone(r['lineup']['home']['official_starting_lineup'])
        self.assertFalse(r['affects_predictions']);self.assertTrue(all(f['predictive_weight']==0 for f in r['factors']))

    def test_duplicates_do_not_double_count_role_minutes(self):
        x=injury();x['injuries']*=2
        self.assertEqual(c.observe(GAME,fixtures(),x,NOW)['lineup']['home']['matched_out_role_minutes'],30)
        x['injuries'][1]={**x['injuries'][1],'status':'Day-To-Day'}
        r=c.observe(GAME,fixtures(),x,NOW)
        self.assertEqual(r['lineup']['home']['out'],[]);self.assertEqual(len(r['lineup']['home']['uncertain']),1)

    def test_known_conflicting_player_ids_do_not_join_by_name(self):
        report=injury();report['injuries'][0]['athlete_id']='999'
        r=c.observe(GAME,fixtures(),report,NOW)
        self.assertFalse(r['lineup']['home']['out'][0]['matched_recent_role'])
        self.assertIsNone(r['factors'][0]['candidate_points'])

    def test_uncertain_missing_late_or_stale_reports_are_unknown(self):
        variants=[injury(status='Day-To-Day'),injury(player='Unseen rookie'),{**injury(),'captured_at':(NOW-timedelta(hours=7)).isoformat()},{**injury(),'captured_at':(NOW+timedelta(minutes=1)).isoformat()},{**injury(),'errors':['failed']},{**injury(),'injuries':[]}]
        later=injury();later['injuries'][0]['date']=(NOW+timedelta(hours=2)).isoformat();variants.append(later)
        for x in variants:
            r=c.observe(GAME,fixtures(),x,NOW)
            self.assertIsNone(r['factors'][0]['candidate_points'])
        r=c.observe({**GAME,'date':(NOW+timedelta(hours=50)).isoformat()},fixtures(),injury(),NOW)
        self.assertFalse(r['lineup']['home']['snapshot_usable'])

    def test_same_day_future_and_late_captured_boxscores_are_excluded(self):
        history=fixtures();valid=c.observe(GAME,history,injury(),NOW)
        bad=copy.deepcopy(history['events']['0'])
        for key,date,captured in [('same','2026-10-27T17:00:00+00:00',NOW.isoformat()),('future',(NOW+timedelta(hours=2)).isoformat(),(NOW+timedelta(hours=3)).isoformat()),('late',bad['date'],(NOW+timedelta(minutes=1)).isoformat())]:
            history['events'][key]={**bad,'event_id':key,'date':date,'captured_at_utc':captured}
        actual=c.observe(GAME,history,injury(),NOW)
        self.assertEqual(valid['input_events'],actual['input_events']);self.assertEqual(valid['factors'],actual['factors'])

    def test_historical_prediction_cannot_use_boxscore_collected_later(self):
        game={**GAME,'date':(NOW-timedelta(days=1)).isoformat()}
        self.assertFalse(c.eligible_events(fixtures()['events'],game,NOW))

    def test_incomplete_or_duplicate_players_do_not_create_full_rotation(self):
        h=fixtures()
        for e in h['events'].values():e['players']['BOS']=e['players']['BOS'][:4]
        r=c.observe(GAME,h,injury(),NOW)
        self.assertEqual(r['lineup']['home']['team_games'],0);self.assertIsNone(r['lineup']['home']['matched_out_role_minutes'])

    def test_overtime_normalizes_pace_proxy_and_insufficient_samples_stay_null(self):
        h=fixtures()
        for e in h['events'].values():e['duration_minutes']=53
        r=c.observe(GAME,h,injury(),NOW)
        self.assertAlmostEqual(r['technical']['home']['pace48'],90.57,2)
        r=c.observe(GAME,fixtures(2),injury(),NOW)
        self.assertIsNone(r['technical']['home']['pace48']);self.assertIsNone(r['factors'][2]['candidate_points'])

    def test_empty_injury_list_does_not_clear_a_team(self):
        r=c.observe(GAME,fixtures(),{**injury(),'injuries':[]},NOW)
        self.assertFalse(r['lineup']['home']['snapshot_usable']);self.assertIsNone(r['lineup']['home']['matched_out_role_minutes'])

    def test_ingestion_and_snapshots_are_idempotent_and_first_freeze_immutable(self):
        history=fixtures()
        with tempfile.TemporaryDirectory()as directory:
            root=pathlib.Path(directory);c.write(root/'context-history.json',history);c.write(root/'games.json',{'games':[GAME]});c.write(root/'injuries.json',injury())
            a=c.run(root,NOW);first=c.read(root/'context-pregame-ledger.json',{})['records']
            b=c.run(root,NOW+timedelta(minutes=5));second=c.read(root/'context-pregame-ledger.json',{})['records']
            self.assertEqual(first,second);self.assertEqual(b['prospective']['new_frozen'],0);self.assertEqual(b['coverage']['distinct_injury_snapshots'],1)
            self.assertEqual(b['ingestion']['new_events'],0);self.assertEqual(b['ingestion']['network_requests'],0)
            c.write(root/'injuries.json',injury(status='Available'));c.run(root,NOW+timedelta(minutes=10))
            self.assertEqual(first,c.read(root/'context-pregame-ledger.json',{})['records'])
            self.assertEqual(len(c.read(root/'context-injury-history.json',{})['snapshots']),2)

    def test_settlement_requires_same_game_and_real_freeze(self):
        r={**c.observe(GAME,fixtures(),injury(),NOW),'frozen_at_utc':NOW.isoformat(),'settlement':None}
        final={**GAME,'home_score':110,'away_score':100}
        c.settle(r,{**final,'home':'MIA'},NOW+timedelta(hours=12));self.assertIsNone(r['settlement'])
        c.settle(r,final,NOW+timedelta(hours=12));self.assertEqual(r['settlement']['home_margin'],10)
        self.assertEqual(r['settlement']['kind'],'feature_observation_labels_not_model_accuracy')
        late={**r,'settlement':None,'frozen_at_utc':GAME['date']};c.settle(late,final,NOW+timedelta(hours=12));self.assertIsNone(late['settlement'])

    def test_backfill_requests_bound_and_failure_cache(self):
        calls=[]
        def fetch(i):calls.append(i);raise OSError('unavailable')
        games=[{**GAME,'id':str(i),'status':'post','date':(NOW-timedelta(days=3)).isoformat(),'home_score':110,'away_score':100}for i in range(20)]
        with tempfile.TemporaryDirectory()as directory:
            root=pathlib.Path(directory)
            _,a=c.merge_archive(root,{'games':games},NOW,True,fetch)
            self.assertEqual(a['network_requests'],12)
            _,b=c.merge_archive(root,{'games':games},NOW,True,fetch)
            self.assertEqual(b['network_requests'],8)
            _,d=c.merge_archive(root,{'games':games},NOW,True,fetch)
            self.assertEqual(d['network_requests'],0)
        self.assertEqual(len(calls),20)

    def test_cached_final_detail_requires_matching_score_and_original_time(self):
        game={**GAME,'id':'a','status':'post','date':(NOW-timedelta(days=2)).isoformat(),'home_score':110,'away_score':100}
        detail={'event_id':'a','boxscore':[{'team':t,'players':[{'name':'X','stats':{'MIN':'30'}}]}for t in('BOS','NY')]}
        previous={'games':[game],'details':[detail],'captured_at':(NOW-timedelta(hours=1)).isoformat()};boxes={'rows':[{'game_id':'a','team':t}for t in('BOS','NY')]}
        cached=c.cached_final_detail(previous,boxes,game,NOW)
        self.assertEqual(cached['detail']['captured_at_utc'],previous['captured_at']);self.assertNotIn('captured_at_utc',detail)
        self.assertIsNone(c.cached_final_detail(previous,boxes,{**game,'home_score':111},NOW))
        self.assertIsNone(c.cached_final_detail({**previous,'captured_at':(NOW-timedelta(hours=25)).isoformat()},boxes,game,NOW))
        self.assertIsNone(c.cached_final_detail({**previous,'captured_at':(NOW+timedelta(hours=1)).isoformat()},boxes,game,NOW))

if __name__=='__main__':unittest.main()
