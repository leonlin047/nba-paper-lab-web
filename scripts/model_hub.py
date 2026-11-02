"""Chronological calibrated linear pool of three available CPU components.

Calibration A precedes weight selection B. Development season 2026 is reported
separately, never used to select historical weights. No private model is copied.
"""
import argparse,copy,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import gbdt_candidate as c
import factor_scorecard as f
from result_ledger import read,write,choose_quote
KINDS=('elo','factor','gbdt')
GRID=[(a/4,b/4,(4-a-b)/4)for a in range(1,5)for b in range(5-a)]

def split_days(rows,minimum=100):
    ordered=sorted(rows,key=lambda r:(r['day'],r['event_id']));boundary=ordered[len(ordered)//2]['day'];a=[r for r in ordered if r['day']<boundary];b=[r for r in ordered if r['day']>=boundary]
    if min(len(a),len(b))<minimum:raise ValueError('insufficient disjoint calibration and weight selection periods')
    c.assert_periods(a,b);return a,b

def raw(rows,kind,target,trees,factors):
    if kind=='elo':return c.base(rows,target)
    if kind=='factor':
        m=factors['models'][target];return np.array([f.prediction(r,target,m['weights'],m['scale'])for r in rows])
    m=trees['models'][target];delta=m['scale']*c.correction(m['model'],rows);b=c.base(rows,target)
    return c.sigmoid(c.logit(b)+delta)if target=='moneyline'else b+delta

def select_weights(values,y,target):
    # Retain at least 25% common baseline; related learners are not independent votes.
    options=[]
    for weights in GRID:
        prediction=sum(w*values[k]for w,k in zip(weights,KINDS));penalty=(.0005 if target=='moneyline'else .01)*sum(w*w for w in weights[1:]);options.append((c.loss(prediction,y,target)+penalty,sum(weights[1:]),weights))
    return list(min(options)[2])

def apply_profile(values,profile,target):
    return c.platt(c.logit(values),profile['platt'])if target=='moneyline'else values+profile['bias']

def fit_pool(a,b,trees,factors,minimum=100):
    c.assert_periods(a,b)
    if min(len(a),len(b))<minimum:raise ValueError('not enough pre-outcome calibration data')
    factors=copy.deepcopy(factors)
    # Original factor integer weights were trained before these periods. Re-select
    # only their small correction scale on A, never on B or the test season.
    for t,m in factors['models'].items():m['scale']=min(f.SCALES[t],key=lambda s:(f.objective(a,t,m['weights'],s,False),s))
    profiles={};weights={}
    for target in c.TARGETS:
        ya=c.labels(a,target);yb=c.labels(b,target);profiles[target]={};values={}
        for kind in KINDS:
            ra=raw(a,kind,target,trees,factors);rb=raw(b,kind,target,trees,factors)
            if target=='moneyline':profile={'platt':c.fit_platt(c.logit(ra),ya)}
            else:
                residual=ya-ra;bias=float(np.mean(residual));profile={'bias':bias,'errors':sorted(float(x-bias)for x in residual)}
            profiles[target][kind]=profile;values[kind]=apply_profile(rb,profile,target)
        weights[target]=select_weights(values,yb,target)
    return {'profiles':profiles,'weights':weights,'factors':factors,'calibration_n':len(a),'weight_selection_n':len(b),'periods':{'calibration':[min(r['day']for r in a),max(r['day']for r in a)],'weight_selection':[min(r['day']for r in b),max(r['day']for r in b)]}}

def components(rows,pool,trees):
    return {t:{k:apply_profile(raw(rows,k,t,trees,pool['factors']),pool['profiles'][t][k],t)for k in KINDS}for t in c.TARGETS}

def pool_predict(rows,pool,trees,baseline=False):
    parts=components(rows,pool,trees);return {t:parts[t]['elo']if baseline else sum(w*parts[t][k]for w,k in zip(pool['weights'][t],KINDS))for t in c.TARGETS}

def development(rows,trees,factors):
    a,b=split_days([r for r in rows if r['season']==2025 and r['y']is not None]);test=[r for r in rows if r['season']==2026 and r['y']is not None];c.assert_periods(a,b,test)
    pool=fit_pool(a,b,trees,factors);candidate=pool_predict(test,pool,trees);base=pool_predict(test,pool,trees,True);intervals={}
    for t in c.TARGETS:
        y=c.labels(test,t);aa=(base[t]-y)**2 if t=='moneyline'else np.abs(base[t]-y);bb=(candidate[t]-y)**2 if t=='moneyline'else np.abs(candidate[t]-y);intervals[t]=c.paired_ci(test,aa,bb)
    return {'kind':'retrospective_development_not_prospective','prior_research_used_test_season':True,'test_n':len(test),'periods':pool['periods'],'weights':dict(pool['weights']),'metrics':{'candidate':c.metrics(test,candidate),'calibrated_baseline':c.metrics(test,base)},'improvement_ci95_by_day':intervals,'automatic_promotion':False}

def mixed_line(values,pool,target,line):
    weights=pool['weights'][target];parts=[c.line_probabilities(float(values[k]),pool['profiles'][target][k]['errors'],line,target=='total')for k in KINDS]
    if any(p is None for p in parts):return None
    return {key:sum(w*p[key]for w,p in zip(weights,parts))for key in ('positive','negative','push')}

def interval(values,pool,target):
    points=[]
    for w,k in zip(pool['weights'][target],KINDS):
        errors=pool['profiles'][target][k]['errors']
        if w>0:points.extend((float(values[k]+e),w/len(errors))for e in errors)
    points.sort();out=[]
    for q in(.05,.95):
        mass=0
        for value,weight in points:
            mass+=weight
            if mass>=q:out.append(value);break
    return out

def registry(private,now):
    stamp=private.get('as_of_utc');age=(now-c.when(stamp)).total_seconds()/3600 if c.when(stamp)else None
    entries=[{'id':k,'name':name,'state':'available_cpu_research','participates':True}for k,name in [('elo','Elo共同比分基準'),('factor','整數因子'),('gbdt','CPU樹模型')]]
    entries += [{'id':'apex','name':'APEX v2.1','state':'waiting_valid_forecasts','participates':False,'eligible_games':private.get('apex_eligible_games'),'minimum':100}, {'id':'online','name':'增量模型','state':'waiting_training_threshold','participates':False,'trained_pairs':private.get('online_trained_pairs'),'minimum':100}]
    return {'models':entries,'private_status_as_of_utc':stamp,'private_status_age_hours':age,'private_status_manual_snapshot':True,'all_models_weighted':False,'independent_votes':False,'automatic_promotion':False}

def run(root,cache_dir,now=None):
    now=now or datetime.now(timezone.utc);cache=read(cache_dir/'state.json',{});native=cache.get('live');auditor=cache.get('audit_bundle');factors=read(root/'factor-model-cache.json',{}).get('fit')
    if not native or not auditor or not factors:raise ValueError('run both available CPU models first')
    public=read(root/'games.json',{});memory=read(root/'gbdt-result-history.json',{}).get('games',[]);history=read(root/'history_games.json',{}).get('games',[]);rows=f.build_records([*history,*memory],public.get('games',[]),now)
    code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();closed=[r for r in rows if r['event_id']in set(native['fit_ids'])];a,b=split_days([r for r in closed if native['bundle']['periods']['calibration'][0]<=r['day']<=native['bundle']['periods']['calibration'][1]])
    key=c.digest({'code':code,'native_version':native['model_version'],'calibration':c.consumed_hash([*a,*b]),'factor_models':factors['models'],'audit_key':cache['audit_key']});saved=read(cache_dir/'hub.json',{});reused=saved.get('key')==key
    if reused:pool=saved['pool'];report=saved['development']
    else:
        report=development(rows,auditor,factors);pool=fit_pool(a,b,native['bundle'],factors);write(cache_dir/'hub.json',{'key':key,'pool':pool,'development':report})
    version='cpu-pool-v1-'+key[:12];future=[r for r in rows if r['y']is None];parts=components(future,pool,native['bundle'])if future else{};forecasts=[]
    for i,row in enumerate(future):
        values={t:{k:float(parts[t][k][i])for k in KINDS}for t in c.TARGETS};prediction={t:sum(w*values[t][k]for w,k in zip(pool['weights'][t],KINDS))for t in c.TARGETS};market=choose_quote(public.get('market_snapshots',[]),row,now)or{};sp=(market.get('spread')or{}).get('home_line');tl=(market.get('total')or{}).get('line');cover=mixed_line(values['margin'],pool,'margin',sp);totals=mixed_line(values['total'],pool,'total',tl)
        details={k:{'home_win_probability':values['moneyline'][k],'expected_margin':values['margin'][k],'expected_total':values['total'][k],'weights':{t:pool['weights'][t][j]for t in c.TARGETS}}for j,k in enumerate(KINDS)}
        p=prediction['moneyline'];margin=prediction['margin'];total=prediction['total'];report_zh=f"本場採三模型融合研究候選，主隊{row['home']}、客隊{row['away']}。以共同Elo基準、整數因子與CPU樹模型分開校準，再用較晚且不重疊時段選擇權重。主勝估計{p:.1%}，主隊預估淨勝{margin:+.1f}分，合計{total:.1f}分。"+('已有實際讓分與總分線，可核對各項方向。'if cover and totals else'部分實際盤口尚未取得，只保留比分推估。')+'三個模型共用部分資料，不視為三份獨立證據。APEX與增量模型尚未符合加入條件，未以虛構預測補足。歷史開發結果不能代替真正賽前驗證，仍保留Elo主模型。'
        forecasts.append({'event_id':row['event_id'],'date':row['date'],'home':row['home'],'away':row['away'],'generated_at_utc':now.isoformat(),'model_version':version,'home_win_probability':p,'expected_margin':margin,'expected_total':total,'baseline':{'home_win_probability':values['moneyline']['elo'],'expected_margin':values['margin']['elo'],'expected_total':values['total']['elo']},'market':{'provider':market.get('provider'),'captured_at_utc':market.get('captured_at_utc'),'home_line':sp,'total_line':tl,'home_no_vig_probability':(market.get('moneyline')or{}).get('home_no_vig_probability')},'cover':cover,'totals':totals,'interval90':{t:interval(values[t],pool,t)for t in('margin','total')},'selection':{'moneyline':False},'components':details,'disagreement':max(values['moneyline'].values())-min(values['moneyline'].values()),'report_zh':report_zh,'experimental':True,'champion_unchanged':True})
    status=registry(read(root/'private-model-readiness.json',{}),now);output={'schema_version':1,'generated_at_utc':now.isoformat(),'model_version':version,'status':'shadow_fusion_not_champion','champion_unchanged':True,'automatic_promotion':False,'registry':status,'weights':{t:dict(zip(KINDS,w))for t,w in pool['weights'].items()},'live_fit':{'periods':pool['periods'],'calibration_n':pool['calibration_n'],'weight_selection_n':pool['weight_selection_n'],'native_model_version':native['model_version']},'cache_reused':reused,'historical_validation':report,'forecasts':forecasts,'limitations':['Related components share inputs; no independent-vote assumption.','No dated lineup ability or historical ATS fitting.','Separate target pools are not a joint-score distribution.','Public readiness is a dated aggregate snapshot, not a private live bridge.']};write(root/'model-hub.json',output);print(json.dumps({k:output[k]for k in('model_version','weights','cache_reused','live_fit')}));return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',default='data');p.add_argument('--cache-dir',default='.candidate-cache');a=p.parse_args();run(Path(a.data_dir),Path(a.cache_dir))
