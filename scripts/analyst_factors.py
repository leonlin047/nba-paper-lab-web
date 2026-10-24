"""Explainable, timestamp-safe NBA matchup evidence. Research only.

Factor statements are *descriptive observations*, not claims of causal impact.
Pace and efficiencies require possessions; points-per-game are NOT OffRtg/DefRtg.
Historical box scores use only already-final ESPN summaries.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from statistics import mean, pstdev
import math

TEAM_ALIAS={"GSW":"GS","NOP":"NO","NYK":"NY","SAS":"SA","UTA":"UTAH","WAS":"WSH"}
def canon(s):return TEAM_ALIAS.get(s,s)
def when(s):
    try:
        x=datetime.fromisoformat(str(s).replace("Z","+00:00"))
        return x if x.tzinfo else None
    except (TypeError,ValueError,OverflowError):return None
def valid_final(g,cutoff):
    date=when(g.get("date"))
    if date is None or date>=cutoff or not g.get("home") or not g.get("away"):return False
    x,y=g.get("home_score"),g.get("away_score")
    return (type(x)==int and type(y)==int and 55<=x<=210 and 55<=y<=210 and x!=y)
def self_scores(g,abbr):
    if canon(g["home"])==abbr:return g["home_score"],g["away_score"],True
    if canon(g["away"])==abbr:return g["away_score"],g["home_score"],False
    return None
def team_form(games,abbr,kickoff,limit=12):
    key=canon(abbr)
    rows=[g for g in games if valid_final(g,kickoff) and
          (canon(g["home"])==key or canon(g["away"])==key)]
    rows.sort(key=lambda g:g["date"])
    rows=rows[-limit:]
    if not rows:return {"team":key,"n":0,"updated_at_utc":None}
    scoring=[self_scores(g,key) for g in rows]
    home_rows=[(g,t) for g,t in zip(rows,scoring) if t[2]]
    away_rows=[(g,t) for g,t in zip(rows,scoring) if not t[2]]
    last_time=when(rows[-1]["date"])
    hours_gap=max(0,round((kickoff-last_time).total_seconds()/3600,1))
    offseason_gap=hours_gap>24*14
    rest_hours=None if offseason_gap else hours_gap
    rest_days=None if offseason_gap else max(0,round(hours_gap/24-1,1))
    # Back-to-back only applies to closely spaced real matches.
    b2b=rest_hours is not None and rest_hours<=36
    target_year=kickoff.year+1 if kickoff.month>=10 else kickoff.year
    current_season_n=sum(
        int(g.get("season_end") or g.get("season_year") or 0)==target_year
        for g in rows)
    pts=[v[0] for v in scoring]
    conceded=[v[1] for v in scoring]
    margins=[a-b for a,b in zip(pts,conceded)]
    totals=[a+b for a,b in zip(pts,conceded)]
    last5=margins[-5:]
    def loc(rows_):return {
        "n":len(rows_),
        "avg_scored":round(mean(r[1][0] for r in rows_),1) if rows_ else None,
        "avg_allowed":round(mean(r[1][1] for r in rows_),1) if rows_ else None,
        "avg_margin":round(mean(r[1][0]-r[1][1] for r in rows_),1) if rows_ else None}
    return {
        "team":key,"n":len(rows),
        "last_event_id":str(rows[-1].get("id")),
        "updated_at_utc":rows[-1]["date"],
        "avg_scored":round(mean(pts),1),
        "avg_allowed":round(mean(conceded),1),
        "avg_margin":round(mean(margins),1),
        "avg_total":round(mean(totals),1),
        "total_sd":round(pstdev(totals),1) if len(totals)>1 else None,
        "wins":sum(x>0 for x in margins),
        "last5_wins":sum(x>0 for x in last5),
        "last5_avg_margin":round(mean(last5),1),
        "home":loc(home_rows),"away":loc(away_rows),
        "rest_hours":rest_hours,"rest_days":rest_days,
        "back_to_back_proxy":b2b,
        "offseason_gap":offseason_gap,"current_season_n":current_season_n
    }
def matchup_form(game,history):
    kickoff=when(game.get("date"))
    if kickoff is None:return {"available":False,"reason":"賽事時間無法驗證"}
    home,away=canon(game["home"]),canon(game["away"])
    finals={str(g["id"]):g for g in history if g.get("id") and valid_final(g,kickoff)}
    pool=list(finals.values())
    h=team_form(pool,home,kickoff)
    a=team_form(pool,away,kickoff)
    h2h=[g for g in pool if
         {canon(g["home"]),canon(g["away"])}=={home,away} and
         when(g["date"])>=kickoff-timedelta(days=730)]
    h2h.sort(key=lambda g:g["date"])
    latest=h2h[-4:]
    margin_for_home=[self_scores(g,home)[0]-self_scores(g,home)[1] for g in latest]
    return {"available":bool(h["n"] and a["n"]),
        "source":"ESPN game results / ten season archive",
        "as_of_utc":kickoff.isoformat(),
        "home":h,"away":a,
        "h2h":{"n":len(latest),"avg_home_team_margin":round(mean(margin_for_home),1) if latest else None,
               "match_ids":[str(g.get("id")) for g in latest]},
        "limitations":["僅為已完賽比分之描述性特徵；得分不等於每100回合攻防效率",
                       "最近樣本跨球員交易或換帥時可能失準",
                       "背靠背依開賽間隔推定，不代表球員實際出賽時間"]}

def parse_made_attempted(s):
    try:
        v=str(s).strip().split("-")
        if len(v)!=2:return None
        a,b=int(v[0]),int(v[1])
        return (a,b) if 0<=a<=b<=150 else None
    except (ValueError,TypeError):return None
def extract_four_factors(summary,event_id,captured_at):
    """Parse real ESPN boxscore team statistics. Compute APPROXIMATE possessions.
    Never confuse that with NBA's tracking possessions or pace.
    """
    teams=((summary.get("boxscore") or {}).get("teams") or [])
    samples=[]
    for t in teams:
        abbr=(t.get("team") or {}).get("abbreviation")
        if not abbr:continue
        stats={x.get("name"):x.get("displayValue") for x in t.get("statistics",[]) if isinstance(x,dict)}
        fg=parse_made_attempted(stats.get("fieldGoalsMade-fieldGoalsAttempted"))
        tp=parse_made_attempted(stats.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
        ft=parse_made_attempted(stats.get("freeThrowsMade-freeThrowsAttempted"))
        def whole(k):
            try:
                v=int(stats.get(k))
                return v if 0<=v<=150 else None
            except (ValueError,TypeError):return None
        oreb,drb,tov=whole("offensiveRebounds"),whole("defensiveRebounds"),whole("totalTurnovers")
        if not all(x is not None for x in (fg,tp,ft,oreb,drb,tov)) or fg[1]==0:continue
        possessions=fg[1]-oreb+tov+0.44*ft[1]
        if not 50<=possessions<=150:continue
        samples.append({
           "team":canon(abbr),"game_id":str(event_id),"captured_at_utc":captured_at,
           "estimated_possessions":round(possessions,1),
           "eFG_pct":round((fg[0]+0.5*tp[0])/fg[1]*100,1),
           "three_point_attempt_rate":round(tp[1]/fg[1]*100,1),
           "turnover_per_est_poss_pct":round(tov/possessions*100,1),
           "free_throw_attempt_rate":round(ft[1]/fg[1]*100,1),
           "oreb":oreb,"dreb":drb,"fga":fg[1],"fta":ft[1],
           "quality":"observed_boxscore_derived_approximate",
           "method":"FGA-OREB+TO+0.44*FTA approximate possessions",
           "source":"ESPN completed-game boxscore"})
    return samples

def matchup_box_factors(game,box_samples,max_days=40):
    cutoff=when(game.get("date"))
    if cutoff is None:return {"home":None,"away":None}
    out={}
    for side in ("home","away"):
        abbr=canon(game[side])
        entries=[x for x in box_samples if canon(x.get("team"))==abbr and
          when(x.get("date")) and cutoff-timedelta(days=max_days)<=when(x["date"])<cutoff]
        entries.sort(key=lambda x:x["date"])
        recent=entries[-8:]
        out[side]={"n":len(recent),
             "games":[x["game_id"] for x in recent],
             "eFG_pct":round(mean(x["eFG_pct"] for x in recent),1) if len(recent)>=3 else None,
             "estimated_possessions":round(mean(x["estimated_possessions"] for x in recent),1) if len(recent)>=3 else None,
             "three_point_attempt_rate":round(mean(x["three_point_attempt_rate"] for x in recent),1) if len(recent)>=3 else None,
             "turnover_per_est_poss_pct":round(mean(x["turnover_per_est_poss_pct"] for x in recent),1) if len(recent)>=3 else None,
             "free_throw_attempt_rate":round(mean(x["free_throw_attempt_rate"] for x in recent),1) if len(recent)>=3 else None,
             "source":"ESPN summary completed game team box statistics",
             "quality":"insufficient_n" if len(recent)<3 else "observed_approximate"}
    return out

def injuries_by_matchup(game,injury_snapshot):
    cutoff=when(game.get("date"))
    captured=when(injury_snapshot.get("captured_at"))
    if not cutoff or not captured:return {"available":False,"note":"傷病來源或擷取時間缺失"}
    # Do NOT assert historical snapshot injury info as known before earlier tipoff.
    if captured>cutoff:return {"available":False,"note":"傷病擷取晚於該場開賽，不可用於賽前分析"}
    team_codes={canon(game["home"]),canon(game["away"])}
    rows=[]
    for injury in injury_snapshot.get("injuries",[]):
        abbr=canon(injury.get("team"))
        if abbr not in team_codes:continue
        status=str(injury.get("status") or "未公布")
        rows.append({"team":abbr,"player":injury.get("player"),"status":status,
          "type":injury.get("type"),"reported_at_utc":injury.get("date"),
          "source":"ESPN injury overview (not official game-specific designation)"})
    return {"available":not injury_snapshot.get("errors"),
        "captured_at_utc":injury_snapshot.get("captured_at"),
        "source":"ESPN NBA injuries",
        "official_game_specific":False,
        "fresh":abs((cutoff-captured).total_seconds())<=72*3600,
        "rows":rows[:35],
        "unknown_impact":True,
        "note":"傷病狀態不等於確認先發，未建立經驗證球員上場時間與正負值，故不擅自調整勝率"}
