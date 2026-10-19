"""Read-only checks and isolated tool inputs; does not change the demo database."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / 'BIM-Safety-Coordination-Agent'
BACKEND = PACKAGE / '02_网站源码/backend'
sys.path.insert(0, str(BACKEND))
from app import tools


def api(path):
    with urlopen('http://127.0.0.1:8000/api' + path, timeout=30) as response:
        return json.load(response)


bundle = json.loads((PACKAGE / '03_测试与验收/业务体验改版_20261019/browser-workflow-case.json').read_text(encoding='utf-8-sig'))
case = bundle['case']
after = next(item for item in bundle['evidence'] if item['evidence_id'] == 'EV-010')
before = next(item for item in bundle['evidence'] if item['evidence_id'] == 'EV-001')
other_guid = '0BGfqjCPX70uXXKLeh5fKj'
conn = sqlite3.connect((BACKEND / 'runtime/app.db').as_uri() + '?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
try:
    with patch.object(tools, 'get_evidence', return_value=copy.deepcopy(after)):
        baseline = tools.verification_check(conn, case, ['EV-010'], '2026-10-16T09:40:00+08:00', True)
    wrong_after = {**copy.deepcopy(after), 'bim_guids': [other_guid]}
    with patch.object(tools, 'get_evidence', return_value=wrong_after):
        mismatch = tools.verification_check(conn, case, ['EV-010'], '2026-10-16T09:40:00+08:00', True)
    wrong_before = {**copy.deepcopy(before), 'bim_guids': [other_guid]}
    with patch.object(tools, 'get_evidence', return_value=wrong_before):
        inspection = tools.evidence_check(conn, case, ['EV-001'])
    historical_rules = tools.rule_retrieval(conn, '临边 栏杆 防护', '1900-01-01T09:00:00+08:00', 3)
finally:
    conn.close()

detail = api('/models/S1-bSDD-example/elements/' + other_guid)['element']
geometry = api('/models/S1-bSDD-example/elements/' + other_guid + '/mesh')['mesh']
health = api('/health')
results = {
    'runtime': {'mode': health['mode'], 'demo_mode': health['demo_mode']},
    'bbox_mismatch': {'guid': other_guid, 'reported': detail['bbox_m'], 'mesh': geometry['bbox_m'],
                      'confirmed': detail['bbox_m'] != geometry['bbox_m']},
    'guid_alignment': {'case_guids': case['bim_guids'], 'injected_evidence_guids': [other_guid],
                       'baseline_verification': baseline['data']['result'],
                       'wrong_guid_verification': mismatch['data']['result'],
                       'wrong_guid_inspection_matched': inspection['data']['matched'],
                       'method': 'isolated mock of evidence lookup; no database updates'},
    'rule_time_filter': {'requested_as_of': '1900-01-01T09:00:00+08:00',
                         'returned': [{'rule_id': row['rule_id'], 'effective': row.get('effective_from')}
                                      for row in historical_rules['data']['results']]},
}
assert baseline['data']['result'] == 'pass_in_demo_scope'
assert results['bbox_mismatch']['confirmed']
assert mismatch['data']['result'] == 'pass_in_demo_scope'
assert inspection['data']['matched']
(Path(__file__).parent / '核查复现结果.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
