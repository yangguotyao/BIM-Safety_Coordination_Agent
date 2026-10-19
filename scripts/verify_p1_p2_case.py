"""Run a fresh, explicitly simulated P1/P2 Case against the local live providers."""
import json
import os
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'BIM-Safety-Coordination-Agent/03_测试与验收/P1-P2_20261019'
REPORT.mkdir(parents=True,exist_ok=True)
client=httpx.Client(base_url=os.getenv('BIM_DEMO_API','http://127.0.0.1:8003/api'),timeout=210)
GUID='2riKNFXuDAvQJxT4q2Dk7a'
BEFORE=ROOT/'data/external/s1/raw/photos_2019_05_29/cc-38570/cc-38570_20190529T083440.jpg'
AFTER=ROOT/'data/external/s1/raw/photos_2019_06_03/cc-38570/cc-38570_20190603T080024.jpg'


def request(method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    if not response.is_success: raise RuntimeError(f'{path}: {response.status_code} {response.text[:1800]}')
    return response.json()


def save(value,name='live-case.json'):
    (REPORT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    return value


def bundle():
    return save(request('GET',f'/cases/{case_id}'))


def analyze():
    run=request('POST',f'/cases/{case_id}/analyze')['run_id']
    print('Run: '+run,flush=True)
    for _ in range(420):
        detail=request('GET',f'/runs/{run}')['run']
        if detail['status'] in {'succeeded','failed'}:
            value=bundle();save(detail,run+'.json')
            if detail['status']=='failed': raise RuntimeError(detail['error'])
            print('Analysis: '+value['case']['status'],flush=True)
            return value
        time.sleep(.5)
    raise RuntimeError('Analysis did not finish in the verification window')


def upload(path,stage,captured):
    with path.open('rb') as stream:
        value=request('POST',f'/cases/{case_id}/evidence/upload',files={'file':(path.name,stream,'image/jpeg')},
            data={'stage':stage,'captured_at':captured,'note':'S1原始公开照片；构件关联与观察量测为人工模拟，不声称真实整改前后对应。'})
    return value['case'],value['evidence'][-1]['evidence_id']


def confirm(case,eid):
    return request('POST',f'/cases/{case_id}/evidence/{eid}/observation',json={
        'expected_case_version':case['version'],'source':'simulated',
        'note':'演示编制观察；高度、固定情况和构件关联由人工模拟，不是图像模型测量或原项目实测。',
        'observation':{'guardrail_state':'present','guardrail_height_m':1.3,'worker_present':True,
            'drop_height_m':2.5,'boundary_is_exposed':True,'guardrail_fixed':True,
            'guardrail_continuous':True,'ppe_confirmed':True}})['case']


case_id=os.getenv('BIM_RESUME_CASE')
if case_id:
    value=bundle();print('Resume: '+case_id,flush=True)
else:
    value=request('POST','/cases',json={'title':'P1 / P2 · 多工种错时与文本澄清闭环',
        'request_text':'检查所选楼板的人员暴露、防护状态、多工种时间与三维范围冲突，并核对巡检文字与确认观察的差异。',
        'actor_id':'p1-p2-integration','as_of':'2019-05-29T08:34:40+08:00','evidence_ids':[],
        'inspection_context':{'guid':GUID,'boundary_confirmed':True,'activity':'05层板边多工种安全检查',
            'owner':'演示协调员','planned_start':'2019-05-29T08:00:00+08:00',
            'planned_end':'2019-06-03T12:00:00+08:00','exposure_distance_m':.6}})
    case=value['case'];case_id=case['case_id'];print('Case: '+case_id,flush=True)
    save(value)
    value=request('PUT',f'/cases/{case_id}/scope',json={'guid':GUID,'edge_index':1,
        'boundary_confirmed':True,'exposure_distance_m':.7,'worker_point_source':'simulated','expected_case_version':case['version']})
    point=value['case']['scope']['worker_point_m'];case=value['case']
    assert value['spatial']['data']['distance_m']==.7,value['spatial']
    case,before=upload(BEFORE,'before','2019-05-29T08:34:40+08:00')
    assert request('POST',f'/cases/{case_id}/evidence/{before}/inspect')['perception']['model']=='qwen3.7-plus'
    case=confirm(case,before)
    activities=[{'task_id':'ACT-P1-01','activity':'板边材料转运','trade':'运输班组','owner':'演示运输负责人',
        'planned_start':'2019-05-29T08:00:00+08:00','planned_end':'2019-05-29T10:00:00+08:00','bim_guids':[GUID],
        'workspace':{'min':[point[0]-2,point[1]-2,point[2]],'max':[point[0]+2,point[1]+2,point[2]+2]}},
        {'task_id':'ACT-P1-02','activity':'相邻区域安装','trade':'安装班组','owner':'演示安装负责人',
        'planned_start':'2019-05-29T09:00:00+08:00','planned_end':'2019-05-29T11:00:00+08:00','bim_guids':[GUID],
        'workspace':{'min':[point[0]-1,point[1]-1,point[2]],'max':[point[0]+3,point[1]+3,point[2]+2]}}]
    value=request('PUT',f'/cases/{case_id}/activity-plan',json={'activities':activities,
        'reason':'编制同区域多工种交叉作业演示计划','expected_case_version':case['version']})
    assert len(value['coordination']['conflicts'])==1
    value=request('POST',f'/cases/{case_id}/site-notes',json={'title':'05层巡检记录（演示编制）',
        'source':'人工编制的演示巡检记录','captured_at':'2019-05-29T08:30:00+08:00',
        'body':'临边防护已设置，防护高度1.3m。\n该区域未见人员。', 'expected_case_version':value['case']['version']})
if not value['site_text']['complete']:
    value=analyze();save(value,'01-text-conflict.json')
    assert value['case']['status']=='needs_evidence'
    assert any(c['field']=='worker_present' for c in value['site_text']['conflicts'])
    for conflict in value['site_text']['conflicts']:
        if conflict.get('resolution'): continue
        value=request('POST',f'/cases/{case_id}/site-notes/resolve',json={
            'conflict_id':conflict['conflict_id'],'observation_hash':conflict['observation_hash'],
            'decision':'retain_observation','reason':'演示记录中的无人描述与本Case已确认的模拟观察不一致；保留确认观察，将该文字记为不可靠。',
            'expected_case_version':value['case']['version']})
assert value['evidence'][0]['observation']['worker_present'] is True
if value['case']['status'] not in {'approved','rectifying','pending_verification','closed'}:
    value=analyze();save(value,'02-pending-review.json');case=value['case']
    assert case['status']=='pending_review'
    assert any(f.get('kind')=='coordination' for f in case['findings'])
    assert any(c['verification_criteria'].get('coordination_required') for c in case['controls'])
    case=request('POST',f'/cases/{case_id}/review',json={'decision':'approve','reviewer':'演示安全员',
        'comment':'批准错时作业措施，保留两项活动及责任主体。','control_version':case['control_version'],
        'expected_case_version':case['version']})['case']
else:
    case=value['case']
activities=value['activity_plan']['activities']
activities[1].update(planned_start='2019-05-29T10:00:00+08:00',planned_end='2019-05-29T12:00:00+08:00')
value=request('PUT',f'/cases/{case_id}/activity-plan',json={'activities':activities,
    'reason':'按已批准措施将安装调整至转运结束后，保留范围和责任主体。','expected_case_version':case['version']})
assert value['case']['status']=='approved'
assert value['coordination']['conflicts']==[]
assert value['case']['review']['activity_plan_revision']==1
save(value,'03-plan-adjusted.json');case=value['case']
case=request('POST',f'/cases/{case_id}/implementation',json={'owner':'演示协调员',
    'implemented_at':'2019-06-03T07:50:00+08:00','expected_case_version':case['version'],
    'comment':'演示实施记录：已按批准措施错时安排并复核工作范围。'})['case']
case,after=upload(AFTER,'after','2019-06-03T08:00:24+08:00')
assert request('POST',f'/cases/{case_id}/evidence/{after}/inspect')['perception']['model']=='qwen3.7-plus'
case=confirm(case,after)
value=request('POST',f'/cases/{case_id}/verify',json={'after_evidence_ids':[after],
    'reviewer_confirmed':True,'expected_case_version':case['version'],'as_of':'2019-06-03T08:10:00+08:00'})
assert value['case']['status']=='closed',value['case']['verification']
value=bundle()
purposes={c['purpose'] for c in value['model_calls'] if c['status']=='succeeded'}
assert {'image_observation','text_observation','task_plan','risk_summary','control_draft'}<=purposes,purposes
summary={'case_id':case_id,'status':value['case']['status'],'guid':GUID,'plan_revision':value['activity_plan']['revision'],
    'models':sorted({c['model'] for c in value['model_calls']}),'model_calls':len(value['model_calls']),
    'total_tokens':sum(c['usage'].get('total_tokens',0) for c in value['model_calls']),
    'evidence_note':'真实公开照片；构件关联、计划、文字记录及量测为明确标注的演示数据。'}
save(summary,'summary.json');print(json.dumps(summary,ensure_ascii=False),flush=True)
