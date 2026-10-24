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
from analyst_factors import matchup_form,matchup_box_factors,injuries_by_matchup
from score_model import market_probabilities

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
        if iso(g.get("date")) is not None and kickoff-dt.timedelta(days=365)<=iso(g["date"])<kickoff
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

def summary(game,forecast,market,total,analysis=None):
    """Evidence-based analyst observation; absence of observed evidence is explicit."""
    away,home=team(game["away"]),team(game["home"])
    p=forecast.get("home_win_probability")
    factors=(analysis or {}).get("form") or {}
    hf,af=factors.get("home") or {},factors.get("away") or {}
    def form_margin(f):
        value=f.get("avg_margin")
        return f"{value:+g}" if isinstance(value,(int,float)) else "—"
    if hf.get("n") and af.get("n"):
        context=f"近{hf['n']}/{af['n']}場淨勝分主{form_margin(hf)}、客{form_margin(af)}。"
    else:
        context="近期樣本不足，不以猜測補上實力差。"
    start=f"{away}對{home}｜獨贏：十季Elo主{pct(p)}、客{pct(1-p) if isinstance(p,(int,float)) else '—'}；{context}"
    spread=(analysis or {}).get("spread") or {}
    market_spread=market.get("spread") if market else None
    line=market_spread.get("home_line") if isinstance(market_spread,dict) else None
    cover=spread.get("home") if spread else None
    if isinstance(line,(int,float)) and isinstance(cover,(int,float)):
        second=f"讓分：主{line:+g}分，試算過盤{pct(cover)}；"
    elif isinstance(line,(int,float)):
        second=f"讓分：主{line:+g}分，分差模型證據不足；"
    else:
        second="讓分：無可驗證盤口，不估過盤率；"
    if hf.get("n") and af.get("n"):
        resth,resta=hf.get("rest_days"),af.get("rest_days")
        if isinstance(resth,(int,float)) and isinstance(resta,(int,float)):
            second+=f"雙方休息{resth:g}/{resta:g}天，未假設固定疲勞效果。"
    total_market=market.get("total") if market else None
    total_line=total_market.get("line") if isinstance(total_market,dict) else None
    estimate=(analysis or {}).get("projection") or {}
    prop=(analysis or {}).get("total") or {}
    over=prop.get("over")
    if isinstance(total_line,(int,float)) and isinstance(over,(int,float)):
        third=f"大小：盤{total_line:g}、模型{estimate['expected_total']:g}，大分{pct(over)}；"
    elif isinstance(total_line,(int,float)):
        third=f"大小：盤{total_line:g}，總分模型尚缺校準；"
    elif estimate:
        third=f"大小：模型預估{estimate['expected_total']:g}分，但缺真實盤口；"
    else:
        third="大小：近期得分樣本不足，暫不提供預估；"
    if hf.get("n") and af.get("n"):
        third+=f"近況場均得分主{hf.get('avg_scored','—')}/客{af.get('avg_scored','—')}。"
    injury=(analysis or {}).get("injuries") or {}
    if injury.get("available") and injury.get("fresh"):
        x=injury.get("rows",[])
        caution=f"傷病通報{len(x)}筆，未量化球員上場影響；讓分與大小僅為試驗估計。"
    else:
        caution="傷病及先發資訊尚未核實；讓分與大小僅為試驗估計，非投注建議。"
    text=start+second+third+caution
    if len(text)>200:
        # Preserve real numbers and observations before dropping repetitive cautions.
        caution="傷兵影響與盤口變動尚未量化。"
        text=start+second+third+caution
    if len(text)>200:
        text=start+second+third
    if len(text)<100:
        text+="缺少的來源需等賽前驗證，不能把報導推測視為球員確定出賽或量化優勢。"
    if not 100<=len(text)<=200:
        raise ValueError(f"Report length invalid {len(text)} for {game.get('id')}: {text}")
    return text

def relevant_reporting(game,articles):
    """Attach up to three earlier newsroom headlines, never social rumors.
    Team alignment is by source metadata, not inferred unverified player names.
    """
    kickoff=iso(game.get("date"))
    if kickoff is None:return []
    teams={game.get("home"),game.get("away")}
    equivalence={"GS":"GSW","GSW":"GS","NY":"NYK","NYK":"NY",
      "NO":"NOP","NOP":"NO","SA":"SAS","SAS":"SA",
      "WSH":"WAS","WAS":"WSH","UTAH":"UTA","UTA":"UTAH"}
    teams|={equivalence[t] for t in list(teams) if t in equivalence}
    links=[]
    for article in articles or []:
        published=iso(article.get("published_at_utc"))
        if published is None or not (kickoff-dt.timedelta(days=3)<=published<=kickoff):continue
        if not any(t in teams for t in article.get("teams",[])):continue
        if article.get("x_post_verified") is True:continue
        url=article.get("url","")
        if not isinstance(url,str) or not url.startswith("https://www.espn.com/"):continue
        links.append({"title":article.get("title","")[:180],"url":url,
            "source":article.get("source","ESPN"),"author":article.get("author",""),
            "published_at_utc":article.get("published_at_utc")})
    links.sort(key=lambda a:a["published_at_utc"],reverse=True)
    return links[:3]

def build_reports(games,predictions,markets,now,historical_games=None,articles=None,analyst_forecasts=None,box_samples=None,injury_snapshot=None,season_priors=None):
    finals=[g for g in games if g.get("status")=="post"
        and isinstance(g.get("home_score"),int) and isinstance(g.get("away_score"),int)]
    # Historical outcomes are permitted only when genuinely scored and dated.
    # The model_total routine rejects games on/after the prediction's tip-off.
    for old in historical_games or []:
        if (old.get("id") and old.get("date")
            and isinstance(old.get("home_score"),int)
            and isinstance(old.get("away_score"),int)
            and old.get("home") and old.get("away")):
            finals.append(old)
    finals=list({str(g["id"]):g for g in finals}.values())
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
        form=matchup_form(g,finals)
        box_factors=matchup_box_factors(g,box_samples or [])
        injury=injuries_by_matchup(g,injury_snapshot or {})
        projection=(analyst_forecasts or {}).get(id_)
        market_probs=market_probabilities(projection,m)
        priors=(season_priors or {}).get("teams") or {}
        aliases={"GS":"GSW","NO":"NOP","NY":"NYK","SA":"SAS","WSH":"WAS","UTAH":"UTA"}
        prior_home=priors.get(g["home"]) or priors.get(aliases.get(g["home"]))
        prior_away=priors.get(g["away"]) or priors.get(aliases.get(g["away"]))
        if int(g.get("season_year") or 2027)!=2027:
            prior_home=prior_away=None
        analysis={"form":form,"box_four_factors":box_factors,
           "previous_season_efficiency":{"home":prior_home,"away":prior_away,
             "source":"PBP Stats previous regular season; not live team performance",
             "limitations":"Offseason roster changes; prior-season offensive PPP is not a game-day prediction"},
           "injuries":injury,"projection":projection,
           "spread":market_probs.get("spread"),
           "total":market_probs.get("total"),
           "market_observation": {"provider":m.get("provider"),
               "captured_at_utc":m.get("captured_at_utc"),
               "rights_status":m.get("rights_status")} if m else None,
           "causality_disclaimer":"近期得分、休息與對戰紀錄為相關因素，非已驗證因果效果"}
        spread=m.get("spread").copy() if m and m.get("spread") else None
        if spread and market_probs.get("spread"):
            spread["home_cover_probability_experimental"]=market_probs["spread"]["home"]
            spread["away_cover_probability_experimental"]=market_probs["spread"]["away"]
            spread["method"]="Chronological score projection, residual sigma fitted on 2022–25; not ATS calibrated"
        total_row={"line":tline,**total} if total else {"line":tline,
            "over_probability_experimental":None,"under_probability_experimental":None}
        if market_probs.get("total") and projection:
            total_row.update({
              "expected_total":projection["expected_total"],
              "total_sd":projection["total_sigma"],
              "over_probability_experimental":market_probs["total"]["over"],
              "under_probability_experimental":market_probs["total"]["under"],
              "whole_point_push_possible":market_probs["total"]["push_possible"],
              "method":"Empirical residual sigma on earlier seasons; holdout scores evaluated, not O/U odds calibrated"})
        row={"event_id":id_,"date":g.get("date"),"home":g["home"],"away":g["away"],
             "home_zh":team(g["home"]),"away_zh":team(g["away"]),
             "markets":{
                "moneyline":{"home_probability_experimental":pred.get("home_win_probability"),
                             "away_probability_experimental":round(1-pred["home_win_probability"],5)
                             if isinstance(pred.get("home_win_probability"),(int,float)) else None},
                "spread":spread,
                "total":total_row},
             "observed_market":m is not None,
             "news_verified":False,"related_reporting":relevant_reporting(g,articles),
             "model_validated":False,"analyst":analysis,
             "report_zh":summary(g,pred,m,total,analysis),
             "generated_at_utc":now}
        out.append(row)
    return out
