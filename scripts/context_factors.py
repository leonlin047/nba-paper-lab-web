"""Point-in-time lineup and technical matchup observations, zero predictive weight.

No inferred medical diagnosis, official starting lineup, RAPM rating or replacement
ability is claimed. Public final box scores are cached once; injury snapshots are
content-addressed. Missing data are null, not a healthy roster or zero minutes.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re,unicodedata
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from statistics import mean
from urllib.request import Request,urlopen
from analyst_factors import canon,when,valid_final,extract_four_factors
UTC=timezone.utc
TW=timezone(timedelta(hours=8))
SCHEMA=1
VERSION='context-v1-'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
RULES=[('rotation_loss','已報缺陣角色差','side'),('load','核心上場負荷差','side'),('shooting','投籃效率對位差','side'),('turnovers','球權失誤對位差','side'),('rebounds','進攻籃板對位差','side'),('pace','回合數相對近期基準','total'),('variance','三分出手依賴','uncertainty')]

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def write(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n');temp.replace(path)

def name_key(name):
    return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(name)).encode('ascii','ignore').decode().lower())

def number(v):
    if v is None or isinstance(v,bool) or v=='':return None
    try:x=float(v)
    except (ValueError,TypeError):return None
    return x if math.isfinite(x) else None

def minutes(value):
    if isinstance(value,str) and ':' in value:
        try:m,s=value.split(':');x=int(m)+int(s)/60
        except (ValueError,TypeError):return None
    else:x=number(value)
    return x if x is not None and 0<=x<=70 else None

def actual_player(p):
    stats=p.get('stats') or {};mins=minutes(stats.get('MIN'));name=p.get('name')
    if not name:return None
    if mins is None and str(stats.get('MIN','')).upper().startswith(('DNP','DND','INACTIVE')):mins=0
    if mins is None:return None
    return {'name':name,'athlete_id':p.get('athlete_id'),'position':p.get('position'),'minutes':mins,
            'points':number(stats.get('PTS')),'rebounds':number(stats.get('REB')),'assists':number(stats.get('AST'))}

def parse_summary(raw,g,observed):
    players={};duration=None
    for t in (raw.get('boxscore') or {}).get('players',[]):
        team=canon((t.get('team') or {}).get('abbreviation'));rows=[]
        if team not in (canon(g['home']),canon(g['away'])):continue
        for group in t.get('statistics',[]):
            for p in group.get('athletes',[]):
                a=p.get('athlete') or {};item=actual_player({'name':a.get('displayName'),'athlete_id':str(a['id']) if a.get('id') else None,'position':(a.get('position') or {}).get('abbreviation'),'stats':dict(zip(group.get('labels',[]),p.get('stats',[])))})
                if item:rows.append(item)
        players[team]=rows
    counts=[]
    for c in (raw.get('header') or {}).get('competitions',[]):
        counts.extend(len(t.get('linescores',[])) for t in c.get('competitors',[]))
    if len(counts)==2 and counts[0]==counts[1] and 4<=counts[0]<=8:duration=48+5*(counts[0]-4)
    teams=extract_four_factors(raw,g['id'],observed)
    return archive_event(g,players,teams,observed,duration)

def archive_event(g,players,teams,observed,duration=None):
    clean={}
    for t,rows in players.items():
        dedup={name_key(p['name']):p for p in rows};clean[canon(t)]=list(dedup.values())
    return {'event_id':str(g['id']),'date':g['date'],'home':canon(g['home']),'away':canon(g['away']),
            'home_score':g['home_score'],'away_score':g['away_score'],'season_year':g.get('season_year',g.get('season_end')),
            'captured_at_utc':observed,'duration_minutes':duration,'players':clean,'teams':teams,
            'source_url':'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+str(g['id'])}

def valid_archive(e,now):
    captured=when(e.get('captured_at_utc'));date=when(e.get('date'))
    return bool(captured and date and date<captured<=now and e.get('home')!=e.get('away') and valid_final({'home':e.get('home'),'away':e.get('away'),'date':e.get('date'),'home_score':e.get('home_score'),'away_score':e.get('away_score')},now))

def fetch_summary(event_id):
    url='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event='+str(event_id)
    with urlopen(Request(url,headers={'User-Agent':'Court-Noir-research/1.0','Accept':'application/json'}),timeout=15)as response:
        raw=response.read(2500001)
    if len(raw)>2500000:raise ValueError('summary exceeds bound')
    return json.loads(raw)

def merge_archive(root,public,now,backfill=False,fetcher=fetch_summary):
    path=root/'context-history.json';history=read(path,{'schema_version':SCHEMA,'events':{},'attempts':{}});events=history['events'];added=0
    observed=public.get('captured_at');lookup={str(g['id']):g for g in public.get('games',[]) if g.get('status')=='post' and g.get('season_phase') in (2,3) and valid_final(g,now)}
    teams=defaultdict(list)
    for t in read(root/'box_factors.json',{}).get('rows',[]):teams[str(t.get('game_id'))].append(t)
    for d in public.get('details',[]):
        event_id=str(d.get('event_id'));g=lookup.get(event_id)
        if not g or event_id in events:continue
        players={canon(b.get('team')):[p for p in (actual_player(x)for x in b.get('players',[]))if p]for b in d.get('boxscore',[])}
        counts=[len(x.get('quarters',[])) for x in d.get('quarter_scores',[])];duration=48+5*(counts[0]-4) if len(counts)==2 and counts[0]==counts[1] and 4<=counts[0]<=8 else None
        event=archive_event(g,players,teams[event_id],d.get("captured_at_utc")or observed,duration)
        if valid_archive(event,now) and all(event['players'].get(t) for t in (event['home'],event['away'])):events[event_id]=event;added+=1
    fetched=0;errors=[];attempts=history.get('attempts',{})
    if backfill:
        missing=sorted((g for i,g in lookup.items() if i not in events and when(g['date'])>=now-timedelta(days=45)),key=lambda g:g['date'])
        for g in missing:
            if fetched>=12:break
            last=when((attempts.get(str(g['id']))or{}).get('at'))
            if last and now-last<timedelta(hours=6):continue
            fetched+=1
            try:
                raw=fetcher(g['id']);event=parse_summary(raw,g,now.isoformat())
                # Reject a summary for a different matchup/event, even on a valid endpoint.
                header=raw.get('header')or{}
                if str(header.get('id'))!=str(g['id']):raise ValueError('summary event mismatch')
                if not valid_archive(event,now) or not all(event['players'].get(t) for t in (event['home'],event['away'])):raise ValueError('summary lacks both valid rosters')
                events[str(g['id'])]=event;added+=1;attempts.pop(str(g['id']),None)
            except Exception as exc:
                attempts[str(g['id'])]={'at':now.isoformat(),'error':type(exc).__name__};errors.append(str(g['id'])+':'+type(exc).__name__)
    history.update(updated_at_utc=now.isoformat(),events=events,attempts=attempts,source_rights='review');write(path,history)
    return history,{'new_events':added,'network_requests':fetched,'cached_events':len(events),'errors':errors,'historical_season_coverage':sorted({e.get('season_year')for e in events.values()if e.get('season_year')})}

def injury_rows(snapshot):
    unique={}
    for row in snapshot.get('injuries',[]) if isinstance(snapshot.get('injuries'),list) else []:
        key=(canon(row.get('team')),name_key(row.get('player')))
        if not key[0]or not key[1]:continue
        old=unique.get(key)
        if old is None:unique[key]=dict(row);continue
        date=when(row.get('date'));previous=when(old.get('date'))
        if date and (not previous or date>previous):unique[key]=dict(row)
        elif date==previous and row.get('status')!=old.get('status'):unique[key]={**old,'status':'Unknown'}
    return list(unique.values())

def cached_final_detail(previous,boxes,game,now):
    old=next((g for g in previous.get('games',[])if str(g.get('id'))==str(game.get('id'))),None)
    if not old or old.get('status')!='post' or any(old.get(k)!=game.get(k)for k in('date','home_score','away_score'))or any(canon(old.get(k))!=canon(game.get(k))for k in('home','away')):return None
    detail=next((d for d in previous.get('details',[])if str(d.get('event_id'))==str(game['id'])),None)
    if not detail:return None
    captured=when(detail.get('captured_at_utc')or previous.get('captured_at'))
    if not captured or not when(game.get('date'))or not when(game['date'])<captured<=now or now-captured>=timedelta(hours=24):return None
    teams=[r for r in boxes.get('rows',[])if str(r.get('game_id'))==str(game['id'])]
    if {canon(r.get('team'))for r in teams}!={canon(game['home']),canon(game['away'])}:return None
    if {canon(r.get('team'))for r in detail.get('boxscore',[])if r.get('players')}!={canon(game['home']),canon(game['away'])}:return None
    from copy import deepcopy
    copied=deepcopy(detail);copied['captured_at_utc']=captured.isoformat()
    return {'detail':copied,'teams':deepcopy(teams)}

def snapshot_injuries(root,snapshot,now):
    archive=read(root/'context-injury-history.json',{'schema_version':SCHEMA,'snapshots':[]})
    captured=when(snapshot.get('captured_at'));rows=snapshot.get('injuries')
    if not captured or captured>now or snapshot.get('errors') or not isinstance(rows,list):return archive,None
    normalized=sorted(({'team':canon(r.get('team')),'player':r.get('player'),'athlete_id':r.get('athlete_id'),'status':r.get('status'),'date':r.get('date')}for r in injury_rows(snapshot) if r.get('team')and r.get('player')),key=lambda r:(r['team'],r['player']))
    digest=hashlib.sha256(json.dumps(normalized,sort_keys=True).encode()).hexdigest()
    current=next((x for x in archive['snapshots'] if x['hash']==digest),None)
    if current is None:
        current={'hash':digest,'first_observed_at_utc':captured.isoformat(),'last_observed_at_utc':captured.isoformat(),'source':snapshot.get('source'),'rows':normalized};archive['snapshots'].append(current)
    elif captured>=when(current['last_observed_at_utc']):current['last_observed_at_utc']=captured.isoformat()
    archive['updated_at_utc']=now.isoformat();write(root/'context-injury-history.json',archive)
    return archive,current

def eligible_events(events,game,now):
    tip=when(game.get('date'));day_start=datetime.combine(tip.astimezone(TW).date(),datetime.min.time(),TW).astimezone(UTC)
    cutoff=min(now,day_start)
    return sorted([e for e in events.values() if valid_archive(e,now) and when(e['date'])<cutoff and when(e['date'])>=now-timedelta(days=45) and when(e['captured_at_utc'])<=min(now,tip)],key=lambda e:(e['date'],e['event_id']))

def team_lineup(team,events,injuries,game,now):
    rows=[e for e in events if team in (e['home'],e['away'])][-5:];groups=defaultdict(list);ids=defaultdict(set);positions={};seen=set()
    complete=[]
    for e in rows:
        ps=e['players'].get(team,[]);total=sum(p['minutes']for p in ps)
        # Incomplete box scores cannot define the rotation or missing appearances.
        duration=e.get('duration_minutes');expected=5*duration if duration else 240
        if len([p for p in ps if p['minutes']>0])<5 or abs(total-expected)>8:continue
        complete.append(e)
        for p in ps:
            key=name_key(p['name']);ob=(e['event_id'],key)
            if ob in seen:continue
            seen.add(ob)
            if p['minutes']>0:groups[key].append((e,p));positions[key]=p.get('position')
            if p.get('athlete_id'):ids[key].add(p['athlete_id'])
    rotation=[]
    for key,observations in groups.items():
        active=observations[-3:];mins=mean(p['minutes']for _,p in active)
        rotation.append({'name':active[-1][1]['name'],'key':key,'active_games':len(active),'expected_minutes_proxy':round(mins,1),'position':positions.get(key),'last_played':active[-1][0]['date'],
                         'minutes_72h':round(sum(p['minutes']for e,p in observations if when(e['date'])>=now-timedelta(hours=72)),1),'athlete_ids':sorted(ids[key])})
    rotation.sort(key=lambda p:-p['expected_minutes_proxy']);index={p['key']:p for p in rotation};by_id={i:p for p in rotation for i in p['athlete_ids']}
    captured=when(injuries.get('captured_at'));tip=when(game['date'])
    usable=bool(captured and now-timedelta(hours=6)<=captured<=now and captured<tip and not injuries.get('errors') and isinstance(injuries.get('injuries'),list) and bool(injuries.get('injuries')) and tip-now<=timedelta(hours=48))
    out=[];uncertain=[];unmatched=[];available=[];later=[]
    for r in injury_rows(injuries):
        if canon(r.get('team'))!=team:continue
        published=when(r.get('date'))
        if not usable or published is None or published>captured:later.append(r.get('player'));continue
        role=by_id.get(str(r.get('athlete_id')))if r.get('athlete_id')else None
        candidate=index.get(name_key(r.get('player')))
        if role is None and candidate and (not r.get('athlete_id')or not candidate['athlete_ids']):role=candidate
        item={'name':r.get('player'),'status':r.get('status'),'published_at_utc':r.get('date'),'matched_recent_role':bool(role and role['active_games']>=2),'expected_minutes_proxy':role['expected_minutes_proxy']if role and role['active_games']>=2 else None}
        status=str(r.get('status','')).lower()
        if status=='out':out.append(item)
        elif status in ('available','active'):available.append(item)
        else:uncertain.append(item)
        if not item['matched_recent_role']:unmatched.append(item['name'])
    # Sum of matched recent active-game role minutes; not actual future lost minutes.
    known_minutes=round(sum(p['expected_minutes_proxy']for p in out if p['expected_minutes_proxy']is not None),1)if usable and len(complete)>=3 else None
    known_out_keys={name_key(p['name'])for p in out};uncertain_keys={name_key(p['name'])for p in uncertain}
    core=[p for p in rotation if p['active_games']>=2 and p['expected_minutes_proxy']>=10]
    return {'team':team,'team_games':len(complete),'sample_events':[e['event_id']for e in complete],
            'out':out,'uncertain':uncertain,'unmatched':unmatched,'ignored_unverifiable':later,'explicit_available':available,'snapshot_usable':usable,
            'matched_out_role_minutes':known_minutes,'full_loss_estimate':None,'replacement_ability':None,'official_starting_lineup':None,
            'recent_rotation':rotation,'observed_core_count':len(core),'core_not_reported_out':sum(p['key']not in known_out_keys and p['key']not in uncertain_keys for p in core),
            'core_minutes_72h':round(sum(p['minutes_72h']for p in core[:5]),1)if len(complete)>=3 and len(core)>=5 else None,
            'replacement_coverage_note':'近期輪替人數僅為觀測，不是已確認可出賽名單或替補能力。'}

def technical(team,events):
    records=[]
    for e in events:
        if team not in (e['home'],e['away']):continue
        own=next((t for t in e['teams']if canon(t.get('team'))==team),None);opp=next((t for t in e['teams']if canon(t.get('team'))!=team),None)
        if not own or not opp:continue
        keys=['estimated_possessions','eFG_pct','turnover_per_est_poss_pct','free_throw_attempt_rate','three_point_attempt_rate','oreb_pct']
        if any(number(t.get(k))is None for t in (own,opp)for k in keys):continue
        poss=(own['estimated_possessions']+opp['estimated_possessions'])/2
        if not 50<=poss<=150:continue
        own_score=e['home_score']if team==e['home']else e['away_score'];opp_score=e['away_score']if team==e['home']else e['home_score'];duration=e.get('duration_minutes')
        records.append({'event_id':e['event_id'],'off':own_score/poss*100,'def':opp_score/poss*100,'pace48':poss*48/duration if duration else None,'own':own,'opp':opp})
    records=records[-8:];n=len(records)
    result={'n':n,'sample_events':[r['event_id']for r in records],'approximate':True}
    for side in ('own','opp'):
        result[side]={k:round(mean(r[side][k]for r in records),2)if n>=3 else None for k in ['eFG_pct','turnover_per_est_poss_pct','free_throw_attempt_rate','three_point_attempt_rate','oreb_pct']}
    for key in ('off','def','pace48'):
        vals=[r[key]for r in records if r[key]is not None];result[key]=round(mean(vals),2)if len(vals)>=3 else None
    return result

def bucket(value,lo,hi=None):
    if value is None:return None
    high=hi if hi is not None else lo*2
    return 2 if value>=high else 1 if value>=lo else -2 if value<=-high else -1 if value<=-lo else 0

def observe(game,history,injuries,now,injury_hash=None):
    events=eligible_events(history['events'],game,now);h=team_lineup(canon(game['home']),events,injuries,game,now);a=team_lineup(canon(game['away']),events,injuries,game,now)
    ht,at=technical(h['team'],events),technical(a['team'],events)
    verified=all(t['snapshot_usable'] and t['team_games']>=3 and not t['uncertain']and not t['unmatched']and not t['ignored_unverifiable'] for t in (h,a))
    # An absent report entry is never an explicit health clearance. This index
    # only compares *reported, matched* absences, not complete roster health.
    loss=a['matched_out_role_minutes']-h['matched_out_role_minutes']if verified else None
    load=(a['core_minutes_72h']-h['core_minutes_72h'])if all(t['core_minutes_72h']is not None for t in (h,a))else None
    def diff(key,reverse=False):
        x,y=ht['own'].get(key),at['own'].get(key);ha,aa=ht['opp'].get(key),at['opp'].get(key)
        if any(v is None for v in (x,y,ha,aa)):return None
        return ((y+ha)-(x+aa))/2 if reverse else ((x+aa)-(y+ha))/2
    values={'rotation_loss':bucket(loss,30,60),'load':bucket(load,100,200),'shooting':bucket(diff('eFG_pct'),2,4),'turnovers':bucket(diff('turnover_per_est_poss_pct',True),2,4),'rebounds':bucket(diff('oreb_pct'),3,6),'pace':None,'variance':None}
    league_pace=[]
    for t in {x for e in events for x in(e['home'],e['away'])}:
        value=technical(t,events).get('pace48')
        if value is not None:league_pace.append(value)
    pace=(ht['pace48']+at['pace48'])/2 if ht['pace48']is not None and at['pace48']is not None else None
    baseline=mean(league_pace)if len(league_pace)>=20 else None
    if pace is not None and baseline is not None:values['pace']=bucket(pace-baseline,2,4)
    t3=[ht['own']['three_point_attempt_rate'],at['own']['three_point_attempt_rate']]
    if all(x is not None for x in t3):values['variance']=1 if min(t3)>=40 else 0
    raw={'rotation_loss':loss,'load':load,'shooting':diff('eFG_pct'),'turnovers':diff('turnover_per_est_poss_pct',True),'rebounds':diff('oreb_pct'),'pace':None if pace is None or baseline is None else pace-baseline,'variance':None if any(x is None for x in t3)else min(t3)}
    parts=[{'id':key,'label':label,'target':target,'candidate_points':values[key],'raw_value':round(raw[key],2)if raw[key]is not None else None,'predictive_weight':0,'applied_points':0,'status':'observational_not_fitted'}for key,label,target in RULES]
    return {'event_id':str(game['id']),'date':game['date'],'home':h['team'],'away':a['team'],'generated_at_utc':now.isoformat(),'context_version':VERSION,
            'model_status':'observational_shadow','affects_predictions':False,'lineup':{'home':h,'away':a,'injury_snapshot_at_utc':injuries.get('captured_at'),'injury_snapshot_hash':injury_hash,'source':injuries.get('source')},
            'technical':{'home':ht,'away':at,'expected_pace48_proxy':round(pace,2)if pace is not None else None,'league_pace48_proxy':round(baseline,2)if baseline is not None else None},'factors':parts,
            'input_events':sorted({i for t in(h,a)for i in t['sample_events']}|{i for t in(ht,at)for i in t['sample_events']}),
            'not_estimated':['player_ability_loss','replacement_ability','official_starting_lineup','rim_or_tracking_matchups','travel_route','predictive_effect'],
            'notes':['目前只觀測，所有預測權重為零；示意門檻不是學得權重。','傷停名單未列名不代表健康；ESPN Out 不冒稱 NBA 官方確認。','缺陣分鐘是近三次有效出賽角色代理，不是能力損失或必須補上的精確分鐘。','只使用較早台北比賽日的完賽資料，且在本次生成前已擷取；無法倒填歷史傷停。','回合數與效率由公開 box score 近似；不是官方 pace 或追蹤資料。']}

def settle(record,g,now):
    if record.get('settlement')is not None:return
    if not valid_final(g,now)or record['home']!=canon(g.get('home'))or record['away']!=canon(g.get('away'))or record['date']!=g.get('date'):return
    frozen=when(record.get('frozen_at_utc'));tip=when(g['date'])
    if not frozen or frozen>tip-timedelta(hours=1):return
    record['settlement']={'observed_at_utc':now.isoformat(),'home_margin':g['home_score']-g['away_score'],'total_points':g['home_score']+g['away_score'],'kind':'feature_observation_labels_not_model_accuracy'}

def run(root,now=None,backfill=False,fetcher=fetch_summary):
    now=now or datetime.now(UTC);root.mkdir(exist_ok=True);public=read(root/'games.json',{});injuries=read(root/'injuries.json',{})
    history,ingestion=merge_archive(root,public,now,backfill,fetcher);inj_archive,current=snapshot_injuries(root,injuries,now)
    futures=[g for g in public.get('games',[])if g.get('status')=='pre' and g.get('season_phase')in(2,3)and when(g.get('date'))and when(g['date'])>now]
    observations=[observe(g,history,injuries,now,current['hash']if current else None)for g in futures]
    ledger=read(root/'context-pregame-ledger.json',{'schema_version':SCHEMA,'records':[]});existing={(r['event_id'],r['context_version']):r for r in ledger['records']};added=0
    base=read(root/'factor-scorecard.json',{});predictions={f['event_id']:f for f in base.get('forecasts',[])}
    for row in observations:
        key=(row['event_id'],VERSION);tip=when(row['date'])
        if key not in existing and timedelta(hours=1)<=tip-now<=timedelta(hours=24):
            base_forecast=predictions.get(row['event_id']);benchmark=None
            if base_forecast and base_forecast.get('home')==row['home']and base_forecast.get('away')==row['away']and base_forecast.get('date')==row['date']and when(base_forecast.get('generated_at_utc'))and when(base_forecast['generated_at_utc'])<=now<tip:
                benchmark={k:base_forecast[k]for k in('model_version','generated_at_utc','home_win_probability','expected_margin','expected_total','market')}
            existing[key]={**row,'frozen_at_utc':now.isoformat(),'benchmark_forecast':benchmark,'settlement':None};added+=1
    finals={str(g['id']):g for g in public.get('games',[])if g.get('status')=='post'}
    for r in existing.values():
        if r['event_id']in finals:settle(r,finals[r['event_id']],now)
    ledger.update(updated_at_utc=now.isoformat(),records=sorted(existing.values(),key=lambda r:(r['date'],r['context_version'])));write(root/'context-pregame-ledger.json',ledger)
    matched=sum(p['matched_recent_role']for r in observations for s in('home','away')for p in r['lineup'][s]['out'])
    known=sum(r['factors'][0]['candidate_points']is not None for r in observations)
    output={'schema_version':SCHEMA,'context_version':VERSION,'generated_at_utc':now.isoformat(),'affects_predictions':False,'predictive_validation':{'status':'not_yet_testable','reason':'No dated historical availability/rotation dataset across training and holdout seasons; never backfill today injury statuses.'},
            'ingestion':ingestion,'coverage':{'future_games':len(observations),'matched_out_observations':matched,'complete_reported_absence_comparisons':known,'technical_matchups':sum(r['technical']['home']['n']>=3 and r['technical']['away']['n']>=3 for r in observations),'distinct_injury_snapshots':len(inj_archive['snapshots'])},
            'prospective':{'frozen':len(existing),'new_frozen':added,'settled':sum(r.get('settlement')is not None for r in existing.values()),'not_prediction_hit_rate':True},'observations':observations,
            'limitations':['Sample windows are short and may exclude traded, long-injured or new players.','Not-reported players are not confirmed healthy; expected starters and replacement ability remain unknown.','No lineup or technical predictive weights have been fitted; no new accuracy or causal claim.','Public source redistribution/commercial rights remain under review.']}
    write(root/'context-factors.json',output)
    print(json.dumps({k:output[k]for k in('ingestion','coverage','prospective','predictive_validation')},ensure_ascii=False));return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',default='data');p.add_argument('--backfill',action='store_true');args=p.parse_args();run(Path(args.data_dir),backfill=args.backfill)
