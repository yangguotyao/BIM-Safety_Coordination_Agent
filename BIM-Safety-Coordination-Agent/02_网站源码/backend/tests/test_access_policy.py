import hashlib
import pytest
from app import access
from app.db import reset_db,transaction
from test_api import client,create_case,analyze


@pytest.fixture(autouse=True)
def isolated():reset_db()


def token(role,projects=None):
    value='test-only-'+role+'-'+str(projects)
    with transaction() as tx:tx.execute('INSERT INTO access_tokens(token_hash,label,role,projects_json) VALUES(?,?,?,?)',
        (hashlib.sha256(value.encode()).hexdigest(),'测试'+role,role,__import__('json').dumps(projects or ['S1-DEMO'])))
    return {'Authorization':'Bearer '+value}


def test_viewer_cannot_analyze_or_approve_even_with_spoofed_name():
    case=analyze(create_case(['EV-003'])['case_id']);headers=token('viewer')
    assert client.get(f"/api/cases/{case['case_id']}",headers=headers).status_code==200
    response=client.post(f"/api/cases/{case['case_id']}/review",headers=headers,json={
        'decision':'approve','reviewer':'管理员','control_version':case['control_version']})
    assert response.status_code==403
    assert client.get(f"/api/cases/{case['case_id']}").json()['case']['status']=='pending_review'


def test_reviewer_can_review_but_cannot_record_rectification():
    case=analyze(create_case(['EV-003'])['case_id']);headers=token('reviewer')
    response=client.post(f"/api/cases/{case['case_id']}/review",headers=headers,json={
        'decision':'approve','control_version':case['control_version']})
    assert response.status_code==200,response.text
    assert client.post(f"/api/cases/{case['case_id']}/implementation",headers=headers,json={}).status_code==403


def test_token_project_scope_applies_to_case_lists_and_direct_access():
    case=create_case(['EV-003']);headers=token('viewer',['OTHER'])
    assert client.get(f"/api/cases/{case['case_id']}",headers=headers).status_code==403
    assert client.get('/api/cases',headers=headers).json()['rows']==[]
    assert client.get('/api/evidence',headers=headers).json()['rows']==[]


def test_strict_mode_requires_valid_token_and_preserves_local_default(monkeypatch):
    assert client.get('/api/access/session').json()['mode']=='local_demo'
    monkeypatch.setattr(access,'ACCESS_MODE','token')
    assert client.get('/api/cases').status_code==401
    assert client.get('/api/cases',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/api/cases',headers=token('viewer')).status_code==200


def test_public_demo_mode_skips_token_gate(monkeypatch):
    monkeypatch.setattr(access,'ACCESS_MODE','public_demo')
    response=client.get('/api/access/session')
    assert response.status_code==200
    assert response.json()=={
        'label':'公开演示访问者','role':'admin','projects':['*'],'mode':'public_demo'}


def test_browser_session_uses_httponly_cookie_and_can_read_scoped_images(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(access,'ACCESS_MODE','token')
    browser=TestClient(app)
    response=browser.get('/api/access/session',headers=token('viewer'))
    assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=strict' in response.headers['set-cookie']
    assert browser.get('/api/files/evidence/EV-010').status_code==200
    assert browser.post('/api/access/logout').status_code==200
    assert browser.get('/api/cases').status_code==401


def test_foreign_origin_cannot_use_local_demo_privileges():
    assert client.post('/api/cases',headers={'Origin':'https://unrelated.invalid'},json={}).status_code==403
