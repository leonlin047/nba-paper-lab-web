"""NBA pregame margin/total distribution with dated feature evidence and frozen validation.

No historical betting lines are claimed. Holdout evaluates actual final point
margin and total only, not ATS hit rate, profitability, or a bookmaker edge.
Parameters chosen before holdout: Elo margin blend=0.55, form blend=0.45,
team shrink constant=8, rolling team last 12, league baseline last 100.
Residual sigma learned exclusively on seasons <=2024-25.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import isfinite, log, sqrt
from statistics import NormalDist, mean, pstdev

from analyst_factors import canon,when,valid_final
NORM=NormalDist()
HISTORY_SD=14.0
SHRINK=8.0
BLEND_ELO=.55
BLEND_FORM=.45
TRAIN_SEASON_END=2025
HOLDOUT_SEASON_END=2026

def sample_model(g,team_games,league_games,elo_prob=None):
    """Rolling only games < tipoff. Outputs explainable predicted margin and total."""
    tip=when(g.get("date"))
    if tip is None:return None
    def eligible(rows):
        return [x for x in rows[-75:] if valid_final(x,tip) and
           when(x["date"])>=tip-timedelta(days=365)][-12:]
    home=canon(g.get("home"))
    away=canon(g.get("away"))
    hs=eligible(team_games.get(home,[]))
    a_s=eligible(team_games.get(away,[]))
    league=eligible_league(league_games,tip)
    if len(league)<50 or len(hs)<3 or len(a_s)<3:return None
    base=mean((x["home_score"]+x["away_score"])/2 for x in league)
    def offense(code,rows):
        own=[x["home_score"] if canon(x["home"])==code else x["away_score"] for x in rows]
        conceded=[x["away_score"] if canon(x["home"])==code else x["home_score"] for x in rows]
        w=len(rows)/(len(rows)+SHRINK)
        return base+w*(mean(own)-base),base+w*(mean(conceded)-base)
    hf,ha=offense(home,hs)
    af,aa=offense(away,a_s)
    # Regular-season home advantage estimated from already completed league results.
    avg_home_margin=mean(x["home_score"]-x["away_score"] for x in league)
    avg_home_margin=max(-8,min(8,avg_home_margin))
    home_pts=(hf+aa)/2+avg_home_margin/2
    away_pts=(af+ha)/2-avg_home_margin/2
    form_margin=home_pts-away_pts
    total=home_pts+away_pts
    if isinstance(elo_prob,(int,float)) and 0<elo_prob<1 and isfinite(elo_prob):
        elo_margin=NORM.inv_cdf(max(.002,min(.998,elo_prob)))*HISTORY_SD
        margin=BLEND_ELO*elo_margin+BLEND_FORM*form_margin
    else:
        elo_margin=None
        margin=form_margin
    return {"expected_home_points":round(home_pts,2),
        "expected_away_points":round(away_pts,2),
        "expected_margin":round(margin,2),
        "expected_total":round(total,2),
        "elo_margin_component":round(elo_margin,2) if elo_margin is not None else None,
        "form_margin_component":round(form_margin,2),
        "league_home_margin":round(avg_home_margin,2),
        "league_games_n":len(league),
        "home_form_n":len(hs),"away_form_n":len(a_s),
        "method":"55% Elo margin + 45% shrunk points for/against; total from shrunk scoring; no injury effect fitted",
        "source":"ESPN historical NBA final scores, strictly pre-tipoff"}

def eligible_league(league_games,tip):
    window_start=tip-timedelta(days=365)
    out=[x for x in league_games[-150:] if window_start<=when(x["date"])<tip]
    return out[-100:]

def evaluate_and_project(historical,current,predictions):
    """Score model is train-calibrated on seasons<=2025, tested on 2025-26.
    Calibrate sigma on historical score residuals without using holdout outcomes.
    """
    max_time=datetime.max.replace(tzinfo=timezone.utc)
    finals={str(g["id"]):g for g in historical if g.get("id") and valid_final(g,max_time)}
    for g in current:
        if g.get("status")=="post" and g.get("id") and
            g.get("season_phase") in (None,2,"2",3,"3") and
            valid_final(g,max_time):
            finals[str(g["id"])]=g
    events=sorted(finals.values(),key=lambda x:(x["date"],str(x["id"])))
    by_team=defaultdict(list)
    league=[]
    elo=defaultdict(lambda:1500.0)
    prev_season=None
    train_margin_errors=[]
    train_total_errors=[]
    holdout_margin=[]
    holdout_total=[]
    holdout_winner_probs=[]
    holdout_winner_truth=[]
    for g in events:
        year=g.get("season_end",g.get("season_year"))
        try:year=int(year)
        except (TypeError,ValueError):continue
        if prev_season is not None and prev_season!=year:
            if year>prev_season:
                for code in elo:elo[code]=1500+(elo[code]-1500)*.65
        prev_season=year
        h,a=canon(g["home"]),canon(g["away"])
        p=1/(1+10**((elo[a]-elo[h]-65)/400))
        projection=sample_model(g,by_team,league,p)
        margin=g["home_score"]-g["away_score"]
        total=g["home_score"]+g["away_score"]
        if projection:
            err_margin=projection["expected_margin"]-margin
            err_total=projection["expected_total"]-total
            if 2023<=year<=TRAIN_SEASON_END:
                train_margin_errors.append(err_margin)
                train_total_errors.append(err_total)
            elif year==HOLDOUT_SEASON_END:
                holdout_margin.append(err_margin)
                holdout_total.append(err_total)
        # Full-season Elo win baseline evaluated separately in elo_history.py
        if year==HOLDOUT_SEASON_END:
            holdout_winner_probs.append(p)
            holdout_winner_truth.append(1 if margin>0 else 0)
        delta=20*((1 if margin>0 else 0)-p)
        elo[h]+=delta
        elo[a]-=delta
        by_team[h].append(g)
        by_team[a].append(g)
        league.append(g)
    margin_sd=max(8.0,min(28.0,pstdev(train_margin_errors))) if len(train_margin_errors)>150 else None
    total_sd=max(12.0,min(40.0,pstdev(train_total_errors))) if len(train_total_errors)>150 else None
    metrics={
        "method":"chronological rolling score projection with fixed coefficients",
        "train_window":"2022-23 to 2024-25",
        "holdout_season":"2025-26",
        "train_margin_n":len(train_margin_errors),"train_total_n":len(train_total_errors),
        "holdout_margin_n":len(holdout_margin),"holdout_total_n":len(holdout_total),
        "margin_mae":round(mean(abs(v) for v in holdout_margin),3) if holdout_margin else None,
        "total_mae":round(mean(abs(v) for v in holdout_total),3) if holdout_total else None,
        "margin_rmse":round(sqrt(mean(v*v for v in holdout_margin)),3) if holdout_margin else None,
        "total_rmse":round(sqrt(mean(v*v for v in holdout_total)),3) if holdout_total else None,
        "margin_sigma_from_train":round(margin_sd,3) if margin_sd else None,
        "total_sigma_from_train":round(total_sd,3) if total_sd else None,
        "margin_interval_68_coverage":round(mean(abs(v)<=margin_sd for v in holdout_margin),4) if margin_sd and holdout_margin else None,
        "total_interval_68_coverage":round(mean(abs(v)<=total_sd for v in holdout_total),4) if total_sd and holdout_total else None,
        "ats_brier":None,"over_under_brier":None,
        "validated_against_historical_odds":False,
        "notes":"獨立季回放僅驗證預測比分誤差。沒有完整歷史盤口及時間戳前，無法宣稱過盤勝率準確或有正期望值。"}
    pregame_by_id={str(p["event_id"]):p for p in predictions}
    future=sorted([g for g in current if g.get("status")=="pre" and str(g.get("id")) in pregame_by_id],key=lambda x:x.get("date") or "")
    # Calibrated before target season; incremental completed 2026-27 finals retained.
    forecasts={}
    for g in future:
        tip=when(g.get("date"))
        if tip is None:continue
        for x in (g["home"],g["away"]):
            by_team[canon(x)].sort(key=lambda row:row["date"])
        forecasts[str(g["id"])]=sample_model(g,by_team,league,pregame_by_id[str(g["id"])].get("home_win_probability"))
        v=forecasts[str(g["id"])]
        if v:
            v["margin_sigma"]=round(margin_sd,3) if margin_sd else None
            v["total_sigma"]=round(total_sd,3) if total_sd else None
            v["trained_before"]="2025-26 historical holdout"
            v["calibrated_from"]="2022-23–2024-25 score residuals"
    return forecasts,metrics

def market_probabilities(projection,market):
    if not projection or not market:return {"spread":None,"total":None}
    m=market.get("spread") or {}
    t=market.get("total") or {}
    line=m.get("home_line")
    total_line=t.get("line")
    result={"spread":None,"total":None}
    if isinstance(line,(int,float)) and not isinstance(line,bool) and projection.get("margin_sigma"):
        p=NORM.cdf((projection["expected_margin"]+line)/projection["margin_sigma"])
        result["spread"]={"home":round(p,5),"away":round(1-p,5) if not float(line).is_integer() else None,
                          "push_possible":float(line).is_integer(),"home_line":line,
                          "method":"score residual sigma fit on 2022-23–2024-25, not historical ATS calibrated"}
    if isinstance(total_line,(int,float)) and not isinstance(total_line,bool) and projection.get("total_sigma"):
        p=NORM.cdf((projection["expected_total"]-total_line)/projection["total_sigma"])
        result["total"]={"over":round(p,5),"under":round(1-p,5) if not float(total_line).is_integer() else None,
                         "push_possible":float(total_line).is_integer(),"line":total_line,
                         "method":"score residual sigma fit on 2022-23–2024-25, not historical O/U calibrated"}
    return result
