"""Chronology, sample integrity and navigation contracts for the integrated platform."""
import json
import subprocess
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


class PlatformTests(unittest.TestCase):
    def test_navigation_and_preserved_research_have_real_targets(self):
        soup = BeautifulSoup((ROOT / 'index.html').read_text(), 'html.parser')
        self.assertEqual({b['data-page'] for b in soup.select('[data-page]')}, {'games', 'results', 'data', 'platform'})
        for b in soup.select('[data-page]'):
            self.assertIsNotNone(soup.find(id='page-' + b['data-page']))
        ids = [e['id'] for e in soup.select('[id]')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(soup.select_one('a[href="./research.html"]'))
        self.assertIn('id="apex-v21-terminal"', (ROOT / 'research.html').read_text())
        self.assertIn('返回 墨場', (ROOT / 'research.html').read_text())

    def test_asof_and_public_data_do_not_leak_private_state(self):
        d = json.loads((ROOT / 'data/integration-status.json').read_text())
        self.assertEqual(d['update_method'], 'manual_sanitized_snapshot')
        self.assertEqual(d['factors']['commercial_rights'], 'not_cleared')
        self.assertEqual(d['models']['online']['old_pairs_retrained'], 0)
        self.assertEqual(d['models']['apex']['evaluated'], 0)
        self.assertEqual(d['models']['ensemble']['public_forecasts'], 0)
        self.assertFalse(d['models']['ensemble']['automatic_promotion'])
        for bad in ['api_key', 'access_token', 'coefficients', 'checkpoint', 'player_name']:
            self.assertNotIn(bad, json.dumps(d))

    def test_forecast_timing_missing_values_and_duplicate_samples(self):
        # Execute the actual helper functions used by the browser.
        script = r'''
const assert = require('node:assert/strict');
const {day,numeric,validBefore,tally,playerForms,scheduleDate,pregameReport,prospectiveTally} = require('./platform.js');
assert.equal(day('2026-10-26T23:30Z'), '2026-10-27');
assert.equal(numeric(null), null); assert.equal(numeric(''), null); assert.equal(numeric(0), 0);
assert.equal(validBefore('2026-10-27T12:00Z','2026-10-27T12:00Z'),false);
assert.equal(validBefore('2026-10-27T11:00Z','2026-10-27T12:00Z'),true);
assert.equal(validBefore('bad','2026-10-27T12:00Z'),false);
assert.deepEqual(tally([{status:'eligible',spread:{hit:true}},{status:'eligible',spread:{hit:null}},{status:'excluded',spread:{hit:true}},{status:'eligible',spread:{hit:false}}],'spread'),{n:2,correct:1});
const games = [{id:'a',status:'post',season_phase:2,date:'2026-10-26T00:00Z'},{id:'preseason',status:'post',season_phase:1,date:'2026-10-25T00:00Z'},{id:'future',status:'post',season_phase:2,date:'2026-11-01T00:00Z'}];
const players = [{name:'A',stats:{MIN:'12:30',PTS:'0',REB:null,AST:'2'}},{name:'B',stats:{MIN:'DNP',PTS:'0'}},{name:'C',stats:{MIN:'0',PTS:'0'}}];
const d = {event_id:'a',boxscore:[{team:'NYK',players}]};
const forms = playerForms(games,[d,d,{...d,event_id:'preseason'},{...d,event_id:'future'}],Date.parse('2026-10-27T00:00Z'));
assert.equal(forms.length,1);assert.equal(forms[0].n,1);assert.equal(forms[0].MIN,12.5);assert.equal(forms[0].PTS,0);assert.equal(forms[0].REB,null);assert.equal(forms[0].team,'NY');
const now=Date.parse('2026-10-27T13:00Z');
const schedule=[{id:'past',date:'2026-10-27T00:00Z',status:'post'},{id:'next',date:'2026-10-27T23:30Z',status:'pre'}];
assert.equal(scheduleDate(schedule,now),'2026-10-28');
assert.equal(scheduleDate([...schedule,{id:'live',date:'2026-10-27T12:00Z',status:'in'}],now),'2026-10-27');
assert.equal(scheduleDate(schedule,now,'2026-10-27'),'2026-10-27');
assert.equal(scheduleDate(schedule,now,'bad'),'2026-10-28');
assert.equal(scheduleDate(schedule,now,'2026-02-30'),'2026-10-28');
assert.equal(scheduleDate([],now),'2026-10-27');
const future={id:'next',home:'NY',away:'DET',status:'pre',date:'2026-10-27T23:30Z'};
const report={event_id:'next',home:'NYK',away:'DET',generated_at_utc:'2026-10-27T12:00Z',report_zh:'獨贏、讓分、大小分的中文分析。'};
assert.equal(pregameReport(future,report,'elo',now),report.report_zh);
assert.equal(pregameReport(future,report,'apex',now),null);
assert.equal(pregameReport(future,report,'factor',now),null);
assert.equal(pregameReport(future,report,'gbdt',now),null);
assert.equal(pregameReport(future,{...report,gbdt_forecast:true},'gbdt',now),report.report_zh);
assert.deepEqual(prospectiveTally([{settlement:null},{settlement:{spread:{push:true,hit:null}}},{settlement:{spread:{push:false,hit:true}}}],'spread'),{n:1,correct:1,push:1});
assert.deepEqual(prospectiveTally([{settlement:{moneyline_hit:false}},{settlement:null}],'moneyline'),{n:1,correct:0,push:0});
assert.equal(pregameReport(future,{...report,factor_forecast:true},'factor',now),report.report_zh);
assert.equal(pregameReport({...future,status:'post'},report,'elo',now),null);
assert.equal(pregameReport(future,{...report,generated_at_utc:future.date},'elo',now),null);
assert.equal(pregameReport(future,{...report,home:'BOS'},'elo',now),null);
assert.equal(pregameReport(future,{...report,event_id:'other'},'elo',now),null);
console.log('chronology and sample integrity passed');
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_motion_is_optional_and_local_assets_are_valid(self):
        import re
        import xml.etree.ElementTree as ET
        soup=BeautifulSoup((ROOT/'index.html').read_text(),'html.parser')
        self.assertTrue(soup.find(id='brand-intro').has_attr('hidden'))
        self.assertIsNotNone(soup.find(id='skip-intro'))
        self.assertIsNotNone(soup.find(id='replay-intro'))
        self.assertIsNotNone(soup.find(id='go-tomorrow'))
        for path in ['assets/court-noir-mark.svg','assets/court-noir-wordmark.svg','assets/noir-entrance.svg']:
            ET.parse(ROOT/path)
        css=(ROOT/'platform.css').read_text()
        for color in re.findall(r'#[0-9a-fA-F]+\b(?![\w-])',css):
            self.assertIn(len(color)-1,(3,4,6,8),color)
        self.assertIn('prefers-reduced-motion:reduce',css)
        js=(ROOT/'platform.js').read_text()
        self.assertNotIn('sessionStorage',js)
        for control in ['enter-platform','watch-intro','header-replay']:
            self.assertIsNotNone(soup.find(id=control))
        self.assertTrue((ROOT/'assets/noir-crew-cinematic-v2.webp').is_file())
        self.assertNotIn('.brand-intro{display:none!important}',css)
        self.assertIn('e.key==="Escape"',js)
        self.assertIn('game-brief',js)
        self.assertIn('pregameReport(g,report,state.model)',js)

    def test_research_screening_is_traceable_without_paper_bodies(self):
        d=json.loads((ROOT/'docs/factor-literature-screening.json').read_text())
        self.assertEqual(d['indexed_candidates'],40)
        self.assertEqual(len(d['records']),d['indexed_candidates'])
        self.assertEqual(len({r['id'] for r in d['records']}),d['unique_candidate_ids'])
        self.assertTrue(all(r['reading'] in ('abstract_screen_only','selected_methods_or_results') for r in d['records']))
        self.assertTrue(all('abstract' not in r and 'body' not in r for r in d['records']))


if __name__ == '__main__':
    unittest.main()
