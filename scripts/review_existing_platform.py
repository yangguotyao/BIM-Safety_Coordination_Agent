"""Reproduce two workflow gaps in an isolated runtime; do not modify the delivery."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
DELIVERY=ROOT/'BIM-Safety-Coordination-Agent'
BACKEND=DELIVERY/'02_网站源码/backend'
OUTPUT=ROOT/'docs/platform_review'
OUTPUT.mkdir(parents=True,exist_ok=True)
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(tempfile.gettempdir())/'codex-bim-platform-review-packages'))
sys.path.insert(0,str(BACKEND))
runtime=Path(tempfile.mkdtemp(prefix='codex-bim-review-regressions-'))
os.environ.update({'RUNTIME_DIR':str(runtime),'DB_PATH':str(runtime/'app.db'),
                   'DATA_ROOT':str(DELIVERY/'01_资料与依据'),'DEMO_MODE':'true'})
from fastapi.testclient import TestClient
from app.main import app

client=TestClient(app)


def post(path,body=None):
    r=client.post(path,json=body) if body is not None else client.post(path)
    if r.status_code>=400:
        raise RuntimeError(f'{path}: {r.status_code} {r.text}')
    return r.json()


def create(eid,title):
    return post('/api/cases',{'title':title,'model_id':'S1-bSDD-example','task_id':'TASK-S1-001',
        'zone_id':'ZONE-S1-L05-EDGE','as_of':'2026-10-16T09:00:00+08:00','evidence_ids':[eid]})['case']


def analyze(case):
    run=post(f"/api/cases/{case['case_id']}/analyze")['run_id']
    for _ in range(300):
        result=client.get('/api/runs/'+run).json()['run']
        if result['status'] in ['succeeded','failed']: break
        time.sleep(.01)
    if result['status']!='succeeded': raise RuntimeError(result)
    return client.get('/api/cases/'+case['case_id']).json()['case']


def approve(case):
    return post(f"/api/cases/{case['case_id']}/review",{'decision':'approve','reviewer':'review actor',
        'reviewed_at':'2026-10-16T09:10:00+08:00','control_version':case['control_version'],
        'expected_case_version':case['version'],'comment':'isolated audit'})['case']


def main():
    c=analyze(create('EV-007','Audit normal then changed conditions'))
    before=c['findings'][0]['result']
    c=approve(c)
    assert c['status']=='closed'
    c=post(f"/api/cases/{c['case_id']}/reopen",{'reason':'New evidence shows guardrail removed',
        'evidence_ids':['EV-011'],'actor':'audit actor'})['case']
    c=analyze(c)
    records=client.get('/api/cases/'+c['case_id']).json()['evidence']
    change=next(x for x in records if x['evidence_id']=='EV-011')
    first={'id':'latest_evidence_not_used_after_reopen','reproduced':c['findings'][0]['result']=='no_issue_in_checked_items',
        'case_id':c['case_id'],'initial_evidence':'EV-007','initial_result':before,
        'change_evidence':'EV-011','change_guardrail_state':change['observation']['guardrail_state'],
        'result_after_reopen_analysis':c['findings'][0]['result'],
        'finding_guardrail_state':c['findings'][0]['inputs']['guardrail_state'],
        'expected':'Use the current evidence for the new analysis, or explicitly require scope/time clarification.'}

    c=analyze(create('EV-001','Audit modified control acceptance'))
    c=post(f"/api/cases/{c['case_id']}/review",{'decision':'modify','reviewer':'review actor',
        'expected_case_version':c['version'],'new_controls':[{'control_id':'CTRL-CUSTOM',
        'action':'Raise the top rail to at least 1.50 m','owner':'demo team',
        'verification_requirements':['Top rail height must be at least 1.50 m']} ]})['case']
    c=approve(c)
    c=post(f"/api/cases/{c['case_id']}/implementation",{'owner':'demo team',
        'implemented_at':'2026-10-16T09:20:00+08:00','expected_case_version':c['version']})['case']
    c=post(f"/api/cases/{c['case_id']}/evidence",{'evidence_ids':['EV-010'],'actor':'audit actor'})['case']
    bundle=post(f"/api/cases/{c['case_id']}/verify",{'after_evidence_ids':['EV-010'],
        'reviewer':'review actor','reviewer_confirmed':True,'as_of':'2026-10-16T09:40:00+08:00',
        'expected_case_version':c['version']})
    c=bundle['case']
    second={'id':'verification_not_bound_to_modified_control','reproduced':c['status']=='closed',
        'case_id':c['case_id'],'approved_control':c['controls'][0]['action'],
        'approved_requirements':c['controls'][0]['verification_requirements'],
        'submitted_height_m':next(x for x in bundle['evidence'] if x['evidence_id']=='EV-010')['observation']['guardrail_height_m'],
        'actual_status':c['status'],'actual_result':c['verification']['result'],
        'height_checks':[x for x in c['verification']['checks'] if '1.2' in x['name']],
        'expected':'Evaluate the approved structured requirements, or flag unsupported custom requirements for explicit verification.'}
    result={'scope':'local TestClient and temporary SQLite, never the public site or delivery runtime',
        'runtime':str(runtime),'probes':[first,second],
        'all_reproduced':first['reproduced'] and second['reproduced']}
    (OUTPUT/'regression-probes.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
