#!/usr/bin/env python3
"""Conservative, rate-limited ingestion of previous-season PBP Stats NBA priors.

Two documented public endpoints, at most once per 24h, no anti-bot bypass.
Do not mistake previous-season PPP or seconds/possession for current-season
live efficiency. No inference of injuries, player on/off, or shot quality.
Source: https://api.pbpstats.com/docs
"""
from __future__ import annotations
import datetime as dt,json,pathlib,urllib.parse,urllib.request

ROOT=pathlib.Path("data")
ROOT.mkdir(exist_ok=True)
PATH=ROOT/"season_priors.json"
URL="https://api.pbpstats.com/get-pace-efficiency-summary/nba?Season=2025-26&SeasonType=Regular%20Season&Type=Team"
TOTALS_URL="https://api.pbpstats.com/get-totals/nba?Season=2025-26&SeasonType=Regular%20Season&Type=Team"
NOW=dt.datetime.now(dt.timezone.utc)

def parse_prior(d,captured):
    entries=d.get("results") if isinstance(d,dict) else None
    if not isinstance(entries,list):raise ValueError("PBP Stats results missing")
    out={}
    for x in entries:
        if not isinstance(x,dict):continue
        key=x.get("team_name")
        try:
            ppp=float(x.get("ppp"))
            spp=float(x.get("spp"))
            rank=int(x.get("ppp_rank"))
        except (TypeError,ValueError):continue
        if not isinstance(key,str) or not (2<=len(key)<=4 and key.isupper()):continue
        if not (.6<=ppp<=1.6 and 6<=spp<=28 and 1<=rank<=30):continue
        out[key]={"team":key,"team_id":str(x.get("team_id") or ""),
                  "offensive_points_per_possession_previous_season":round(ppp,4),
                  "offensive_seconds_per_possession_previous_season":round(spp,2),
                  "offensive_ppp_rank_previous_season":rank,
                  "season":"2025-26","source":"PBP Stats NBA regular season",
                  "not_current_season":True}
    if len(out)<28:raise ValueError("Insufficient PBP Stats teams "+str(len(out)))
    return {"captured_at_utc":captured,"source":"PBP Stats API publicly documented summary",
        "source_docs":"https://api.pbpstats.com/docs","season":"2025-26",
        "stats_meaning":"previous regular-season offensive PPP and offensive seconds per possession",
        "rights_status":"review","data_status":"observed_previous_season_aggregate",
        "teams":out,"team_count":len(out),
        "use_cases":["descriptive baseline","offseason comparison"],
        "excluded":["current-season pace","on/off injury changes","current lineup confirmation"]}

def combine_totals(prior,body):
    """Derive actual previous-season OffRtg, DefRtg and Pace from PBP possessions."""
    rows=body.get("multi_row_table_data") if isinstance(body,dict) else None
    if not isinstance(rows,list):raise ValueError("PBP team totals missing")
    good=0
    for row in rows:
        if not isinstance(row,dict):continue
        code=row.get("TeamAbbreviation")
        target=prior["teams"].get(code)
        if target is None:continue
        try:
            seconds=float(row["SecondsPlayed"])
            offense_pos=float(row["OffPoss"])
            defense_pos=float(row["DefPoss"])
            scored=float(row["Points"])
            conceded=float(row["OpponentPoints"])
            made2=float(row["FG2M"])
            made3=float(row["FG3M"])
            attempts2=float(row["FG2A"])
            attempts3=float(row["FG3A"])
            turnovers=float(row["Turnovers"])
            freethrows=float(row["FTA"])
            oreb_rate=float(row["OffFGReboundPct"])
        except (TypeError,ValueError,KeyError):continue
        if min(seconds,offense_pos,defense_pos,scored,conceded,attempts2+attempts3)<=0:continue
        ortg=100*scored/offense_pos
        drtg=100*conceded/defense_pos
        pace=(offense_pos+defense_pos)*1440/seconds
        efg=100*(made2+1.5*made3)/(attempts2+attempts3)
        tov=100*turnovers/offense_pos
        ftr=100*freethrows/(attempts2+attempts3)
        if not (80<=ortg<=160 and 80<=drtg<=160 and 70<=pace<=130 and 30<=efg<=85 and 0<oreb_rate<1):continue
        target.update({
          "offensive_rating_previous_season":round(ortg,2),
          "defensive_rating_previous_season":round(drtg,2),
          "net_rating_previous_season":round(ortg-drtg,2),
          "possessions_per_48_previous_season":round(pace,2),
          "efg_pct_previous_season":round(efg,2),
          "turnover_per_100_possessions_previous_season":round(tov,2),
          "offensive_fg_rebound_pct_previous_season":round(100*oreb_rate,2),
          "free_throw_attempt_rate_pct_previous_season":round(ftr,2),
          "total_offensive_possessions_previous_season":int(offense_pos),
          "total_defensive_possessions_previous_season":int(defense_pos)})
        good+=1
    if good<28:raise ValueError("Insufficient PBP possession-derived efficiency teams "+str(good))
    prior["possession_total_teams"]=good
    prior["stats_meaning"]="2025-26 offensive/defensive points per 100 PBP possessions, estimated possessions per 48, eFG, turnover, OREB, FTA and offense PPP/spp"
    return prior

def fetch_json(url):
    req=urllib.request.Request(url,headers={
        "Accept":"application/json",
        "User-Agent":"NBA-Paper-Lab-attributed-research/1.0"})
    with urllib.request.urlopen(req,timeout=25) as response:
        return json.loads(response.read(1200000))

def main():
    if PATH.exists():
        try:
            old=json.loads(PATH.read_text())
            at=dt.datetime.fromisoformat(old["captured_at_utc"].replace("Z","+00:00"))
            if old.get("team_count",0)>=28 and old.get("schema_version",0)>=2 and NOW-at<dt.timedelta(hours=24):
                print("Prior cache fresh:",old["team_count"],"teams")
                return
        except (OSError,ValueError,KeyError,TypeError):pass
    try:
        normalized=parse_prior(fetch_json(URL),NOW.isoformat())
        normalized["schema_version"]=2
        try:
            normalized=combine_totals(normalized,fetch_json(TOTALS_URL))
        except Exception as exc:
            normalized["possession_total_teams"]=0
            normalized["secondary_source_error_type"]=type(exc).__name__
            print("PBP Stats second endpoint unavailable:",type(exc).__name__)
        PATH.write_text(json.dumps(normalized,ensure_ascii=False,separators=(",",":"))+"\n")
        print("PBP Stats previous-season priors:",normalized["team_count"])
    except Exception as exc:
        print("PBP Stats prior request unavailable:",type(exc).__name__,str(exc)[:90])
        # Never destroy a previously verified snapshot or fabricate substitute values.
        if not PATH.exists():
            PATH.write_text(json.dumps({"captured_at_utc":NOW.isoformat(),"source":"PBP Stats API",
                "data_status":"unavailable","team_count":0,"teams":{},
                "rights_status":"review","error_type":type(exc).__name__},
                ensure_ascii=False)+"\n")

if __name__=="__main__":main()
