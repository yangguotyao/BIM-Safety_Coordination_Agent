"""Exercise the running local service with configured providers and new photo uploads."""
import json
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'BIM-Safety-Coordination-Agent/03_测试与验收/实模型版_20261019'
REPORT.mkdir(parents=True,exist_ok=True)
client = httpx.Client(base_url='http://127.0.0.1:8001/api',timeout=210)
GUID = '2riKNFXuDAvQJxT4q2Dk7a'
BEFORE = ROOT / 'data/external/s1/raw/photos_2019_05_29/cc-38570/cc-38570_20190529T083440.jpg'
AFTER = ROOT / 'data/external/s1/raw/photos_2019_06_03/cc-38570/cc-38570_20190603T080024.jpg'


def request(method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    if not response.is_success:
        raise RuntimeError(f'{path}: {response.status_code} {response.text[:1200]}')
    return response.json()


def bundle():
    value=request('GET',f'/cases/{case_id}')
    (REPORT / 'real-api-case.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return value


def analyze():
    run=request('POST',f'/cases/{case_id}/analyze')['run_id']
    for _ in range(300):
        detail=request('GET',f'/runs/{run}')['run']
        if detail['status'] in {'succeeded','failed'}:
            value=bundle()
            (REPORT / f'{run}.json').write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding='utf-8')
            if detail['status']=='failed': raise RuntimeError(detail['error'])
            print('Analysis: '+value['case']['status'],flush=True)
            return value
        time.sleep(.5)
    raise RuntimeError('Analysis did not finish in the verification window')


def upload(path,stage,captured):
    with path.open('rb') as stream:
        value=request('POST',f'/cases/{case_id}/evidence/upload',files={'file':(path.name,stream,'image/jpeg')},
            data={'stage':stage,'captured_at':captured,'note':'S1原始公开照片；与选中构件人工关联用于流程演示，非定位实测。'+path.name})
    return value['case'],value['evidence'][-1]['evidence_id']


def confirm(case,eid,height):
    return request('POST',f'/cases/{case_id}/evidence/{eid}/observation',json={
        'expected_case_version':case['version'],'source':'simulated',
        'note':'原始S1现场照片；构件关联与本演示量测为人工模拟。高度不是Qwen测量，也不声称真实整改前后对应。',
        'observation':{'guardrail_state':'present','guardrail_height_m':height,'worker_present':True,
            'drop_height_m':2.5,'boundary_is_exposed':True,'guardrail_fixed':True,
            'guardrail_continuous':True,'ppe_confirmed':True}})['case']


created=request('POST','/cases',json={'title':'实模型版 · S1新照片与模拟量测闭环',
    'request_text':'全面检查所选L05楼板区域临边防护高度与人员暴露，基于实际工具和有效规范形成待审核措施。',
    'actor_id':'live-integration','as_of':'2019-05-29T08:34:40+08:00','evidence_ids':[],
    'inspection_context':{'guid':GUID,'boundary_confirmed':True,'activity':'S1现场照片关联的楼板安全巡检演示',
        'owner':'实模型联调演示班组','planned_start':'2019-05-29T08:00:00+08:00',
        'planned_end':'2019-06-03T12:00:00+08:00','exposure_distance_m':.6}})
case_id=created['case']['case_id']
print('Case: '+case_id,flush=True)
case,before=upload(BEFORE,'before','2019-05-29T08:34:40+08:00')
value=analyze()
assert value['case']['status']=='needs_evidence'
assert value['evidence'][0]['perception']['model']=='qwen3.7-plus'
assert not value['evidence'][0]['perception']['confirmed']
case=confirm(value['case'],before,1.0)
value=analyze()
case=value['case']
assert case['status']=='pending_review'
assert case['bim_guids']==[GUID]
assert case['rule_ids']==['JGJ-4.3.1'],case['rule_ids']
case=request('POST',f'/cases/{case_id}/review',json={'decision':'approve',
    'control_version':case['control_version'],'expected_case_version':case['version']})['case']
case=request('POST',f'/cases/{case_id}/implementation',json={'owner':'实模型联调演示班组',
    'implemented_at':'2019-06-03T07:50:00+08:00','expected_case_version':case['version'],
    'comment':'人工记录的整改演示，非原项目真实实施事实。'})['case']
case,after=upload(AFTER,'after','2019-06-03T08:00:24+08:00')
perception=request('POST',f'/cases/{case_id}/evidence/{after}/inspect')['perception']
assert perception['model']=='qwen3.7-plus'
case=confirm(case,after,1.3)
value=request('POST',f'/cases/{case_id}/verify',json={'after_evidence_ids':[after],
    'reviewer_confirmed':True,'expected_case_version':case['version'],'as_of':'2019-06-03T08:10:00+08:00'})
assert value['case']['status']=='closed',value['case']['verification']
value=bundle()
purposes={call['purpose'] for call in value['model_calls'] if call['status']=='succeeded'}
assert {'image_observation','task_plan','risk_summary','control_draft'} <= purposes
assert all(call['usage'].get('total_tokens',0)>0 for call in value['model_calls'] if call['status']=='succeeded')
print(json.dumps({'case_id':case_id,'status':value['case']['status'],'guid':GUID,
    'rules':value['case']['rule_ids'],'model_calls':len(value['model_calls']),
    'models':sorted({call['model'] for call in value['model_calls']}),
    'total_tokens':sum(call['usage'].get('total_tokens',0) for call in value['model_calls'])},ensure_ascii=False),flush=True)
