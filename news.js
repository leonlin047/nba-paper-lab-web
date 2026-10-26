"use strict";
(()=>{
 const articles=document.getElementById("news-articles"),people=document.getElementById("insiders-list");
 if(!articles||!people)return;
 const elem=(tag,value)=>{const n=document.createElement(tag);if(value!==undefined)n.textContent=String(value);return n};
 async function load(path){
  const r=await fetch("./data/"+path+"?v="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw Error("HTTP "+r.status);
  return r.json();
 }
 function link(parent,name,url){const a=elem("a",name);a.href=url;a.target="_blank";a.rel="noopener noreferrer";a.style.cssText="color:#4456FE;text-decoration:underline;overflow-wrap:anywhere";parent.append(a);return a}
 Promise.all([load("news.json").catch(e=>({articles:[],errors:[String(e)]})),load("insiders.json").catch(e=>({sources:[],error:String(e)}))]).then(([news,registry])=>{
  articles.replaceChildren();
  articles.append(elem("p",news.captured_at_utc?"更新："+new Date(news.captured_at_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"尚無更新時間"));
  if(news.errors&&news.errors.length)articles.append(elem("p","新聞來源目前有讀取問題；尚未驗證任何 X 平台即時貼文。"));
  const rows=(news.articles||[]).filter(x=>x&&x.title&&x.url&&x.url.startsWith("https://")&&!x.x_post_verified).slice(0,25);
  if(!rows.length)articles.append(elem("p","目前沒有可用的新聞快照，請直接查看官方消息來源。"));
  for(const entry of rows){const block=elem("div");block.style.cssText="padding:11px 0;border-bottom:1px solid #E3E7F0";link(block,entry.title,entry.url);
   const stamp=entry.published_at_utc?new Date(entry.published_at_utc).toLocaleString("zh-TW",{timeZone:"Asia/Taipei"}):"發布時間未提供";
   const teams=(entry.teams||[]).map(t=>window.NbaZh?window.NbaZh.teamShort(t):t).join("、");
   block.append(elem("p",stamp+(teams?" · 相關球隊："+teams:"")+" · ESPN 新聞（不是 X 貼文）"));articles.append(block);}
  people.replaceChildren();
  if(registry.error)people.append(elem("p","來源清單暫不可用："+registry.error));
  people.append(elem("p","名單依消息用途分類，並非每則發言都有同等可信度。交易傳聞、分析意見不能直接當成球員出賽事實。"));
  const groups=[["官方優先","official"],["聯盟消息記者","national_insider"],["球隊線記者","beat_reporter"],["球隊公關","team_official"],["聯盟分析","national_analyst"]];
  for(const [title,key] of groups){
    const items=(registry.sources||[]).filter(x=>x.type===key);
    if(!items.length)continue;
    const section=elem("details"),head=elem("summary",title+"（"+items.length+"）");head.style.cssText="padding:12px 0;font-weight:700";section.append(head);if(key==="official")section.open=true;
    for(const x of items){const row=elem("div");row.style.cssText="padding:10px 0;border-top:1px solid #E3E7F0";
      link(row,(x.name_zh||x.name)+(x.handle?" · @"+x.handle:""),x.url);
      const topics=(x.topics||[]).join("、");
      row.append(elem("p",(x.reliability||"待驗證")+(topics?" · "+topics:"")));
      section.append(row)}
    people.append(section);
  }
 }).catch(e=>{articles.textContent="消息資料載入失敗："+e.message;people.textContent="來源清單載入失敗："+e.message});
})();
