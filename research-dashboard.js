"use strict";
(()=>{
 const $=id=>document.getElementById(id);
 const root=$("research-terminal");if(!root)return;
 const elt=(tag,cls,value)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(value!==undefined&&value!==null)x.textContent=String(value);return x};
 const fmt=n=>typeof n==="number"&&Number.isFinite(n)?(n*100).toFixed(1)+"%":"—";
 const num=n=>typeof n==="number"&&Number.isFinite(n)?n:null;
 const safe=v=>v===null||v===undefined?"—":String(v);
 const time=t=>t?new Date(t).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"—";
 const risk=meta=>meta&&meta.out_of_sample===true&&meta.sample_size>=200&&typeof meta.brier==="number"?"有樣本外檢驗":"尚未驗證";
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
 function predictions(rows,meta,markets,raw){
   const box=$("pl-predictions");box.replaceChildren();
   if(!Array.isArray(rows)||!rows.length){box.append(gauge(null),elt("p","pl-muted","暫無有效的賽前模型快照。"));return}
   const byId=new Map((markets||[]).map(m=>[String(m.event_id),m]));
   const older=new Map((raw||[]).map(m=>[String(m.event_id),m]));
   for(const game of rows){
     const market=byId.get(String(game.event_id))||oldMarket(older.get(String(game.event_id)),game,game.home_win_probability);
     const card=elt("article","pl-panel"),select=elt("select");card.append(elt("strong","",safe(game.away)+" @ "+safe(game.home)));
     const started=game.date?new Date(game.date).getTime()<=Date.now():false;
     card.append(elt("p","pl-muted",(game.date?time(game.date)+" · ":"")+(started?"賽前舊快照（賽事可能已開打）":"賽前預測")));
     select.style.cssText="display:block;width:100%;margin:12px 0;padding:12px;background:#0b172a;color:#fff;border:1px solid #526688;border-radius:10px";
     select.setAttribute("aria-label","玩法與隊伍");
     for(const [v,label] of [["ml_home","獨贏｜主隊"],["ml_away","獨贏｜客隊"],["spread_home","讓分／受讓｜主隊"],["spread_away","讓分／受讓｜客隊"]]){const o=elt("option","",label);o.value=v;select.append(o)}
     const view=elt("div");
     function repaint(){
       view.replaceChildren();
       const home=select.value.endsWith("home"),spread=select.value.startsWith("spread");
       const elo=num(game.home_win_probability),est=elo===null?null:(home?elo:1-elo);
       const m=market?market.moneyline:null,s=market?market.spread:null;
       if(spread){
         const line=s?(home?s.home_line:s.away_line):null;
         const cover=s?(home?s.home_cover_probability_experimental:s.away_cover_probability_experimental):null;
         view.append(gauge(num(cover)),elt("p","pl-muted","過盤機率（實驗模型）："+fmt(num(cover))));
         view.append(elt("p","pl-muted","讓分／受讓線："+(line===null||line===undefined?"未確認":(line>0?"+":"")+line)));
         if(s&&s.details)view.append(elt("p","pl-muted","來源盤口標示："+s.details));
         if(s&&s.whole_point_push_possible)view.append(elt("p","pl-muted","整數盤可能走水：此連續近似模型未估計走水機率。"));
         view.append(elt("p","pl-muted","固定分差標準差 12 分的常態近似，尚未依歷史數據校準或回測。"));
       }else{
         view.append(gauge(est),elt("p","pl-muted","Elo 試驗獨贏勝率："+fmt(est)));
         const fair=m?(home?m.home_no_vig_probability:m.away_no_vig_probability):null;
         const odds=m?(home?m.home_american:m.away_american):null;
         view.append(elt("p","pl-muted","市場去水後隱含機率："+fmt(num(fair))));
         view.append(elt("p","pl-muted","美式獨贏賠率："+safe(odds)));
       }
       view.append(elt("p","pl-muted",market?"觀測："+safe(market.provider)+" · "+time(market.captured_at_utc):"本場沒有對應的盤口觀測"));
       const stale=market&&market.captured_at_utc&&(Date.now()-Date.parse(market.captured_at_utc)>2*3600000);
       if(stale)view.append(elt("p","pl-muted","注意：盤口已超過兩小時，非即時盤。"));
       view.append(elt("p","pl-muted","模型狀態："+risk(meta)+"；盤口資料授權尚待確認。僅供紙上研究，不代表實際可投注價格。"));
     }
     select.addEventListener("change",repaint);card.append(select,view);repaint();box.append(card);
   }
 }
 function marketOverview(markets,raw){
   const box=$("pl-odds");box.replaceChildren();
   const entries=markets&&markets.length?markets:(raw||[]).map(x=>oldMarket(x));
   if(!entries.length){box.append(elt("p","pl-muted","尚未取得可驗證的國際／台灣盤口。"));return}
   box.append(elt("p","pl-muted","下列為觀測到的國際盤口，不是台灣運彩報價；不同來源不得直接混用。"));
   for(const m of entries){
     const c=elt("article","pl-panel"),x=m.moneyline||{},s=m.spread||{};
     c.append(elt("strong","",safe(m.away||"客隊")+" @ "+safe(m.home||"主隊")+" · "+safe(m.provider)));
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
   if(probe){const c=elt("div","pl-panel");c.append(elt("strong","","玩運彩公開頁面連線檢查"),elt("p","pl-muted","頁面："+safe(probe.fetch_status)+" · 欄位："+(probe.has_market_headers?"可辨識":"未辨識")+" · 已驗證盤口筆數："+safe(probe.nba_market_rows_verified)),elt("p","pl-muted","連線成功不代表完成逐場抓取或獲授權再發布。"));box.append(c)}
 }
 async function json(url){const r=await fetch(url+"?v="+Date.now(),{cache:"no-store"});if(!r.ok)throw Error(url+" HTTP "+r.status);return r.json()}
 async function load(){
   $("pl-update").textContent="讀取盤口與預測快照…";
   try{
     const [d,g,p]=await Promise.all([json("./data/research.json"),json("./data/games.json"),json("./data/playsport_status.json").catch(()=>null)]);
     predictions(d.predictions,d.validation,g.market_snapshots,g.odds_discovery);
     if($("model-sample"))$("model-sample").textContent=safe(d.validation&&d.validation.sample_size);
     if($("model-brier"))$("model-brier").textContent=num(d.validation&&d.validation.brier)!==null?d.validation.brier.toFixed(4):"—";
     marketOverview(g.market_snapshots,g.odds_discovery);
     sources(d,p);
     $("pl-update").textContent="資料版本："+safe(d.version)+" · 更新："+time(d.updated_at_utc);
   }catch(e){$("pl-update").textContent="研究資料讀取失敗："+e.message;}
 }
 $("pl-refresh").addEventListener("click",load);
 load();
})();