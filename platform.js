"use strict";
(() => {
  const aliases = {NYK:"NY",NOP:"NO",GSW:"GS",WAS:"WSH",UTA:"UTAH",SAS:"SA"};
  const canonical = t => aliases[t] || t;
  const numeric = v => v !== null && v !== undefined && v !== "" && Number.isFinite(Number(v)) ? Number(v) : null;
  const day = v => { const n = new Date(v).getTime(); return Number.isFinite(n) ? new Date(n + 8 * 3600000).toISOString().slice(0,10) : ""; };
  const validBefore = (generated, tip) => Number.isFinite(Date.parse(generated)) && Date.parse(generated) < Date.parse(tip);
  function scheduleDate(games, now=Date.now(), requested="") {
    if (/^\d{4}-\d{2}-\d{2}$/.test(requested) && day(`${requested}T12:00:00+08:00`)===requested) return requested;
    const current=day(now),pending=games.filter(g=>g.status==="in"||(g.status==="pre"&&Date.parse(g.date)>now));
    if(pending.some(g=>day(g.date)===current))return current;
    const next=pending.map(g=>day(g.date)).filter(d=>d>=current).sort()[0];return next||current;
  }
  function pregameReport(game, report, model="elo", now=Date.now()) {
    if(!["elo","factor","gbdt"].includes(model)||game.status!=="pre"||Date.parse(game.date)<=now||!report||!validBefore(report.generated_at_utc,game.date))return null;
    if(model==="factor"&&!report.factor_forecast)return null;
    if(model==="gbdt"&&!report.gbdt_forecast)return null;
    if(String(report.event_id)!==String(game.id)||canonical(report.home)!==canonical(game.home)||canonical(report.away)!==canonical(game.away))return null;
    return typeof report.report_zh==="string"&&report.report_zh.trim()?report.report_zh.trim():null;
  }
  function tally(rows, field) {
    const eligible = rows.filter(r => r.status === "eligible" && typeof r[field]?.hit === "boolean");
    return {n:eligible.length, correct:eligible.filter(r => r[field].hit).length};
  }
  function prospectiveTally(records, key) {
    const settled=records.filter(r=>r.settlement),items=settled.map(r=>key==="moneyline"?{hit:r.settlement.moneyline_hit,push:false}:r.settlement[key]).filter(Boolean);
    const decided=items.filter(x=>!x.push&&typeof x.hit==="boolean");
    return {n:decided.length,correct:decided.filter(x=>x.hit).length,push:items.filter(x=>x.push).length};
  }
  function playerForms(games, details, now = Date.now()) {
    const gm = new Map(games.filter(g => g.status === "post" && g.season_phase === 2 && Date.parse(g.date) <= now).map(g => [String(g.id),g]));
    const groups = new Map(), seen = new Set();
    for (const detail of details) {
      const game = gm.get(String(detail.event_id)); if (!game) continue;
      for (const box of detail.boxscore || []) for (const p of box.players || []) {
        const mins = typeof p.stats?.MIN === "string" && p.stats.MIN.includes(":") ? (() => {const [m,s]=p.stats.MIN.split(":").map(Number);return m+s/60;})() : numeric(p.stats?.MIN);
        if (mins === null || !Number.isFinite(mins) || mins <= 0) continue;
        const team = canonical(box.team), key = `${p.name}|${team}`, observation = `${key}|${game.id}`;
        if (seen.has(observation)) continue; seen.add(observation);
        if (!groups.has(key)) groups.set(key,{name:p.name,team,appearances:[]});
        groups.get(key).appearances.push({date:game.date,event_id:game.id,MIN:mins,PTS:numeric(p.stats?.PTS),REB:numeric(p.stats?.REB),AST:numeric(p.stats?.AST)});
      }
    }
    return [...groups.values()].map(p => {
      p.appearances.sort((a,b) => Date.parse(b.date)-Date.parse(a.date));
      const recent = p.appearances.slice(0,5), average = k => {const nums=recent.map(x=>x[k]).filter(x=>x!==null);return nums.length?nums.reduce((a,b)=>a+b,0)/nums.length:null;};
      return {...p,n:recent.length,last:recent[0].date,MIN:average("MIN"),PTS:average("PTS"),REB:average("REB"),AST:average("AST")};
    }).sort((a,b) => (b.PTS ?? -1)-(a.PTS ?? -1));
  }
  if (typeof module !== "undefined") module.exports = {canonical,numeric,day,validBefore,tally,playerForms,scheduleDate,pregameReport,prospectiveTally};
  if (typeof document === "undefined") return;
  const $ = id => document.getElementById(id);
  function el(tag, cls, text) { const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=String(text);return n; }
  function link(label, href, cls) { const n=el("a",cls,label);n.href=href;return n; }
  const team = t => window.NbaZh?.teamShort(canonical(t)) || canonical(t);
  const fullTeam = t => window.NbaZh?.team(canonical(t)) || canonical(t);
  const player = p => window.NbaZh?.player(p) || p;
  const pct = v => numeric(v) === null ? "—" : `${(Number(v)*100).toFixed(1)}%`;
  const fmt = v => numeric(v) === null ? "—" : Number(v).toFixed(1);
  const signed = v => numeric(v) === null ? "—" : `${Number(v)>0?"+":""}${Number(v)}`;
  const stamp = v => Number.isFinite(Date.parse(v)) ? new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(v)) : "時間未提供";
  const today = day(Date.now());
  const tomorrow = day(Date.now()+86400000);
  const state = {date:today,model:"elo",dataset:"teams",page:"games",files:{},failed:[],players:[]};
  function empty(target,title,body) {const n=el("div","empty");n.append(el("strong","",title),el("div","",body));target.append(n);}
  function symbol(t) {return el("span","team-symbol",canonical(t));}
  function setPage(name, updateHash=true) {
    if (!["games","results","data","platform"].includes(name)) name="games";
    state.page=name;
    document.querySelectorAll(".page").forEach(n => n.hidden=n.id!==`page-${name}`);
    document.querySelectorAll("[data-page]").forEach(n => {if(n.dataset.page===name)n.setAttribute("aria-current","page");else n.removeAttribute("aria-current");});
    if(updateHash)history.replaceState(null,"",`#${name}`);
    if(name==="games")renderGames();if(name==="results")renderResults();if(name==="data")renderData();if(name==="platform")renderPlatform();
  }
  function renderDates() {
    const target=$("schedule-dates");target.replaceChildren();
    const dates=[...new Set((state.files.games?.games||[]).map(g=>day(g.date)).filter(Boolean).concat(today))].sort();
    for(const date of dates) {
      const d=new Date(`${date}T12:00:00+08:00`),b=el("button");b.type="button";b.dataset.date=date;b.setAttribute("aria-pressed",String(date===state.date));
      const weekday=new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",weekday:"short"}).format(d);
      b.append(el("span","",date===today?"今天":date===tomorrow?"明天":weekday),el("strong","",date.slice(8)),el("span","",`${Number(date.slice(5,7))} 月`));
      b.addEventListener("click",()=>selectSchedule(date));target.append(b);
    }
    const active=target.querySelector('[aria-pressed="true"]');if(active)target.scrollLeft=Math.max(0,active.offsetLeft-target.offsetLeft-80);
  }
  function selectSchedule(date) {state.date=date;const url=new URL(location.href);url.searchParams.set("date",date);url.hash="games";history.replaceState(null,"",url);setPage("games",false);renderDates();}
  let introPlaying=false;
  function playIntro(force=false) {
    if(introPlaying)return;
    const overlay=$("brand-intro"),reduce=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // The user explicitly enters the platform; session memory must not hide it.
    // Reduced-motion visitors see the same static cover with working controls.
    overlay.classList.toggle("motion-reduced",reduce);
    const previous=document.activeElement,background=[document.querySelector(".topbar"),document.querySelector(".app-shell")];
    let finished=false;introPlaying=true;overlay.hidden=false;overlay.classList.remove("intro-leaving");background.forEach(n=>n.inert=true);document.body.classList.add("intro-active");
    const controls=[$("skip-intro"),$("enter-platform"),$("watch-intro")];
    const key=e=>{if(e.key==="Escape")finish();if(e.key==="Tab"){const index=controls.indexOf(document.activeElement);e.preventDefault();controls[(index+(e.shiftKey?-1:1)+controls.length)%controls.length].focus();}};
    const finish=()=>{if(finished)return;finished=true;document.removeEventListener("keydown",key);overlay.classList.add("intro-leaving");setTimeout(()=>{overlay.hidden=true;overlay.classList.remove("intro-leaving");background.forEach(n=>n.inert=false);document.body.classList.remove("intro-active");introPlaying=false;if(previous&&previous!==document.body)previous.focus();else $("content").focus({preventScroll:true});},220);};
    const restart=()=>{const old=overlay.querySelector(".cinema-image"),fresh=old.cloneNode(true);old.replaceWith(fresh);};
    $("skip-intro").onclick=finish;$("enter-platform").onclick=finish;$("watch-intro").onclick=restart;document.addEventListener("keydown",key);$("enter-platform").focus({preventScroll:true});restart();
  }
  function contextFor(g){return state.files["context-factors"]?.observations?.find(r=>String(r.event_id)===String(g.id||g.event_id)&&r.date===g.date&&canonical(r.home)===canonical(g.home)&&canonical(r.away)===canonical(g.away)&&validBefore(r.generated_at_utc,g.date)&&Date.parse(r.generated_at_utc)<=Date.now());}
  function contextPanel(r) {
    const box=el("details","context-panel"),head=el("summary","","陣容觀測已接入 · 尚未加權");box.append(head,el("p","context-intro","已連結傷停與近期輪替，僅供觀測及前瞻驗證；以下觀測級別不加入勝率、讓分或大小分。"));
    for(const side of ["away","home"]){const t=r.lineup[side],panel=el("section","lineup-team");panel.append(el("h4","",`${team(t.team)} · ${side==="home"?"主隊":"客隊"}`),el("p","",`有效近況 ${t.team_games} 場 · 已匹配缺陣角色分鐘合計 ${t.matched_out_role_minutes===null?"未知":fmt(t.matched_out_role_minutes)+" 分"}`));
      if(!t.snapshot_usable)panel.append(el("p","context-missing","傷停快照過期、無法核對或距開賽超過48小時，保留未知。"));
      const items=[...t.out,...t.uncertain];for(const p of items)panel.append(el("p","",`${player(p.name)} · ${injuryStatus(p.status)} · ${p.expected_minutes_proxy===null?"近期角色分鐘未知":`近期出賽角色約 ${fmt(p.expected_minutes_proxy)} 分鐘`}`));if(!items.length)panel.append(el("p","","目前可用來源未列相關紀錄；不代表全員健康。"));
      if(t.unmatched.length)panel.append(el("p","context-missing",`${t.unmatched.length} 位來源球員缺足夠近期角色紀錄，沒有視為零影響。`));panel.append(el("small","",`近期核心 ${t.observed_core_count} 人 · 非缺陣且非存疑名單 ${t.core_not_reported_out} 人（未確認可出賽） · 近72小時前五角色實際分鐘 ${fmt(t.core_minutes_72h)}`));box.append(panel);}
    const technical=r.technical;box.append(el("h4","","技術對位觀測"),el("p","",`主／客技術樣本 ${technical.home.n}／${technical.away.n} 場 · 預期回合代理 ${fmt(technical.expected_pace48_proxy)}。由 box score 近似，非官方 pace；少於3場留未知。`));
    const table=el("table","context-table"),tr=el("tr");for(const label of ["候選條件","觀測級別","套用權重"])tr.append(el("th","",label));const thead=el("thead");thead.append(tr);table.append(thead);const tbody=el("tbody");for(const f of r.factors){const line=el("tr");line.append(el("td","",f.label),el("td","",f.candidate_points===null?"未知":signed(f.candidate_points)),el("td","","0 · 未訓練"));tbody.append(line);}table.append(tbody);box.append(table,el("p","context-missing","觀測門檻為待驗證規格，沒有學得預測效果。替補能力、官方先發、完整球員能力損失仍未知。"),el("small","",`${r.context_version} · 觀測 ${stamp(r.generated_at_utc)} · 傷停擷取 ${stamp(r.lineup.injury_snapshot_at_utc)}（台北） · ${r.lineup.source||"來源未提供"}`));return box;
  }
  function factorFor(g){return state.files["factor-scorecard"]?.forecasts?.find(f=>String(f.event_id)===String(g.id)&&canonical(f.home)===canonical(g.home)&&canonical(f.away)===canonical(g.away)&&validBefore(f.generated_at_utc,g.date));}
  function factorReport(f){return {event_id:f.event_id,date:f.date,home:f.home,away:f.away,generated_at_utc:f.generated_at_utc,factor_forecast:true,report_zh:f.report_zh,markets:{spread:{home_line:f.market.home_line,away_line:f.market.home_line===null?null:-f.market.home_line,home_cover_probability_experimental:f.cover?.positive,away_cover_probability_experimental:f.cover?.negative},total:{line:f.market.total_line,expected_total:f.expected_total,over_probability_experimental:f.totals?.positive,under_probability_experimental:f.totals?.negative}},analyst:{projection:{expected_margin:f.expected_margin,expected_total:f.expected_total},market_observation:{provider:f.market.provider,captured_at_utc:f.market.captured_at_utc}},factor:f};}
  function candidateFor(g){return state.files["gbdt-candidate"]?.forecasts?.find(f=>String(f.event_id)===String(g.id)&&f.date===g.date&&canonical(f.home)===canonical(g.home)&&canonical(f.away)===canonical(g.away)&&validBefore(f.generated_at_utc,g.date)&&Date.parse(f.generated_at_utc)<=Date.now());}
  function candidateReport(f){return {...factorReport(f),factor_forecast:false,gbdt_forecast:true,factor:null,candidate:f};}
  function candidateDetails(f){
    const box=el("details","context-panel");box.append(el("summary","",f.selection.moneyline?"CPU 樹模型 · 勝負精選條件達標":"CPU 樹模型 · 全部估計／未列精選"));
    const reasons={schedule_or_results_snapshot_stale:"賽程快照超過六小時",outside_48h_publish_window:"距開賽超過48小時",major_recent_rotation_change_not_fitted:"近期主要輪替傷停未納入訓練",lineup_snapshot_unavailable:"缺少可核對的最新陣容觀測"};
    box.append(el("p","",`勝負精選門檻 ${pct(f.selection.threshold)}，由較早校準期設定；只適用勝負。讓分與大小分尚未取得歷史盤口校準，全部以實驗估計呈現。`),el("p","",`主隊淨勝的校準誤差90%參考區間 ${f.interval90.margin.map(fmt).join(" 至 ")} 分；兩隊總分 ${f.interval90.total.map(fmt).join(" 至 ")} 分。這是單場結果範圍，並非平均值的信賴區間。`));
    if(f.selection.quality_reasons.length)box.append(el("p","context-missing",f.selection.quality_reasons.map(x=>reasons[x]||x).join("；")));
    box.append(el("small","",`${f.model_version} · 輸入截至 ${stamp(f.last_input_game)} · 盤口 ${stamp(f.market.captured_at_utc)}（台北）`));
    if(f.cover?.push>0||f.totals?.push>0)box.append(el("p","",`整數盤走盤估計：讓分 ${pct(f.cover?.push)}，大小 ${pct(f.totals?.push)}；與兩側方向機率合計100%。`));return box;
  }
  function marketsFor(g) {
    if(g.status!=="pre" || Date.parse(g.date)<=Date.now())return null;
    if(state.model==="gbdt"){const f=candidateFor(g);return f?{report:candidateReport(f),probability:f.home_win_probability}:null;}
    if(state.model==="factor"){const f=factorFor(g);return f?{report:factorReport(f),probability:f.home_win_probability}:null;}
    if(state.model!=="elo")return null;
    const r=state.files.reports?.reports?.find(r=>String(r.event_id)===String(g.id) && canonical(r.home)===canonical(g.home) && canonical(r.away)===canonical(g.away) && validBefore(r.generated_at_utc,g.date));
    const pred=state.files.research?.predictions?.find(p=>String(p.event_id)===String(g.id) && validBefore(state.files.research.updated_at_utc,g.date));
    return r||pred?{report:r,probability:numeric(pred?.home_win_probability) ?? numeric(r?.markets?.moneyline?.home_probability_experimental)}:null;
  }
  function predictionCells(g) {
    const m=marketsFor(g),cells=[];
    if(!m)return null;
    const probability=m.probability,spread=m.report?.markets?.spread,total=m.report?.markets?.total;
    if(probability!==null)cells.push(["勝負",team(probability>=.5?g.home:g.away),pct(probability>=.5?probability:1-probability)]);else cells.push(["勝負","未提供","—"]);
    const cover=numeric(spread?.home_cover_probability_experimental);
    const awayCover=numeric(spread?.away_cover_probability_experimental);
    if(cover!==null && numeric(spread?.home_line)!==null) {const home=awayCover===null?cover>=.5:cover>=awayCover;cells.push(["讓分／受讓",`${team(home?g.home:g.away)} ${signed(home?spread.home_line:spread.away_line)}`,pct(home?cover:awayCover)]);}else {const margin=m.report?.analyst?.projection?.expected_margin;cells.push(["讓分／受讓",numeric(margin)===null?"盤口未齊":`主淨勝 ${signed(Number(margin).toFixed(1))}`,"模型估計・待盤口"]);}
    const over=numeric(total?.over_probability_experimental);
    const under=numeric(total?.under_probability_experimental);
    if(over!==null && numeric(total?.line)!==null){const pickOver=under===null?over>=.5:over>=under;cells.push(["大小分",`${pickOver?"大":"小"} ${total.line}`,pct(pickOver?over:under)]);}else {const expected=m.report?.analyst?.projection?.expected_total;cells.push(["大小分",numeric(expected)===null?"盤口未齊":`估 ${fmt(expected)} 分`,"模型估計・待盤口"]);}
    return cells;
  }
  function renderGames() {
    const target=$("game-list");target.replaceChildren();
    const games=(state.files.games?.games||[]).filter(g=>day(g.date)===state.date).sort((a,b)=>Date.parse(a.date)-Date.parse(b.date));
    $("game-count").textContent=`${games.length} 場比賽`;
    $("schedule-title").textContent=state.date===tomorrow?"明日預測":state.date===today?"今日賽事":`${state.date.slice(5).replace("-"," / ")} 賽事預測`;
    $("selected-date-context").textContent=`${state.date} · 台北時間 UTC+8 · ${games.length} 場${state.date===tomorrow?"，各場附中文賽前報告":""}`;
    $("go-tomorrow").setAttribute("aria-pressed",String(state.date===tomorrow));
    $("model-context").textContent=state.model==="gbdt"?"CPU 樹模型候選：以 Elo 為基準學習修正，勝負、分差、總分各自訓練及校準。保留全部估計，另標示預先設定的勝負精選；真正發布後的成績獨立累積，尚未取代 Elo。":state.model==="factor"?"計分實驗已跑歷史實測。分數以主隊／大分為正；每場重新計算，未知項目另列。改善幅度很小且信賴區間包含零，尚未取代 Elo。":state.model==="elo"?"Elo 勝率與比分推估供研究參考；讓分、大小分機率尚未完成盤口校準。無盤口時只列模型淨勝／總分估計，不捏造過盤方向。":state.model==="apex"?"APEX v2.1 已整合至私人研究流程，尚無獲准公開的真實賽前預測；目前不顯示候補模型的模擬數字。":"Elo × APEX 融合已完成研究實作，仍在累積有效賽前紀錄，尚未成為公開主模型。";
    const quoted=games.filter(g=>{const m=state.files.reports?.reports?.find(r=>String(r.event_id)===String(g.id));return numeric(m?.markets?.spread?.home_line)!==null&&numeric(m?.markets?.total?.line)!==null;}).length;
    $("market-availability").textContent=`本日 ${games.length} 場 · ${quoted} 場已取得讓分與總分線 · ${games.length-quoted} 場待來源報價。模型估計與實際盤口分開顯示。`;
    if(!games.length)empty(target,"這一天沒有可用賽程","可切換其他日期；缺少資料不代表當天一定沒有比賽。");
    for(const g of games) {
      const card=el("article","game-card"),top=el("div","game-top");
      const time=new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(g.date));
      const status=g.status==="post"?"已完賽":g.status==="in"?"進行中":Date.parse(g.date)<=Date.now()?"待來源更新":"未開賽";
      top.append(el("span","",`${g.season_phase===1?"熱身賽":"NBA"} · ${time}`),el("span",`status-chip ${g.status==="in"?"live":""}`,status));
      const match=el("div","matchup");
      for(const [i,t] of [g.away,g.home].entries()) {
        const tm=el("div");tm.append(symbol(t),el("strong","team-name",team(t)),el("div","team-role",i===0?"客場":"主場"));match.append(tm);
        if(i===0){const score=el("div",g.status==="pre"?"vs":"match-score",g.status==="pre"?"VS":`${g.away_score ?? "—"} : ${g.home_score ?? "—"}`);if(g.status!=="pre")score.append(el("small","",g.status==="post"?"FINAL":"LIVE"));match.append(score);}
      }
      card.append(top,match);
      const cells=predictionCells(g);
      if(cells){const grid=el("div","market-grid");for(const [label,pick,p] of cells){const c=el("div","market-cell");c.append(el("span","",label),el("strong","",pick),el("em","",p));grid.append(c);}card.append(grid);}
      else card.append(el("div","model-unavailable",g.status==="post"?"賽事已結束 · 當時預測請至「預測成績」查核封存紀錄。":g.status==="in"?"比賽進行中 · 不新增賽前預測。":state.model==="elo"?"尚無符合時序的公開預測。":"此模型尚無可公開的賽前預測。"));
      const report=marketsFor(g)?.report,brief=pregameReport(g,report,state.model);
      if(brief){const n=el("section","game-brief"),head=el("div","brief-heading");head.append(el("h3","","中文賽前報告"),el("span","",`${[...brief].length} 字 · ${state.model==="factor"?"計分實驗":state.model==="gbdt"?"CPU 樹模型":"Elo"}`));n.append(head,el("p","",brief),el("div","brief-source",`產生 ${stamp(report.generated_at_utc)}（台北） · 以公開資料摘要，非已驗證投注績效`));card.append(n);}
      if(state.model==="factor"&&report?.factor)card.append(factorBreakdown(report.factor));
      if(report?.candidate)card.append(candidateDetails(report.candidate));
      const context=contextFor(g);if(context&&["elo","factor","gbdt"].includes(state.model)&&g.status==="pre"&&Date.parse(g.date)>Date.now())card.append(contextPanel(context));
      const bottom=el("div","card-bottom");bottom.append(el("span","",g.venue||"場館待提供"));const open=el("button","text-button","單場分析 ↗");open.addEventListener("click",()=>openGame(g));bottom.append(open);card.append(bottom);target.append(card);
    }
    const updated=state.files.games?.captured_at;$("game-source").textContent=`來源：ESPN 公開賽事資料 · 擷取 ${stamp(updated)}（台北）${Date.now()-Date.parse(updated)>86400000?" · 資料超過 24 小時，請核對最新狀態":""}`;
  }
  function metricCard(label,number,note) {const n=el("div","metric-card");n.append(el("span","",label),el("div","metric-number",number),el("p","",note));return n;}
  function setupResults() {
    const audit=state.files["pregame-audit"],sel=$("result-day");sel.replaceChildren();
    const option=(v,label)=>{const o=el("option","",label);o.value=v;sel.append(o);};option("all","全部公開封存日");
    const days=[...new Set((audit?.rows||[]).map(r=>r.date_taiwan).concat((state.files["factor-pregame-ledger"]?.records||[]).map(r=>day(r.date)),(state.files["gbdt-pregame-ledger"]?.records||[]).map(r=>day(r.date)),today))].sort().reverse();for(const d of days)option(d,`${d}${d===today?"（今天）":""}`);
    $("audit-scope").textContent=audit?`目前公開逐場核對涵蓋 ${audit.report_period_taiwan.join(" 至 ")}。${today} 的最新私人核對尚未完整同步至此頁。讓分與大小分的盤口來源未驗證，以下為研究方向核對。` : "封存資料暫時無法讀取，未顯示成績。";
  }
  function factorBreakdown(f) {
    const box=el("details","factor-breakdown"),summary=el("summary","","逐項加減分 · 查看依據");box.append(summary);
    const totals=el("div","factor-totals");for(const [key,label]of [["moneyline","勝負"],["margin","分差"],["total","總分"]]){const part=f.scores[key],n=el("div");n.append(el("span","",label),el("strong","",`${signed(part.score)} 分`),el("small","",`${part.known}/${part.possible} 項可確認`));totals.append(n);}box.append(totals);
    for(const [key,label]of [["moneyline","勝負"],["margin","分差"],["total","總分"]]){box.append(el("h4","",label));for(const part of f.scores[key].parts){const line=el("div","factor-line");line.append(el("span","",part.label),el("strong",part.points===null?"quiet":"",part.points===null?"未確認":`${signed(part.points)} 分`));box.append(line);}}
    box.append(el("p","",`正分支持主隊／大分，負分支持客隊／小分。零權重表示訓練未選用；未知項目不當成已確認的零。休息與密集賽程合計最多 ±2 分。分數每場重置，不跨場累加。`),el("small","",`${f.model_version} · 輸入截至 ${stamp(f.last_input_game)} · 盤口擷取 ${stamp(f.market.captured_at_utc)}`));
    if(f.cover?.push>0||f.totals?.push>0)box.append(el("p","",`整數盤走盤機率：讓分 ${pct(f.cover?.push)}，總分 ${pct(f.totals?.push)}。主客／大小機率與走盤合計為 100%。`));return box;
  }
  function developmentPanel(model,d) {
    const box=el("details","disclosure");box.append(el("summary","",model==="gbdt"?"歷史開發回測 · 非真實賽前成績":"歷史因子測試與舊盤口重播 · 非真實賽前成績"));
    if(model==="gbdt"){
      const v=d.historical_validation,m=v.metrics,c=m.candidate,b=m.calibrated_baseline,ci=v.improvement_ci95_by_day,selected=v.selection;
      box.append(el("p","",`2019–2023賽季結束年訓練 ${v.train_n} 場；2024選規格 ${v.validation_n} 場；2025校準 ${v.calibration_n} 場；2026測試 ${v.test_n} 場。2026曾用於先前研究，不能視為全新外部驗證。`));
      const table=el("table","context-table"),body=el("tbody");for(const values of [["項目","候選","同條件校準基準"],["勝負",`${c.moneyline.correct}/${c.moneyline.n}`,`${b.moneyline.correct}/${b.moneyline.n}`],["勝率 Brier",c.moneyline.brier.toFixed(5),b.moneyline.brier.toFixed(5)],["分差 MAE",fmt(c.margin.mae),fmt(b.margin.mae)],["總分 MAE",fmt(c.total.mae),fmt(b.total.mae)]]){const tr=el("tr");for(const value of values)tr.append(el("td","",value));body.append(tr);}table.append(body);box.append(table);
      box.append(el("p","",`改善的95%比賽日重抽樣區間：Brier ${ci.moneyline.map(x=>x.toFixed(5)).join(" 至 ")}；分差 ${ci.margin.map(x=>x.toFixed(3)).join(" 至 ")} 分；總分 ${ci.total.map(x=>x.toFixed(3)).join(" 至 ")} 分。正數代表候選誤差較小。`),el("p","",`較早校準期預設約40%覆蓋，實際測試 ${pct(selected.actual_test_coverage)}（${selected.n}場）。這個相同子集的獨贏：候選 ${selected.same_subset_metrics.candidate.moneyline.correct}/${selected.n}，校準基準 ${selected.same_subset_metrics.calibrated_baseline.moneyline.correct}/${selected.n}。精選命中率不能代表全部場次。`),el("p","","基準為同一 Elo／比分基準另行校準，並使用完全相同測試場次；歷史沒有可比對的完整即時盤口，不宣稱超越市場或其他平台。"));
    }else{
      const v=d.validation,m=v.metrics,r=d.odds_replay.summary;
      box.append(el("p","",`歷史 ${v.test_n} 場：勝負 ${m.moneyline.candidate.correct}/${m.moneyline.candidate.n}，基準 ${m.moneyline.baseline.correct}；分差 MAE ${fmt(m.margin.candidate.mae)}，總分 MAE ${fmt(m.total.candidate.mae)}。三項改善區間皆跨零，尚未證明穩定優勢。`),el("p","",`真實舊盤口重新計算：讓分 ${r.spread.correct}/${r.spread.n}（基準 ${r.spread.baseline_correct}）；大小 ${r.total.correct}/${r.total.n}（基準 ${r.total.baseline_correct}）。這是賽後重播，不計入上方成績。`));
    }
    box.append(link("完整方法與限制 ↗",`https://github.com/leonlin047/nba-paper-lab-web/blob/main/docs/${model==="gbdt"?"CPU_CANDIDATE_RELEASE":"FACTOR_SCORECARD_RELEASE"}.md`,"audit-link"));return box;
  }
  function renderProspectiveResults(target,metrics,model,date,market) {
    const candidate=model==="gbdt",d=state.files[candidate?"gbdt-candidate":"factor-scorecard"],name=candidate?"CPU 樹模型候選":"計分因子";
    if(!d){empty(target,"模型資料暫時無法讀取","請重新整理後再查閱。");return;}
    let records=state.files[candidate?"gbdt-pregame-ledger":"factor-pregame-ledger"]?.records||[];
    if(!candidate)records=records.filter(r=>r.model_version===d.model_version);
    records=records.filter(r=>date==="all"||day(r.date)===date).sort((a,b)=>Date.parse(b.date)-Date.parse(a.date));
    for(const [key,label]of [["moneyline","勝負"],["spread","讓分／受讓"],["total","大小分"]]){const t=prospectiveTally(records,key);metrics.append(metricCard(label,t.n?`${t.correct} / ${t.n}`:"—",t.n?`方向相符 ${pct(t.correct/t.n)}${t.push?` · 走盤${t.push}場另計`:""}`:`尚無已結算有效結果${t.push?` · 走盤${t.push}場`:""}`));}
    $("result-count").textContent=`${name} · ${records.length} 場首次封存 · ${records.filter(r=>r.settlement).length} 場已結算`;
    if(candidate){const rows=records.filter(r=>r.settlement),selected=rows.filter(r=>r.selection.moneyline),n=prospectiveTally(selected,"moneyline"),paired=rows.filter(r=>r.settlement.market_brier!==null&&numeric(r.settlement.market_brier)!==null),note=el("div","notice");const average=field=>paired.reduce((sum,r)=>sum+r.settlement[field],0)/paired.length;
      note.append(el("strong","","全部預測與勝負精選分開核對"),el("p","",`本次範圍勝負精選已結算 ${n.n} 場${n.n?`，相符 ${n.correct}/${n.n}`:"，尚無命中率"}。精選不套用至讓分與大小分。各場使用當時版本，不因更新重複計場。`),el("p","",paired.length?`同場賽前市場基準 ${paired.length} 場：候選 Brier ${average("brier").toFixed(5)}，去水市場 Brier ${average("market_brier").toFixed(5)}；越低越好。來源擷取時間保留在首次封存。`:"尚無已結算且有同場去水市場機率的可比樣本，不能宣稱勝過市場。"));target.append(note);}
    if(!records.length)empty(target,"此範圍尚無首次封存紀錄","只收開賽前1至24小時真正產生的預測，沒有用賽後回測補足成績。");
    for(const r of records){const outcome=r.settlement,card=el("article","result-row"),heading=el("div","result-title");heading.append(el("span","",`${team(r.away)} @ ${team(r.home)}`),el("time","",day(r.date)));card.append(heading);
      const picks=el("div","result-picks");for(const [key,label]of [["moneyline","勝負"],["spread","讓分／受讓"],["total","大小分"]].filter(([k])=>market==="all"||market===k)){
        const probs=key==="spread"?r.cover:r.totals,positive=probs?.positive>=probs?.negative;let pick=key==="moneyline"?`${team(r.home_win_probability>=.5?r.home:r.away)} ${pct(Math.max(r.home_win_probability,1-r.home_win_probability))}`:!probs?"待實際盤口":key==="spread"?`${team(positive?r.home:r.away)} ${signed(positive?r.market.home_line:-r.market.home_line)}`:`${positive?"大":"小"} ${r.market.total_line}`;
        const hit=key==="moneyline"?outcome?.moneyline_hit:outcome?.[key]?.hit,push=outcome?.[key]?.push,n=el("div");n.append(el("span","",label),el("strong","",pick),el("div",push?"quiet":hit===true?"hit":hit===false?"miss":"quiet",!outcome?"待完賽":push?"走盤":hit===true?"✓ 相符":hit===false?"× 未符":"無有效盤口"));picks.append(n);
      }card.append(picks);if(outcome)card.append(el("p","context-note",`實際主隊淨勝 ${signed(outcome.actual_margin)} · 合計 ${outcome.actual_total} 分`));
      card.append(el("p","result-proof",`首次封存 ${stamp(r.frozen_at_utc)} · ${r.model_version}${candidate?` · ${r.selection.moneyline?"勝負精選":"全部估計"}`:""}`));target.append(card);
    }
    target.append(developmentPanel(model,d),link("原始首次封存與結算 JSON ↗",`./data/${candidate?"gbdt":"factor"}-pregame-ledger.json`,"audit-link"));
  }
  function renderResults() {
    const target=$("result-list"),metrics=$("result-metrics");target.replaceChildren();metrics.replaceChildren();
    const model=$("result-model").value,date=$("result-day").value,market=$("result-market").value;
    const experimental=["factor","gbdt"].includes(model);$("result-day").disabled=false;$("result-market").disabled=false;
    $("audit-scope").textContent=experimental?"以下只統計真正賽前首次封存，按日期分列勝負、讓分與大小分；待賽不計入分母，走盤另列。歷史回測在下方另行展開。盤口來源與商業使用權仍待確認。":"Elo 為既有公開封存核對；讓分與大小分的盤口來源未驗證，只作研究方向核對。";
    if(experimental){renderProspectiveResults(target,metrics,model,date,market);return;}
    const rows=model==="elo"?(state.files["pregame-audit"]?.rows||[]).filter(r=>date==="all"||r.date_taiwan===date):[];
    const definitions=[["moneyline","勝負"],["spread","讓分／受讓"],["total","大小分"]];
    for(const [key,label]of definitions){const t=tally(rows,key),c=metricCard(label,t.n?`${t.correct} / ${t.n}`:"—",t.n?`方向命中 ${(t.correct/t.n*100).toFixed(1)}%${key==="moneyline"?"":" · 盤口來源未驗證"}`:"尚無有效封存結果");metrics.append(c);}
    $("result-count").textContent=`${rows.filter(r=>r.status==="eligible").length} 場符合封存條件`;
    if(!rows.length)empty(target,"尚無可公開核對的逐場紀錄",model==="elo"?"此日期尚無完整公開封存資料，不能以當前模型重跑補成賽前成績。":"此模型尚無可公開驗證的真實賽前結果；歷史回測另存於研究紀錄。");
    for(const r of rows) {
      const card=el("article","result-row"),heading=el("div","result-title");heading.append(el("span","",`${team(r.away)} ${r.away_score ?? "—"} : ${r.home_score ?? "—"} ${team(r.home)}`),el("time","",r.date_taiwan));card.append(heading);
      if(r.status!=="eligible")card.append(el("p","context-note","排除：沒有符合規則的賽前封存，未納入命中率。"));
      else {const picks=el("div","result-picks");for(const [key,label] of definitions.filter(([key])=>market==="all"||key===market)){const p=r[key],n=el("div");let pick="未提供";if(p)pick=key==="total"?(p.pick==="over"?"大分":"小分"):team(p.pick==="home"?r.home:r.away);const outcome=p?.hit===true?"✓ 相符":p?.hit===false?"× 未符":"— 待核對";n.append(el("span","",label),el("strong","",pick),el("div",p?.hit===true?"hit":p?.hit===false?"miss":"quiet",outcome));picks.append(n);}card.append(picks);}
      const proof=el("div","result-proof",r.freeze_utc?`封存 ${stamp(r.freeze_utc)}（台北） · `:"無可驗證封存 · ");
      if(/^[0-9a-f]{40}$/.test(r.source_commit||""))proof.append(link(`來源 ${r.source_commit.slice(0,7)} ↗`,`https://github.com/leonlin047/nba-paper-lab-web/commit/${r.source_commit}`));
      card.append(proof);target.append(card);
    }
  }
  const teams=["ATL","BKN","BOS","CHA","CHI","CLE","DAL","DEN","DET","GS","HOU","IND","LAC","LAL","MEM","MIA","MIL","MIN","NO","NY","OKC","ORL","PHI","PHX","POR","SAC","SA","TOR","UTAH","WSH"];
  function recentTeam(t) {return (state.files.games?.games||[]).filter(g=>g.status==="post"&&g.season_phase===2&&[canonical(g.home),canonical(g.away)].includes(canonical(t))&&Date.parse(g.date)<=Date.now()).sort((a,b)=>Date.parse(b.date)-Date.parse(a.date)).slice(0,5);}
  function injuryStatus(v) {return ({Out:"缺陣","Day-To-Day":"每日觀察",Questionable:"出賽存疑",Doubtful:"出賽機會低",Probable:"可能出賽"})[v]||v||"未提供";}
  function injuryCard(i) {const n=el("div","injury-card"),h=el("h3");h.append(el("span","",player(i.player)),el("span","injury-label",injuryStatus(i.status)));n.append(h,el("p","",`${fullTeam(i.team)} · ${[i.type,i.detail].filter(Boolean).join(" / ")||"原因未提供"}`),el("p","",`來源紀錄 ${stamp(i.date)} · 預估回歸 ${i.return_date||"未提供"}`));return n;}
  function renderData() {
    const target=$("data-list"),q=$("data-search").value.trim().toLowerCase(),match=(...v)=>v.some(x=>String(x||"").toLowerCase().includes(q));target.replaceChildren();
    if(state.dataset==="teams") {
      $("data-context").textContent="30 支球隊 · 近況僅取目前資料中最近 5 場例行賽；並非完整賽季排名。點選球隊查看近況與傷停。";
      const grid=el("div","team-grid");for(const t of teams.filter(t=>match(t,team(t),fullTeam(t)))){const g=recentTeam(t),wins=g.filter(g=>canonical(g.home)===t?g.home_score>g.away_score:g.away_score>g.home_score).length,b=el("button","team-card");b.append(symbol(t),el("h3","",fullTeam(t)),el("p","",g.length?`近 ${g.length} 場 · ${wins} 勝 ${g.length-wins} 敗`:"目前無可用例行賽近況"));b.addEventListener("click",()=>openTeam(t));grid.append(b);}target.append(grid);if(!grid.children.length)empty(target,"找不到這支球隊","可使用中文名稱或英文縮寫搜尋。");
    } else if(state.dataset==="players") {
      $("data-context").textContent="最近最多 5 次例行賽出賽的場均數據；僅涵蓋已收錄公開 box score，不等於完整聯盟名單。缺值保留空白，DNP 不視為當前傷停。";
      const ps=state.players.filter(p=>match(p.name,player(p.name),p.team,fullTeam(p.team)));
      if(!ps.length)empty(target,"沒有符合的球員紀錄","目前收錄範圍內尚無該球員的有效出賽資料。");
      else {const wrap=el("div","table-wrap"),table=el("table","data-table"),head=el("thead"),tr=el("tr");for(const t of ["球員 / 球隊","場次","分鐘","得分","籃板","助攻","最近出賽"])tr.append(el("th","",t));head.append(tr);table.append(head);const body=el("tbody");for(const p of ps){const r=el("tr"),name=el("td","",player(p.name));name.append(el("small","",`${fullTeam(p.team)} · ${p.name}`));r.append(name);for(const value of [p.n,fmt(p.MIN),fmt(p.PTS),fmt(p.REB),fmt(p.AST),day(p.last)])r.append(el("td","",value));body.append(r);}table.append(body);wrap.append(table);target.append(wrap);}
    } else {
      $("data-context").textContent="ESPN 公開傷停紀錄 · 狀態依來源公告，未列名不代表健康；預估回歸日期可能變動。";
      const injuries=(state.files.injuries?.injuries||[]).filter(i=>match(i.player,player(i.player),i.team,fullTeam(i.team)));
      const grid=el("div","injury-grid");for(const i of injuries)grid.append(injuryCard(i));target.append(grid);if(!injuries.length)empty(target,"沒有符合的傷停紀錄","未查到公告不代表球員確定健康。");
    }
    $("data-source").textContent=`${state.dataset==="injuries"?"ESPN 傷停":"ESPN 賽事與球員 box score"} · 擷取 ${stamp(state.dataset==="injuries"?state.files.injuries?.captured_at:state.files.games?.captured_at)}（台北） · 資料限內測研究，商業使用權待確認`;
  }
  function openDialog(content) {$("dialog-content").replaceChildren(...content);$("game-dialog").showModal();}
  function openTeam(t) {
    const title=el("h2","",fullTeam(t));title.id="dialog-title";const recent=recentTeam(t),content=[title,el("p","subtitle","資料中最近 5 場例行賽 · 不含熱身賽")];
    const list=el("div");for(const g of recent)list.append(el("p","dialog-subtitle",`${day(g.date)} · ${team(g.away)} ${g.away_score} : ${g.home_score} ${team(g.home)}`));if(!recent.length)empty(list,"尚無可用近況","等待資料累積。");content.push(list,el("h3","","球隊傷停"));
    const injuries=(state.files.injuries?.injuries||[]).filter(i=>canonical(i.team)===canonical(t));if(injuries.length)for(const i of injuries)content.push(injuryCard(i));else content.push(el("p","dialog-subtitle","目前公開檔未收錄此隊傷停；不代表全員健康。"));openDialog(content);
  }
  function openGame(g) {
    const title=el("h2","",`${team(g.away)} vs ${team(g.home)}`);title.id="dialog-title";
    const content=[title,el("p","subtitle",`${stamp(g.date)}（台北） · ${g.venue||"場館未提供"}`)],cells=predictionCells(g),report=marketsFor(g)?.report;
    if(cells){const grid=el("div","metric-grid");for(const [label,pick,p]of cells)grid.append(metricCard(label,pick,p));content.push(grid,el("p","dialog-subtitle",`${state.model==="factor"?"計分實驗":state.model==="gbdt"?"CPU 樹模型":"Elo"} 研究輸出 · 產生 ${stamp(report?.generated_at_utc||state.files.research?.updated_at_utc)} · 盤口 ${report?.analyst?.market_observation?.provider||"來源未提供"} / ${stamp(report?.analyst?.market_observation?.captured_at_utc)}`));}
    else content.push(el("p","context-note",g.status==="post"?"已完賽。不使用賽後重算填入當時預測；請在預測成績頁查核已封存場次。":"此模型目前沒有符合時序的公開賽前預測。"));
    const brief=pregameReport(g,report,state.model);if(brief){const n=el("section","panel match-report");n.append(el("h3","",`中文賽前報告 · ${[...brief].length} 字`),el("p","",brief));content.push(n);}
    if(report?.factor)content.push(factorBreakdown(report.factor));
    if(report?.candidate)content.push(candidateDetails(report.candidate));
    const context=contextFor(g);if(context&&["elo","factor","gbdt"].includes(state.model)&&g.status==="pre"&&Date.parse(g.date)>Date.now())content.push(contextPanel(context));
    const analysis=el("div","game-analysis");for(const t of [g.away,g.home]){const n=el("div"),form=report?.analyst?.form?.[canonical(t)===canonical(g.home)?"home":"away"],recent=recentTeam(t);n.append(el("h3","",fullTeam(t)));if(form?.n)n.append(el("p","",`賽前近況樣本 ${form.n} 場`),el("p","",`場均得分 ${fmt(form.avg_scored)} / 失分 ${fmt(form.avg_allowed)}`),el("p","",`近 5 場 ${form.last5_wins ?? "—"} 勝 · 休息 ${fmt(form.rest_days)} 天`));else n.append(el("p","",`目前資料中 ${recent.length} 場例行賽近況`));analysis.append(n);}content.push(el("h3","","球隊近況"),analysis,el("h3","","相關傷停"));
    const injuries=(state.files.injuries?.injuries||[]).filter(i=>[canonical(g.home),canonical(g.away)].includes(canonical(i.team)));if(injuries.length)for(const i of injuries)content.push(injuryCard(i));else content.push(el("p","dialog-subtitle","目前未收錄相關傷停公告，不代表全員健康。"));
    const detail=state.files.games?.details?.find(d=>String(d.event_id)===String(g.id));if(detail?.boxscore?.length){content.push(el("h3","","單場球員數據"));for(const b of detail.boxscore){const panel=el("div","panel");panel.append(el("h3","",fullTeam(b.team)));for(const p of b.players||[])panel.append(el("div","",`${player(p.name)} · ${p.stats?.MIN ?? "—"} 分鐘 / ${p.stats?.PTS ?? "—"} 分 / ${p.stats?.REB ?? "—"} 籃板 / ${p.stats?.AST ?? "—"} 助攻`));content.push(panel);}}
    content.push(el("p","dialog-subtitle","球隊近況為描述性資料。傷停與球員因子尚未加入公開模型權重，不代表已量化其因果影響。"));openDialog(content);
  }
  function renderCandidateOverview(){const target=$("gbdt-overview"),d=state.files["gbdt-candidate"];target.replaceChildren();target.append(el("h3","","CPU 樹模型 · 候選實測"));if(!d){target.append(el("p","","首次排程驗證後提供模型與預測資料。"));return;}
    const v=d.historical_validation,c=v.metrics.candidate,b=v.metrics.calibrated_baseline;target.append(el("p","",`LightGBM CPU，獨贏、分差、總分分開學習，使用分離時段校準。歷史開發 ${v.test_n} 場，獨贏 ${c.moneyline.correct}/${v.test_n}，同條件校準基準 ${b.moneyline.correct}/${v.test_n}。獨贏改善區間跨零，維持候選狀態。`),el("p","",`真正賽前已首次封存 ${d.prospective.frozen} 場，已結算 ${d.prospective.settled} 場。模型每週有新賽果才重訓；同週沿用快取，本次舊樣本重訓 ${d.cache.old_rows_refit} 場。程式或既有資料更正會重新驗證。無需 GPU，分析不逐場呼叫語言模型。`),el("p","","陣容與技術觀測仍未學得跨季權重；歷史盤口特徵也未加入。每場保留預測時間、版本與當時可用市場機率，尚不自動取代 Elo。"),link("方法、實測與限制 ↗","https://github.com/leonlin047/nba-paper-lab-web/blob/main/docs/CPU_CANDIDATE_RELEASE.md","audit-link"),el("p","source-line",`${d.model_version} · ${stamp(d.generated_at_utc)}（台北）`));}
  function renderPlatform() {
    renderCandidateOverview();
    const factor=state.files["factor-scorecard"],overview=$("factor-overview");overview.replaceChildren();overview.append(el("h3","","計分因子 · 已實測並開啟前瞻封存"));if(factor){const v=factor.validation;overview.append(el("p","",`已完成 ${v.test_n} 場歷史測試，以及 ${factor.odds_replay.rows.length} 場真實舊盤口重播。勝負與分差各 4 項、總分 3 項候選因子；整數權重限定 −2 至 +2，未知項目獨立標示。休息與賽程密度合計最多兩分。`),el("p","",`小幅改善仍在統計誤差內，維持實驗模型。當前 ${factor.prospective.frozen_current_model} 場真正賽前封存、${factor.prospective.settled} 場已結算。舊資料未變時直接沿用訓練快取，本次舊樣本重訓 ${factor.cache.old_samples_refit} 場；時序完整性仍會檢查。`),el("p","source-line",`${factor.model_version} · ${stamp(factor.generated_at_utc)}（台北）`));}else overview.append(el("p","","計分資料暫時無法讀取。"));
    const ctx=state.files["context-factors"],ctxPanel=$("context-overview");ctxPanel.replaceChildren();ctxPanel.append(el("h3","","陣容與技術對位 · 觀測已接入，預測權重尚未啟用"));if(ctx){ctxPanel.append(el("p","",`已增量保存 ${ctx.ingestion.cached_events} 場球員與技術細節，${ctx.coverage.technical_matchups}/${ctx.coverage.future_games} 場未來對戰具有雙方各至少3場技術樣本。傷停快照按內容去重，共 ${ctx.coverage.distinct_injury_snapshots} 個不同版本。`),el("p","",`近期角色缺陣、上場負荷、投籃／失誤／籃板對位、節奏與三分依賴已產生逐場觀測。${ctx.prospective.frozen} 場觀測已在開賽前1至24小時首次封存，${ctx.prospective.settled} 場附上賽果；這些不是新模型命中率。`),el("p","","目前沒有跨季歷史傷停與陣容資料可擬合、外測，所以所有新增權重保持0。替補能力與官方先發仍未知；不會憑球星名氣自行扣分。"),link("陣容觀測實作與限制 ↗","https://github.com/leonlin047/nba-paper-lab-web/blob/main/docs/LINEUP_CONTEXT_RELEASE.md","audit-link"));}else ctxPanel.append(el("p","","陣容觀測暫時無法讀取。"));
    const s=state.files["integration-status"],target=$("model-status");target.replaceChildren();if(!s){empty(target,"狀態暫時無法讀取","未以過期模型狀態代替最新紀錄。");return;}
    const defs=[["Elo","公開研究主模型",`${s.models.elo.frozen} 場私人賽前封存，${s.models.elo.labeled} 場已連結賽果。公開預測依原賽事資料流程更新。`],["APEX v2.1","候補模型 · 累積證據",`有效賽前核對 ${s.models.apex.evaluated} / ${s.models.apex.minimum} 場；尚無獲准公開的真實賽前預測。`],["Elo × APEX","融合研究已實作","使用一致的機率融合與歷史資料選權重；目前仍為候補，尚未證明優於 Elo。"],["增量學習","只學習新樣本",`已學習 ${s.models.online.trained} / ${s.models.online.minimum} 場；本次舊樣本重訓 ${s.models.online.old_pairs_retrained} 場。樣本足夠前不發布預測。`]];
    for(const [name,label,text]of defs){const n=el("div","model-card");n.append(el("span","model-label",label),el("h3","",name),el("p","",text));if(name==="增量學習"){const bar=el("div","progress"),fill=el("div");fill.style.width=`${Math.min(100,s.models.online.trained/s.models.online.minimum*100)}%`;bar.append(fill);n.append(bar);}target.append(n);}
    const panel=$("integration-summary");panel.replaceChildren();const stats=el("div","compact-stats");for(const [v,label]of [[s.factors.player_rows,"球員單場觀測"],[s.factors.injury_rows,"官方傷停／涵蓋紀錄"],[s.factors.form_groups,"球員與球隊近況群組"]]){const n=el("div");n.append(el("strong","",v.toLocaleString()),el("span","",label));stats.append(n);}panel.append(stats,el("p","","上述數量是私人資料收集的彙總，不等於公開頁面上的球員數。新球員因子已接入收集層，尚未加入模型權重；公開球員頁使用現有公開 box score。"),el("p","","已啟用增量學習與未變資料的評估快取；舊證據仍做必要完整性檢查，避免重複學習同一場比賽。數值流程使用 CPU，無需你的手機或電腦持續開機，也不逐筆呼叫付費語言模型。既有託管平台用量仍受其免費額度限制。"));
    const more=link("私人完整核對報告（需 GitHub 權限） ↗",s.private_report_url,"audit-link");panel.append(more,el("p","source-line",`目前報告下載檔預計 ${s.private_report_expires} 到期；這是具期限的私人報告入口，公開站不提供會員登入。`));
    const stale=Date.now()-Date.parse(s.as_of_utc)>86400000;$("platform-asof").textContent=`模型／整合彙總 ${stamp(s.as_of_utc)}（台北） · 人工確認快照，非私人資料即時同步${stale?" · 已超過 24 小時，需重新核對":""}`;$("platform-asof").classList.toggle("stale",stale);
  }
  async function init() {
    $("today-label").textContent=today.replaceAll("-"," / ");
    const names=["games","research","reports","pregame-audit","injuries","integration-status","factor-scorecard","factor-pregame-ledger","context-factors","gbdt-candidate","gbdt-pregame-ledger"];
    const outcomes=await Promise.allSettled(names.map(async name=>{const r=await fetch(`./data/${name}.json`,{cache:"no-store"});if(!r.ok)throw new Error(String(r.status));return r.json();}));
    outcomes.forEach((r,i)=>{if(r.status==="fulfilled")state.files[names[i]]=r.value;else state.failed.push(names[i]);});
    state.date=scheduleDate(state.files.games?.games||[],Date.now(),new URLSearchParams(location.search).get("date")||"");
    state.players=playerForms(state.files.games?.games||[],state.files.games?.details||[]);
    $("load-status").textContent=state.failed.length?`部分資料暫時無法讀取：${state.failed.join("、")}。可重新整理重試。`:"";$("load-status").classList.toggle("error",!!state.failed.length);
    renderDates();setupResults();const requestedDate=new URLSearchParams(location.search).get("date");if(requestedDate&&[...$("result-day").options].some(o=>o.value===requestedDate))$("result-day").value=requestedDate;setPage(location.hash.slice(1),false);
  }
  document.querySelectorAll("[data-page]").forEach(b=>b.addEventListener("click",()=>{setPage(b.dataset.page);window.scrollTo({top:0,behavior:"instant"});}));
  document.querySelectorAll("[data-goto]").forEach(b=>b.addEventListener("click",()=>{setPage(b.dataset.goto);window.scrollTo({top:0,behavior:"instant"});}));
  document.querySelectorAll("[data-model]").forEach(b=>b.addEventListener("click",()=>{state.model=b.dataset.model;document.querySelectorAll("[data-model]").forEach(n=>n.setAttribute("aria-pressed",String(n===b)));renderGames();}));
  document.querySelectorAll("[data-dataset]").forEach(b=>b.addEventListener("click",()=>{state.dataset=b.dataset.dataset;document.querySelectorAll("[data-dataset]").forEach(n=>n.setAttribute("aria-pressed",String(n===b)));renderData();}));
  for(const id of ["result-day","result-market","result-model"])$(id).addEventListener("change",renderResults);
  $("data-search").addEventListener("input",renderData);$("refresh").addEventListener("click",()=>location.reload());$("dialog-close").addEventListener("click",()=>$("game-dialog").close());
  $("go-today").addEventListener("click",()=>selectSchedule(today));$("go-tomorrow").addEventListener("click",()=>selectSchedule(tomorrow));
  $("header-replay").addEventListener("click",()=>playIntro(true));
  $("replay-intro").addEventListener("click",()=>playIntro(true));
  $("game-dialog").addEventListener("click",e=>{if(e.target===$("game-dialog")){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
  window.addEventListener("hashchange",()=>setPage(location.hash.slice(1),false));
  playIntro();
  init().catch(()=>{$("load-status").textContent="資料載入失敗，請重新整理；未顯示替代預測。";$("load-status").classList.add("error");});
})();
