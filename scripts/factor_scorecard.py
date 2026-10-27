"""CPU-only experimental integer scorecards, dated replay and frozen forward ledger.

Weights are fitted on 2022-24 seasons, scales selected on 2024-25, and
2025-26 is evaluated without fitting to its labels. This is retrospective
research, not an independent prospective claim or an automatic model upgrade.
All games on one Taiwan calendar day share a frozen prior-day state.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist, mean, pstdev
from random import Random
import sys

from analyst_factors import canon, when, valid_final
from score_model import sample_model

UTC=timezone.utc
TW=timezone(timedelta(hours=8))
NORMAL=NormalDist()
SCHEMA=1
SIDE=[
    ("rest","休息間隔差","fatigue"),
    ("congestion","近七日賽程密度","fatigue"),
    ("residual_form","近期表現超出 Elo 的程度","form"),
    ("matchup","比分近況相對實力基準","matchup"),
]
TOTAL=[
    ("team_total","兩隊近期總分偏離基準","team"),
    ("league_shift","聯盟近期總分變化","league"),
    ("both_b2b","雙方短間隔出賽","fatigue"),
]
RULES={"moneyline":SIDE,"margin":SIDE,"total":TOTAL}
BASE_SCALE={"moneyline":.1,"margin":1.0,"total":2.0}
SCALES={"moneyline":[0,.05,.1,.15,.2],"margin":[0,.5,1,1.5,2],"total":[0,1,2,3]}

def sign_bin(x, threshold):
    return 1 if x>=threshold else -1 if x<=-threshold else 0

def sigmoid(x):
    return 1/(1+math.exp(-max(-35,min(35,x))))

def logit(p):
    p=max(.000001,min(.999999,p));return math.log(p/(1-p))

def day_of(value):
    t=when(value);return t.astimezone(TW).date().isoformat() if t else None

def year_of(g):
    try:return int(g.get("season_end",g.get("season_year")))
    except (ValueError,TypeError):return None

def score(values, weights, rules):
    groups=defaultdict(int)
    for value,weight,(_,_,group) in zip(values,weights,rules):
        if value is not None:groups[group]+=int(value)*int(weight)
    # Rest and congestion are correlated; never count more than two points.
    if "fatigue" in groups:groups["fatigue"]=max(-2,min(2,groups["fatigue"]))
    return sum(groups.values())

def features(g, teams, league, residuals, projection):
    h,a=canon(g["home"]),canon(g["away"]);tip=when(g["date"])
    def recent(t):return [x for x in teams[t][-25:] if tip-timedelta(days=365)<=when(x["date"])<tip][-12:]
    hs,aws=recent(h),recent(a)
    def gap(rows):
        hours=(tip-when(rows[-1]["date"])).total_seconds()/3600 if rows else None
        return hours if hours is not None and 0<hours<=336 else None
    hg,ag=gap(hs),gap(aws)
    rest=None if hg is None or ag is None else (1 if hg>=48 and ag<=30 else -1 if ag>=48 and hg<=30 else 0)
    hc=sum(tip-timedelta(days=7)<=when(x["date"])<tip for x in hs)
    ac=sum(tip-timedelta(days=7)<=when(x["date"])<tip for x in aws)
    congestion=sign_bin(ac-hc,2)
    he=[v for t,v in residuals[h][-12:] if t<tip][-5:]
    ae=[v for t,v in residuals[a][-12:] if t<tip][-5:]
    excess=None if len(he)<3 or len(ae)<3 else sign_bin((mean(he)-mean(ae))*min(len(he),len(ae))/(min(len(he),len(ae))+8),2)
    matchup=sign_bin(projection["form_margin_component"]-projection["elo_margin_component"],3)
    def avg_total(rows):return mean(x["home_score"]+x["away_score"] for x in rows[-5:])
    team_total=sign_bin((avg_total(hs)+avg_total(aws))/2-projection["expected_total"],4)
    recent_league=league[-100:]
    league_shift=sign_bin(mean(x["home_score"]+x["away_score"] for x in recent_league[-20:])-mean(x["home_score"]+x["away_score"] for x in recent_league),3)
    both=None if hg is None or ag is None else int(hg<=30 and ag<=30)
    return [rest,congestion,excess,matchup],[team_total,league_shift,both],{"home_gap_hours":hg,"away_gap_hours":ag,"home_games_7d":hc,"away_games_7d":ac,"home_recent_n":len(hs),"away_recent_n":len(aws)}

def build_records(historical,current,now):
    """Replay uses prior Taiwan game-days only; never same-day final labels."""
    finals={}
    for g in historical:
        if g.get("id") and valid_final(g,now) and year_of(g) and g.get("phase")!="preseason":finals[str(g["id"])]=g
    for g in current:
        if g.get("status")=="post" and g.get("season_phase") in (2,3,"2","3") and valid_final(g,now):finals[str(g["id"])]=g
    futures={str(g["id"]):g for g in current if g.get("status")=="pre" and when(g.get("date")) and when(g["date"])>now and g.get("season_phase") in (2,3,"2","3")}
    events=defaultdict(list)
    for g in list(finals.values())+list(futures.values()):
        if day_of(g.get("date")):events[day_of(g["date"])].append(g)
    elo=defaultdict(lambda:1500.0);teams=defaultdict(list);league=[];residuals=defaultdict(list)
    previous_season=None;rows=[]
    for game_day in sorted(events):
        games=sorted(events[game_day],key=lambda g:(g["date"],str(g["id"])))
        season=year_of(games[0])
        if previous_season is not None and season>previous_season:
            for key in elo:elo[key]=1500+(elo[key]-1500)*.65
        previous_season=season
        updates=[]
        for g in games:
            h,a=canon(g["home"]),canon(g["away"])
            p=1/(1+10**((elo[a]-elo[h]-65)/400))
            e_margin=NORMAL.inv_cdf(max(.002,min(.998,p)))*14
            projection=sample_model(g,teams,league,p)
            is_final=str(g["id"]) in finals
            if projection:
                side,total,evidence=features(g,teams,league,residuals,projection)
                row={"event_id":str(g["id"]),"date":g["date"],"day":game_day,"season":year_of(g),"home":h,"away":a,"p":p,
                     "margin_base":projection["expected_margin"],
                     "total_base":projection["expected_total"],"side":side,"total":total,"evidence":evidence,
                     "last_input_game":league[-1]["date"] if league else None,
                     "y":int(g["home_score"]>g["away_score"]) if is_final else None,
                     "margin_y":g["home_score"]-g["away_score"] if is_final else None,
                     "total_y":g["home_score"]+g["away_score"] if is_final else None}
                rows.append(row)
            if is_final:updates.append((g,h,a,p,e_margin))
        # Freeze the whole day before updating ratings or rolling features.
        for g,h,a,p,e_margin in updates:
            actual=g["home_score"]-g["away_score"]
            delta=20*((1 if actual>0 else 0)-p);elo[h]+=delta;elo[a]-=delta
            teams[h].append(g);teams[a].append(g);league.append(g)
            residuals[h].append((when(g["date"]),actual-e_margin));residuals[a].append((when(g["date"]),-actual+e_margin))
    return rows

def prediction(row,target,weights,scale):
    s=score(row["total"] if target=="total" else row["side"],weights,RULES[target])
    if target=="moneyline":return sigmoid(logit(row["p"])+scale*s)
    return row[target+"_base"]+scale*s

def objective(rows,target,weights,scale,penalty=True):
    if not rows:return float("inf")
    losses=[]
    for r in rows:
        p=prediction(r,target,weights,scale)
        if target=="moneyline":losses.append(-(r["y"]*math.log(max(p,1e-12))+(1-r["y"])*math.log(max(1-p,1e-12))))
        else:losses.append((p-r[target+"_y"])**2)
    l1={"moneyline":.00015,"margin":.05,"total":.1}[target]
    return mean(losses)+(l1*sum(abs(v) for v in weights) if penalty else 0)

def fit_models(rows):
    train=[r for r in rows if r["y"] is not None and 2023<=r["season"]<=2024]
    validation=[r for r in rows if r["y"] is not None and r["season"]==2025]
    test=[r for r in rows if r["y"] is not None and r["season"]==2026]
    if min(len(train),len(validation),len(test))<500:raise ValueError("Insufficient multi-season data; do not fit a replacement")
    models={}
    for target,rules in RULES.items():
        weights=[0]*len(rules);scale=BASE_SCALE[target]
        for _ in range(3):
            changed=False
            for j in range(len(weights)):
                options=[]
                for w in (0,-1,1,-2,2):
                    candidate=weights.copy();candidate[j]=w
                    options.append((objective(train,target,candidate,scale),sum(abs(x) for x in candidate),tuple(candidate)))
                best=list(min(options)[2])
                changed|=best!=weights;weights=best
            if not changed:break
        calibrated=min(SCALES[target],key=lambda k:(objective(validation,target,weights,k,False),k))
        models[target]={"weights":weights,"scale":calibrated,"rules":[{"id":i,"label":label,"group":group,"weight":w} for (i,label,group),w in zip(rules,weights)]}
    baseline_margin=[r["margin_y"]-r["margin_base"] for r in train]
    baseline_total=[r["total_y"]-r["total_base"] for r in train]
    sigmas={"margin":max(8,min(28,pstdev(baseline_margin))),"total":max(12,min(40,pstdev(baseline_total)))}
    return {"models":models,"sigmas":sigmas,"train_n":len(train),"validation_n":len(validation),"test_n":len(test),"metrics":evaluate(test,models)}

def evaluate(rows,models):
    out={}
    for target in RULES:
        model=models[target];base=[r["p"] if target=="moneyline" else r[target+"_base"] for r in rows]
        cand=[prediction(r,target,model["weights"],model["scale"]) for r in rows]
        if target=="moneyline":
            def metrics(values):return {"n":len(rows),"correct":sum((p>=.5)==bool(r["y"]) for p,r in zip(values,rows)),"brier":mean((p-r["y"])**2 for p,r in zip(values,rows)),"log_loss":mean(-(r["y"]*math.log(max(p,1e-12))+(1-r["y"])*math.log(max(1-p,1e-12))) for p,r in zip(values,rows))}
        else:
            def metrics(values):return {"n":len(rows),"mae":mean(abs(p-r[target+"_y"]) for p,r in zip(values,rows)),"rmse":math.sqrt(mean((p-r[target+"_y"])**2 for p,r in zip(values,rows)))}
        out[target]={"baseline":metrics(base),"candidate":metrics(cand)}
        differences=[(p-r["y"])**2-(q-r["y"])**2 if target=="moneyline" else abs(p-r[target+"_y"])-abs(q-r[target+"_y"]) for r,p,q in zip(rows,base,cand)]
        groups=defaultdict(list)
        for r,difference in zip(rows,differences):groups[r["day"]].append(difference)
        rng=Random(20261028);keys=sorted(groups);samples=[]
        for _ in range(250):
            selected=[groups[keys[rng.randrange(len(keys))]] for _ in keys]
            samples.append(sum(map(sum,selected))/sum(map(len,selected)))
        samples.sort();out[target]["improvement_ci95_day_bootstrap"]=[samples[6],samples[243]]
    return out

def probabilities(mu,sigma,line,total=False):
    """Continuity-corrected integer outcome bins, including a real push bin."""
    if type(line) not in (int,float) or not math.isfinite(line):return None
    boundary=line if total else -line
    if float(boundary).is_integer():
        low=NORMAL.cdf((boundary-.5-mu)/sigma);high=1-NORMAL.cdf((boundary+.5-mu)/sigma)
        push=max(0,1-low-high)
    else:
        low=NORMAL.cdf((boundary-mu)/sigma);high=1-low;push=0
    return {"positive":high,"negative":low,"push":push}

def contributions(row,target,model):
    values=row["total"] if target=="total" else row["side"]
    parts=[]
    for value,rule in zip(values,model["rules"]):
        parts.append({**rule,"value":value,"points":None if value is None else value*rule["weight"]})
    return {"score":score(values,model["weights"],RULES[target]),"parts":parts,"known":sum(v is not None for v in values),"possible":len(values),"fatigue_group_cap":2}

def forecast(row,fit,market,now,version):
    models=fit["models"]
    p=prediction(row,"moneyline",models["moneyline"]["weights"],models["moneyline"]["scale"])
    margin=prediction(row,"margin",models["margin"]["weights"],models["margin"]["scale"])
    total=prediction(row,"total",models["total"]["weights"],models["total"]["scale"])
    sp=(market or {}).get("spread") or {};tl=(market or {}).get("total") or {}
    cover=probabilities(margin,fit["sigmas"]["margin"],sp.get("home_line"));totals=probabilities(total,fit["sigmas"]["total"],tl.get("line"),True)
    side_score=contributions(row,"moneyline",models["moneyline"])["score"]
    total_score=contributions(row,"total",models["total"])["score"]
    spread_text=(f"主隊讓分線為{sp['home_line']:+g}，估計主隊過盤機率{cover['positive']:.1%}。" if cover else "讓分線尚未取得，先列模型淨勝估計，不產生過盤方向。")
    total_text=(f"總分線{tl['line']:g}，估計大分機率{totals['positive']:.1%}。" if totals else "總分線尚未取得，先列模型總分估計，不產生大小方向。")
    report=(f"本場採計分實驗模型，主隊為{row['home']}、客隊為{row['away']}。勝負因子合計{side_score:+d}分，主勝機率{p:.1%}；模型預估主隊淨勝{margin:+.1f}分。{spread_text}總分因子合計{total_score:+d}分，預估兩隊合計{total:.1f}分。{total_text}休息與密集賽程合計設有兩分上限，避免重複計分。傷停影響、旅行與時差尚無足夠歷史資料，不加權推測。歷史改善幅度小，未證明穩定優勢；請連同資料時間及逐項分數閱讀。")
    return {"event_id":row["event_id"],"date":row["date"],"home":row["home"],"away":row["away"],"generated_at_utc":now.isoformat(),"model_version":version,"report_zh":report,
            "home_win_probability":p,"expected_margin":margin,"expected_total":total,
            "baseline":{"home_win_probability":row["p"],"expected_margin":row["margin_base"],"expected_total":row["total_base"]},
            "scores":{t:contributions(row,t,models[t]) for t in RULES},"evidence":row["evidence"],"last_input_game":row["last_input_game"],
            "market":{"provider":(market or {}).get("provider"),"captured_at_utc":(market or {}).get("captured_at_utc"),"home_line":sp.get("home_line"),"total_line":tl.get("line")},
            "cover":cover,"totals":totals,
            "status":"experimental","promoted_to_champion":False,"not_enabled":["injury_impact","travel_distance","circadian_direction","historical_four_factors"]}

def odds_replay(rows,fit,archive,now):
    by_id={r["event_id"]:r for r in rows if r["y"] is not None};out=[];skipped=defaultdict(int)
    for event_id,item in (archive.get("games") or {}).items():
        q=item.get("first") or {};r=by_id.get(str(event_id));observed=when(q.get("observed_at_utc"));tip=when(r["date"]) if r else None
        if not r:skipped["no_final_or_features"]+=1;continue
        if not q.get("join_verified") or not q.get("eligible_for_pregame_backtest") or not observed or observed>now or observed>tip-timedelta(minutes=60):skipped["no_verified_pregame_line_at_60m"]+=1;continue
        if canon(q.get("home"))!=r["home"] or canon(q.get("away"))!=r["away"]:skipped["matchup_mismatch"]+=1;continue
        f=forecast(r,fit,{"spread":q.get("spread"),"total":q.get("total"),"provider":archive.get("source"),"captured_at_utc":q.get("observed_at_utc")},now,"replay")
        result={"event_id":r["event_id"],"day":r["day"],"home":r["home"],"away":r["away"],"line_observed_at":q["observed_at_utc"],"source_url":q.get("source_url"),"kind":"retrospective_not_real_frozen_factor_forecast"}
        for target,key,actual,line in [("spread","cover",r["margin_y"],f["market"]["home_line"]),("total","totals",r["total_y"],f["market"]["total_line"])]:
            probs=f[key]
            if probs is None:result[target]=None;continue
            value=actual-line if target=="total" else actual+line
            pick="positive" if probs["positive"]>=probs["negative"] else "negative"
            result[target]={"line":line,"pick":pick,"push":value==0,"hit":None if value==0 else ((value>0)==(pick=="positive"))}
            base_probs=probabilities(r["margin_base"] if target=="spread" else r["total_base"],fit["sigmas"]["margin" if target=="spread" else "total"],line,target=="total")
            base_pick=base_probs["positive"]>=base_probs["negative"]
            result[target]["baseline_hit"]=None if value==0 else ((value>0)==base_pick)
        out.append(result)
    summary={}
    for target in ("spread","total"):
        evaluated=[r[target] for r in out if r.get(target) and not r[target]["push"]]
        summary[target]={"n":len(evaluated),"correct":sum(x["hit"] for x in evaluated),"baseline_correct":sum(x["baseline_hit"] for x in evaluated),"pushes":sum(bool(r.get(target) and r[target]["push"]) for r in out)}
    return {"kind":"historical_replay_with_archived_pregame_lines","not_prospective":True,"rights_status":"review","rows":out,"summary":summary,"skipped":dict(skipped)}

def json_read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def atomic_json(path,data):
    tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n");tmp.replace(path)

def run(root,now=None):
    now=now or datetime.now(UTC);history=json_read(root/"history_games.json",{}).get("games",[]);public=json_read(root/"games.json",{});current=public.get("games",[])
    dependencies=b"".join((Path(__file__).parent/name).read_bytes() for name in ("factor_scorecard.py","score_model.py","analyst_factors.py"))
    fingerprint=hashlib.sha256(dependencies+f"{sys.version_info.major}.{sys.version_info.minor}".encode()+json.dumps(history,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    rows=build_records(history,current,now);cache=json_read(root/"factor-model-cache.json",{})
    reused=cache.get("fingerprint")==fingerprint and cache.get("schema_version")==SCHEMA
    fit=cache.get("fit") if reused else fit_models(rows)
    if not reused:atomic_json(root/"factor-model-cache.json",{"schema_version":SCHEMA,"fingerprint":fingerprint,"fit":fit,"created_at_utc":now.isoformat()})
    version="integer-v1-"+fingerprint[:12]
    markets={}
    for m in public.get("market_snapshots",[]):
        observed=when(m.get("captured_at_utc"));tip=when(m.get("date"))
        if not observed or observed>now or not tip or observed>=tip:continue
        key=str(m.get("event_id"));quality=sum((m.get("spread") or {}).get("home_line") is not None for _ in [0])+int((m.get("total") or {}).get("line") is not None)
        if key not in markets or quality>markets[key][0]:markets[key]=(quality,m)
    forecasts=[forecast(r,fit,markets.get(r["event_id"],(0,None))[1],now,version) for r in rows if r["y"] is None]
    ledger=json_read(root/"factor-pregame-ledger.json",{"schema_version":1,"records":[]});existing={(r["event_id"],r["model_version"]):r for r in ledger["records"]}
    added=0
    for f in forecasts:
        key=(f["event_id"],version)
        if key not in existing and when(f["date"])-now>=timedelta(minutes=60):existing[key]={**f,"frozen_at_utc":now.isoformat(),"settlement":None};added+=1
    finals={str(g["id"]):g for g in current if g.get("status")=="post" and valid_final(g,now)}
    for record in existing.values():
        g=finals.get(record["event_id"])
        if not g or record.get("settlement") is not None:continue
        # Only a genuine prior freeze can produce prospective evidence.
        if when(record["frozen_at_utc"])>when(record["date"])-timedelta(minutes=60):continue
        actual_margin=g["home_score"]-g["away_score"];actual_total=g["home_score"]+g["away_score"]
        result={"observed_at_utc":now.isoformat(),"moneyline_hit":(record["home_win_probability"]>=.5)==(actual_margin>0),"actual_margin":actual_margin,"actual_total":actual_total}
        for key,actual,line in [("spread",actual_margin,record["market"].get("home_line")),("total",actual_total,record["market"].get("total_line"))]:
            probability=record.get("cover" if key=="spread" else "totals")
            if line is None or probability is None:result[key]=None;continue
            value=actual+line if key=="spread" else actual-line
            pick=probability["positive"]>=probability["negative"]
            result[key]={"push":value==0,"hit":None if value==0 else pick==(value>0)}
        record["settlement"]=result
    ledger["records"]=sorted(existing.values(),key=lambda r:(r["date"],r["model_version"]));ledger["updated_at_utc"]=now.isoformat();atomic_json(root/"factor-pregame-ledger.json",ledger)
    settled=[r for r in ledger["records"] if r["model_version"]==version and r.get("settlement")]
    result={"schema_version":SCHEMA,"model_version":version,"generated_at_utc":now.isoformat(),"status":"experimental_live_shadow","champion_unchanged":True,"automatic_promotion":False,
            "method":"integer weights in [-2,2], fatigue group capped at two, train-only coordinate search, later-season scale selection",
            "validation":{"kind":"retrospective_day_frozen_replay","train_seasons":[2023,2024],"scale_selection_season":2025,"test_season":2026,"prior_research_used_this_test_season":True,"same_day_labels_withheld":True,**fit},
            "forecasts":forecasts,"odds_replay":odds_replay(rows,fit,json_read(root/"tw_odds_history.json",{}),now),
            "prospective":{"frozen_current_model":sum(r["model_version"]==version for r in ledger["records"]),"settled":len(settled),"moneyline_correct":sum(r["settlement"]["moneyline_hit"] for r in settled),"new_frozen":added},
            "cache":{"fit_reused":reused,"old_samples_refit":0 if reused else fit["train_n"],"fingerprint":fingerprint},
            "limitations":["Historical replay is not real frozen prospective performance.","Market directions require an observed line; missing odds are not synthesized.","Score-distribution probabilities are experimental, not ATS-calibrated.","Injury/travel/box-score impact lacks dated historical coverage and is not scored.","Candidate weights are public research rules; no original private model state is published."]}
    atomic_json(root/"factor-scorecard.json",result)
    print(json.dumps({"forecasts":len(forecasts),"train":fit["train_n"],"validation":fit["validation_n"],"test":fit["test_n"],"metrics":fit["metrics"],"weights":{t:m["weights"] for t,m in fit["models"].items()},"scales":{t:m["scale"] for t,m in fit["models"].items()},"odds_replay":result["odds_replay"]["summary"],"prospective":result["prospective"],"cache_reused":reused},ensure_ascii=False))
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--data-dir",default="data");args=parser.parse_args();run(Path(args.data_dir))
