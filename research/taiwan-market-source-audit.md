# 台灣 NBA 盤口來源稽核（2026-10-24）

## 已驗證可用（本專案實際執行）
- ESPN summary pickcenter: DraftKings moneyline, spread, total; 最近一次快照 8 場。ESPN ID 可直接與賽事匹配。授權／公開再發布尚待確認。
- NBA CDN odds endpoint: GitHub Actions HTTP 403，不能作為主來源。

## 候選：台灣合法盤口
1. JBot https://sportsbot.tech/api/sportslottery/ ： GET https://api.sportsbot.tech/v2/odds?sport=NBA&date=YYYY-MM-DD&mode=both，X-JBot-Token。初盤/尾盤/歷史變動；需申請金鑰。官方明示免費試用不可排程，請勿用免費 token 跑 GitHub Actions。
2. 台灣運彩官網 https://article.sportslottery.com.tw/ ：盤口官方參考，賽事 ID、主客場及開賽時間需對照 ESPN；網站結構可能變動。
3. 公開社群專案 https://github.com/show0621/sports-quant ：聲稱採用台灣運彩 Blob、玩運彩歷史資料與 JBot；未獨立確認端點當前有效性、授權、賠率真實性。
4. https://twsport.github.io/ ：宣稱跟蹤台灣運彩與澳門莊家；第三方資料，需逐筆核對時間與來源。

## 地下盤口的供應鏈研究（不可視為已驗證）
常見可能路徑：國際 odds feed／白標平台／代理與鏡像站／轉換水位及盤口顯示。沒有業者內部文件或封包證據，不能斷言特定網站採用哪一家 feed。研究時僅使用可公開訪問、合法授權的內容；不繞過登入、反機器人或地理封鎖。

## 必要資料模型
source, provider, source_event_id, espn_event_id, home, away, start_utc, market (moneyline/spread/total), selection, line, odds_decimal, observed_at_utc, opening_or_current, rights_status, fetch_status。
- 同一比賽比對主客場＋開賽時間；不得只以名稱模糊匹配。
- 美式賠率正數 1+odds/100，負數 1+100/abs(odds)。
- 市場雙邊去水後機率： (1/odds_side) / (1/odds_home + 1/odds_away)。
- 讓分盤「過盤率」需獨立分差分布模型，且需處理整數盤走水；不得套用獨贏率。
- 沒有來源時間／授權／可重現快照時不得標為已驗證。

## 待辦與限制
目前無 JBot 金鑰，故不能聲稱已接通台灣運彩。公開盤口若要再發布需審核資料提供商條款。自動化測試不等於外部 API 可用性測試。
