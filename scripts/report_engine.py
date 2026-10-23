"""Auditable Chinese NBA pregame observation reports.

One 100-200 Chinese-character report per future game. Includes all three
markets (moneyline, spread, total); missing quotes remain missing. The
experimental total model uses earlier final scores only, with no leakage.
No generated/invented player injuries, reporter posts or sportsbook prices.
"""
from __future__ import annotations

import datetime as dt
import math
from statistics import NormalDist, pstdev

NORMAL=NormalDist()
TEAM_ZH={
"ATL":"亞特蘭大老鷹","BKN":"布魯克林籃網","BOS":"波士頓塞爾提克",
"CHA":"夏洛特黃蜂","CHI":"芝加哥公牛","CLE":"克里夫蘭騎士",
"DAL":"達拉斯獨行俠","DEN":"丹佛金塊","DET":"底特律活塞",
"GS":"金州勇士","GSW":"金州勇士","HOU":"休士頓火箭",
"IND":"印第安納溜馬","LAC":"洛杉磯快艇","LAL":"洛杉磯湖人",
"MEM":"曼菲斯灰熊","MIA":"邁阿密熱火","MIL":"密爾瓦基公鹿",
"MIN":"明尼蘇達灰狼","NO":"紐奧良鵜鶘","NOP":"紐奧良鵜鶘",
"NY":"紐約尼克","NYK":"紐約尼克","OKC":"奧克拉荷馬雷霆",
"ORL":"奧蘭多魔術","PHI":"費城76人","PHX":"鳳凰城太陽",
"POR":"波特蘭拓荒者","SAC":"沙加緬度國王","SA":"聖安東尼奧馬刺",
"SAS":"聖安東尼奧馬刺","TOR":"多倫多暴龍","UTAH":"猶他爵士",
"UTA":"猶他爵士","WSH":"華盛頓巫師","WAS":"華盛頓巫師"
}
SD_SPREAD=12.0

def iso(s):
    try:return dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    except (TypeError,ValueError):return None

def pct(p):
    if isinstance(p,(int,float)) and math.isfinite(p) and 0<=p<=1:
        return f"{p*100:.1f}%"
    return "—"

def team(code):
    return TEAM_ZH.get(code,str(code))

def model_total(future,completed,market_line):
    """Shrunk points-for and points-against total, league-wide empirical sigma.
    Each input final must predate the future game's tipoff. Minimum data gates.
    """
    kickoff=iso(future.get("date"))
    if kickoff is None:return None
    prior=[g for g in completed
        if iso(g.get("date")) is not None and iso(g["date"])<kickoff
        and isinstance(g.get("home_score"),int) and isinstance(g.get("away_score"),int)
        and 50<=g["home_score"]<=200 and 50<=g["away_score"]<=200
        and g["home"]!=g["away"]]
    prior.sort(key=lambda x:x["date"])
    if len(prior)<30:return None
    home_games=[g for g in prior if future["home"] in (g["home"],g["away"])][-12:]
    away_games=[g for g in prior if future["away"] in (g["home"],g["away"])][-12:]
    if len(home_games)<3 or len(away_games)<3:return None
    window=prior[-100:]
    base=sum(g["home_score"]+g["away_score"] for g in window)/(2*len(window))
    def strength(code,rows):
        offense,conceded=[],[]
        for x in rows:
            own=x["home_score"] if x["home"]==code else x["away_score"]
            other=x["away_score"] if x["home"]==code else x["home_score"]
            offense.append(own);conceded.append(other)
        weight=len(rows)/(len(rows)+8)
        return (base+weight*(sum(offense)/len(rows)-base),
                base+weight*(sum(conceded)/len(rows)-base))
    hfor,hagainst=strength(future["home"],home_games)
    afor,aagainst=strength(future["away"],away_games)
    expected=(hfor+aagainst)/2+(afor+hagainst)/2
    totals=[x["home_score"]+x["away_score"] for x in window]
    sigma=max(14.0,min(32.0,pstdev(totals)))
    prob_over=None
    if isinstance(market_line,(int,float)) and math.isfinite(market_line) and 130<=market_line<=320:
        # Continuous normal ignores push probability on integer totals.
        prob_over=round(NORMAL.cdf((expected-market_line)/sigma),5)
    return {"expected_total":round(expected,1),"total_sd":round(sigma,1),
        "over_probability_experimental":prob_over,
        "under_probability_experimental":round(1-prob_over,5) if prob_over is not None and not float(market_line).is_integer() else None,
        "whole_point_push_possible":isinstance(market_line,(int,float)) and float(market_line).is_integer(),
        "league_sample_size":len(window),"home_sample_size":len(home_games),
        "away_sample_size":len(away_games),
        "method":"shrunk team for/against + league total variance; experimental, not calibrated"}

def summary(game,forecast,market,total):
    away,home=team(game["away"]),team(game["home"])
    p=forecast.get("home_win_probability")
    start=f"{away}對{home}｜獨贏：近期Elo估主隊{pct(p)}、客隊{pct(1-p) if isinstance(p,(int,float)) else '—'}，僅屬試驗基準。"
    spread=market.get("spread") if market else None
    line=spread.get("home_line") if isinstance(spread,dict) else None
    cover=spread.get("home_cover_probability_experimental") if isinstance(spread,dict) else None
    if isinstance(line,(int,float)) and cover is not None:
        second=f"讓分：觀測主隊{line:+g}分，試驗過盤{pct(cover)}；分差波動採固定假設，未經校準。"
    elif isinstance(line,(int,float)):
        second=f"讓分：觀測主隊{line:+g}分，但缺少可驗證分差模型，過盤機率暫不提供。"
    else:
        second="讓分：目前沒有可核對的實際盤口，不能計算對應過盤機率。"
    mtotal=market.get("total") if market else None
    total_line=mtotal.get("line") if isinstance(mtotal,dict) else None
    if total and isinstance(total_line,(int,float)):
        over=total.get("over_probability_experimental")
        if over is not None:
            third=f"大小：盤口{total_line:g}分，試算總分{total['expected_total']:g}，大分{pct(over)}；只用近期樣本。"
        else:
            third=f"大小：盤口{total_line:g}分，但有效得分樣本不足，大、小分機率暫不提供。"
    elif total:
        third=f"大小：試算總分{total['expected_total']:g}分，但無真實大小分門檻，無法判斷大、小分過盤率。"
    else:
        third="大小：近期得分資料或實際總分盤不足，無法可靠推算大、小分機率。"
    caution="賽前請再核對傷病、確認先發與盤口時間；X記者消息尚未自動核實。所有數值均非已驗證優勢，僅供紙上研究。"
    report=start+second+third+caution
    if not 100<=len(report)<=200:
        raise ValueError(f"Report length invalid {len(report)} for {game.get('id')}: {report}")
    return report

def build_reports(games,predictions,markets,now):
    finals=[g for g in games if g.get("status")=="post"
        and isinstance(g.get("home_score"),int) and isinstance(g.get("away_score"),int)]
    by_id={str(m.get("event_id")):m for m in markets}
    future={str(g["id"]):g for g in games if g.get("status")=="pre"}
    out=[]
    for pred in predictions:
        id_=str(pred.get("event_id"))
        g=future.get(id_)
        if g is None:continue
        m=by_id.get(id_)
        tline=m.get("total",{}).get("line") if m else None
        total=model_total(g,finals,tline)
        row={"event_id":id_,"date":g.get("date"),"home":g["home"],"away":g["away"],
             "home_zh":team(g["home"]),"away_zh":team(g["away"]),
             "markets":{
                "moneyline":{"home_probability_experimental":pred.get("home_win_probability"),
                             "away_probability_experimental":round(1-pred["home_win_probability"],5)
                             if isinstance(pred.get("home_win_probability"),(int,float)) else None},
                "spread":m.get("spread") if m else None,
                "total":{"line":tline,**total} if total else {"line":tline,
                      "over_probability_experimental":None,"under_probability_experimental":None}},
             "observed_market":m is not None,
             "news_verified":False,"model_validated":False,
             "report_zh":summary(g,pred,m,total),
             "generated_at_utc":now}
        out.append(row)
    return out
