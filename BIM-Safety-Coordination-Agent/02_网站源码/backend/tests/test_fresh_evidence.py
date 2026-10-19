from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import reset_db, connect
from app import vision, tools
from test_api import analyze

client = TestClient(app)
GUID = '0FOHK4aT910wgskSbVHn0U'
IMAGE = Path(__file__).resolve().parents[3] / '01_资料与依据/07_案例与验收模板/演示证据图/EV-001.png'
OBSERVATION = dict(guardrail_state='absent',guardrail_height_m=None,worker_present=True,
                   drop_height_m=2.5,boundary_is_exposed=True,guardrail_fixed=False,
                   guardrail_continuous=False,ppe_confirmed=True)


@pytest.fixture(autouse=True)
def isolated_case():
    reset_db()


def upload(case, stage):
    response = client.post(f"/api/cases/{case['case_id']}/evidence/upload", files={'file':('new-input.png',IMAGE.read_bytes(),'image/png')},
                           data={'captured_at':'2026-10-16T09:30:00+08:00' if stage=='after' else case['as_of'], 'stage':stage})
    assert response.status_code==200,response.text
    bundle=response.json()
    return bundle['case'],bundle['evidence'][-1]


def confirm(case, evidence, observation):
    response=client.post(f"/api/cases/{case['case_id']}/evidence/{evidence['evidence_id']}/observation",
        json={'observation':observation,'source':'simulated','note':'isolated test input',
              'expected_case_version':case['version']})
    assert response.status_code==200,response.text
    return response.json()['case']


@pytest.mark.parametrize('after_height,expected',[(1.1,'reopened'),(1.5,'closed')])
def test_new_images_require_confirmation_and_use_approved_checks(monkeypatch,after_height,expected):
    context={'guid':GUID,'boundary_confirmed':True,'activity':'独立新输入任务','owner':'新输入班组',
             'planned_start':'2026-10-16T08:00:00+08:00','planned_end':'2026-10-16T12:00:00+08:00'}
    response=client.post('/api/cases',json={'evidence_ids':[],'bim_guids':[GUID],
        'inspection_context':context,'as_of':'2026-10-16T09:00:00+08:00','request_text':'全面检查临边防护'})
    assert response.status_code==201,response.text
    case=response.json()['case']
    assert case['evidence_ids']==[]
    assert case['zone_id']!='ZONE-S1-L05-EDGE'
    case,before=upload(case,'before')
    monkeypatch.setattr(vision,'chat_json',lambda **kwargs:{'summary':'明确为示意图，待人工确认',
        'image_kind':'diagram','observation':{**OBSERVATION,'guardrail_height_m':9,'worker_point_m':[1,2,3]}})
    perceived=client.post(f"/api/cases/{case['case_id']}/evidence/{before['evidence_id']}/inspect")
    assert perceived.status_code==200,perceived.text
    assert perceived.json()['perception']['observation']['guardrail_height_m'] is None
    assert perceived.json()['perception']['observation']['worker_point_m'] is None
    conn=connect()
    try: assert tools.evidence_check(conn,case)['data']['data_complete'] is False
    finally: conn.close()
    case=confirm(case,before,OBSERVATION)
    case=analyze(case['case_id'])
    assert case['status']=='pending_review'
    assert case['controls'][0]['owner']=='新输入班组'
    response=client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'approve',
        'control_version':case['control_version'],'expected_case_version':case['version']})
    assert response.status_code==200,response.text
    case=response.json()['case']
    response=client.post(f"/api/cases/{case['case_id']}/implementation",json={'owner':'新输入班组',
        'implemented_at':'2026-10-16T09:20:00+08:00','expected_case_version':case['version']})
    assert response.status_code==200,response.text
    case,after=upload(response.json()['case'],'after')
    assert case['status']=='pending_verification'
    case=confirm(case,after,{**OBSERVATION,'guardrail_state':'present',
        'guardrail_height_m':after_height,'guardrail_fixed':True,'guardrail_continuous':True})
    response=client.post(f"/api/cases/{case['case_id']}/verify",json={
        'after_evidence_ids':[after['evidence_id']],'reviewer_confirmed':True,
        'expected_case_version':case['version'],'as_of':'2026-10-16T09:40:00+08:00'})
    assert response.status_code==200,response.text
    assert response.json()['case']['status']==expected


def test_boundary_confirmation_and_real_geometry_context():
    options=client.get('/api/inspection-context',params={'guid':GUID}).json()
    assert options['element']['guid']==GUID
    assert options['edge_options']
    response=client.post('/api/cases',json={'evidence_ids':[], 'inspection_context':{
        'guid':GUID,'boundary_confirmed':False,'activity':'检查','owner':'班组',
        'planned_start':'2026-10-16T08:00:00+08:00','planned_end':'2026-10-16T12:00:00+08:00'}})
    assert response.status_code==422
    assert response.json()['error']['code']=='boundary_confirmation_required'
    rules=client.get('/api/rules',params={'as_of':'1900-01-01T09:00:00+08:00','q':'临边'}).json()
    assert rules['results']==[]
