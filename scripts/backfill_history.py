#!/usr/bin/env python3
"""Resumable ESPN NBA ten-season game-result archive (2016-17 .. 2025-26).

Source: ESPN site v2 team schedules. Only completed *historical outcomes*.
No future scores, no synthetic rows and no copied predictive ratings.
Rate limit: one request ~0.8 sec; retry transient errors and preserve progress.
"""
import datetime as dt
import json
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=pathlib.Path("data")
ROOT.mkdir(exist_ok=True)
GAMES=ROOT/"history_games.json"
STATUS=ROOT/"history_status.json"
BASE="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
SEASONS=list(range(2017,2027))
HEAD={"User-Agent":"NBA-Paper-Lab-history/1.0 (public schedule research)","Accept":"application/json"}


def fetch(route,params=None):
    url=BASE+route
    if params:url+="?"+urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers=HEAD)
            with urllib.request.urlopen(req,timeout=18) as resp:
                return json.loads(resp.read(4000000))
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError):
            if attempt==2:raise
            time.sleep(2+attempt*3)


def teams_from_response(d):
    raw=d.get("sports",[])
    if raw:
        raw=raw[0].get("leagues",[])
        raw=raw[0].get("teams",[]) if raw else []
    else:raw=d.get("teams",[])
    out=[]
    for item in raw:
        team=item.get("team",item) if isinstance(item,dict) else {}
        if team.get("id") and team.get("abbreviation"):
            out.append(str(team["id"]))
    return sorted(set(out),key=int)


def score(c):
    raw=c.get("score")
    if isinstance(raw,dict):raw=raw.get("value",raw.get("displayValue"))
    try:
        x=int(float(raw))
        return x if 0<=x<=230 else None
    except (TypeError,ValueError):return None


def game(e,season,phase):
    try:
        comp=e["competitions"][0]
        sides={c["homeAway"]:c for c in comp["competitors"]}
        h,a=sides["home"],sides["away"]
        # Team schedule entries often omit status even for final scored games.
        meta=e.get("season",{})
        if isinstance(meta,dict) and meta.get("year") is not None and int(meta["year"])!=season:return None
        phase_meta=e.get("seasonType",{})
        if isinstance(phase_meta,dict) and phase_meta.get("type") is not None and int(phase_meta["type"])!=phase:return None
        when=dt.datetime.fromisoformat(str(e["date"]).replace("Z","+00:00"))
        if when.tzinfo is None or when>=dt.datetime.now(dt.timezone.utc):return None
        status=e.get("status",{}).get("type",{})
        if status and status.get("completed") is not True and str(status.get("state"))!="post":return None
        hs,as_=score(h),score(a)
        if hs is None or as_ is None or hs==as_:return None
        home,away=h["team"]["abbreviation"],a["team"]["abbreviation"]
        if home==away or not e.get("id") or not e.get("date"):return None
        return {"id":str(e["id"]),"date":e["date"],"season_end":season,
         "phase":"regular" if phase==2 else "postseason","home":home,"away":away,
         "home_score":hs,"away_score":as_}
    except (KeyError,IndexError,TypeError,ValueError):return None


def main():
    existing=json.loads(GAMES.read_text()) if GAMES.exists() else {"games":[]}
    archive={str(g["id"]):g for g in existing.get("games",[]) if g.get("id")}
    prev=json.loads(STATUS.read_text()) if STATUS.exists() else {}
    completed=set(prev.get("completed_sources",[]))
    # Previous status-less-event bug incorrectly marked 600 sources as complete.
    if prev.get("game_count")==0 and completed:completed.clear()
    errors=[]
    teams=teams_from_response(fetch("teams"))
    if len(teams)<28:
        raise SystemExit("ESPN returned insufficient team identifiers: "+str(len(teams)))
    # Limit per run if needed while retaining cursor state; default all 10 seasons.
    max_sources=max(1,int(os.getenv("NBA_HISTORY_BATCH_SOURCES","650")))
    processed=0
    for season in SEASONS:
        for phase in (2,3):
            for team in teams:
                key=f"{season}/{phase}/{team}"
                if key in completed:continue
                if processed>=max_sources:break
                try:
                    data=fetch(f"teams/{team}/schedule",{"season":season,"seasontype":phase})
                    rows=data.get("events",[])
                    if not isinstance(rows,list):raise ValueError("schedule events not list")
                    for e in rows:
                        result=game(e,season,phase)
                        if result:archive[result["id"]]=result
                    if phase==2 and not any(
                        isinstance(x.get("season"),dict) and int(x["season"].get("year",0))==season
                        for x in rows):raise ValueError("regular-season response missing requested season")
                    completed.add(key)
                except Exception as exc:
                    errors.append({"source":key,"error":type(exc).__name__})
                processed+=1
                time.sleep(0.75)
            if processed>=max_sources:break
        if processed>=max_sources:break
    games=sorted(archive.values(),key=lambda x:(x["date"],x["id"]))
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    counts={str(y):sum(x["season_end"]==y for x in games) for y in SEASONS}
    GAMES.write_text(json.dumps({"captured_at":now,"source":"ESPN public NBA team schedules","games":games},ensure_ascii=False,separators=(",",":"))+"\n")
    sufficiently_covered=all(counts[str(y)]>=600 for y in SEASONS)
    STATUS.write_text(json.dumps({"updated_at_utc":now,"years":SEASONS,"regular_and_playoffs":True,
        "completed_sources":sorted(completed),"expected_sources":len(SEASONS)*2*len(teams),
        "games_by_season":counts,"game_count":len(games),"errors":errors,
        "complete":len(completed)==len(SEASONS)*2*len(teams) and sufficiently_covered,
        "note":"Complete only with all source queries and at least 600 actual scored games per season."},ensure_ascii=False,separators=(",",":"))+"\n")
    print("NBA history:",len(games),"games,",len(completed),"/",len(SEASONS)*2*len(teams),"sources; errors:",len(errors))

if __name__=="__main__":main()
