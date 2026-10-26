"use strict";
(()=>{
 const $=id=>document.getElementById(id);
 const root=$("audit-metrics"),results=$("audit-results"),selector=$("audit-day"),market=$("audit-market");
 if(!root||!results||!selector||!market)return;
 const name={ATL:"老鷹",BOS:"塞爾提克",BKN:"籃網",CHA:"黃蜂",CHI:"公牛",CLE:"騎士",DAL:"獨行俠",DEN:"金塊",DET:"活塞",GS:"勇士",GSW:"勇士",HOU:"火箭",IND:"溜馬",LAC:"快艇",LAL:"湖人",MEM:"灰熊",MIA:"熱火",MIL:"公鹿",MIN:"灰狼",NO:"鵜鶘",NOP:"鵜鶘",NY:"尼克",NYK:"尼克",OKC:"雷霆",ORL:"魔術",PHI:"76人",PHX:"太陽",POR:"拓荒者",SAC:"國王",SA:"馬刺",SAS:"馬刺",TOR:"暴龍",UTAH:"爵士",UTA:"爵士",WSH:"巫師",WAS:"巫師"};
 const label=c=>(name[c]||c)+" ("+c+")";
 const el=(tag,content,cls)=>{const x=document.createElement(tag);if(content!==undefined)x.textContent=String(content);if(cls)x.className=cls;return x};
 const fmt=n=>typeof n==="number"&&Number.isFinite(n)?(n*100).toFixed(1)+"%":"—";
 const cats={moneyline:"獨贏",spread:"讓分／受讓合計",favorite_spread:"推薦讓分方",underdog_spread:"推薦受讓方",over:"推薦大分",under:"推薦小分",totals:"大小合計"};
 const mlabels={moneyline:"獨贏",spread:"讓分／受讓",over:"大分",under:"小分",total:"大小分合計"};
 const note="注意：讓分與大小是試驗模型對賽前參考線的事後核對，來源再發布權限待確認，未驗證歷史 ATS／O-U 校準；命中率並非投注績效。";
 const state={};
 function metric(label,x){
  const card=el("div",undefined,"card");
  card.append(el("div",label,"eyebrow"));
  card.append(el("div",x?.games?x.accuracy_pct.toFixed(2)+"%":"樣本不足","metric"));
  card.append(el("div",x?.games?x.correct+" 中／"+x.games+" 場":"0 場，不計命中率","muted"));
  return card;
 }
 function hitStatus(p){return p?.hit===true?"命中":p?.hit===false?"未命中":p?.hit===null?"走盤／排除":"未建立合格預測";}
 function chosenRow(row,category){
  if(category==="moneyline")return row.moneyline;
  if(category==="spread")return row.spread;
  if(category==="over")return row.total?.pick==="over"?row.total:null;
  if(category==="under")return row.total?.pick==="under"?row.total:null;
  return row.total;
 }
 function rowDisplay(row,category){
  const s=el("details",undefined,"audit-row"),preview=el("summary");
  const pick=chosenRow(row,category);
  const icon=!pick?"●":pick.hit===true?"✓":pick.hit===false?"✗":"—";
  preview.append(el("span",icon+" "+row.date_taiwan+"　"+label(row.away)+" @ "+label(row.home)+"　"+row.away_score+"－"+row.home_score,
    pick?.hit===true?"audit-good":pick?.hit===false?"audit-bad":"audit-muted"));
  s.append(preview);
  if(row.status!=="eligible"){
   s.append(el("p","排除：該場沒有提前超過 60 分鐘凍結的固定 Elo 預測。","muted"));return s;
  }
  if(!pick){s.append(el("p","此市場沒有有效研究樣本，不計算命中率。","muted"));return s}
  const hit=hitStatus(pick);
  const marketDetails=category==="moneyline"
   ?"預測勝方："+label(pick.pick==="home"?row.home:row.away)+"／主勝估計："+fmt(pick.home_probability)
   :category==="spread"
   ?"研究選擇："+(pick.pick_type==="underdog"?"受讓方":"讓分方")+"（"+label(pick.pick==="home"?row.home:row.away)+"）／相應覆蓋概率："+fmt(pick.pick==="home"?pick.p_home_cover:1-pick.p_home_cover)
   :"研究選擇："+(pick.pick==="over"?"大分":"小分")+"／相應試驗概率："+fmt(pick.pick==="over"?pick.p_over:1-pick.p_over);
  s.append(el("p",marketDetails+"。實際結果："+hit+"。","muted"));
  s.append(el("p","賽前留存時間："+new Date(row.freeze_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"})+"；已保存 GitHub 提交："+row.source_commit.slice(0,12)+"。","muted"));
  if(category!=="moneyline")s.append(el("p","參考盤口數值暫不重新展示；資料權限 "+row.market_reference_status+"。","muted"));
  return s;
 }
 function show(data){
  const day=selector.value,cat=market.value;
  const rows=data.rows.filter(row=>day==="all"||row.date_taiwan===day);
  const eligible=rows.filter(row=>row.status==="eligible");
  const stats=day==="all"?data.overall:data.by_day[day];
  root.replaceChildren();
  for(const k of ["moneyline","underdog_spread","favorite_spread","spread","over","under","totals"])
    root.append(metric(cats[k],stats[k]));
  results.replaceChildren();
  const shown=rows.filter(row=>{
    if(cat==="over")return row.status!=="eligible"||row.total?.pick==="over";
    if(cat==="under")return row.status!=="eligible"||row.total?.pick==="under";
    return true;
  });
  $("audit-count").textContent="此條件共 "+shown.length+" 場，凍結標準：開賽前逾 "+data.required_lead_minutes+" 分鐘；"+eligible.length+" 場合格。逐場展開可查看保存版本、預測方向與賽果。";
  if(!shown.length)results.append(el("p","這個條件沒有可驗證的比賽；不能宣稱準確率。","muted"));
  for(const row of shown)results.append(rowDisplay(row,cat==="total"?"total":cat));
  const expl=$("learning-status");
  expl.replaceChildren();
  expl.append(el("h2","目前是否具有自主進化 AI？"));
  expl.append(el("p","目前還沒有能自主探索、反覆訓練、時序驗證、通過門檻後安全升級的自我進化系統。","lab-note"));
  for(const [a,b] of [
   ["Elo","每次新賽果會調整球隊 Elo 分數；K=20、主場優勢65點、跨季回歸0.65等參數固定。這是分數遞推更新，不是模型自主進化。"],
   ["分差與總分","已有早期球季殘差擬合、2025–26 時序回放及實驗預測，但缺歷史經授權盤口的覆蓋率與校準，不能標成可用過盤勝率。"],
   ["LightGBM／CatBoost","私人研究儲存庫有候選模型與 CPU 合成測試；尚未以已核准真實賽前特徵連續驗證並升級到此網站。"],
   ["智慧報告","採固定規則整合近期比分、休息日、前季效率、傷病與試驗模型，並非能自行證明推論正確的語言智能。"],
   ["下一道升級門檻","先固定每場賽前資料與模型版本，建立獨立球季樣本外測試、Brier／Log Loss／校準與基準比較，再由人工審核是否換模型。"]
  ]){
    const p=el("p",undefined,"muted");p.append(el("strong",a+"："),document.createTextNode(b));expl.append(p);
  }
  expl.append(el("p",note,"lab-note"));
 }
 fetch("./data/pregame-audit.json",{cache:"no-store"})
 .then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json()})
 .then(data=>{
  if(data.schema_version!==1||data.model!=="elo_10season_chronological_fixed"||!Array.isArray(data.rows)||data.eligible_games!==19)throw Error("稽核資料與模型版本不符");
  selector.addEventListener("change",()=>show(data));
  market.addEventListener("change",()=>show(data));
  show(data);
 }).catch(error=>{
  root.replaceChildren();root.append(el("p","交叉稽核尚未載入："+error.message,"lab-note"));
  results.replaceChildren();results.append(el("p","沒有可核對的賽前快照，不顯示命中率。","muted"));
 });
})();