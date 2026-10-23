#!/usr/bin/env python3
"""Public-page availability probe for Playsport NBA. No bypass, no mirrored content."""
import datetime as dt,json,pathlib,re,urllib.request,urllib.error
from html.parser import HTMLParser
URL="https://www.playsport.cc/predict/games?allianceid=3"
OUT=pathlib.Path("data/playsport_status.json")
class TextExtractor(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style"):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ("script","style") and self.skip:self.skip-=1
 def handle_data(self,data):
  if not self.skip:self.parts.append(data.strip())
def main():
 result={"source":"Playsport NBA public webpage","url":URL,"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"fetch_status":"unknown","nba_market_rows_verified":0,"redistribution_authorized":False,"published_market_data":False}
 try:
  req=urllib.request.Request(URL,headers={"User-Agent":"NBA-Paper-Lab/1.0 research status probe","Accept":"text/html"})
  with urllib.request.urlopen(req,timeout=20) as resp:
   data=resp.read(800000).decode("utf-8","replace")
   result["http_status"]=resp.status
  parser=TextExtractor();parser.feed(data)
  text=" ".join(parser.parts)
  result["fetch_status"]="reachable"
  result["has_market_headers"]=all(x in text for x in ("國際盤","運彩盤"))
  result["no_data_notice"]="暫無資料" in text
  result["market_rows_verified"]=0
  result["note"]="Page headers alone do not verify odds. Do not publish copied markets without rights review."
 except urllib.error.HTTPError as e:
  result.update(fetch_status="http_error",http_status=e.code)
 except Exception as e:
  result.update(fetch_status="error",error_type=type(e).__name__)
 OUT.parent.mkdir(exist_ok=True)
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
