"""Offline, isolated engineering replay. No live LLM calls or operator DB writes.

This is a controlled routing/cache ablation, not a paper's LLM accuracy study.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

backend=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(backend))
runtime=Path(tempfile.mkdtemp(prefix='bim-policy-eval-'))
os.environ.update(RUNTIME_DIR=str(runtime),DB_PATH=str(runtime/'app.db'),DEMO_MODE='true')
for key in ['MODEL_BASE_URL','MODEL_API_KEY','MODEL_NAME','VISION_BASE_URL','VISION_API_KEY','VISION_MODEL']:os.environ[key]=''
from fastapi.testclient import TestClient
from app.main import app
from app import agent
from app.db import reset_db

client=TestClient(app)
original_graph=agent._build_graph;original_cache=agent.cache_key
clock='2026-10-16T09:00:00+08:00'


def call(path,body=None):
    response=client.get('/api'+path) if body is None else client.post('/api'+path,json=body)
    assert response.status_code<300,(path,response.status_code,response.text)
    return response.json()


def analyze(caseid):
    call('/cases/'+caseid+'/analyze',{})
    bundle=call('/cases/'+caseid)
    assert bundle['runs'][0]['status']=='succeeded',bundle['runs'][0]
    return bundle


def inspect_case(eid,request='全面检查L05临边防护和人员暴露'):
    return analyze(call('/cases',{'evidence_ids':[eid],'as_of':clock,'request_text':request})['case']['case_id'])


def rectify(bundle,eid):
    case=bundle['case'];path='/cases/'+case['case_id']
    call(path+'/review',{'decision':'approve','control_version':case['control_version'],'expected_case_version':case['version']})
    call(path+'/implementation',{'implemented_at':'2026-10-16T09:20:00+08:00'})
    case=call(path+'/evidence',{'evidence_ids':[eid]})['case']
    return call(path+'/verify',{'after_evidence_ids':[eid],'reviewer_confirmed':True,'as_of':'2026-10-16T09:40:00+08:00','expected_case_version':case['version']})


def metric(name,bundle,expected_status,expected_result):
    case=bundle['case'];run=call('/runs/'+case['last_run_id'])['run']
    risk=case['findings'][0]['result'] if case['findings'] else None
    return {'scenario':name,'status':case['status'],'risk_result':risk,'expected_status':expected_status,'expected_result':expected_result,
        'correct':case['status']==expected_status and risk==expected_result,
        'cached_read_results':sum(e['status']=='cached' for e in run['events']),
        'summary_steps':sum(e['tool']=='demo_template' for e in run['events']),
        'live_model_calls':len(run['model_calls']),'evidence_gap_count':len(case['decision_package'].get('evidence_gaps',[]))}


def run(mode):
    reset_db();agent._build_graph=lambda saver=None:original_graph(saver,adaptive=mode=='bounded_adaptive')
    agent.cache_key=original_cache if mode=='bounded_adaptive' else lambda *_:None
    started=time.monotonic();rows=[]
    for eid,name,result,status in [('EV-007','正常检查','no_issue_in_checked_items','pending_review'),('EV-001','防护缺失','risk_candidate','pending_review'),
        ('EV-003','栏杆偏低','risk_candidate','pending_review'),('EV-004','关键观察未知','needs_evidence','needs_evidence'),
        ('EV-005','时段不匹配','needs_evidence','needs_evidence'),('EV-009','防护状态未知','needs_evidence','needs_evidence')]:
        bundle=inspect_case(eid);row=metric(name,bundle,status,result)
        if status=='needs_evidence':row['approval_blocked']=client.post('/api/cases/'+bundle['case']['case_id']+'/review',json={'decision':'approve'}).status_code==409
        rows.append(row)
    rows.append(metric('超出楼层范围',inspect_case('EV-003','检查L04栏杆高度'),'needs_evidence','needs_evidence'))
    for eid,name,status in [('EV-010','整改后复核通过','closed'),('EV-006','整改后复核失败','reopened')]:
        rows.append(metric(name,rectify(inspect_case('EV-003'),eid),status,'risk_candidate'))
    # Same image/Case: initially unknown height, then an explicit simulated input.
    case=call('/cases',{'evidence_ids':[],'as_of':clock,'request_text':'全面检查L05临边防护和人员暴露'})['case']
    image=backend.parents[1]/'01_资料与依据/07_案例与验收模板/演示证据图/EV-003.png'
    response=client.post('/api/cases/'+case['case_id']+'/evidence/upload',files={'file':('controlled.png',image.read_bytes(),'image/png')},data={'captured_at':clock,'stage':'before'})
    assert response.status_code==200,response.text
    bundle=response.json();case=bundle['case'];eid=case['evidence_ids'][0]
    observation={'guardrail_state':'present','guardrail_height_m':None,'worker_present':True,'drop_height_m':2.5,
        'boundary_is_exposed':True,'guardrail_fixed':True,'guardrail_continuous':True,'ppe_confirmed':True}
    for height,name,status,result in [(None,'补证前高度未知','needs_evidence','needs_evidence'),(1.0,'人工补证后局部重算','pending_review','risk_candidate')]:
        observation['guardrail_height_m']=height
        bundle=call('/cases/'+case['case_id']+'/evidence/'+eid+'/observation',{'observation':observation,'source':'simulated','note':'隔离的工程回放输入，非现场实测','expected_case_version':case['version']})
        bundle=analyze(case['case_id']);case=bundle['case'];rows.append(metric(name,bundle,status,result))
    return {'mode':mode,'cases':rows,'correct':sum(r['correct'] for r in rows),'total':len(rows),
        'false_clearances':sum(r['expected_result']!='no_issue_in_checked_items' and r['risk_result']=='no_issue_in_checked_items' for r in rows),
        'cached_read_results':sum(r['cached_read_results'] for r in rows),'summary_steps':sum(r['summary_steps'] for r in rows),
        'elapsed_ms':round((time.monotonic()-started)*1000),'live_model_calls':sum(r['live_model_calls'] for r in rows)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    results=[run('fixed_sequence'),run('bounded_adaptive')]
    report={'kind':'isolated_deterministic_engineering_replay','data_nature':'预置示意图与明确标注的人工模拟观察',
        'comparison':'仅对补证路由与只读结果复用作控制对照；使用相同工程规则、工具、资料和验收条件',
        'limitations':'无真实大模型效果、费用或论文统计显著性结论；领域标注测试集与多次真实模型实验另行进行。',
        'results':results}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{key:r[key] for key in ['mode','correct','total','false_clearances','cached_read_results','summary_steps','live_model_calls']} for r in results],ensure_ascii=False))
    assert all(r['correct']==r['total'] and r['false_clearances']==0 for r in results)


if __name__=='__main__':main()
