#!/usr/bin/env python3
"""Collect public factual Taiwanese 運彩盤 quotes displayed at Playsport.

No logins, CAPTCHA bypass, proxies, impersonation or paid picks. Only two
public 'today/tomorrow' NBA tables at a low rate. Do not reproduce HTML or
user-produced predictions. Quotes must be sourced and timestamped.
Rights to broader public redistribution require review; source is disclosed.

Requires: beautifulsoup4. Runs independently of ESPN game-details workflow.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT=pathlib.Path("data")
ROOT.mkdir(exist_ok=True)
OUT=ROOT/"tw_odds.json"
HISTORY=ROOT/"tw_odds_history.json"
URL="https://www.playsport.cc/predict/games?allianceid=3"
TZ=ZoneInfo("Asia/Taipei")
UTC=dt.timezone.utc
ALIASES={"老鷹":"ATL","塞爾提":"BOS","塞爾提克":"BOS","籃網":"BKN",
 "黃蜂":"CHA","公牛":"CHI","騎士":"CLE","獨行俠":"DAL",
 "金塊":"DEN","活塞":"DET","勇士":"GS","火箭":"HOU",
 "溜馬":"IND","快艇":"LAC","湖人":"LAL","灰熊":"MEM",
 "熱火":"MIA","公鹿":"MIL","灰狼":"MIN","鵜鶘":"NO",
 "尼克":"NY","雷霆":"OKC","魔術":"ORL","76人":"PHI",
 "太陽":"PHX","拓荒者":"POR","國王":"SAC","馬刺":"SA",
 "暴龍":"TOR","爵士":"UTAH","巫師":"WSH"}
ESPN_ALIAS={"GSW":"GS","NOP":"NO","NYK":"NY","SAS":"SA",
 "UTA":"UTAH","WAS":"WSH"}
NUM=re.compile(r"^[+-]?\d+(?:\.\d+)?$")
GAME_ID=re.compile(r"^\d{13}$")
TIME=re.compile(r"^(AM|PM)\s*(\d{1,2}):(\d\d)$",re.I)
HEAD={"User-Agent":"NBA-Paper-Lab/1.0 public NBA research, low-rate attribution",
 "Accept":"text/html"}
SOURCE_STATUS="public_observation_redistribution_rights_review"

def numeric(value):
    if value is None:return None
    value=str(value).replace(",","").strip()
    if not NUM.fullmatch(value):return None
    try:return float(value)
    except ValueError:return None

def cell_data(row,class_name):
    td=row.find("td",class_=class_name,recursive=False)
    if td is None:return None,None
    wrapper=td.select_one("span.data-wrap")
    if not wrapper:return None,None
    head=wrapper.find("strong",recursive=False)
    odds=wrapper.find("span",recursive=False)
    line=numeric(head.get_text(" ",strip=True)) if head else None
    dec=numeric(odds.get_text(" ",strip=True)) if odds else None
    if dec is None or not 1.01<=dec<=40:dec=None
    return line,dec

def team_pair(rows):
    away,home=rows
    first=away.find("td",class_="td-teaminfo",recursive=False)
    second=home.find("td",class_="td-teaminfo",recursive=False)
    if first is None:return None,None,"missing_away"
    fa=first.select('a[href*="teamid="]')
    if len(fa)==2 and second is None:
        a=ALIASES.get(fa[0].get_text(" ",strip=True))
        h=ALIASES.get(fa[1].get_text(" ",strip=True))
        return a,h,"settled_nested"
    if len(fa)==1 and second is not None:
        sa=second.select('a[href*="teamid="]')
        if len(sa)==1:
            return (ALIASES.get(fa[0].get_text(" ",strip=True)),
                ALIASES.get(sa[0].get_text(" ",strip=True)),"split_rows")
    return None,None,"ambiguous"

def time_utc(row,gameid):
    info=row.find("td",class_="td-gameinfo",recursive=False)
    if not info:return None
    text=info.select_one("h4")
    if not text:return None
    m=TIME.fullmatch(text.get_text(" ",strip=True))
    if not m:return None
    ap,hh,mm=m.groups()
    hr=int(hh);minute=int(mm)
    if not 1<=hr<=12 or not 0<=minute<=59:return None
    hr=hr%12+(12 if ap.upper()=="PM" else 0)
    try:
        return dt.datetime.strptime(gameid[:8],"%Y%m%d").replace(
            hour=hr,minute=minute,tzinfo=TZ).astimezone(UTC)
    except ValueError:return None

def fair(a,b):
    if a is None or b is None:return None
    over=1/a+1/b
    if not .8<=over<=1.6:return None
    return {"home":round((1/a)/over,5),"away":round((1/b)/over,5),
            "overround":round(over-1,5)}

def parse_table(html,observed_at,page_url):
    """Output only factual bookmaker quote numbers, no full-site HTML."""
    soup=BeautifulSoup(html,"html.parser")
    table=soup.select_one("table.predictgame-table")
    if table is None:return [],["nba_table_missing"]
    rows=defaultdict(list)
    for row in table.select("tr[gameid]"):
        gid=row.get("gameid","")
        if GAME_ID.fullmatch(gid):rows[gid].append(row)
    events=[];errors=[]
    for gid,pair in rows.items():
        if len(pair)!=2:
            errors.append(gid+":paired_rows_missing");continue
        away,home=pair
        if away.find("td",class_="td-gameinfo",recursive=False) is None:
            errors.append(gid+":missing_tipoff");continue
        a,h,layout=team_pair(pair)
        tip=time_utc(away,gid)
        if not a or not h or a==h or tip is None:
            errors.append(gid+":ambiguous_teams_or_time:"+layout);continue
        as_,as_price=cell_data(away,"td-bank-bet01")
        hs,hs_price=cell_data(home,"td-bank-bet01")
        _,am=cell_data(away,"td-bank-bet03")
        _,hm=cell_data(home,"td-bank-bet03")
        at,over=cell_data(away,"td-bank-bet02")
        ht,under=cell_data(home,"td-bank-bet02")
        if as_ is None or hs is None or abs(as_+hs)>.011:
            as_=hs=as_price=hs_price=None
        if at is None or ht is None or abs(at-ht)>.011 or not 100<=at<=350:
            at=over=under=None
        three=sum([
            hm is not None and am is not None,
            hs is not None and hs_price is not None and as_price is not None,
            at is not None and over is not None and under is not None])
        if not three:
            errors.append(gid+":no_two_sided_market");continue
        pregame=observed_at<tip and layout!="settled_nested"
        events.append({"source_game_id":gid,"home":h,"away":a,
            "tipoff_utc":tip.isoformat(),"source_url":page_url,
            "observed_at_utc":observed_at.isoformat(),
            "observation_phase":"pregame" if pregame else "post_start_observation",
            "eligible_for_pregame_backtest":pregame,
            "layout":layout,"complete_markets":three,
            "moneyline":{"home_decimal":hm,"away_decimal":am,
                "no_vig_probabilities":fair(hm,am)},
            "spread":{"home_line":hs,"away_line":as_,
                "home_decimal":hs_price,"away_decimal":as_price},
            "total":{"line":at,"over_decimal":over,"under_decimal":under}})
    return events,errors

def match_espn(events,games):
    """Unique team AND tipoff match. No odds assigned to a guessed event."""
    candidates=[]
    seen=set()
    for m in events:
        parsed=dt.datetime.fromisoformat(m["tipoff_utc"])
        good=[]
        for g in games:
            home=ESPN_ALIAS.get(g.get("home"),g.get("home"))
            away=ESPN_ALIAS.get(g.get("away"),g.get("away"))
            if home!=m["home"] or away!=m["away"]:continue
            try:date=dt.datetime.fromisoformat(g["date"].replace("Z","+00:00"))
            except (KeyError,TypeError,ValueError):continue
            if abs((date-parsed).total_seconds())<=90*60:good.append(g)
        if len(good)!=1 or str(good[0]["id"]) in seen:continue
        item=dict(m)
        item["event_id"]=str(good[0]["id"])
        item["join_verified"]=True
        item["join_method"]="both_teams_and_tipoff_within_90min"
        item["tipoff_utc"]=good[0]["date"]
        candidates.append(item);seen.add(item["event_id"])
    return candidates

def fetch_page(url):
    req=urllib.request.Request(url,headers=HEAD)
    with urllib.request.urlopen(req,timeout=23) as response:
        if response.status!=200:raise ValueError("HTTP "+str(response.status))
        html=response.read(500000)
    return html.decode("utf-8","replace")

def load_json(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,ValueError,UnicodeError):return {}

def main():
    now=dt.datetime.now(UTC)
    games=load_json(ROOT/"games.json").get("games",[])
    if not games:raise SystemExit("No ESPN schedule; keep existing Taiwan data")
    collected=[];errors=[];successful=0
    for mode in ("today","tomorrow"):
        url=URL+"&gameday="+mode
        try:
            rows,errs=parse_table(fetch_page(url),now,url)
            collected.extend(rows)
            errors.extend(errs[:20])
            successful+=1
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ValueError,OSError) as exc:
            errors.append(mode+":"+type(exc).__name__+":"+str(exc)[:80])
        # Rate-limited consecutive public-page requests, not stealth or bypass.
        if mode=="today":time.sleep(1.5)
    if successful==0:
        raise SystemExit("Both public pages unavailable; keep previous verified data")
    matched=match_espn(collected,games)
    future=[x for x in matched if x["eligible_for_pregame_backtest"]]
    # Durable first/last genuine pre-tipoff observations per event.
    old=load_json(HISTORY)
    past=old.get("games",{})
    if not isinstance(past,dict):past={}
    for x in future:
        eid=x["event_id"]
        if eid not in past:
            past[eid]={"first":x,"last":x,"times_observed":1}
        elif past[eid]["last"].get("observed_at_utc")!=x["observed_at_utc"]:
            past[eid]["last"]=x
            past[eid]["times_observed"]+=1
    # bounded, no full HTML replication or third-party premium predictions.
    past=dict(sorted(past.items(),key=lambda kv:kv[1]["first"]["tipoff_utc"])[-200:])
    HISTORY.write_text(json.dumps({"captured_at_utc":now.isoformat(),
        "source":"玩運彩公開 NBA 運彩盤（第三方整理）","games":past,
        "license_status":SOURCE_STATUS,"no_reconstructed_opening_odds":True},
        ensure_ascii=False,separators=(",",":"))+"\n")
    latest={"captured_at_utc":now.isoformat(),"source":"玩運彩 · 運彩盤（公開頁面觀測）",
        "source_url":URL,"data_provider_disclaimer":"網頁公開資訊的第三方整理，非台灣運彩官方即時 API",
        "rights_status":SOURCE_STATUS,"collection":"today_and_tomorrow",
        "source_games_parsed":len(collected),"matched":len(matched),
        "pregame_matches":len(future),
        "complete_pregame":sum(x["complete_markets"]==3 for x in future),
        "games":future,"errors":errors,
        "notes":"只將觀測早於開賽的賽事標為賽前；使用來源實際數值及時間；不推定開盤、收盤、投注推薦或所有盤皆可下注"}
    OUT.write_text(json.dumps(latest,ensure_ascii=False,separators=(",",":"))+"\n")
    print("TW public market",len(collected),"parsed",len(matched),"matched",len(future),"pregame",latest["complete_pregame"],"complete; errors",errors[:3])

if __name__=="__main__":main()
