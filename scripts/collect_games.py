#!/usr/bin/env python3
"""Collect public ESPN game schedule, final box-score details, and experimental pregame Elo.
Research snapshots only. Respect provider terms; no access-control bypass.
"""
import datetime as dt, json, pathlib, time, urllib.request, urllib.parse
from market_model import build_market
from espn_odds import compact_market,validate_quote
from report_engine import build_reports
from elo_history import train_and_forecast
from analyst_factors import extract_four_factors
from score_model import evaluate_and_project,market_probabilities
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
    return {"id":e["id"],"date":e.get("date"),"home":h["team"]["abbreviation"],"away":a["team"]["abbreviation"],"home_name":h["team"].get("displayName"),"away_name":a["team"].get("displayName"),"home_score":score(h),"away_score":score(a),"status":st.get("state"),"status_label":st.get("description"),"season_year":(e.get("season") or {}).get("year"),"season_phase":(e.get("season") or {}).get("type"),"venue":c.get("venue",{}).get("fullName"),"broadcasts":[b.get("names",[]) for b in c.get("broadcasts",[])]}
today=dt.datetime.now(UTC).date()
events={}
scoreboard_odds=[]
errors=[]
def register_scoreboard_event(e):
    item=game(e)
    events[str(e["id"])]=item
    if item.get("status")!="pre":return
    comps=e.get("competitions") or []
    if not comps:return
    for quote in comps[0].get("odds",[]) or []:
        captured=dt.datetime.now(UTC).isoformat()
        normalized=compact_market(quote,item["id"],captured,"ESPN scoreboard embedded odds")
        if normalized:
            scoreboard_odds.append(validate_quote(normalized,item["home"],item["away"]))

# ESPN scoreboard accepts single-day YYYYMMDD dates; unsupported ranges caused HTTP 400.
# Collect recent completed games and next seven days, with bounded requests.
for offset in list(range(-14,1))+list(range(1,8)):
    day=today+dt.timedelta(days=offset)
    try:
        data=fetch("scoreboard",{"dates":day.strftime("%Y%m%d"),"limit":"100"})
        for e in data.get("events",[]):
            try:register_scoreboard_event(e)
            except (KeyError,IndexError,TypeError,AttributeError):pass
    except Exception as exc:
        errors.append(day.isoformat()+": "+str(exc)[:100])
# Fallback to default scoreboard when dated queries fail.
if not events:
    try:
        data=fetch("scoreboard")
        for e in data.get("events",[]):
            try:register_scoreboard_event(e)
            except (KeyError,IndexError,TypeError,AttributeError):pass
    except Exception as exc:errors.append("default scoreboard: "+str(exc)[:100])
games=sorted(events.values(),key=lambda x:x.get("date") or "")
if not games:
    raise SystemExit("No games fetched; keep previous snapshot. "+str(errors))
# Train on scored historical results only. Chronological evaluation is auditable.
historical=[]
history_path=ROOT/"history_games.json"
if history_path.exists():
    try:
        archive=json.loads(history_path.read_text())
        if isinstance(archive.get("games"),list):historical=archive["games"]
    except (ValueError,OSError) as exc:
        errors.append("historical Elo input: "+type(exc).__name__)
predictions,validation=train_and_forecast(historical,games)
analyst_forecasts,analyst_validation=evaluate_and_project(historical,games,predictions)
# ESPN scoreboard embedded odds expose nested moneyline, spread and total
# prices even when top-level summary fields are absent. Supplement missing
# markets from summary; never invent unobserved quotes or claim TW odds.
odds_discovery=list(scoreboard_odds)
def market_coverage(q):
    return sum([
        q.get("home_moneyline") is not None and q.get("away_moneyline") is not None,
        q.get("home_spread_verified") is not None
          and q.get("home_spread_american") is not None and q.get("away_spread_american") is not None,
        q.get("over_under") is not None
          and q.get("over_american") is not None and q.get("under_american") is not None
    ])
selected={}
for quote in scoreboard_odds:
    key=(str(quote["event_id"]),quote["provider"])
    if key not in selected or market_coverage(quote)>market_coverage(selected[key]):
        selected[key]=quote
to_supplement=[]
for g in [x for x in games if x["status"]=="pre"]:
    known=[q for q in selected.values() if str(q["event_id"])==str(g["id"])]
    if not known or max(market_coverage(q) for q in known)<3:
        to_supplement.append(g)
for g in to_supplement[:32]:
    try:
        d=fetch("summary",{"event":g["id"]})
        for original in d.get("pickcenter",[]) or []:
            quoted=compact_market(original,g["id"],dt.datetime.now(UTC).isoformat(),"ESPN game summary pickcenter")
            if not quoted:continue
            quoted=validate_quote(quoted,g["home"],g["away"])
            key=(str(quoted["event_id"]),quoted["provider"])
            if key not in selected or market_coverage(quoted)>market_coverage(selected[key]):
                selected[key]=quoted
    except Exception as exc:
        errors.append("odds discovery "+str(g["id"])+": "+str(exc)[:80])
odds_discovery=list(selected.values())
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
# Join traceable public market observations by ESPN ID.
by_id={str(g["id"]):g for g in games}
forecast_by_id={str(p["event_id"]):p for p in predictions}
market_snapshots=[]
for q in odds_discovery:
    event_id=str(q.get("event_id") or "")
    if event_id not in by_id:continue
    market_snapshots.append(build_market(q,by_id[event_id],forecast_by_id.get(event_id)))
market_snapshots=list({(m["event_id"],m["provider"]):m for m in market_snapshots}.values())
complete_market_events=set()
for item in market_snapshots:
    quote=selected.get((str(item["event_id"]),item["provider"]))
    ml=item.get("moneyline") or {}
    sp=item.get("spread") or {}
    total=item.get("total") or {}
    if (quote and ml.get("home_decimal") is not None and ml.get("away_decimal") is not None
        and sp.get("home_line") is not None and total.get("line") is not None
        and all(quote.get(field) is not None for field in (
            "home_spread_american","away_spread_american",
            "over_american","under_american"))):
        complete_market_events.add(str(item["event_id"]))
coverage_asof=dt.datetime.now(UTC)
near_term=[]
for event in games:
    if event.get("status")!="pre":continue
    try:
        when=dt.datetime.fromisoformat(str(event.get("date")).replace("Z","+00:00"))
        if coverage_asof<=when<coverage_asof+dt.timedelta(hours=24):
            near_term.append(str(event["id"]))
    except (ValueError,TypeError):pass
market_coverage_report={
    "next_24h_game_count":len(near_term),
    "next_24h_complete_three_market_events":len(set(near_term)&complete_market_events),
    "as_of_utc":coverage_asof.isoformat(),
    "future_game_count":sum(g.get("status")=="pre" for g in games),
    "paired_market_events":len({str(q["event_id"]) for q in market_snapshots}),
    "complete_three_market_events":len(complete_market_events),
    "scoreboard_quotes_detected":len(scoreboard_odds),
    "source":"ESPN scoreboard embedded odds + game summary",
    "taiwan_sportslottery_connected":False,
    "rights_status":"review"
}
for m in market_snapshots:
    projection=analyst_forecasts.get(str(m["event_id"]))
    conditional=market_probabilities(projection,m)
    if conditional.get("spread"):
        m["spread"]["home_cover_probability_experimental"]=conditional["spread"]["home"]
        m["spread"]["away_cover_probability_experimental"]=conditional["spread"]["away"]
        m["spread"]["method"]="Frozen score-error distribution; not calibrated on historical ATS lines"
    if conditional.get("total"):
        m["total"]["over_probability_experimental"]=conditional["total"]["over"]
        m["total"]["under_probability_experimental"]=conditional["total"]["under"]
        m["total"]["expected_total"]=projection["expected_total"]
        m["total"]["total_sigma"]=projection["total_sigma"]
    original=next((q for q in odds_discovery if str(q.get("event_id"))==str(m["event_id"]) and q.get("provider")==m["provider"]),None)
    if original:
        m["observed_prices"]={
          "spread_home_american":original.get("home_spread_american"),
          "spread_away_american":original.get("away_spread_american"),
          "total_over_american":original.get("over_american"),
          "total_under_american":original.get("under_american")}
        m["provider_open_last"]=original.get("provider_open_last")
        m["source_endpoint"]=original.get("source_endpoint")
        m["market_note"]="Only observation capture time is verified; provider open/close labels lack per-change times. Not Taiwan lottery."
# Add box scores for most recent final games, limiting provider load.
finals=[g for g in games if g["status"]=="post" and g["date"] and g["date"][:10]>=str(today-dt.timedelta(days=3))]
details=[]
box_samples=[]
for g in finals[-45:]:
    try:
        d=fetch("summary",{"event":g["id"]})
        sample_time=dt.datetime.now(UTC).isoformat()
        for fact in extract_four_factors(d,g["id"],sample_time):
            fact["date"]=g["date"]
            box_samples.append(fact)
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
(ROOT/"box_factors.json").write_text(json.dumps({
    "captured_at_utc":now,"source":"ESPN completed game summaries",
    "method":"eFG%, 3PA rate, TO% and approximate possessions from actual box scores; not official pace",
    "rows":box_samples,"sample_count":len(box_samples),
    "note":"Market analysis only uses box score games before the future tipoff"
},ensure_ascii=False,separators=(",",":"))+"\n")
snapshot={"market_coverage":market_coverage_report,"odds_discovery":odds_discovery,"odds_observations":odds_observations,"normalized_markets":normalized_markets,"market_snapshots":market_snapshots,"captured_at":now,"source":"ESPN public scoreboard and summary endpoints","games":games,"details":details,"errors":errors}
(ROOT/"games.json").write_text(json.dumps(snapshot,ensure_ascii=False,separators=(",",":"))+"\n")
# League-wide public injury report; empty/failed data is never presented as healthy.
injury_snapshot={"captured_at":now,"source":"ESPN NBA league injuries","injuries":[],"errors":[]}
try:
    injury_data=fetch("injuries")
    raw_groups=injury_data.get("injuries",[])
    if not isinstance(raw_groups,list):raw_groups=[]
    for group in raw_groups:
        if not isinstance(group,dict):continue
        team=group.get("team") or {}
        entries=group.get("injuries")
        if not isinstance(entries,list):entries=[group] if group.get("athlete") else []
        for rec in entries:
            if not isinstance(rec,dict):continue
            athlete=rec.get("athlete") or {}
            if not isinstance(athlete,dict):athlete={}
            details=rec.get("details") or {}
            if not isinstance(details,dict):details={}
            st=rec.get("status")
            if isinstance(st,dict):st=st.get("name") or st.get("displayName")
            name=athlete.get("displayName") or athlete.get("fullName")
            if not name:continue
            athlete_team=athlete.get("team") or {}
            team_code=(athlete_team.get("abbreviation") if isinstance(athlete_team,dict) else None)
            if not team_code and isinstance(team,dict):team_code=team.get("abbreviation")
            injury_snapshot["injuries"].append({
                "team":team_code,
                "team_name":(athlete_team.get("displayName") if isinstance(athlete_team,dict) else None) or group.get("displayName"),
                "player":name,"status":st or "未公布",
                "type":details.get("type"),"detail":details.get("detail"),
                "date":rec.get("date"),"return_date":details.get("returnDate")})
except Exception as exc:
    injury_snapshot["errors"].append(type(exc).__name__+": "+str(exc)[:90])
(ROOT/"injuries.json").write_text(json.dumps(injury_snapshot,ensure_ascii=False,separators=(",",":"))+"\n")
(ROOT/"analyst_validation.json").write_text(json.dumps({
    "updated_at_utc":now,"validation":analyst_validation,
    "forecasts":analyst_forecasts,
    "source":"ESPN scored historical games; no historical sportsbook odds were used",
    "market_cover_brier":None,"market_total_brier":None
},ensure_ascii=False,separators=(",",":"))+"\n")
# Generate one 100–200 character three-market Chinese report per future game.
# Keep reports separate from source price snapshots for provenance and auditing.
now_reports=dt.datetime.now(UTC).isoformat()
headlines=[]
news_path=ROOT/"news.json"
if news_path.exists():
    try:
        headline_file=json.loads(news_path.read_text())
        if isinstance(headline_file.get("articles"),list):headlines=headline_file["articles"]
    except (ValueError,OSError) as exc:
        errors.append("news report input: "+type(exc).__name__)
season_priors={}
prior_path=ROOT/"season_priors.json"
if prior_path.exists():
    try:season_priors=json.loads(prior_path.read_text())
    except (OSError,ValueError):errors.append("PBP priors JSON unavailable")
reports=build_reports(games,predictions,market_snapshots,now_reports,
    historical_games=historical,articles=headlines,
    analyst_forecasts=analyst_forecasts,box_samples=box_samples,
    injury_snapshot=injury_snapshot,season_priors=season_priors)
(ROOT/"reports.json").write_text(json.dumps({
    "version":"1.1","captured_at":now_reports,"analyst_validation":analyst_validation,
    "reports":reports,"generated":len(reports),"historical_games_available":len(historical),"news_items_available":len(headlines),"previous_season_team_priors":season_priors.get("team_count",0),
    "description":"獨贏／讓分／大小分三市場之試驗模型觀察；無資料時明示缺值",
    "market_data_rights":"來源資料授權待確認；僅展示自製分析"
},ensure_ascii=False,separators=(",",":"))+"\n")
# model is NOT backtested and therefore has NO high/medium/low confidence classification.
research={"version":"0.5","updated_at_utc":now,"validation":validation,"analyst_validation":analyst_validation,"predictions":predictions,"odds_comparison":[],"odds_discovery_count":len(odds_discovery),"odds_observation_count":len(odds_observations),"normalized_market_count":len(normalized_markets),"market_snapshot_count":len(market_snapshots),"market_coverage":market_coverage_report,"report_count":len(reports),"sources":[{"name":"ESPN scoreboard / summary","type":"賽事、近期完賽細節","status":"已取得快照","rights":"再發布條款待審核"},{"name":"ESPN injuries","type":"目前傷病資訊","status":"已取得 "+str(len(injury_snapshot["injuries"]))+" 筆" if not injury_snapshot["errors"] else "取得失敗","rights":"再發布條款待審核"},{"name":"ESPN team boxscore four factors","type":"已完賽進攻籃板、失誤、罰球與eFG","status":"已擷取 "+str(len(box_samples))+" 筆隊伍資料","rights":"再發布條款待審核"},{"name":"PBP Stats","type":"2025–26 前季PPP與每次進攻耗時（不是本季現況）","status":"已取得 "+str(season_priors.get("team_count",0))+" 隊" if season_priors.get("team_count",0)>=28 else "前季數據不可用","rights":"再發布條款待審核"},{"name":"固定參數 10 季 Elo","type":"逐場時序檢驗之獨贏基準（讓分／大小仍未驗證）","status":"已計算" if predictions else "無未開賽賽事","rights":"僅研究用途"},{"name":"台灣運彩","type":"台灣盤口","status":"尚無核准資料接口","rights":"未確認"},{"name":"The Odds API","type":"國際盤口","status":"需要 API 金鑰及授權","rights":"依服務條款"}]}
(ROOT/"research.json").write_text(json.dumps(research,ensure_ascii=False,separators=(",",":"))+"\n")
print("saved",len(games),"games",len(details),"details",len(predictions),"experimental forecasts; errors",len(errors))
