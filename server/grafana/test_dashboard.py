import copy
import json
from pathlib import Path
import unittest

from build_dashboard import dashboard, queries
from render_dashboard import render

ROOT = Path(__file__).resolve().parent


class DashboardContract(unittest.TestCase):
    def test_classic_format_and_existing_panel_identity(self):
        self.assertEqual(dashboard['schemaVersion'], 39)
        self.assertTrue(dashboard['title'])
        self.assertNotIn('spec', dashboard)
        self.assertTrue({1, 2, 3}.issubset({p['id'] for p in dashboard['panels']}))

    def test_generated_files_are_reproducible(self):
        self.assertEqual(json.loads((ROOT/'dashboard.json').read_text()), dashboard)
        self.assertEqual({p.stem: p.read_text() for p in (ROOT/'queries').glob('*.flux')}, queries)

    def test_render_preserves_template_and_resolves_every_datasource(self):
        original = copy.deepcopy(dashboard)
        result = render(dashboard, 'test-source', 'existing-dashboard')
        self.assertEqual(dashboard, original)
        self.assertEqual(result['uid'], 'existing-dashboard')
        self.assertNotIn('__inputs', result)
        self.assertNotIn('${DS_INFLUXDB}', json.dumps(result))
        for panel in result['panels']:
            if panel['type'] != 'text': self.assertEqual(panel['datasource']['uid'], 'test-source')

    def test_panels_do_not_overlap(self):
        occupied = set()
        for panel in dashboard['panels']:
            g = panel['gridPos']
            self.assertLessEqual(g['x'] + g['w'], 24)
            cells = {(x, y) for x in range(g['x'], g['x']+g['w']) for y in range(g['y'], g['y']+g['h'])}
            self.assertFalse(occupied & cells, panel['title'])
            occupied |= cells

    def test_units_and_string_state_regressions(self):
        panels = {p['id']: p for p in dashboard['panels']}
        self.assertEqual(panels[7]['options']['reduceOptions']['fields'], '/^_value$/')
        self.assertEqual(panels[3]['fieldConfig']['defaults']['unit'], 'suffix: días')
        self.assertIn({'id': 'unit', 'value': 'celsius'}, panels[3]['fieldConfig']['overrides'][0]['properties'])

    def test_bench_label_and_history_gap_policy(self):
        panels = {p['id']: p for p in dashboard['panels']}
        self.assertIn('FASE D pendiente', panels[4]['options']['content'])
        self.assertFalse(panels[1]['fieldConfig']['defaults']['custom']['spanNulls'])
        self.assertIn('createEmpty: true', queries['curva_temperaturas'])
        self.assertIn('fn: last', queries['curva_aplicada'])
        for query in queries.values():
            self.assertIn('v.timeRangeStart', query)
            self.assertIn('v.timeRangeStop', query)
            self.assertNotIn('range(start: 0)', query)
            self.assertNotIn('|> to(', query)


if __name__ == '__main__': unittest.main()
