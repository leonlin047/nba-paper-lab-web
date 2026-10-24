"use strict";(()=>{const el=id=>document.getElementById(id);const line=(parent,tag,text)=>{const n=document.createElement(tag);n.textContent=text;parent.append(n);return n};async function run(){try{const r=await fetch("./data/games.json?t="+Date.now(),{cache:"no-store"});if(!r.ok)throw Error("HTTP "+r.status);const d=await r.json();
const reportsData=await fetch("./data/reports.json?v="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():{}).catch(()=>({}));
const reportMap=new Map((reportsData.reports||[]).map(x=>[String(x.event_id),x]));
const twData=await fetch("./data/tw_odds.json?v="+Date.now(),{cache:"no-store"}).then(r=>r.ok?r.json():{}).catch(()=>({}));
const twMap=new Map((twData.games||[]).filter(x=>x.join_verified&&x.eligible_for_pregame_backtest).map(x=>[String(x.event_id),x]));
const zh=window.NbaZh||{teamShort:v=>v,player:v=>v};
const usPrice=v=>typeof v==="number"?(v>0?"+":"")+v:"—";
const upcoming=el("upcoming-games"),completed=el("completed-details");upcoming.replaceChildren();completed.replaceChildren();const games=Array.isArray(d.games)?d.games:[];const future=games.filter(g=>g.status==="pre").slice(0,45);if(!future.length)line(upcoming,"p","目前沒有未開賽的賽程快照。");for(const g of future){const c=line(upcoming,"div",zh.teamShort(g.away)+" 對 "+zh.teamShort(g.home)+" · "+new Date(g.date).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}));c.style.cssText="padding:12px 0;border-bottom:1px solid #304362";const tw=twMap.get(String(g.id));
if(tw){
  const ml=tw.moneyline||{},sp=tw.spread||{},t=tw.total||{};
  const domestic=line(c,"p","台灣運彩盤｜獨贏主／客 "+(ml.home_decimal??"—")+"/"+(ml.away_decimal??"—")+
    "；讓分主 "+(sp.home_line??"—")+"／客 "+(sp.away_line??"—")+"（賠率 "+(sp.home_decimal??"—")+"/"+(sp.away_decimal??"—")+"）"+
    "；大小 "+(t.line??"—")+"（大"+(t.over_decimal??"—")+"／小"+(t.under_decimal??"—")+"）");
  domestic.style.cssText="font-weight:600;color:#bcdefe";
  line(c,"p","公開來源：玩運彩運彩盤（第三方整理，非官方API）；擷取 "+
    new Date(tw.observed_at_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}));
}
const q=(d.market_snapshots||[]).find(x=>String(x.event_id)===String(g.id));if(q){
 const x=q.moneyline||{},s=q.spread||{},t=q.total||{},p=q.observed_prices||{};
 line(c,"p","觀測國際盤："+(q.provider||"未知莊家")+" · 獨贏 主 "+usPrice(x.home_american)+"／客 "+usPrice(x.away_american)+"（美式）");
 line(c,"p","讓分 主 "+(s.home_line??"—")+"／客 "+(s.away_line??"—")+"；雙邊賠率 "+usPrice(p.spread_home_american)+"／"+usPrice(p.spread_away_american));
 line(c,"p","大小分 "+(t.line??"—")+"；大 "+usPrice(p.total_over_american)+"／小 "+usPrice(p.total_under_american));
 line(c,"p","擷取時間："+(q.captured_at_utc?new Date(q.captured_at_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"未記錄")+"；非台灣運彩、非即時保證。");
}else line(c,"p","本場尚無真實盤口，模型勝率並非莊家賠率。");const report=reportMap.get(String(g.id));
if(report){const block=document.createElement("details");
 block.style.cssText="padding:8px 0;margin-top:8px;border-top:1px solid #304362";
 const heading=document.createElement("summary");heading.textContent="獨贏／讓分／大小分觀察報告（100–200 字）";
 block.append(heading);line(block,"p",report.report_zh);
 c.append(block);}
 const link=line(c,"button","查看三市場機率與分析 →");link.type="button";link.style.cssText="padding:7px 10px;margin-top:4px;border-radius:8px;background:#244376;color:white;border:1px solid #5271aa";link.addEventListener("click",()=>{const t=document.querySelector('[data-target="research"]');if(t){t.click();document.getElementById("research").scrollIntoView({behavior:"smooth",block:"start"})}})}const details=Array.isArray(d.details)?d.details:[];if(!details.length)line(completed,"p","目前尚無完賽球員與節次明細。");for(const detail of details.slice().reverse()){const game=games.find(g=>g.id===detail.event_id);if(!game)continue;const card=document.createElement("details");card.style.cssText="padding:12px 0;border-bottom:1px solid #304362";const title=document.createElement("summary");title.textContent=zh.teamShort(game.away)+" "+game.away_score+" — "+game.home_score+" "+zh.teamShort(game.home)+"（點開查看）";card.append(title);for(const team of detail.quarter_scores||[])line(card,"p",zh.teamShort(team.team)+" 各節："+(team.quarters||[]).join(" / "));for(const team of detail.boxscore||[]){line(card,"h3",zh.teamShort(team.team)+" 球員統計");for(const player of (team.players||[]).slice(0,18)){const row=line(card,"p",zh.player(player.name)+" · "+Object.entries(player.stats||{}).slice(0,9).map(([k,v])=>k+":"+v).join("  "));row.style.cssText="font-size:12px;color:#a7b7d0;overflow-wrap:anywhere"}}completed.append(card)}}catch(e){el("completed-details").textContent="明細尚未就緒："+e.message;el("upcoming-games").textContent="賽程尚未就緒："+e.message}}run()})();