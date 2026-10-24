"use strict";
(()=>{
 const $=id=>document.getElementById(id);
 const root=$("research-terminal");if(!root)return;
 const elt=(tag,cls,value)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(value!==undefined&&value!==null)x.textContent=String(value);return x};
 const fmt=n=>typeof n==="number"&&Number.isFinite(n)?(n*100).toFixed(1)+"%":"—";
 const num=n=>typeof n==="number"&&Number.isFinite(n)?n:null;
 const american=v=>typeof v==="number"&&Number.isFinite(v)?(v>0?"+":"")+v:"—";
 const decimalFromAmerican=v=>typeof v==="number"&&Math.abs(v)>=100?(v>0?1+v/100:1+100/Math.abs(v)).toFixed(2):"—";
 const safe=v=>v===null||v===undefined?"—":String(v);
 const time=t=>t?new Date(t).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"—";
 const risk=meta=>meta&&meta.out_of_sample===true&&meta.sample_size>=200&&typeof meta.brier==="number"?"十季 Elo 獨贏已完成時序驗證":"獨贏模型尚未完成足夠時序驗證";
 function gauge(prob){
   const wrap=elt("div","pl-gauge"),needle=elt("div","pl-needle"),label=elt("div","pl-gauge-value",fmt(prob));
   if(num(prob)!==null&&prob>=0&&prob<=1)needle.style.transform="translateX(-50%) rotate("+(-90+prob*180)+"deg)";
   else needle.style.display="none";
   wrap.append(needle,label);return wrap;
 }
 function oldMarket(q,game,p){
   if(!q)return null;
   const decimal=x=>{const n=Number(x);return Number.isFinite(n)&&Math.abs(n)>=100?(n>0?1+n/100:1+100/Math.abs(n)):null};
   const hd=decimal(q.home_moneyline),ad=decimal(q.away_moneyline),den=hd&&ad?1/hd+1/ad:null;
   return {event_id:q.event_id,provider:q.provider,captured_at_utc:q.captured_at_utc,rights_status:q.rights_status,
    moneyline:{home_american:q.home_moneyline,away_american:q.away_moneyline,home_decimal:hd,away_decimal:ad,home_no_vig_probability:den?(1/hd)/den:null,away_no_vig_probability:den?(1/ad)/den:null},
    spread:{home_line:null,away_line:null,details:q.details,home_cover_probability_experimental:null,away_cover_probability_experimental:null},
    total:{line:q.over_under}};
 }
 function predictions(rows,meta,markets,raw,reports){
   const box=$("pl-predictions");box.replaceChildren();
   if(!Array.isArray(rows)||!rows.length){box.append(gauge(null),elt("p","pl-muted","暫無有效的賽前模型快照。"));return}
   const byId=new Map((markets||[]).map(m=>[String(m.event_id),m]));
   const byReport=new Map((reports||[]).map(m=>[String(m.event_id),m]));
   const older=new Map((raw||[]).map(m=>[String(m.event_id),m]));
   for(const game of rows){
     const market=byId.get(String(game.event_id))||oldMarket(older.get(String(game.event_id)),game,game.home_win_probability);
     const report=byReport.get(String(game.event_id));
     const card=elt("article","pl-panel"),select=elt("select");card.append(elt("strong","",(window.NbaZh?window.NbaZh.teamShort(game.away):safe(game.away))+" 對 "+(window.NbaZh?window.NbaZh.teamShort(game.home):safe(game.home))));
     const started=game.date?new Date(game.date).getTime()<=Date.now():false;
     card.append(elt("p","pl-muted",(game.date?time(game.date)+" · ":"")+(started?"賽前舊快照（賽事可能已開打）":"賽前預測")));
     select.style.cssText="display:block;width:100%;margin:12px 0;padding:12px;background:#0b172a;color:#fff;border:1px solid #526688;border-radius:10px";
     select.setAttribute("aria-label","玩法與隊伍");
     for(const [v,label] of [["ml_home","獨贏｜主隊"],["ml_away","獨贏｜客隊"],["spread_home","讓分／受讓｜主隊"],["spread_away","讓分／受讓｜客隊"],["total_over","大小分｜大分"],["total_under","大小分｜小分"]]){const o=elt("option","",label);o.value=v;select.append(o)}
     const view=elt("div");
     function repaint(){
       view.replaceChildren();
       const home=select.value.endsWith("home"),spread=select.value.startsWith("spread"),isTotal=select.value.startsWith("total");
       const elo=num(game.home_win_probability),est=elo===null?null:(home?elo:1-elo);
       const m=market?market.moneyline:null,s=market?market.spread:null;
       if(isTotal){
         const total=report&&report.markets?report.markets.total:null;
         const line=total?total.line:(market&&market.total?market.total.line:null);
         const result=total?(select.value==="total_over"?total.over_probability_experimental:total.under_probability_experimental):null;
         view.append(gauge(num(result)),elt("p","pl-muted",select.value==="total_over"?"大分機率（試驗估計）："+fmt(num(result)):"小分機率（試驗估計）："+fmt(num(result))));
         view.append(elt("p","pl-muted","觀測總分盤："+safe(line)));
         const quotes=market&&market.observed_prices||{};
         view.append(elt("p","pl-muted","實際大小分賠率（美式／十進位）· 大 "+
           american(quotes.total_over_american)+"／"+decimalFromAmerican(quotes.total_over_american)+
           "，小 "+american(quotes.total_under_american)+"／"+decimalFromAmerican(quotes.total_under_american)));
         if(total&&typeof total.expected_total==="number")view.append(elt("p","pl-muted","近期攻守得分模型預估總分："+total.expected_total+" 分"));
         else view.append(elt("p","pl-muted","得分樣本不足或未取得，不能提供可靠估計。"));
         if(total&&total.whole_point_push_possible)view.append(elt("p","pl-muted","整數盤可能走水，未估計走水機率。"));
         view.append(elt("p","pl-muted","近期攻守得分與分差波動模型尚未完整回測，切勿把估計視為確定結果。"));
       }else if(spread){
         const line=s?(home?s.home_line:s.away_line):null;
         const cover=s?(home?s.home_cover_probability_experimental:s.away_cover_probability_experimental):null;
         view.append(gauge(num(cover)),elt("p","pl-muted","過盤機率（實驗模型）："+fmt(num(cover))));
         view.append(elt("p","pl-muted","讓分／受讓線："+(line===null||line===undefined?"未確認":(line>0?"+":"")+line)));
         const q=market&&market.observed_prices||{};
         const odd=home?q.spread_home_american:q.spread_away_american;
         view.append(elt("p","pl-muted","實際讓分賠率（美式／十進位）："+american(odd)+"／"+decimalFromAmerican(odd)));
         if(s&&s.details)view.append(elt("p","pl-muted","來源盤口標示："+s.details));
         if(s&&s.whole_point_push_possible)view.append(elt("p","pl-muted","整數盤可能走水：此連續近似模型未估計走水機率。"));
         const sigma=report&&report.analyst&&report.analyst.projection&&report.analyst.projection.margin_sigma;
         view.append(elt("p","pl-muted","歷史比分殘差標準差："+safe(sigma)+"分；尚未以歷史盤口驗證過盤率。"));
       }else{
         view.append(gauge(est),elt("p","pl-muted","Elo 試驗獨贏勝率："+fmt(est)));
         const fair=m?(home?m.home_no_vig_probability:m.away_no_vig_probability):null;
         const odds=m?(home?m.home_american:m.away_american):null;
         view.append(elt("p","pl-muted","市場去水後隱含機率："+fmt(num(fair))));
         view.append(elt("p","pl-muted","實際獨贏賠率（美式／十進位）："+american(odds)+"／"+decimalFromAmerican(odds)));
       }
       view.append(elt("p","pl-muted",market?"觀測："+safe(market.provider)+" · "+time(market.captured_at_utc):"本場沒有對應的盤口觀測"));
       const stale=market&&market.captured_at_utc&&(Date.now()-Date.parse(market.captured_at_utc)>2*3600000);
       if(stale)view.append(elt("p","pl-muted","注意：盤口已超過兩小時，非即時盤。"));
       view.append(elt("p","pl-muted","模型狀態："+risk(meta)+"；讓分及大小分模型尚未完成校準／獨立驗證。盤口資料授權尚待確認，僅供紙上研究。"));
     }
     select.addEventListener("change",repaint);card.append(select,view);repaint();
     const overview=elt("p","pl-muted");
     const homeProb=game.home_win_probability;
     const cover=market&&market.spread?market.spread.home_cover_probability_experimental:null;
     const total=report&&report.markets?report.markets.total:null;
     overview.textContent="三市場總覽 · 主隊獨贏 "+fmt(num(homeProb))+"｜主隊過盤 "+fmt(num(cover))+"｜大分 "+fmt(num(total&&total.over_probability_experimental));
     card.append(overview);
     const reportBlock=elt("details");
     reportBlock.style.cssText="padding-top:10px;border-top:1px solid #42536a;margin-top:10px";
     reportBlock.append(elt("summary","","中文三市場觀察報告（100–200 字）"));
     const observation=elt("p","pl-muted",report&&report.report_zh?report.report_zh:"報告尚未生成，請確認資料更新工作流程。");
     observation.style.cssText="font-size:14px;line-height:1.8;white-space:normal";
     reportBlock.append(observation);
     const evidence=report&&report.analyst;
     if(evidence){
       const facts=elt("details");facts.style.cssText="padding:10px 0;border-top:1px solid #344a6c";
       facts.append(elt("summary","","分析師數據證據與限制（依賽前時間回溯）"));
       const section=(name,value)=>facts.append(elt("p","pl-muted",name+"："+value));
       const f=evidence.form||{},h=f.home||{},a=f.away||{};
       const label=code=>window.NbaZh?window.NbaZh.teamShort(code):code;
       const fmtCount=x=>typeof x==="number"?x.toFixed(1):"—";
       const noteForm=(name,x)=>x.n?name+" 近"+x.n+"場 "+x.wins+"勝，場均得"+fmtCount(x.avg_scored)+"／失"+fmtCount(x.avg_allowed)+"，淨勝"+fmtCount(x.avg_margin)+"，休息"+fmtCount(x.rest_days)+"天"+(x.back_to_back_proxy?"（背靠背間隔）":""):"無有效最近場次";
       section("近期主隊",noteForm(label(game.home),h));
       section("近期客隊",noteForm(label(game.away),a));
       if(h.home&&h.home.n)section("主隊主場",h.home.n+"場淨勝"+fmtCount(h.home.avg_margin)+"分");
       if(a.away&&a.away.n)section("客隊客場",a.away.n+"場淨勝"+fmtCount(a.away.avg_margin)+"分");
       if(f.h2h&&f.h2h.n)section("過去兩年交手",f.h2h.n+"場，當前主隊平均淨勝"+fmtCount(f.h2h.avg_home_team_margin)+"分；跨季樣本不等於今季實力");
       if(h.n&&a.n)section("跨季樣本檢查","主隊"+(h.current_season_n??"—")+"/"+h.n+"場、客隊"+(a.current_season_n??"—")+"/"+a.n+"場屬本賽季；休賽季轉隊可能改變代表性。");
       const prior=evidence.previous_season_efficiency||{},ph=prior.home||{},pa=prior.away||{};
       if(ph.offensive_points_per_possession_previous_season!=null&&pa.offensive_points_per_possession_previous_season!=null){
          section("前季回合效率（PBP Stats）","主／客每回合得分 "+ph.offensive_points_per_possession_previous_season+"/"+pa.offensive_points_per_possession_previous_season+
            "，每次進攻耗時 "+ph.offensive_seconds_per_possession_previous_season+"/"+pa.offensive_seconds_per_possession_previous_season+
            "秒；此為2025–26完整賽季，不是本賽季即時效率。");
         if(ph.offensive_rating_previous_season!=null&&pa.offensive_rating_previous_season!=null){
           section("前季每100回合進攻效率","主／客 "+ph.offensive_rating_previous_season+"／"+pa.offensive_rating_previous_season+
             "，防守失分／100回合 "+ph.defensive_rating_previous_season+"／"+pa.defensive_rating_previous_season+"（越低越好）");
           section("前季實際回合與四要素","主／客Pace "+ph.possessions_per_48_previous_season+"／"+pa.possessions_per_48_previous_season+
             "，eFG% "+ph.efg_pct_previous_season+"／"+pa.efg_pct_previous_season+
             "，TO% "+ph.turnover_per_100_possessions_previous_season+"／"+pa.turnover_per_100_possessions_previous_season+
             "，OREB% "+ph.offensive_fg_rebound_pct_previous_season+"／"+pa.offensive_fg_rebound_pct_previous_season);
         }
       }else section("前季回合資料","PBP Stats 前季效率未取得，不以場均分數冒充回合效率。");
       const box=evidence.box_four_factors||{},bh=box.home||{},ba=box.away||{};
       if(bh.n>=3&&ba.n>=3){
          section("投籃與控球（實際賽後統計）","主／客eFG% "+fmtCount(bh.eFG_pct)+"／"+fmtCount(ba.eFG_pct)+"；三分出手率 "+fmtCount(bh.three_point_attempt_rate)+"／"+fmtCount(ba.three_point_attempt_rate));
          section("估算回合數與失誤率","主／客估算回合 "+fmtCount(bh.estimated_possessions)+"／"+fmtCount(ba.estimated_possessions)+"；TO% "+fmtCount(bh.turnover_per_est_poss_pct)+"／"+fmtCount(ba.turnover_per_est_poss_pct)+"（非官方Pace）");
          section("籃板與罰球四要素","主／客OREB% "+fmtCount(bh.oreb_pct)+"／"+fmtCount(ba.oreb_pct)+"，FTA/FGA% "+fmtCount(bh.free_throw_attempt_rate)+"／"+fmtCount(ba.free_throw_attempt_rate));
       }else section("節奏／四要素","目前每隊有效團隊boxscore不足3場；不拿場均得分冒充Pace或攻防效率");
       const p=evidence.projection||{};
       if(typeof p.expected_margin==="number")section("賽前分差／總分模型","預估主隊淨勝"+fmtCount(p.expected_margin)+"分、總分"+fmtCount(p.expected_total)+"分，歷史殘差σ約"+fmtCount(p.margin_sigma)+"/"+fmtCount(p.total_sigma)+"分");
       else section("賽前分差／總分模型","有效球隊歷史樣本不足，暫無可驗證的模型估算");
       const injury=evidence.injuries||{};
       if(injury.available&&injury.fresh){
         const rows=injury.rows||[];
         section("傷病清單",rows.length+"筆（ESPN；非聯盟針對本場的正式出賽公告）");
         for(const x of rows.slice(0,8))section(label(x.team)+"傷病",((window.NbaZh&&window.NbaZh.player(x.player))||x.player||"未知球員")+" · "+(x.status||"未公布")+(x.type?" · "+x.type:""));
       }else section("傷病證據",injury.note||"無賽前有效時間戳或狀態，禁止推定已健康");
       if(market&&market.provider_open_last){
         const mv=market.provider_open_last,sp=mv.pointSpread||{},ttl=mv.total||{},ml=mv.moneyline||{};
         const price=z=>z&&z.odds!=null?String(z.odds):"—";
         const line=z=>z&&z.line!=null?String(z.line):"—";
         if(sp.home)section("提供商讓分標記","主隊開盤 "+line(sp.home.open)+"（"+price(sp.home.open)+"）→ 目前 "+line(sp.home.close)+"（"+price(sp.home.close)+"）");
         if(ttl.over)section("提供商大小標記","大分開盤 "+line(ttl.over.open)+" → 目前 "+line(ttl.over.close));
         if(ml.home)section("提供商獨贏標記","主隊開盤 "+price(ml.home.open)+" → 目前 "+price(ml.home.close));
         section("盤口時序限制","開盤／目前為業者欄位，未取得每次變動的精確時間；不可據此證明資金流向或過去資訊已知。");
       }
       section("來源與缺值","ESPN完成比賽比分、近期團隊boxscore、當前傷病快照、莊家盤口觀測；各證據採賽前時間過濾。"+
         "目前未以X貼文推定先發或球員上場時間，新聞標題僅供查核。");
       reportBlock.append(facts);
     }
     if(report&&Array.isArray(report.related_reporting)&&report.related_reporting.length){
       reportBlock.append(elt("p","pl-muted","關聯球隊近期新聞（非 X 即時貼文；不能據此認定先發）："));
       for(const story of report.related_reporting){
         if(!story||typeof story.url!=="string"||!story.url.startsWith("https://www.espn.com/"))continue;
         const node=elt("p","pl-muted");
         const link=elt("a","",story.title||"ESPN 新聞報導");
         link.href=story.url;link.target="_blank";link.rel="noopener noreferrer";
         link.style.cssText="color:#a6caff;text-decoration:underline";
         node.append(link,elt("span",""," · "+time(story.published_at_utc)));
         reportBlock.append(node);
       }
     }
     if(box.children.length===0)reportBlock.open=true;
     card.append(reportBlock);
     box.append(card);
   }
 }
 function marketOverview(markets,raw){
   const box=$("pl-odds");box.replaceChildren();
   const entries=markets&&markets.length?markets:(raw||[]).map(x=>oldMarket(x));
   if(!entries.length){box.append(elt("p","pl-muted","尚未取得可驗證的國際／台灣盤口。"));return}
   box.append(elt("p","pl-muted","下列為觀測到的國際盤口，不是台灣運彩報價；不同來源不得直接混用。"));
   for(const m of entries){
     const c=elt("article","pl-panel"),x=m.moneyline||{},s=m.spread||{};
     c.append(elt("strong","",(window.NbaZh?window.NbaZh.teamShort(m.away):safe(m.away||"客隊"))+" 對 "+(window.NbaZh?window.NbaZh.teamShort(m.home):safe(m.home||"主隊"))+" · "+safe(m.provider)));
     c.append(elt("p","pl-muted","獨贏 主／客："+safe(x.home_american)+" / "+safe(x.away_american)+"（美式）"));
     c.append(elt("p","pl-muted","去水隱含機率 主／客："+fmt(num(x.home_no_vig_probability))+" / "+fmt(num(x.away_no_vig_probability))));
     c.append(elt("p","pl-muted","讓分："+safe(s.details)+" · 大小："+safe(m.total&&m.total.line)));
     c.append(elt("p","pl-muted","觀測時間："+time(m.captured_at_utc)));
     box.append(c);
   }
 }
 function sources(d,probe){
   const box=$("pl-sources");box.replaceChildren();
   for(const s of d.sources||[]){const c=elt("div","pl-panel");c.append(elt("strong","",safe(s.name)),elt("p","pl-muted","狀態："+safe(s.status)+" · 授權："+safe(s.rights)));box.append(c)}
   // Playsport availability probe remains in the repository for audit,
   // but is not a sportsbook data input and must not be portrayed as one.
   // Public attribution is shown for sources actually used in forecasts.
 }
 async function json(url){const r=await fetch(url+"?v="+Date.now(),{cache:"no-store"});if(!r.ok)throw Error(url+" HTTP "+r.status);return r.json()}
 async function load(){
   $("pl-update").textContent="讀取盤口與預測快照…";
   try{
     const [d,g,p,reportsData]=await Promise.all([json("./data/research.json"),json("./data/games.json"),json("./data/playsport_status.json").catch(()=>null),json("./data/reports.json").catch(()=>null)]);
     predictions(d.predictions,d.validation,g.market_snapshots,g.odds_discovery,reportsData&&reportsData.reports);
     if($("model-sample"))$("model-sample").textContent=safe(d.validation&&d.validation.sample_size);
     if($("model-brier"))$("model-brier").textContent=num(d.validation&&d.validation.brier)!==null?d.validation.brier.toFixed(4):"—";
     if($("model-logloss"))$("model-logloss").textContent=num(d.validation&&d.validation.log_loss)!==null?d.validation.log_loss.toFixed(4):"—";
     if($("model-score-mae")){
        const stats=d.analyst_validation||{};
        const m=typeof stats.margin_mae==="number"?stats.margin_mae.toFixed(2):"—";
        const t=typeof stats.total_mae==="number"?stats.total_mae.toFixed(2):"—";
        const pure=typeof stats.ablation_holdout_elo_only_mae==="number"?stats.ablation_holdout_elo_only_mae.toFixed(2):"—";
        const naive=typeof stats.ablation_holdout_total_naive_league_mae==="number"?stats.ablation_holdout_total_naive_league_mae.toFixed(2):"—";
        const ci=stats.ablation_total_vs_league_day_cluster_ci95;
        const interval=Array.isArray(ci)?"，日期區塊95%CI ["+ci[0]+", "+ci[1]+"]":"";
        const verdict=typeof stats.ablation_margin_selected_vs_elo_mae_improvement==="number"?(stats.ablation_margin_selected_vs_elo_mae_improvement>0?"較純Elo誤差較低":"尚未勝過純Elo"):"優劣未知";
        $("model-score-mae").textContent="2025–26時序驗證（"+(stats.holdout_margin_n||0)+"場）：混合分差MAE "+m+"分／純Elo "+pure+"分（"+verdict+"）。總分MAE "+t+"分／單純聯盟均值 "+naive+"分，改善"+(stats.ablation_total_vs_league_mae_improvement??"—")+"分"+interval+"。仍缺歷史時間戳盤口，不能驗證讓分或大小分投注報酬。";
     }
     marketOverview(g.market_snapshots,g.odds_discovery);
     sources(d,p);
     $("pl-update").textContent="資料版本："+safe(d.version)+" · 更新："+time(d.updated_at_utc);
   }catch(e){$("pl-update").textContent="研究資料讀取失敗："+e.message;}
 }
 $("pl-refresh").addEventListener("click",load);
 load();
})();