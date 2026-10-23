"""Fixed-parameter 10-season chronological NBA Elo baseline and heldout audit.

The 2025–26 season is evaluated prequentially using only prior results.
Elo constants are fixed before evaluation (home edge 65 Elo, K=20,
offseason regression 0.65). Do NOT interpret Brier as profit forecasts.
Separate moneyline evaluation from unvalidated spread/total approximations.
"""
from __future__ import annotations

import math
import statistics

BASE=1500.0
K=20.0
HOME_ADV=65.0
RETAIN=0.65
HOLDOUT_SEASON=2026

def win_prob(home_rating,away_rating):
    return 1.0/(1.0+10.0**((away_rating-home_rating-HOME_ADV)/400.0))

def safe_event(g):
    try:
        from datetime import datetime
        datetime.fromisoformat(str(g["date"]).replace("Z","+00:00"))
        home,away=g["home"],g["away"]
        if not home or not away or home==away:return False
        if not isinstance(g.get("home_score"),int) or not isinstance(g.get("away_score"),int):return False
        if g["home_score"]<55 or g["away_score"]<55 or g["home_score"]>230 or g["away_score"]>230:return False
        if g["home_score"]==g["away_score"]:return False
        return True
    except (KeyError,ValueError,TypeError):return False

def season(g):
    value=g.get("season_end",g.get("season_year"))
    try:return int(value)
    except (TypeError,ValueError):return None

def train_and_forecast(historical,current):
    """Returns one forecast per scheduled game, walk-forward evaluation metadata."""
    history={str(g["id"]):g for g in historical if g.get("id") and safe_event(g) and season(g) is not None}
    finals=[g for g in current if g.get("status")=="post" and safe_event(g)
        and (g.get("season_phase") in (None,2,"2"))]
    for g in finals:
        history[str(g["id"])]=g
    all_final=sorted(history.values(),key=lambda x:(x["date"],str(x["id"])))
    future=[g for g in current if g.get("status")=="pre" and g.get("date")]
    # Events are streamed in date order. Forecast must precede future score changes.
    work=sorted([(g["date"],0,g) for g in future]+[(g["date"],1,g) for g in all_final],
                key=lambda x:(x[0],x[1],str(x[2].get("id"))))
    elo={}
    active_season=None
    brier=[]
    logloss=[]
    preds=[]
    total_train=0
    for _date,is_final,g in work:
        year=season(g)
        if year is None:continue
        if active_season is None:active_season=year
        if year!=active_season:
            if year>active_season:
                for code in elo:elo[code]=BASE+(elo[code]-BASE)*RETAIN
            active_season=year
        home,away=g["home"],g["away"]
        ph=elo.get(home,BASE)
        pa=elo.get(away,BASE)
        p=win_prob(ph,pa)
        if not is_final:
            preds.append({"event_id":str(g["id"]),"date":g["date"],"home":home,"away":away,
              "home_win_probability":round(p,5),"model":"elo_10season_chronological_fixed",
              "validated":False,"training_seasons":"2016–17 through 2025–26, regular and postseason",
              "sample_size_at_prediction":total_train})
        else:
            result=1 if g["home_score"]>g["away_score"] else 0
            if year==HOLDOUT_SEASON and g.get("phase")!="preseason":
                brier.append((p-result)**2)
                q=max(1e-9,min(1-1e-9,p))
                logloss.append(-(result*math.log(q)+(1-result)*math.log(1-q)))
            shift=K*(result-p)
            elo[home]=ph+shift
            elo[away]=pa-shift
            total_train+=1
    preds.sort(key=lambda x:(x["date"],x["event_id"]))
    n=len(brier)
    return preds,{
        "sample_size":n,"out_of_sample":n>=1000,
        "brier":round(statistics.mean(brier),5) if n else None,
        "log_loss":round(statistics.mean(logloss),5) if n else None,
        "holdout_season_end":HOLDOUT_SEASON,
        "historical_final_games":len([x for x in all_final if season(x)<=2026]),
        "training_games_through_snapshot":total_train,
        "seasons":"2016-17–2025-26",
        "model":"fixed_elo_chronological",
        "spread_total_validated":False,
        "notes":"2025–26逐場時序滾動檢驗：賽前僅用已完賽結果；參數固定，未對盤口或投注獲利做驗證。仍需跨季外部測試。",
    }
