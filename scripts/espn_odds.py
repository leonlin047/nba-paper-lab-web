"""Source-attributed NBA scoreboard/summary market adapter.

ESPN scoreboard's odds lack top-level *_moneyLine fields in many snapshots;
odds are instead under moneyline.home.close.odds etc. Never substitute the
favorite flag or model probability for a bookmaker quote.

Only capture direct public response data. The source's reuse/redistribution
terms are under review, so do not claim these are licensed Taiwan odds.
"""
from __future__ import annotations
import math,re

ALIASES={"GSW":"GS","NOP":"NO","NYK":"NY","SAS":"SA","WAS":"WSH","UTA":"UTAH"}

def safe_num(v,minimum=None,maximum=None):
    try:
        if isinstance(v,bool):return None
        if isinstance(v,str):
            v=v.strip()
            if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?",v):return None
        n=float(v)
        if not math.isfinite(n) or (minimum is not None and n<minimum) or (maximum is not None and n>maximum):return None
        return n
    except (TypeError,ValueError):return None

def american(v):
    n=safe_num(v)
    return int(n) if n is not None and abs(n)>=100 and abs(n)<=10000 and n==int(n) else None

def nested(q,group,side,period,key):
    t=q.get(group)
    if not isinstance(t,dict):return None
    t=t.get(side)
    if not isinstance(t,dict):return None
    t=t.get(period)
    return t.get(key) if isinstance(t,dict) else None

def compact_market(q,game_id,captured_at,source):
    """Normalize an odds quote to the existing market_model.build_market input.
    Requires at least one observed concrete market; returns None otherwise.
    """
    if not isinstance(q,dict):return None
    provider=q.get("provider") or {}
    name=provider.get("name") if isinstance(provider,dict) else provider
    if not isinstance(name,str) or not name.strip():return None
    home_odds=q.get("homeTeamOdds") if isinstance(q.get("homeTeamOdds"),dict) else {}
    away_odds=q.get("awayTeamOdds") if isinstance(q.get("awayTeamOdds"),dict) else {}
    home_ml=american(home_odds.get("moneyLine"))
    away_ml=american(away_odds.get("moneyLine"))
    if home_ml is None:home_ml=american(nested(q,"moneyline","home","close","odds"))
    if away_ml is None:away_ml=american(nested(q,"moneyline","away","close","odds"))
    spread=safe_num(q.get("spread"),-70,70)
    total=safe_num(q.get("overUnder"),100,350)
    home_line=safe_num(nested(q,"pointSpread","home","close","line"),-70,70)
    away_line=safe_num(nested(q,"pointSpread","away","close","line"),-70,70)
    if home_line is not None and away_line is not None and abs(home_line+away_line)>.01:
        home_line=None;away_line=None
    if spread is None:spread=home_line
    if total is None:total=safe_num(nested(q,"total","over","close","line").lstrip("oO") if isinstance(nested(q,"total","over","close","line"),str) else nested(q,"total","over","close","line"),100,350)
    details=q.get("details")
    if not isinstance(details,str):details=None
    if details is None and spread is not None:
        # We cannot invent a named favorite; build_market accepts an explicit
        # verified home_line separately.
        pass
    hs=american(home_odds.get("spreadOdds"))
    aws=american(away_odds.get("spreadOdds"))
    if hs is None:hs=american(nested(q,"pointSpread","home","close","odds"))
    if aws is None:aws=american(nested(q,"pointSpread","away","close","odds"))
    oo=american(q.get("overOdds"))
    uo=american(q.get("underOdds"))
    if oo is None:oo=american(nested(q,"total","over","close","odds"))
    if uo is None:uo=american(nested(q,"total","under","close","odds"))
    if home_ml is None and away_ml is None and spread is None and total is None:return None
    # Provenance-preserving compact opens & currently displayed close markers,
    # without copying sportsbook referral URLs or branding elements.
    op_last={}
    for group,sides in (("moneyline",("home","away")),("pointSpread",("home","away")),("total",("over","under"))):
        data={}
        for side in sides:
            item={}
            for period in ("open","close"):
                line=nested(q,group,side,period,"line")
                odds=american(nested(q,group,side,period,"odds"))
                if line is not None or odds is not None:
                    item[period]={"line":str(line) if line is not None else None,
                                  "odds":str(odds) if odds is not None else None}
            if item:data[side]=item
        if data:op_last[group]=data
    return {
        "event_id":str(game_id),"provider":name.strip(),
        "spread":spread,"home_line_observed":home_line,"away_line_observed":away_line,
        "over_under":total,"details":details,
        "home_moneyline":home_ml,"away_moneyline":away_ml,
        "home_spread_american":hs,"away_spread_american":aws,
        "over_american":oo,"under_american":uo,
        "provider_open_last":op_last,
        "captured_at_utc":captured_at,
        "source_endpoint":source,
        "market_data_type":"observed_bookmaker_quote",
        "rights_status":"review"
    }

def normalize_team(code):
    return ALIASES.get(str(code or "").upper(),str(code or "").upper())

def validate_quote(quote,home,away):
    """Cross-check bookmakers' named favorite and both directional lines."""
    from market_model import home_spread_from_pickcenter
    details=quote.get("details")
    home_line=quote.get("home_line_observed")
    raw=quote.get("spread")
    details_line=None
    if isinstance(details,str):
        m=re.fullmatch(r"\s*([A-Za-z]{2,5})\s*([+-])\s*(\d+(?:\.\d+)?)\s*",details)
        if m:
            name,sign,value=m.groups()
            signed=float(value)*(-1 if sign=="-" else 1)
            if normalize_team(name)==normalize_team(home):details_line=signed
            elif normalize_team(name)==normalize_team(away):details_line=-signed
            else:
                quote["invalid_reason"]="named_favorite_does_not_match_game"
                quote["home_spread_verified"]=None
                return quote
    if home_line is not None and details_line is not None and abs(home_line-details_line)>.011:
        quote["invalid_reason"]="home_line_disagrees_with_named_favorite"
        quote["home_spread_verified"]=None
        return quote
    verified=home_line if home_line is not None else details_line
    if verified is not None and raw is not None and abs(raw-verified)>.011:
        quote["invalid_reason"]="raw_spread_disagrees_with_verified_line"
        verified=None
    away_line=quote.get("away_line_observed")
    if verified is not None and away_line is not None and abs(verified+away_line)>.011:
        quote["invalid_reason"]="opposite_spread_lines_do_not_balance"
        verified=None
    quote["home_spread_verified"]=verified
    return quote
