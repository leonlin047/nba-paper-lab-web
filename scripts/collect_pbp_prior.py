#!/usr/bin/env python3
"""Conservative, rate-limited ingestion of previous-season PBP Stats NBA priors.

One documented public endpoint, at most once per 24h, no anti-bot bypass.
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

def main():
    if PATH.exists():
        try:
            old=json.loads(PATH.read_text())
            at=dt.datetime.fromisoformat(old["captured_at_utc"].replace("Z","+00:00"))
            if old.get("team_count",0)>=28 and NOW-at<dt.timedelta(hours=24):
                print("Prior cache fresh:",old["team_count"],"teams")
                return
        except (OSError,ValueError,KeyError,TypeError):pass
    try:
        req=urllib.request.Request(URL,headers={
            "Accept":"application/json","User-Agent":"NBA-Paper-Lab-attributed-research/1.0"})
        with urllib.request.urlopen(req,timeout=25) as resp:
            d=json.loads(resp.read(500000))
        normalized=parse_prior(d,NOW.isoformat())
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
