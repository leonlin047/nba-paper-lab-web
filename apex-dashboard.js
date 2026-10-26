"use strict";
(() => {
  const get=id=>document.getElementById(id);
  const host=get("apex-v21-terminal");
  if(!host) return;
  const element=(tag,value,cls)=>{
    const n=document.createElement(tag);
    if(value!==undefined)n.textContent=String(value);
    if(cls)n.className=cls;
    return n;
  };
  const row=(parent,label,value)=>{
    const r=element("div",undefined,"apex-row");
    r.append(element("span",label),element("strong",value));
    parent.append(r);
  };
  const boxed=(parent,title,text)=>{
    const c=element("article",undefined,"card");
    c.append(element("h3",title));
    if(text)c.append(element("p",text,"muted"));
    parent.append(c);
    return c;
  };
  const pct=value=>typeof value==="number"&&Number.isFinite(value)&&(value>=0&&value<=1)?(100*value).toFixed(1)+"%":"未驗證";
  const fmt=value=>typeof value==="number"&&Number.isFinite(value)?value.toFixed(1):"—";
  let data=null;
  function overview(){
    host.replaceChildren();
    const dt=data?.as_of_utc?Date.parse(data.as_of_utc):NaN;
    const stale=!Number.isFinite(dt)||Date.now()-dt>24*3600*1000;
    const h=element("div",undefined,"pl-panel");
    h.append(element("div","APEX v2.1 · JOINT SCORE CHALLENGER","eyebrow"));
    h.append(element("h2","獨立研究模型，已整合賽前平行記錄"));
    h.append(element("p","這不是把 Elo 換個名字。APEX 使用近期衰減加權的球隊攻防 Ridge 估計，將預期比分同時轉為分差與總分的二維常態研究近似。","muted"));
    h.append(element("p","正式採用主模型仍是 Elo；APEX 只能作為受控平行研究，不會自動取代 Elo。","lab-note"));
    const fresh=Number.isFinite(dt)?new Date(dt).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"未知";
    h.append(element("p","私人稽核觀測："+fresh+"（台灣）"+(stale?" · 此快照已過期":"")+"；公開網站只有人工核對的聚合資訊，並非私人研究資料庫的即時鏡像。","muted"));
    host.append(h);
    const grid=element("div",undefined,"grid");
    for(const [label,num,note] of [
      ["已凍結 APEX 平行快照",data.new_shadow_snapshots+" 筆","合併後首次收集；不可事後補造"],
      ["已有賽後配對可評估",data.eligible_paired_games+" 場","需真實賽前同時保存兩種模型"],
      ["最低開放比較門檻",data.minimum_evaluated_games+" 場","不足門檻不公布勝率或優劣"],
      ["舊 Elo 封存被排除",data.skipped_preexisting_stale_elo+" 筆","開發新模型前的記錄不得補算成舊預測"]
    ]){
      const card=boxed(grid,label,note);
      card.insertBefore(element("div",num,"metric"),card.querySelector("p"));
    }
    host.append(grid);
    const choices=element("div",undefined,"apex-switch");
    const views=[
      ["metrics","Elo vs Apex"],
      ["score","分差／總分"],
      ["sources","資料與驗證"]
    ];
    const body=element("div",undefined,"pl-panel");
    const buttons=[];
    function show(mode){
      body.replaceChildren();
      for(const b of buttons)b.setAttribute("aria-pressed",String(b.dataset.mode===mode));
      if(mode==="metrics"){
        body.append(element("h3","同場賽前 Elo 對照 APEX v2.1"));
        const t=element("div",undefined,"apex-grid");
        for(const [name,metric] of [["模型","Elo／APEX v2.1"],["配對樣本",data.eligible_paired_games+" 場"],["APEX Brier","尚無符合門檻的結果"],["Elo 同場 Brier","尚無符合門檻的結果"],["是否優於 Elo","尚無證據"]])row(t,name,metric);
        body.append(t);
        body.append(element("p","APEX 必須在開賽前與 Elo 使用相同資料截止時間，各自存成不可修改快照；等真實賽後標籤且同場配對至少 "+data.minimum_evaluated_games+" 筆才比較誤差。","lab-note"));
      }else if(mode==="score"){
        body.append(element("h3","聯合比分模型：輸出與限制"));
        const items=[["主隊預期得分","expected_home_points"],["客隊預期得分","expected_away_points"],["預估主隊淨勝分","expected_margin_home_minus_away"],["預估全場總分","expected_total_points"]];
        const publicPredictions=Array.isArray(data.authorized_public_forecasts)?data.authorized_public_forecasts:[];
        if(!publicPredictions.length){
          body.append(element("p","目前沒有獲准公開且真正賽前凍結的 APEX v2.1 單場預測。無法提供可驗證的當場得分、大小分或讓分機率；不能把 Elo 機率假裝成 APEX。","lab-note"));
        }else{
          for(const prediction of publicPredictions.slice(0,30)){
            if(prediction?.source_rights!=="approved_public_preview"||prediction?.model!=="apex_v21_joint_score_challenger")continue;
            const c=boxed(body,String(prediction.away_team||"?")+" @ "+String(prediction.home_team||"?"),"觀測時間："+String(prediction.forecast_at||"未知")+" · 模型機率未校準");
            for(const [n,k] of items)row(c,n,fmt(prediction[k]));
            row(c,"研究性主勝近似",pct(prediction.home_win_probability_proxy));
          }
        }
        body.append(element("p","二維常態分布與模型歷史樣本內殘差，只是探索性估計；尚無可驗證的讓分／大小分過盤率。","muted"));
      }else{
        body.append(element("h3","研究資料完整性"));
        const info=[["私有主分支","APEX v2.1 已合併"],["APEX 凍結工作","已隨核准收集流程啟用"],["資料來源","已授權私人 NBA Games as-of 記錄"],["校準狀態","未校準（Gaussian probability proxy）"],["賽前資料回填","嚴禁將賽後補成賽前"],["自動升級","停用；人工審查"],["發布限制","私人原始資料及未獲權利的盤口不可公開"]];
        for(const [k,v] of info)row(body,k,v);
        const link=element("a","查看 APEX v2.1 程式與審查");
        link.href=data.pr_url;link.rel="noopener noreferrer";link.target="_blank";body.append(link);
      }
    }
    for(const [id,label] of views){
      const b=element("button",label);
      b.type="button";b.dataset.mode=id;b.className="apex-button";b.addEventListener("click",()=>show(id));
      buttons.push(b);choices.append(b);
    }
    host.append(choices,body);show("metrics");
  }
  fetch("./data/apex-v21-status.json",{cache:"no-store"}).then(r=>{
    if(!r.ok)throw Error("HTTP "+r.status);
    return r.json();
  }).then(value=>{
    if(value?.schema_version!==1||value?.model_id!=="apex_v21_genuinely_frozen_shadow"||
      value?.release_status!=="merged_private_main"||typeof value?.eligible_paired_games!=="number"||
      typeof value?.minimum_evaluated_games!=="number"||value?.research_only!==true)throw Error("APEX 研究資料格式不符合");
    data=value;overview();
  }).catch(e=>{
    host.replaceChildren();
    host.append(element("p","無法取得經審核的 APEX 研究狀態："+e.message+"。未顯示任何替代或虛構預測。","lab-note"));
  });
})();