"""Bounded public scoreboard collection with identities needed for safe settlement."""
import json
import urllib.request
from datetime import datetime,timezone
from pathlib import Path
from analyst_factors import canon
from result_ledger import write as atomic_json

NBA='https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json'
ESPN='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'

def normalize_espn(raw):
    rows=[]
    for e in raw.get('events',[]):
        competition=e['competitions'][0];sides={x['homeAway']:x for x in competition['competitors']};state=e['status']['type']['state']
        rows.append({'event_id':str(e['id']),'source_event_id':str(e['id']),'provider':'ESPN','date':e['date'],'home':canon(sides['home']['team']['abbreviation']),'away':canon(sides['away']['team']['abbreviation']),'status':{'pre':'未開賽','in':'進行中','post':'已結束'}[state],**{side+'_score':int(sides[side]['score'])if state!='pre'else None for side in ('home','away')}})
    return rows

def normalize_nba(raw):
    rows=[]
    for g in raw['scoreboard']['games']:
        state=int(g['gameStatus']);rows.append({'source_event_id':str(g['gameId']),'provider':'NBA','date':g['gameTimeUTC'],'home':canon(g['homeTeam']['teamTricode']),'away':canon(g['awayTeam']['teamTricode']),'status':{1:'未開賽',2:'進行中',3:'已結束'}[state],**{side+'_score':int(g[side+'Team']['score'])if state!=1 else None for side in ('home','away')}})
    return rows

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'nba-paper-lab-research/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20)as response:body=response.read(2_000_001)
    if len(body)>2_000_000:raise ValueError('response too large')
    return json.loads(body)

def run(root=Path('data'),now=None,fetch=get):
    errors=[];now=now or datetime.now(timezone.utc)
    for url,normalize,source in [(NBA,normalize_nba,'NBA scoreboard CDN'),(ESPN,normalize_espn,'ESPN scoreboard API')]:
        try:
            rows=normalize(fetch(url))
            if not rows:raise ValueError('empty scoreboard; preserve last nonempty observation')
            output={'schema_version':2,'captured_at':now.isoformat(),'games':rows,'source':source,'errors':errors};atomic_json(root/'scoreboard.json',output);print(json.dumps({'games':len(rows),'source':source,'errors':errors}));return output
        except (OSError,ValueError,KeyError,TypeError,IndexError)as exc:errors.append(type(exc).__name__+': '+str(exc)[:120])
    print(json.dumps({'status':'sources_unavailable_preserved_previous','errors':errors}));return None

if __name__=='__main__':run()
