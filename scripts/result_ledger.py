"""Independent market-first ledgers and lightweight, identity-checked settlement.

A missing first moneyline quote never prevents a later genuine pregame market
forecast from being frozen. It never replaces any published earlier prediction.
"""
from __future__ import annotations
import argparse,copy,json,math
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from statistics import mean
from analyst_factors import canon,when,valid_final
UTC=timezone.utc
FAMILIES={'elo':('elo-forecasts.json','elo-pregame-ledger.json'),'factor':('factor-scorecard.json','factor-pregame-ledger.json'),'gbdt':('gbdt-candidate.json','gbdt-pregame-ledger.json'),'ensemble':('model-hub.json','ensemble-pregame-ledger.json')}

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def write(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n');tmp.replace(path)

def same_event(a,b):
    return str(a.get('event_id',a.get('id')))==str(b.get('event_id',b.get('id'))) and when(a.get('date'))==when(b.get('date')) and canon(a.get('home'))==canon(b.get('home')) and canon(a.get('away'))==canon(b.get('away'))

def quote_ok(m,g,now):
    observed=when(m.get('captured_at_utc'));tip=when(g.get('date'))
    return bool(same_event(m,g)and observed and tip and timedelta(0)<=now-observed<=timedelta(hours=6)and now<tip)

def choose_quote(markets,g,now):
    eligible=[m for m in markets if quote_ok(m,g,now)]
    return max(eligible,key=lambda m:(sum((m.get(k)or{}).get(v)is not None for k,v in [('spread','home_line'),('total','line')]),m['captured_at_utc']))if eligible else None

def forecast_ok(r,now,window=True):
    generated=when(r.get('generated_at_utc'));tip=when(r.get('date'))
    return bool(generated and tip and generated<=now and generated<tip and (not window or timedelta(hours=1)<=tip-now<=timedelta(hours=24)))

def first_per_event(records):
    result={}
    for r in sorted(records,key=lambda r:r.get('frozen_at_utc','')):result.setdefault(str(r['event_id']),r)
    return list(result.values())

def seed_and_freeze_markets(existing,families,current,now):
    keys={(r['model_family'],r['event_id'],r['market_kind'])for r in existing};added=0
    # Historical imports must already have been published as pregame forecasts.
    for source,group in [('published_first_forecast_import',families),('new_quote_first_publication',current)]:
        for family,records in group.items():
            for r in records:
                freeze=when(r.get('frozen_at_utc'))if source.startswith('published')else now
                if not freeze or not forecast_ok(r,freeze,window=not source.startswith('published')) or freeze>now:continue
                observed=when(r.get('market',{}).get('captured_at_utc'));tip=when(r.get('date'))
                if not observed or not timedelta(0)<=freeze-observed<=timedelta(hours=6)or freeze>tip-timedelta(hours=1):continue
                for kind,key,line in [('spread','cover','home_line'),('total','totals','total_line')]:
                    ident=(family,str(r['event_id']),kind);probs=r.get(key);value=r.get('market',{}).get(line)
                    if ident in keys or not probs or type(value)not in(int,float)or not math.isfinite(value):continue
                    if not float(value*2).is_integer():continue
                    if any(type(probs.get(k))not in(int,float)or not 0<=probs[k]<=1 for k in ('positive','negative')):continue
                    if abs(sum(probs.get(k,0)for k in('positive','negative','push'))-1)>1e-5:continue
                    record=copy.deepcopy(r);record.update(model_family=family,market_kind=kind,frozen_at_utc=freeze.isoformat(),freeze_provenance=source)
                    # Settlement must be recomputed against this specific market.
                    record['settlement']=None;existing.append(record);keys.add(ident);added+=1
    return added

def freeze_first(records,forecasts,now,source_at):
    captured=when(source_at)
    if not captured or not timedelta(0)<=now-captured<=timedelta(hours=6):return 0
    seen={r['event_id']for r in records};added=0
    for r in forecasts:
        if r['event_id']not in seen and forecast_ok(r,now):records.append({**copy.deepcopy(r),'frozen_at_utc':now.isoformat(),'settlement':None});seen.add(r['event_id']);added+=1
    return added

def reconcile_games(public,scoreboard,now):
    observed=when(scoreboard.get('captured_at'));tip_matches=0
    if not observed or not timedelta(0)<=now-observed<=timedelta(hours=6):return 0
    for row in scoreboard.get('games',[]):
        if row.get('status')!='已結束' or not when(row.get('date')):continue
        candidates=[g for g in public.get('games',[])if when(g.get('date'))==when(row['date'])and canon(g.get('home'))==canon(row.get('home'))and canon(g.get('away'))==canon(row.get('away'))]
        if row.get('provider')=='ESPN':candidates=[g for g in candidates if str(g.get('id'))==str(row.get('event_id'))]
        if len(candidates)!=1:continue
        g=candidates[0];final={**g,'status':'post','home_score':row.get('home_score'),'away_score':row.get('away_score')}
        if not valid_final(final,now)or when(g['date'])>=observed:continue
        if any(g.get(k)!=final[k]for k in('status','home_score','away_score')):
            g.update(status='post',status_label='Final',home_score=final['home_score'],away_score=final['away_score'],score_observed_at_utc=observed.isoformat(),score_source=scoreboard.get('source'));tip_matches+=1
    public['scoreboard_reconciled_at_utc']=observed.isoformat();public['scoreboard_source']=scoreboard.get('source');return tip_matches

def settle(r,g,now):
    freeze=when(r.get('frozen_at_utc'));tip=when(r.get('date'))
    if not same_event(r,g)or not freeze or not tip or freeze>tip-timedelta(hours=1)or not valid_final(g,now):return False
    margin=g['home_score']-g['away_score'];total=g['home_score']+g['away_score'];old=r.get('settlement')
    if old and old.get('actual_margin')==margin and old.get('actual_total')==total:return False
    p=r.get('home_win_probability')
    if type(p)not in(int,float)or not 0<=p<=1:return False
    y=int(margin>0);bp=(r.get('baseline')or{}).get('home_win_probability');mp=(r.get('market')or{}).get('home_no_vig_probability')
    result={'observed_at_utc':now.isoformat(),'moneyline_hit':(p>=.5)==bool(y),'actual_margin':margin,'actual_total':total,'brier':(p-y)**2,'baseline_brier':None if bp is None else(bp-y)**2,'baseline_moneyline_hit':None if bp is None else(bp>=.5)==bool(y),'market_brier':None if mp is None else(mp-y)**2,'market_moneyline_hit':None if mp is None else(mp>=.5)==bool(y)}
    for target,key,line,actual in [('spread','cover','home_line',margin),('total','totals','total_line',total)]:
        probs=r.get(key);value=(r.get('market')or{}).get(line)
        if probs is None or value is None:result[target]=None;continue
        delta=actual+value if target=='spread'else actual-value;result[target]={'push':delta==0,'hit':None if delta==0 else(probs['positive']>=probs['negative'])==(delta>0)}
    if old:r.setdefault('settlement_revisions',[]).append(old)
    r['settlement']=result;return True

def elo_forecasts(public,reports,now):
    games={str(g['id']):g for g in public.get('games',[])if g.get('status')=='pre'and when(g['date'])>now};out=[]
    for r in reports.get('reports',[]):
        g=games.get(str(r.get('event_id')))
        if not g or not same_event(r,g)or not forecast_ok(r,now,False):continue
        m=r.get('markets',{});p=(m.get('moneyline')or{}).get('home_probability_experimental');projection=(r.get('analyst')or{}).get('projection',{});quote=choose_quote(public.get('market_snapshots',[]),g,now)
        if p is None or not projection:continue
        spread=m.get('spread')or{};total=m.get('total')or{};market={'provider':(quote or{}).get('provider'),'captured_at_utc':(quote or{}).get('captured_at_utc'),'home_line':None,'total_line':None,'home_no_vig_probability':((quote or{}).get('moneyline')or{}).get('home_no_vig_probability')};cover=totals=None
        if quote and (quote.get('spread')or{}).get('home_line')==spread.get('home_line'):
            h=spread.get('home_cover_probability_experimental');a=spread.get('away_cover_probability_experimental');line=spread.get('home_line')
            # Legacy normal estimates do not model integer-line pushes. Leave unknown.
            if h is not None and a is not None and line is not None and not float(line).is_integer():cover={'positive':h,'negative':a,'push':0};market['home_line']=line
        if quote and (quote.get('total')or{}).get('line')==total.get('line'):
            o=total.get('over_probability_experimental');u=total.get('under_probability_experimental');line=total.get('line')
            if o is not None and u is not None and line is not None and not float(line).is_integer():totals={'positive':o,'negative':u,'push':0};market['total_line']=line
        out.append({'event_id':str(r['event_id']),'date':r['date'],'home':canon(r['home']),'away':canon(r['away']),'generated_at_utc':r['generated_at_utc'],'model_version':'public-elo-score-v1','home_win_probability':p,'expected_margin':projection['expected_margin'],'expected_total':projection['expected_total'],'report_zh':r['report_zh'],'market':market,'cover':cover,'totals':totals,'selection':{'moneyline':False}})
    return out

def summary(records,market_records,family):
    rows=first_per_event(records);closed=[r for r in rows if r.get('settlement')];out={'frozen':len(rows),'settled':len(closed),'moneyline_correct':sum(r['settlement']['moneyline_hit']for r in closed)}
    for target in ('spread','total'):
        eligible=[r for r in market_records if r['model_family']==family and r['market_kind']==target and r.get('settlement')and r['settlement'].get(target)];decided=[r for r in eligible if not r['settlement'][target]['push']]
        out[target]={'n':len(decided),'correct':sum(r['settlement'][target]['hit']for r in decided),'push':len(eligible)-len(decided),'frozen':sum(r['model_family']==family and r['market_kind']==target for r in market_records)}
    return out

def run(root,now=None,freeze=True):
    now=now or datetime.now(UTC);public=read(root/'games.json',{});scoreboard=read(root/'scoreboard.json',{});reconciled=reconcile_games(public,scoreboard,now)
    if reconciled:write(root/'games.json',public)
    finals={str(g['id']):g for g in read(root/'gbdt-result-history.json',{}).get('games',[])}
    finals.update({str(g['id']):g for g in public.get('games',[])if g.get('status')=='post'})
    generated=elo_forecasts(public,read(root/'reports.json',{}),now)
    if freeze:write(root/'elo-forecasts.json',{'generated_at_utc':now.isoformat(),'forecasts':generated})
    ledgers={family:read(root/name,{'schema_version':1,'records':[]})for family,(_,name)in FAMILIES.items()};current={family:(generated if family=='elo' else read(root/file,{}).get('forecasts',[]))for family,(file,_)in FAMILIES.items()}
    if freeze:
        for family in ('elo','ensemble'):freeze_first(ledgers[family]['records'],current[family],now,public.get('captured_at'))
    markets=read(root/'market-pregame-ledger.json',{'schema_version':1,'records':[]});added=seed_and_freeze_markets(markets['records'],{k:v['records']for k,v in ledgers.items()},current if freeze else{},now);settled=0
    for r in [*markets['records'],*[r for ledger in ledgers.values()for r in ledger['records']]]:
        if r['event_id']in finals:settled+=settle(r,finals[r['event_id']],now)
    for family,(_,name)in FAMILIES.items():ledgers[family]['updated_at_utc']=now.isoformat();write(root/name,ledgers[family])
    markets['updated_at_utc']=now.isoformat();write(root/'market-pregame-ledger.json',markets)
    result={'generated_at_utc':now.isoformat(),'scoreboard_at_utc':scoreboard.get('captured_at'),'last_full_collection_at_utc':public.get('captured_at'),'reconciled_games':reconciled,'new_market_freezes':added,'settlements_updated':settled,'models':{k:summary(v['records'],markets['records'],k)for k,v in ledgers.items()},'policy':'moneyline first publication; each score market freezes independently on first valid quote; no retrospective missing-line backfill'};write(root/'settlement-status.json',result);print(json.dumps(result));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',default='data');p.add_argument('--settle-only',action='store_true');args=p.parse_args();run(Path(args.data_dir),freeze=not args.settle_only)
