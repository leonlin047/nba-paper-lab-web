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
        self.assertIn('返回 Paper Lab', (ROOT / 'research.html').read_text())

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
const {day,numeric,validBefore,tally,playerForms} = require('./platform.js');
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
console.log('chronology and sample integrity passed');
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
