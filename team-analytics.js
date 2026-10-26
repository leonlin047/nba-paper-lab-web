"use strict";
(()=>{
 const $=id=>document.getElementById(id),root=$("team-output"),compare=$("team-compare"),input=$("search");
 if(!root||!compare||!input)return;
 const ZH=window.NbaZh;
 const names=new Map([["ATL","老鷹"],["BOS","塞爾提克"],["BKN","籃網"],["CHA","黃蜂"],["CHI","公牛"],["CLE","騎士"],["DAL","獨行俠"],["DEN","金塊"],["DET","活塞"],["GSW","勇士"],["HOU","火箭"],["IND","溜馬"],["LAC","快艇"],["LAL","湖人"],["MEM","灰熊"],["MIA","熱火"],["MIL","公鹿"],["MIN","灰狼"],["NOP","鵜鶘"],["NYK","尼克"],["OKC","雷霆"],["ORL","魔術"],["PHI","76人"],["PHX","太陽"],["POR","拓荒者"],["SAC","國王"],["SAS","馬刺"],["TOR","暴龍"],["UTA","爵士"],["WAS","巫師"]]);
 const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(cls)node.className=cls;return node};
 const val=(x,dp=1)=>typeof x==="number"&&Number.isFinite(x)?x.toFixed(dp):"尚無資料";
 const label=(k)=>names.get(k)?names.get(k)+" ("+k+")":k;
 const metrics=[
  ["進攻效率 ORtg","offensive_rating_previous_season",1],
  ["防守效率 DRtg","defensive_rating_previous_season",1],
  ["淨效率 Net","net_rating_previous_season",1],
  ["每48分鐘回合估計","possessions_per_48_previous_season",1],
  ["有效命中率 eFG%","efg_pct_previous_season",1],
  ["失誤／百回合","turnover_per_100_possessions_previous_season",1],
  ["進攻籃板率%","offensive_fg_rebound_pct_previous_season",1],
  ["罰球出手率%","free_throw_attempt_rate_pct_previous_season",1]
 ];
 const state={teams:{},captured:"",season:"",rights:""};
 function summary(t,parent){
   const row=el("article",undefined,"team-result");
   row.append(el("strong",label(t.team)));
   const cols=el("div",undefined,"team-metrics");
   for(const [name,key,dp] of metrics){
    const c=el("span",name);
    c.append(el("b",val(t[key],dp)));cols.append(c);
   }
   row.append(cols);parent.append(row);
 }
 function directory(){
  root.replaceChildren();
  const q=input.value.toLowerCase().trim();
  const items=Object.values(state.teams).filter(t=>(label(t.team)+" "+t.team).toLowerCase().includes(q));
  if(!items.length){root.append(el("p","查無符合的球隊","muted"));return}
  root.append(el("p","上季統計；PBP Stats 已收集的 30 隊描述數據，不代表今天的陣容、傷兵或進攻實力。","muted"));
  for(const t of items) summary(t,root);
 }
 function compareTeams(){
  const home=$("team-compare-home"),away=$("team-compare-away");
  if(!home||!away)return;
  const h=state.teams[home.value],a=state.teams[away.value];
  const out=$("team-compare-output");out.replaceChildren();
  if(!h||!a||h.team===a.team){out.append(el("p","請選擇不同球隊。","muted"));return}
  const table=el("table");table.style.cssText="width:100%;border-collapse:collapse;font-size:12px";
  const head=el("tr");
  for(const title of ["指標",label(h.team),label(a.team)]){
   const cell=el("th",title);cell.style.padding="9px 5px";cell.style.textAlign="left";head.append(cell);
  }
  table.append(head);
  for(const [name,key,dp] of metrics){
   const tr=el("tr");
   for(const value of [name,val(h[key],dp),val(a[key],dp)]){
    const td=el("td",value);td.style.cssText="padding:10px 5px;border-top:1px solid #344864";tr.append(td);
   }
   table.append(tr);
  }
  out.append(table);
  out.append(el("p","這是同一個 2025–26 球季的球隊歷史描述，不包含今天傷病或新賽季對戰調整。","lab-note"));
 }
 function init(d){
  if(d?.team_count!==30||!d.teams||Object.keys(d.teams).length!==30)throw Error("30隊資料不完整");
  state.teams=d.teams;state.captured=d.captured_at_utc;state.season=d.season;state.rights=d.rights_status;
  const title=el("p","進階統計來源："+d.source+"｜球季："+d.season+"｜擷取："+new Date(d.captured_at_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"})+"。目前資料再發布權限："+d.rights_status+"（待確認）。","muted");
  root.parentElement.insertBefore(title,root);
  compare.replaceChildren();
  compare.append(el("h2","上季兩隊進階數值比較"));
  const controls=el("div",undefined,"team-controls");
  for(const [id,defaultCode] of [["team-compare-home","BOS"],["team-compare-away","LAL"]]){
   const select=el("select");
   select.id=id;select.setAttribute("aria-label",id==="team-compare-home"?"選擇第一支球隊":"選擇第二支球隊");
   for(const key of Object.keys(d.teams).sort()){
    const option=el("option",label(key));option.value=key;select.append(option);
   }
   select.value=defaultCode;select.addEventListener("change",compareTeams);controls.append(select);
  }
  compare.append(controls);
  const output=el("div");output.id="team-compare-output";compare.append(output);
  input.addEventListener("input",directory);
  directory();compareTeams();
 }
 fetch("./data/season_priors.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json()}).then(init).catch(e=>{
  compare.replaceChildren();compare.append(el("p","30隊進階統計載入失敗："+e.message,"muted"));
 });
})();