"""CPU challenger: Elo offsets, residual score trees, chronological calibration.

Historical development replay and genuine prospective records are separate.
No private APEX parameters, future prices or today's injury labels are fitted
into historical games. Backend model cache is not a public page/data artifact.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from statistics import mean
from random import Random
import numpy as np
import lightgbm as lgb
from analyst_factors import canon,when,valid_final
from factor_scorecard import build_records,atomic_json,json_read,day_of
UTC=timezone.utc
SCHEMA=1
TARGETS=('moneyline','margin','total')
FEATURES=['elo_logit','margin_baseline','total_baseline','home_gap_hours','away_gap_hours','gap_difference','home_games_7d','away_games_7d','games_7d_difference','home_recent_n','away_recent_n','rest_rule','congestion_rule','residual_form_rule','matchup_rule','team_total_rule','league_total_rule','both_short_gap_rule','month_sin','month_cos']
CONFIGS=[{'num_leaves':7,'min_data_in_leaf':150,'rounds':80},{'num_leaves':15,'min_data_in_leaf':150,'rounds':100}]
SCALES=(0.,.25,.5,1.)
SEED=20261028

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-30,30)))
def logit(p):return np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6)))

def feature_vector(r):
    e=r['evidence'];h=e.get('home_gap_hours');a=e.get('away_gap_hours');hc=e.get('home_games_7d');ac=e.get('away_games_7d');month=when(r['date']).month
    vals=[float(logit(r['p'])),r['margin_base'],r['total_base'],h,a,None if h is None or a is None else h-a,hc,ac,None if hc is None or ac is None else hc-ac,e.get('home_recent_n'),e.get('away_recent_n'),*r['side'],*r['total'],math.sin(month*math.pi/6),math.cos(month*math.pi/6)]
    if len(vals)!=len(FEATURES):raise ValueError('feature schema mismatch')
    if any(v is not None and (isinstance(v,bool)or not math.isfinite(float(v)))for v in vals):raise ValueError('nonfinite feature')
    return [np.nan if v is None else float(v)for v in vals]

def matrix(rows):return np.asarray([feature_vector(r)for r in rows],dtype=float)
def base(rows,target):return np.asarray([r['p']if target=='moneyline'else r[target+'_base']for r in rows],dtype=float)
def labels(rows,target):return np.asarray([r['y']if target=='moneyline'else r[target+'_y']for r in rows],dtype=float)
def loss(pred,y,target):
    if target=='moneyline':
        p=np.clip(pred,1e-8,1-1e-8);return float(np.mean(-(y*np.log(p)+(1-y)*np.log(1-p))))
    return float(np.mean((pred-y)**2))

def train_tree(rows,target,config):
    x=matrix(rows);b=base(rows,target);y=labels(rows,target)
    params={'objective':'binary'if target=='moneyline'else'regression','learning_rate':.035,'verbosity':-1,'num_threads':1,'seed':SEED,'deterministic':True,'force_col_wise':True,'lambda_l2':10.,'max_depth':4,'feature_fraction':1.,'boost_from_average':False,**{k:v for k,v in config.items()if k!='rounds'}}
    dataset=lgb.Dataset(x,label=y if target=='moneyline'else y-b,init_score=logit(b)if target=='moneyline'else None,feature_name=FEATURES,free_raw_data=True)
    booster=lgb.train(params,dataset,num_boost_round=config['rounds'])
    return booster.model_to_string()

def correction(model,rows):
    # Dataset init_score is not part of the serialized predictor. Explicitly
    # restore the Elo offset below during both calibration and prediction.
    return lgb.Booster(model_str=model).predict(matrix(rows),raw_score=True,num_threads=1)

def fit_platt(raw,y):
    raw=np.asarray(raw,float);y=np.asarray(y,float)
    if len(raw)!=len(y)or not len(raw)or not np.isfinite(raw).all()or not np.isin(y,[0,1]).all():raise ValueError('invalid calibration data')
    if len(set(y.tolist()))<2:return {'slope':1.,'intercept':0.,'status':'insufficient_classes'}
    x=np.column_stack([raw,np.ones(len(raw))]);theta=np.array([1.,0.]);prior=theta.copy();penalty=.1
    for _ in range(60):
        p=sigmoid(x@theta);grad=x.T@(p-y)+penalty*(theta-prior);hessian=x.T@(x*(p*(1-p))[:,None])+np.eye(2)*penalty
        step=np.linalg.solve(hessian,grad);new=theta-step
        # Positive slope preserves ordering. Bound pathological small-sample fits.
        new[0]=np.clip(new[0],.1,3.);new[1]=np.clip(new[1],-3.,3.)
        if np.max(np.abs(new-theta))<1e-8:theta=new;break
        theta=new
    return {'slope':float(theta[0]),'intercept':float(theta[1]),'status':'fitted_disjoint_period'}

def platt(raw,fit):return sigmoid(fit['slope']*np.asarray(raw)+fit['intercept'])

def assert_periods(*groups):
    for g in groups:
        if not g:raise ValueError('empty chronological period')
        if len({r['event_id']for r in g})!=len(g):raise ValueError('duplicate game')
    for left,right in zip(groups,groups[1:]):
        if max(r['day']for r in left)>=min(r['day']for r in right):raise ValueError('periods overlap or share a calendar day')

def fit_bundle(train,validation,calibration,configs=CONFIGS,configs_by_target=None):
    assert_periods(train,validation,calibration);models={}
    for target in TARGETS:
        bv=base(validation,target);yv=labels(validation,target);options=[]
        target_configs=configs_by_target[target] if configs_by_target else configs
        for ci,config in enumerate(target_configs):
            model=train_tree(train,target,config);delta=correction(model,validation)
            for scale in SCALES:
                pred=sigmoid(logit(bv)+scale*delta)if target=='moneyline'else bv+scale*delta
                options.append((loss(pred,yv,target),scale,ci,model))
        _,scale,ci,model=min(options,key=lambda x:(x[0],x[1],x[2]));bc=base(calibration,target);delta=correction(model,calibration);yc=labels(calibration,target)
        chosen={'model':model,'scale':scale,'config':dict(target_configs[ci])}
        if target=='moneyline':
            chosen['calibration']=fit_platt(logit(bc)+scale*delta,yc);chosen['baseline_calibration']=fit_platt(logit(bc),yc)
            p=platt(logit(bc)+scale*delta,chosen['calibration']);chosen['selection_threshold']=float(np.quantile(np.maximum(p,1-p),.6))
        else:
            residual=yc-(bc+scale*delta);chosen['bias']=float(np.mean(residual));chosen['errors']=sorted(float(v)for v in residual-chosen['bias'])
            baseline_errors=yc-bc;chosen['baseline_bias']=float(np.mean(baseline_errors));chosen['baseline_errors']=sorted(float(v)for v in baseline_errors-chosen['baseline_bias'])
        gains=lgb.Booster(model_str=model).feature_importance(importance_type='gain');chosen['feature_gain']={name:float(gain)*scale for name,gain in zip(FEATURES,gains)}
        models[target]=chosen
    return {'models':models,'train_n':len(train),'validation_n':len(validation),'calibration_n':len(calibration),'periods':{'train':[min(r['day']for r in train),max(r['day']for r in train)],'validation':[min(r['day']for r in validation),max(r['day']for r in validation)],'calibration':[min(r['day']for r in calibration),max(r['day']for r in calibration)]}}

def predict(rows,bundle,baseline=False):
    result={}
    for target,m in bundle['models'].items():
        b=base(rows,target);delta=np.zeros(len(rows))if baseline else m['scale']*correction(m['model'],rows)
        if target=='moneyline':result[target]=platt(logit(b)+delta,m['baseline_calibration']if baseline else m['calibration'])
        else:result[target]=b+delta+(m['baseline_bias']if baseline else m['bias'])
    return result

def metrics(rows,pred):
    y=labels(rows,'moneyline');p=np.asarray(pred['moneyline']);out={'moneyline':{'n':len(rows),'correct':int(np.sum((p>=.5)==y)),'brier':float(np.mean((p-y)**2)),'log_loss':loss(p,y,'moneyline')}}
    for t in ('margin','total'):
        error=np.asarray(pred[t])-labels(rows,t);out[t]={'n':len(rows),'mae':float(np.mean(np.abs(error))),'rmse':float(np.sqrt(np.mean(error**2)))}
    return out

def paired_ci(rows,a,b):
    # Positive differences mean the candidate has LOWER loss/error.
    groups=defaultdict(list)
    for r,x,y in zip(rows,a,b):groups[r['day']].append(float(x-y))
    keys=sorted(groups);rng=Random(SEED);values=[]
    for _ in range(300):
        samples=[groups[keys[rng.randrange(len(keys))]]for _ in keys];values.append(sum(map(sum,samples))/sum(map(len,samples)))
    values.sort();return [values[7],values[292]]

def audit(rows,configs=CONFIGS):
    closed=[r for r in rows if r['y']is not None];train=[r for r in closed if 2019<=r['season']<=2023];validation=[r for r in closed if r['season']==2024];calibration=[r for r in closed if r['season']==2025];test=[r for r in closed if r['season']==2026]
    if min(len(train),len(validation),len(calibration),len(test))<500:raise ValueError('insufficient multi-season audit data')
    assert_periods(train,validation,calibration,test);bundle=fit_bundle(train,validation,calibration,configs);pred=predict(test,bundle);baseline=predict(test,bundle,True)
    raw={'moneyline':base(test,'moneyline'),'margin':base(test,'margin'),'total':base(test,'total')};ms={'candidate':metrics(test,pred),'calibrated_baseline':metrics(test,baseline),'raw_baseline':metrics(test,raw)}
    intervals={}
    for t in TARGETS:
        y=labels(test,t);aa=(baseline[t]-y)**2 if t=='moneyline'else np.abs(baseline[t]-y);bb=(pred[t]-y)**2 if t=='moneyline'else np.abs(pred[t]-y)
        intervals[t]=paired_ci(test,aa,bb)
    threshold=bundle['models']['moneyline']['selection_threshold'];selected=np.maximum(pred['moneyline'],1-pred['moneyline'])>=threshold
    subset=[r for r,s in zip(test,selected)if s];selected_metrics={k:metrics(subset,{t:v[selected]for t,v in values.items()})if subset else None for k,values in [('candidate',pred),('calibrated_baseline',baseline)]}
    # All comparisons use exactly the same test games / selection masks.
    report={'kind':'retrospective_development_replay','not_prospective':True,'prior_research_used_test_season':True,'test_season':2026,'test_n':len(test),'periods':bundle['periods'],'train_n':len(train),'validation_n':len(validation),'calibration_n':len(calibration),'metrics':ms,'improvement_ci95_by_day':intervals,
            'selection':{'calibration_target_coverage':.4,'threshold':threshold,'actual_test_coverage':float(np.mean(selected)),'n':len(subset),'same_subset_metrics':selected_metrics},'automatic_promotion':False,
            'conclusion':'No claim of superiority; development test season was used in earlier research and prospective evidence is required.'}
    return bundle,report

def model_code_hash():
    names=['gbdt_candidate.py','factor_scorecard.py','score_model.py','analyst_factors.py'];payload=b''.join((Path(__file__).parent/n).read_bytes()for n in names)
    return hashlib.sha256(payload+json.dumps({'engine':lgb.__version__,'numpy':np.__version__,'python':list(sys.version_info[:2]),'features':FEATURES,'configs':CONFIGS},sort_keys=True).encode()).hexdigest()

def consumed_hash(rows):
    return digest([{k:r.get(k)for k in ('event_id','date','day','season','p','margin_base','total_base','side','total','evidence','y','margin_y','total_y')}for r in sorted(rows,key=lambda x:x['event_id'])])

def live_fit(rows,chosen,cache,code,now):
    closed=sorted([r for r in rows if r['y']is not None and r['season']>=2019 and r['day']<day_of(now.isoformat())],key=lambda r:(r['day'],r['event_id']))
    week=now.astimezone(timezone(timedelta(hours=8))).strftime('%G-W%V');prior=cache.get('live',{});ids=set(prior.get('fit_ids',[]));consumed=[r for r in closed if r['event_id']in ids]
    unchanged=bool(prior and cache.get('code')==code and len(consumed)==len(ids)and consumed_hash(consumed)==prior.get('consumed_hash'))
    new_n=sum(r['event_id']not in ids for r in closed)
    if unchanged and (prior.get('training_week')==week or new_n==0):return prior,True,new_n
    if len(closed)<2000:raise ValueError('insufficient live training history')
    # Entire calendar days stay on one side of the rolling calibration boundary.
    cal_day=closed[-500]['day'];val_day=closed[-1000]['day']
    train=[r for r in closed if r['day']<val_day];validation=[r for r in closed if val_day<=r['day']<cal_day];calibration=[r for r in closed if r['day']>=cal_day]
    assert_periods(train,validation,calibration)
    # Configurations were selected in the earlier fixed development period.
    # Live validation only chooses correction shrinkage, not architecture.
    configs={t:[chosen['models'][t]['config']]for t in TARGETS}
    bundle=fit_bundle(train,validation,calibration,configs_by_target=configs)
    state={'bundle':bundle,'training_week':week,'fitted_at_utc':now.isoformat(),'fit_ids':[r['event_id']for r in closed],'consumed_hash':consumed_hash(closed)}
    state['model_version']='cpu-gbdt-v1-'+digest({'code':code,'data':state['consumed_hash'],'week':week})[:12]
    return state,False,new_n

def cdf(errors,x):return (int(np.searchsorted(errors,x,side='right'))+.5)/(len(errors)+1)
def line_probabilities(mu,errors,line,total=False):
    if type(line)not in(int,float)or not math.isfinite(line)or not float(line*2).is_integer()or not errors:return None
    boundary=line if total else-line
    if float(boundary).is_integer():
        low=cdf(errors,boundary-.5-mu);high=1-cdf(errors,boundary+.5-mu);push=max(0.,1-low-high)
    else:low=cdf(errors,math.floor(boundary)+.5-mu);high=1-low;push=0.
    return {'positive':high,'negative':low,'push':push,'method':'empirical_calibration_score_errors_not_historical_ATS_calibration'}

def valid_market(m,g,now):
    observed=when(m.get('captured_at_utc'));tip=when(g.get('date'))
    return bool(observed and tip and timedelta(0)<=now-observed<=timedelta(hours=6) and now<tip and observed<tip and str(m.get('event_id'))==str(g.get('event_id',g.get('id')))
        and m.get('date')==g.get('date')and canon(m.get('home'))==canon(g.get('home'))and canon(m.get('away'))==canon(g.get('away')))

def observed_market(markets,row,now):
    eligible=[m for m in markets if valid_market(m,row,now)]
    if not eligible:return None
    return max(eligible,key=lambda m:(sum((m.get('spread')or{}).get('home_line')is not None for _ in[0])+int((m.get('total')or{}).get('line')is not None)+int((m.get('moneyline')or{}).get('home_no_vig_probability')is not None),m['captured_at_utc']))

def valid_context(context,row,now):
    if not context:return False
    generated=when(context.get('generated_at_utc'));injury=when(context.get('lineup',{}).get('injury_snapshot_at_utc'));tip=when(row.get('date'))
    return bool(generated and injury and tip and timedelta(0)<=now-generated<=timedelta(hours=6)
        and timedelta(0)<=now-injury<=timedelta(hours=6) and generated<tip and injury<=generated
        and str(context.get('event_id'))==str(row.get('event_id')) and context.get('date')==row.get('date')
        and canon(context.get('home'))==canon(row.get('home')) and canon(context.get('away'))==canon(row.get('away'))
        and all(context.get('lineup',{}).get(side,{}).get('snapshot_usable') for side in ('home','away')))

def make_forecast(row,bundle,now,version,market,source_at,context=None):
    pred=predict([row],bundle);basep=predict([row],bundle,True);p=float(pred['moneyline'][0]);margin=float(pred['margin'][0]);total=float(pred['total'][0]);m=market or{};sp=(m.get('spread')or{}).get('home_line');tl=(m.get('total')or{}).get('line');mp=(m.get('moneyline')or{}).get('home_no_vig_probability')
    if type(mp)not in(int,float)or not 0<mp<1:mp=None
    threshold=bundle['models']['moneyline']['selection_threshold'];reasons=[];captured=when(source_at)
    if not captured or not timedelta(0)<=now-captured<=timedelta(hours=6):reasons.append('schedule_or_results_snapshot_stale')
    if when(row['date'])-now>timedelta(hours=48):reasons.append('outside_48h_publish_window')
    if valid_context(context,row,now):
        for side in ('home','away'):
            t=context.get('lineup',{}).get(side,{})
            if any((x.get('expected_minutes_proxy')or 0)>=28 for x in [*t.get('out',[]),*t.get('uncertain',[])]):reasons.append('major_recent_rotation_change_not_fitted');break
    else:reasons.append('lineup_snapshot_unavailable')
    selected=max(p,1-p)>=threshold and not reasons
    intervals={t:[float(v+np.quantile(bundle['models'][t]['errors'],.05)),float(v+np.quantile(bundle['models'][t]['errors'],.95))]for t,v in [('margin',margin),('total',total)]}
    cover=line_probabilities(margin,bundle['models']['margin']['errors'],sp);totals=line_probabilities(total,bundle['models']['total']['errors'],tl,True)
    report=(f"本場採CPU樹模型候選版，主隊{row['home']}、客隊{row['away']}。Elo作為實力基準，再由歷史休息、賽程與比分條件學習修正，最後使用分開時段校準。主勝估計{p:.1%}，主隊預估淨勝{margin:+.1f}分，兩隊合計{total:.1f}分。"+('已有實際讓分與總分線，可對照研究方向。'if cover and totals else'部分盤口尚未取得，只列比分估計，不補造參考線。')+('本場達到預先設定的勝負精選條件。'if selected else'本場未納入勝負精選，仍保留全部估計以供核對。')+'陣容與技術觀測尚未學得跨季權重，不以球星名氣直接調分。歷史開發回測不能當成真實賽前成績；請連同資料時間、區間與限制閱讀。')
    return {'event_id':row['event_id'],'date':row['date'],'home':row['home'],'away':row['away'],'generated_at_utc':now.isoformat(),'model_version':version,'report_zh':report,'home_win_probability':p,'expected_margin':margin,'expected_total':total,
            'baseline':{'home_win_probability':float(basep['moneyline'][0]),'raw_elo_probability':row['p'],'expected_margin':float(basep['margin'][0]),'expected_total':float(basep['total'][0])},'market':{'provider':m.get('provider'),'captured_at_utc':m.get('captured_at_utc'),'home_line':sp,'total_line':tl,'home_no_vig_probability':mp,'rights_status':m.get('rights_status','review')},
            'cover':cover,'totals':totals,'interval90':intervals,'selection':{'moneyline':selected,'threshold':threshold,'quality_reasons':sorted(set(reasons)),'score_market_selection_enabled':False},'last_input_game':row['last_input_game'],'source_snapshot_at_utc':source_at,'experimental':True,'champion_unchanged':True,
            'feature_coverage':{'trained_features':len(FEATURES),'lineup_weights_enabled':False,'historical_market_features_enabled':False,'unavailable':['historical_lineup_ability','replacement_ability','dated_technical_history','historical_market_edge']}}

def settle(record,g,now):
    if record.get('settlement')is not None:return
    tip=when(record.get('date'));freeze=when(record.get('frozen_at_utc'))
    if not tip or not freeze or freeze>tip-timedelta(hours=1)or not valid_final(g,now)or str(g.get('id'))!=record['event_id']or canon(g.get('home'))!=record['home']or canon(g.get('away'))!=record['away']or g.get('date')!=record['date']:return
    margin=g['home_score']-g['away_score'];total=g['home_score']+g['away_score'];y=int(margin>0);p=record['home_win_probability'];b=record['baseline']['home_win_probability'];mp=record['market'].get('home_no_vig_probability')
    result={'observed_at_utc':now.isoformat(),'moneyline_hit':(p>=.5)==bool(y),'actual_margin':margin,'actual_total':total,'brier':(p-y)**2,'baseline_brier':(b-y)**2,'baseline_moneyline_hit':(b>=.5)==bool(y),'market_brier':None if mp is None else(mp-y)**2,'market_moneyline_hit':None if mp is None else(mp>=.5)==bool(y)}
    for target,actual,line,key in [('spread',margin,record['market'].get('home_line'),'cover'),('total',total,record['market'].get('total_line'),'totals')]:
        probs=record.get(key)
        if line is None or not probs:result[target]=None;continue
        value=actual+line if target=='spread'else actual-line;positive=probs['positive']>=probs['negative']
        result[target]={'push':value==0,'hit':None if value==0 else positive==(value>0)}
    record['settlement']=result

def prospective_stats(records):
    rows=[r for r in records if r.get('settlement')];selected=[r for r in rows if r['selection']['moneyline']];out={'frozen':len(records),'settled':len(rows),'selected_settled':len(selected)}
    for name,src in [('all',rows),('selected',selected)]:
        eligible=[r for r in src if r['settlement'].get('market_brier')is not None]
        out[name]={'n':len(src),'moneyline_correct':sum(r['settlement']['moneyline_hit']for r in src),'mean_brier':mean(r['settlement']['brier']for r in src)if src else None,'baseline_mean_brier':mean(r['settlement']['baseline_brier']for r in src)if src else None,'market_paired_n':len(eligible),'market_paired_candidate_brier':mean(r['settlement']['brier']for r in eligible)if eligible else None,'market_paired_market_brier':mean(r['settlement']['market_brier']for r in eligible)if eligible else None}
        for target in ('spread','total'):
            market_rows=[r['settlement'][target]for r in src if r['settlement'].get(target)]
            decided=[r for r in market_rows if not r['push']]
            out[name][target]={'n':len(decided),'correct':sum(r['hit']for r in decided),'push':sum(r['push']for r in market_rows)}
    return out

def freeze_forecasts(existing,forecasts,now):
    """First publication per event, even across a weekly model-version change."""
    seen={r['event_id']for r in existing};added=0
    for f in forecasts:
        gap=when(f['date'])-now
        if f['event_id']not in seen and timedelta(hours=1)<=gap<=timedelta(hours=24)and'schedule_or_results_snapshot_stale'not in f['selection']['quality_reasons']:
            existing.append({**f,'frozen_at_utc':now.isoformat(),'settlement':None});seen.add(f['event_id']);added+=1
    return added

def accumulate_results(archive,current,now):
    """Retain final score facts after they leave the rolling schedule window."""
    existing={str(g['id']):g for g in archive.get('games',[])};added=0;corrected=0
    keys=('id','date','home','away','home_score','away_score','season_year','season_end','season_phase','status')
    for g in current:
        if g.get('status')!='post' or g.get('season_phase')not in(2,3,'2','3')or not valid_final(g,now):continue
        key=str(g['id']);value={k:g[k]for k in keys if k in g};prior=existing.get(key)
        if prior and all(value.get(k)==prior.get(k)for k in keys):continue
        # Reject identity collisions, but accept a same-event official score correction.
        if prior and any(value.get(k)!=prior.get(k)for k in('date','home','away')):continue
        added+=not bool(prior);corrected+=bool(prior)
        existing[key]={**value,'first_observed_at_utc':prior['first_observed_at_utc']if prior else now.isoformat(),'last_changed_at_utc':now.isoformat()}
    return {'schema_version':SCHEMA,'games':sorted(existing.values(),key=lambda g:(g['date'],str(g['id'])))}, {'new_results':added,'corrected_results':corrected,'cached_results':len(existing)-added}

def run(root,cache_dir,now=None):
    now=now or datetime.now(UTC);root.mkdir(exist_ok=True);cache_dir.mkdir(parents=True,exist_ok=True);public=json_read(root/'games.json',{});history=json_read(root/'history_games.json',{}).get('games',[]);current=public.get('games',[])
    captured=when(public.get('captured_at'))
    if not captured or captured>now:raise ValueError('unverifiable source snapshot')
    memory,ingestion=accumulate_results(json_read(root/'gbdt-result-history.json',{}),current,now)
    atomic_json(root/'gbdt-result-history.json',memory)
    rows=build_records([*history,*memory['games']],current,now);code=model_code_hash();cache_file=cache_dir/'state.json';cache=json_read(cache_file,{})
    audit_rows=[r for r in rows if r['y']is not None and 2019<=r['season']<=2026];audit_key=digest({'code':code,'rows':consumed_hash(audit_rows)});audit_reused=cache.get('audit_key')==audit_key
    if audit_reused:auditor=cache['audit_bundle'];report=cache['audit_report']
    else:auditor,report=audit(rows)
    live,reused,new_labels=live_fit(rows,auditor,cache,code,now)
    atomic_json(cache_file,{'schema_version':SCHEMA,'code':code,'audit_key':audit_key,'audit_bundle':auditor,'audit_report':report,'live':live})
    contexts={str(r['event_id']):r for r in json_read(root/'context-factors.json',{}).get('observations',[])if when(r.get('generated_at_utc'))and when(r['generated_at_utc'])<=now}
    forecasts=[make_forecast(r,live['bundle'],now,live['model_version'],observed_market(public.get('market_snapshots',[]),r,now),public['captured_at'],contexts.get(r['event_id']))for r in rows if r['y']is None]
    ledger=json_read(root/'gbdt-pregame-ledger.json',{'schema_version':SCHEMA,'records':[]});existing=ledger['records'];added=freeze_forecasts(existing,forecasts,now)
    finals={str(g['id']):g for g in memory['games']}
    for r in existing:
        if r['event_id']in finals:settle(r,finals[r['event_id']],now)
    ledger.update(updated_at_utc=now.isoformat(),records=sorted(existing,key=lambda r:(r['date'],r['model_version'])));atomic_json(root/'gbdt-pregame-ledger.json',ledger)
    model_summary={t:{k:m[k]for k in('scale','config','feature_gain')}for t,m in live['bundle']['models'].items()}
    output={'schema_version':SCHEMA,'model_version':live['model_version'],'generated_at_utc':now.isoformat(),'status':'prospective_shadow','automatic_promotion':False,'champion_unchanged':True,'method':'Elo log-odds offset + LightGBM residual trees; separate chronological Platt / empirical score-error calibration','engine':{'name':'LightGBM','version':lgb.__version__,'device':'cpu','threads':1},'features':FEATURES,'historical_validation':report,'result_memory':ingestion,'live_training':{'fitted_at_utc':live['fitted_at_utc'],'training_week':live['training_week'],'periods':live['bundle']['periods'],'train_n':live['bundle']['train_n'],'validation_n':live['bundle']['validation_n'],'calibration_n':live['bundle']['calibration_n'],'models':model_summary},
            'cache':{'audit_reused':audit_reused,'live_reused':reused,'new_closed_labels_since_fit':new_labels,'old_rows_refit':0 if reused else live['bundle']['train_n'],'policy':'weekly when new labels exist; immediate refit for code or consumed-label corrections'},'forecasts':forecasts,'prospective':{**prospective_stats(ledger['records']),'new_frozen':added},
            'limitations':['Development replay used a season seen in previous research; it is not untouched external evidence.','No historical market-line calibration; cover/total probabilities are experimental.','Lineup and technical observations remain unweighted until dated historical training coverage exists.','No APEX coefficients or proprietary third-party model were imported.','Same-event pregame market baselines are recorded only when an observed quote is available.','Model files stay in backend cache and are not committed to public page data.']}
    atomic_json(root/'gbdt-candidate.json',output);print(json.dumps({'model_version':output['model_version'],'forecasts':len(forecasts),'metrics':report['metrics'],'intervals':report['improvement_ci95_by_day'],'selection':report['selection'],'scales':{t:m['scale']for t,m in live['bundle']['models'].items()},'prospective':output['prospective'],'cache':output['cache']},ensure_ascii=False));return output

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',default='data');p.add_argument('--cache-dir',default='.candidate-cache');args=p.parse_args();run(Path(args.data_dir),Path(args.cache_dir))
