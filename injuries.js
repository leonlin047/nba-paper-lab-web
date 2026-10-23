"use strict";
(()=>{
 const target=document.getElementById("injuries-data");if(!target)return;
 const elem=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
 async function load(){
  try{
   const r=await fetch("./data/injuries.json?v="+Date.now(),{cache:"no-store"});
   if(!r.ok)throw Error("HTTP "+r.status);
   const d=await r.json();target.replaceChildren();
   if(d.errors&&d.errors.length){target.append(elem("p","傷病資料目前取得失敗，不能據此判定球員能否出賽。"));return}
   const date=d.captured_at?new Date(d.captured_at).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"未知";
   target.append(elem("p","更新："+date+" · 已回報 "+(d.injuries||[]).length+" 筆（並非完整健康名單）"));
   if(!d.injuries||!d.injuries.length){target.append(elem("p","目前來源未提供傷病條目，不代表所有球員健康。"));return}
   const groups=new Map();
   for(const injury of d.injuries){const name=injury.team||injury.team_name||"未知球隊";if(!groups.has(name))groups.set(name,[]);groups.get(name).push(injury)}
   for(const [team,items] of [...groups].sort((a,b)=>a[0].localeCompare(b[0]))){
    const section=elem("details"),sum=elem("summary",team+" · "+items.length+" 筆");sum.style.cssText="font-weight:700;padding:12px 0";section.append(sum);
    for(const x of items){const p=elem("p",(x.player||"未知球員")+" · "+(x.status||"未公布")+(x.type?" · "+x.type:""));p.style.cssText="font-size:13px;border-bottom:1px solid #304362;padding:8px 0";section.append(p)}
    target.append(section);
   }
  }catch(e){target.textContent="傷病快照尚未就緒："+e.message+"；無法據此判定出賽狀況。"}
 }
 load();
})();