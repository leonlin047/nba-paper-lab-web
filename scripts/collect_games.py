#!/usr/bin/env python3
"""Collect public ESPN game schedule, final box-score details, and experimental pregame Elo.
Research snapshots only. Respect provider terms; no access-control bypass.
"""
import datetime as dt, json, pathlib, time, urllib.request, urllib.parse
UTC=dt.timezone.utc
ROOT=pathlib.Path("data")
ROOT.mkdir(exist_ok=True)
HEAD={"User-Agent":"NBA-Paper-Lab-research/1.0 (public-data research)","Accept":"application/json"}
BASE="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
def fetch(endpoint,params=None):
    url=BASE+endpoint
    if params:url+="?"+urllib.parse.urlencode(params)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=22) as resp:
                raw=resp.read(2500000)
            return json.loads(raw)
        except Exception as e:
            if attempt==1:raise
            time.sleep(1)
def sides(c):
    teams={t["homeAway"]:t for t in c["competitors"]}
    return teams["home"],teams["away"]
def game(e):
    c=e["competitions"][0];h,a=sides(c)
    st=e.get("status",{}).get("type",{})
    def score(x):
        try:return int(x["score"])
        except (KeyError,TypeError,ValueError):return None
    return {"id":e["id"],"date":e.get("date"),"home":h["team"]["abbreviation"],"away":a["team"]["abbreviation"],"home_name":h["team"].get("displayName"),"away_name":a["team"].get("displayName"),"home_score":score(h),"away_score":score(a),"status":st.get("state"),"status_label":st.get("description"),"venue":c.get("venue",{}).get("fullName"),"broadcasts":[b.get("names",[]) for b in c.get("broadcasts",[])]}
today=dt.datetime.now(UTC).date()
events={}
errors=[]
# ESPN scoreboard accepts single-day YYYYMMDD dates; unsupported ranges caused HTTP 400.
# Collect recent completed games and next seven days, with bounded requests.
for offset in list(range(-14,1))+list(range(1,8)):
    day=today+dt.timedelta(days=offset)
    try:
        data=fetch("scoreboard",{"dates":day.strftime("%Y%m%d"),"limit":"100"})
        for e in data.get("events",[]):
            try:events[e["id"]]=game(e)
            except (KeyError,IndexError,TypeError):pass
    except Exception as exc:
        errors.append(day.isoformat()+": "+str(exc)[:100])
# Fallback to default scoreboard when dated queries fail.
if not events:
    try:
        data=fetch("scoreboard")
        for e in data.get("events",[]):
            try:events[e["id"]]=game(e)
            except (KeyError,IndexError,TypeError):pass
    except Exception as exc:errors.append("default scoreboard: "+str(exc)[:100])
games=sorted(events.values(),key=lambda x:x.get("date") or "")
if not games:
    raise SystemExit("No games fetched; keep previous snapshot. "+str(errors))
# Never train on future results: ordered completed events only.
elo={}
predictions=[]
for g in games:
    h,a=g["home"],g["away"]
    ph=elo.get(h,1500);pa=elo.get(a,1500)
    p=1/(1+10**((pa-ph-65)/400))
    if g["status"]=="pre":
        predictions.append({"event_id":g["id"],"date":g["date"],"home":h,"away":a,"home_win_probability":round(p,4),"model":"elo_recent_experimental","validated":False})
    elif g["status"]=="post" and g["home_score"] is not None and g["away_score"] is not None:
        result=1 if g["home_score"]>g["away_score"] else 0
        shift=20*(result-p)
        elo[h]=ph+shift;elo[a]=pa-shift
# ESPN summary may include licensed/attributed market lines. Never infer missing prices.
# This is source discovery only; publication requires rights review.
odds_discovery=[]
for g in [x for x in games if x["status"]=="pre"][:8]:
    try:
        d=fetch("summary",{"event":g["id"]})
        for q in d.get("pickcenter",[]) or []:
            if not isinstance(q,dict):continue
            provider=q.get("provider") or {}
            odds_discovery.append({"event_id":g["id"],"provider":provider.get("name") if isinstance(provider,dict) else str(provider),"spread":q.get("spread"),"over_under":q.get("overUnder"),"details":q.get("details"),"home_moneyline":q.get("homeTeamOdds",{}).get("moneyLine") if isinstance(q.get("homeTeamOdds"),dict) else None,"away_moneyline":q.get("awayTeamOdds",{}).get("moneyLine") if isinstance(q.get("awayTeamOdds"),dict) else None,"captured_at_utc":dt.datetime.now(UTC).isoformat(),"rights_status":"review"})
    except Exception as exc:errors.append("odds discovery "+g["id"]+": "+str(exc)[:80])
# Public NBA odds endpoint: normalize observed markets only, never synthesize quotes.
# Treat upstream rights as review until authorized for public redistribution.
odds_observations=[]
try:
    with urllib.request.urlopen(urllib.request.Request(
        "https://cdn.nba.com/static/json/liveData/odds/odds_todaysGames.json",headers=HEAD),timeout=15) as response:
        raw=response.read(2500000)
    odds_raw=json.loads(raw)
    candidate=odds_raw.get("games",[])
    if isinstance(candidate,dict):candidate=list(candidate.values())
    for event in candidate:
        if not isinstance(event,dict):continue
        for market in event.get("markets",[]) or []:
            if not isinstance(market,dict):continue
            for book in market.get("books",[]) or []:
                if not isinstance(book,dict):continue
                for outcome in book.get("outcomes",[]) or []:
                    if not isinstance(outcome,dict):continue
                    try:
                        price=float(outcome["odds"])
                        if not (1<price<10000):continue
                    except (ValueError,TypeError,KeyError):continue
                    odds_observations.append({"nba_game_id":event.get("gameId"),"market":market.get("name"),"bookmaker":book.get("name"),"book_country":book.get("countryCode"),"selection":outcome.get("type"),"decimal_odds":price,"spread":outcome.get("spread"),"opening_odds":outcome.get("opening_odds"),"opening_spread":outcome.get("opening_spread"),"captured_at_utc":dt.datetime.now(UTC).isoformat(),"rights_status":"review"})
except Exception as exc:
    errors.append("NBA public odds endpoint: "+str(exc)[:110])
# Normalize ESPN-discovered American odds into decimal and no-vig probabilities.
# Do not label these observations as licensed public redistribution.
def american_to_decimal(x):
    try:
        n=float(x)
        if n==0:return None
        return round(1+n/100 if n>0 else 1+100/abs(n),5)
    except (ValueError,TypeError):return None
normalized_markets=[]
for q in odds_discovery:
    h=american_to_decimal(q.get("home_moneyline"))
    a=american_to_decimal(q.get("away_moneyline"))
    if h and a:
        ih,ia=1/h,1/a
        normalized_markets.append({"event_id":q["event_id"],"provider":q.get("provider"),"market":"moneyline","home_decimal":h,"away_decimal":a,"home_market_probability":round(ih/(ih+ia),5),"away_market_probability":round(ia/(ih+ia),5),"overround":round(ih+ia-1,5),"captured_at_utc":q.get("captured_at_utc"),"rights_status":"review"})
    if isinstance(q.get("spread"),(int,float)):
        normalized_markets.append({"event_id":q["event_id"],"provider":q.get("provider"),"market":"spread","spread_raw":q["spread"],"details":q.get("details"),"over_under":q.get("over_under"),"home_cover_probability":None,"away_cover_probability":None,"captured_at_utc":q.get("captured_at_utc"),"rights_status":"review"})
# Add box scores for most recent final games, limiting provider load.
finals=[g for g in games if g["status"]=="post" and g["date"] and g["date"][:10]>=str(today-dt.timedelta(days=3))]
details=[]
for g in finals[-18:]:
    try:
        d=fetch("summary",{"event":g["id"]})
        box=[]
        for t in d.get("boxscore",{}).get("players",[]):
            players=[]
            for group in t.get("statistics",[]):
                labels=group.get("labels",[])
                for athlete in group.get("athletes",[]):
                    player=athlete.get("athlete",{})
                    players.append({"name":player.get("displayName"),"stats":dict(zip(labels,athlete.get("stats",[])))})
            box.append({"team":t.get("team",{}).get("abbreviation"),"players":players})
        lines=[]
        for c in d.get("header",{}).get("competitions",[]):
            for team in c.get("competitors",[]):
                lines.append({"team":team.get("team",{}).get("abbreviation"),"quarters":[x.get("value") for x in team.get("linescores",[])]})
        details.append({"event_id":g["id"],"boxscore":box,"quarter_scores":lines})
    except Exception as exc:errors.append("summary "+g["id"]+": "+str(exc)[:80])
now=dt.datetime.now(UTC).isoformat()
snapshot={"odds_discovery":odds_discovery,"odds_observations":odds_observations,"normalized_markets":normalized_markets,"captured_at":now,"source":"ESPN public scoreboard and summary endpoints","games":games,"details":details,"errors":errors}
(ROOT/"games.json").write_text(json.dumps(snapshot,ensure_ascii=False,separators=(",",":"))+"\n")
# model is NOT backtested and therefore has NO high/medium/low confidence classification.
research={"version":"0.2","updated_at_utc":now,"validation":{"sample_size":0,"out_of_sample":False,"brier":None},"predictions":predictions,"odds_comparison":[],"odds_discovery_count":len(odds_discovery),"odds_observation_count":len(odds_observations),"normalized_market_count":len(normalized_markets),"sources":[{"name":"ESPN scoreboard / summary","type":"賽事、近期完賽細節","status":"已取得快照","rights":"再發布條款待審核"},{"name":"ESPN 60-day Elo","type":"未驗證試驗預測","status":"已計算" if predictions else "無未開賽賽事","rights":"僅研究用途"},{"name":"台灣運彩","type":"台灣盤口","status":"尚無核准資料接口","rights":"未確認"},{"name":"The Odds API","type":"國際盤口","status":"需要 API 金鑰及授權","rights":"依服務條款"}]}
(ROOT/"research.json").write_text(json.dumps(research,ensure_ascii=False,separators=(",",":"))+"\n")
print("saved",len(games),"games",len(details),"details",len(predictions),"experimental forecasts; errors",len(errors))
