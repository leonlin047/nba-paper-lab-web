#!/usr/bin/env python3
"""Collect NBA headlines from a documented public RSS feed, not X post scraping.

Headlines are links to reporting, not verified game-day lineup confirmations.
No login, X proxy, fake account or unofficial profile-scraping.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=pathlib.Path("data")
ROOT.mkdir(exist_ok=True)
URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=45"
HEAD={"User-Agent":"NBA-Paper-Lab-News-Research/1.0","Accept":"application/json,application/xml,text/xml"}
TEAM_KEYWORDS={
    "ATL":["hawks","atlanta"],"BOS":["celtics","boston"],"BKN":["nets","brooklyn"],
    "CHA":["hornets","charlotte"],"CHI":["bulls","chicago"],"CLE":["cavaliers","cleveland","cavs"],
    "DAL":["mavericks","dallas","mavs"],"DEN":["nuggets","denver"],"DET":["pistons","detroit"],
    "GS":["warriors","golden state","curry"],"HOU":["rockets","houston"],
    "IND":["pacers","indiana"],"LAC":["clippers"],"LAL":["lakers","lebron"],
    "MEM":["grizzlies","memphis"],"MIA":["heat","miami"],"MIL":["bucks","milwaukee"],
    "MIN":["timberwolves","minnesota","wolves"],"NO":["pelicans","new orleans"],
    "NY":["knicks","new york"],"OKC":["thunder","oklahoma city"],
    "ORL":["magic","orlando"],"PHI":["76ers","sixers","philadelphia"],
    "PHX":["suns","phoenix"],"POR":["trail blazers","blazers","portland"],
    "SAC":["kings","sacramento"],"SA":["spurs","san antonio"],
    "TOR":["raptors","toronto"],"UTAH":["jazz","utah"],"WSH":["wizards","washington"],
}

def parse_rss(payload, captured_at):
    root=ET.fromstring(payload)
    records=[]
    seen=set()
    for item in root.findall(".//item")[:100]:
        title=(item.findtext("title") or "").strip()
        link=(item.findtext("link") or "").strip()
        if not title or not link:continue
        url=urllib.parse.urlparse(link)
        if url.scheme!="https" or not (url.hostname=="espn.com" or (url.hostname or "").endswith(".espn.com")):
            continue
        if link in seen:continue
        seen.add(link)
        pub=item.findtext("pubDate") or ""
        stamp=None
        if pub:
            try:
                stamp=email.utils.parsedate_to_datetime(pub)
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
                stamp=stamp.astimezone(dt.timezone.utc).isoformat()
            except (ValueError,TypeError,OverflowError):pass
        lower=title.lower()
        teams=[abbr for abbr,terms in TEAM_KEYWORDS.items()
               if any(re.search(r"(?<![a-z])"+re.escape(term)+r"(?![a-z])",lower) for term in terms)]
        records.append({"title":title[:240],"url":link,"published_at_utc":stamp,
            "source":"ESPN NBA RSS","teams":teams,
            "x_post_verified":False,"injury_verified":False,
            "note":"新聞標題本身不是球員出賽確認"})
    return records[:60]

def parse_api_news(payload,captured_at):
    if not isinstance(payload,dict) or not isinstance(payload.get("articles"),list):
        raise ValueError("News API missing article list")
    articles=[]
    seen=set()
    for item in payload.get("articles",[])[:100]:
        if not isinstance(item,dict):continue
        title=(item.get("headline") or "").strip()
        links=item.get("links") or {}
        web=links.get("web") or {}
        if isinstance(web,dict):web=web.get("href")
        link=str(web or "").strip()
        if not title or not link:continue
        url=urllib.parse.urlparse(link)
        if url.scheme!="https" or not (url.hostname=="espn.com" or (url.hostname or "").endswith(".espn.com")):continue
        if link in seen:continue
        seen.add(link)
        published=item.get("published")
        date=None
        if published:
            try:
                stamp=dt.datetime.fromisoformat(str(published).replace("Z","+00:00"))
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
                date=stamp.astimezone(dt.timezone.utc).isoformat()
            except (ValueError,TypeError):pass
        teams=[]
        for category in item.get("categories") or []:
            if not isinstance(category,dict) or category.get("type")!="team":continue
            team=category.get("team") or {}
            code=team.get("abbreviation")
            if isinstance(code,str) and 2<=len(code)<=4 and code not in teams:teams.append(code)
        lower=title.lower()
        if not teams:
            teams=[code for code,keywords in TEAM_KEYWORDS.items()
              if any(re.search(r"(?<![a-z])"+re.escape(keyword)+r"(?![a-z])",lower) for keyword in keywords)]
        articles.append({"title":title[:240],"url":link,"published_at_utc":date,
           "source":"ESPN NBA News API","author":str(item.get("byline") or "")[:100],
           "teams":teams,"x_post_verified":False,"injury_verified":False,
           "note":"新聞標題不是官方出賽確認；請查核原文"})
    return articles[:60]

def main():
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    output={"captured_at_utc":now,"source":"ESPN NBA News API","feed":URL,
        "articles":[],"errors":[],"x_posts_connected":False,
        "notes":"X 記者名單另存 insiders.json；未以 X API 取得貼文，不主張貼文已驗證。"}
    try:
        req=urllib.request.Request(URL,headers=HEAD)
        with urllib.request.urlopen(req,timeout=20) as resp:
            raw=resp.read(1_800_000)
        payload=json.loads(raw)
        output["articles"]=parse_api_news(payload,now)
        if not output["articles"]:output["errors"].append("RSS_EMPTY")
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,ET.ParseError,ValueError,TypeError) as exc:
        output["errors"].append(type(exc).__name__+": "+str(exc)[:100])
    (ROOT/"news.json").write_text(json.dumps(output,ensure_ascii=False,separators=(",",":"))+"\n")
    print("NBA reporting:",len(output["articles"]),"articles; errors:",output["errors"])

if __name__=="__main__":main()
