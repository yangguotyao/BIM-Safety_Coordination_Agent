"""The built-in rectification diagrams must work without uploading a new file."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import reset_db
from test_api import create_case,analyze

client=TestClient(app)


@pytest.fixture(autouse=True)
def isolated_case():
    reset_db()


def approved(before):
    case=analyze(create_case([before],'内置整改资料验收')['case_id'])
    response=client.post(f"/api/cases/{case['case_id']}/review",json={
        'decision':'approve','reviewed_at':'2026-10-16T09:10:00+08:00',
        'control_version':case['control_version'],'expected_case_version':case['version']})
    assert response.status_code==200,response.text
    return response.json()['case']


@pytest.mark.parametrize('before,after',[('EV-001','EV-002'),('EV-003','EV-010')])
def test_builtin_material_closes_matching_risk_without_upload(before,after):
    case=approved(before)
    materials=client.get('/api/evidence',params={'stage':'after','zone_id':case['zone_id']}).json()['rows']
    original=next(item for item in materials if item['evidence_id']==after)
    assert original['source']=='seed' and original['observation']['simulated'] is True
    assert original['bim_guids']==case['bim_guids']
    assert client.get(original['image_url']).status_code==200
    response=client.post(f"/api/cases/{case['case_id']}/implementation",json={
        'owner':'演示整改班组','implemented_at':'2026-10-16T09:20:00+08:00',
        'comment':'复用内置模拟整改资料','expected_case_version':case['version']})
    assert response.status_code==200,response.text
    response=client.post(f"/api/cases/{case['case_id']}/evidence",json={'evidence_ids':[after]})
    assert response.status_code==200,response.text
    bundle=response.json();case=bundle['case']
    assert case['status']=='pending_verification' and case['evidence_ids']==[before,after]
    attached=next(item for item in bundle['evidence'] if item['evidence_id']==after)
    assert attached['captured_at']==original['captured_at']
    assert attached['observation']==original['observation']
    response=client.post(f"/api/cases/{case['case_id']}/verify",json={
        'after_evidence_ids':[after],'reviewer_confirmed':True,
        'as_of':'2026-10-16T09:40:00+08:00','expected_case_version':case['version']})
    assert response.status_code==200,response.text
    assert response.json()['case']['status']=='closed'
    assert response.json()['case']['verification']['result']=='pass_in_demo_scope'


def test_old_builtin_material_does_not_advance_to_verification():
    case=approved('EV-003')
    response=client.post(f"/api/cases/{case['case_id']}/implementation",json={
        'implemented_at':'2026-10-16T09:40:00+08:00','expected_case_version':case['version']})
    assert response.status_code==200,response.text
    response=client.post(f"/api/cases/{case['case_id']}/evidence",json={'evidence_ids':['EV-010']})
    assert response.json()['case']['status']=='rectifying'
    response=client.post(f"/api/cases/{case['case_id']}/verify",json={
        'after_evidence_ids':['EV-010'],'reviewer_confirmed':True,'as_of':'2026-10-16T09:50:00+08:00'})
    assert response.status_code==409


def test_builtin_material_cannot_be_relabelled_as_another_region():
    response=client.post('/api/cases',json={'evidence_ids':[],'inspection_context':{
        'guid':'2riKNFXuDAvQJxT4q2Dk7a','boundary_confirmed':True,'activity':'其他构件检查','owner':'演示班组',
        'planned_start':'2026-10-16T08:00:00+08:00','planned_end':'2026-10-16T12:00:00+08:00'}})
    assert response.status_code==201,response.text
    case=response.json()['case']
    response=client.post(f"/api/cases/{case['case_id']}/evidence",json={'evidence_ids':['EV-010']})
    assert response.status_code==422
    assert response.json()['error']['code']=='evidence_scope_mismatch'
