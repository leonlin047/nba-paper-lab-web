"""Bounded, attributable fallback for public ESPN core quotes. No synthetic lines."""
from datetime import datetime,timedelta,timezone
import json
from urllib.parse import urlparse
from urllib.request import Request,urlopen
from espn_odds import compact_market,validate_quote

ROOT="https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/"
UTC=timezone.utc

def fetch_json(url):
    with urlopen(Request(url,headers={"User-Agent":"Court-Noir-research/1.0","Accept":"application/json"}),timeout=12) as response:
        return json.loads(response.read(1500000))

def supplement(games,selected,coverage,cache_path,now=None,fetcher=fetch_json):
    now=now or datetime.now(UTC)
    try:cache=json.loads(cache_path.read_text())
    except (OSError,ValueError):cache={"events":{}}
    event_cache=cache.get("events") or {};quotes=[];statuses=[]
    for game in sorted(games,key=lambda g:g.get("date") or ""):
        if len(statuses)>=12:break
        if game.get("status")!="pre":continue
        try:tip=datetime.fromisoformat(game["date"].replace("Z","+00:00"))
        except (ValueError,KeyError):continue
        if tip.tzinfo is None or not now<tip<=now+timedelta(hours=48):continue
        known=[q for q in selected.values() if str(q.get("event_id"))==str(game["id"])]
        if known and max(coverage(q) for q in known)>=3:continue
        event_id=str(game["id"])
        if not event_id.isdigit():continue
        prior=event_cache.get(event_id)
        try:age=now-datetime.fromisoformat(prior["checked_at_utc"])
        except (TypeError,ValueError,KeyError):age=timedelta(days=999)
        if prior and timedelta(0)<=age<timedelta(minutes=55):
            quotes.extend(prior.get("quotes") or []);statuses.append({"event_id":event_id,"status":prior["status"],"cache_reused":True});continue
        url=f"{ROOT}{event_id}/competitions/{event_id}/odds?limit=100"
        status={"event_id":event_id,"checked_at_utc":now.isoformat(),"source_url":url,"quotes":[]}
        try:
            listing=fetcher(url);items=listing.get("items") or []
            for item in items[:2]:
                ref=item.get("$ref","")
                if ref:
                    ref=ref.replace("http://sports.core.api.espn.com/","https://sports.core.api.espn.com/",1)
                    expected=f"{ROOT}{event_id}/competitions/{event_id}/odds/"
                    if not ref.startswith(expected) or urlparse(ref).hostname!="sports.core.api.espn.com":continue
                    original=fetcher(ref)
                else:original=item
                quote=compact_market(original,event_id,now.isoformat(),"ESPN public core odds")
                if quote:status["quotes"].append(validate_quote(quote,game["home"],game["away"]))
            status["status"]="observed" if status["quotes"] else "no_quote_returned"
            status["provider_items_returned"]=len(items)
        except Exception as exc:
            status["status"]="source_error";status["error"]=type(exc).__name__+": "+str(exc)[:120]
        event_cache[event_id]=status;quotes.extend(status["quotes"]);statuses.append({k:v for k,v in status.items() if k!="quotes"})
    cache={"schema_version":1,"as_of_utc":now.isoformat(),"rights_status":"review","request_bound":"12 missing near-term events; at most two provider records per event; 55-minute cache","events":dict(list(event_cache.items())[-100:]),"last_run":statuses}
    cache_path.write_text(json.dumps(cache,ensure_ascii=False,separators=(",",":"))+"\n")
    return quotes
