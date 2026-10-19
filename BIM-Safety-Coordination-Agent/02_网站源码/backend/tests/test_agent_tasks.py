from __future__ import annotations

import pytest
from pydantic import ValidationError
from test_api import analyze, client, create_case
from app import coordinator
from app.coordinator import CORE_TOOLS, TaskSpec, build_context, plan_task
from app.db import transaction
from app.control_requirements import normalize_criteria


def request_case(message, evidence='EV-001', actor='test-user'):
    response = client.post('/api/cases', json={'title': 'Agent task test', 'request_text': message,
        'actor_id': actor, 'evidence_ids': [evidence]})
    assert response.status_code == 201, response.text
    return response.json()['case']


def ask(case, message, actor='test-user'):
    response = client.post(f"/api/cases/{case['case_id']}/ask", json={
        'message': message, 'actor_id': actor, 'expected_case_version': case['version']})
    assert response.status_code == 202, response.text
    return client.get(f"/api/cases/{case['case_id']}").json()['case']


def approve_and_implement(case):
    path = f"/api/cases/{case['case_id']}"
    response = client.post(path+'/review', json={'decision':'approve', 'reviewer':'test reviewer',
        'control_version':case['control_version'], 'expected_case_version':case['version']})
    assert response.status_code == 200, response.text
    case = response.json()['case']
    response = client.post(path+'/implementation', json={'owner':'test crew',
        'expected_case_version':case['version'], 'implemented_at':'2026-10-16T09:20:00+08:00'})
    assert response.status_code == 200, response.text
    response = client.post(path+'/evidence', json={'evidence_ids':['EV-010']})
    assert response.status_code == 200, response.text
    return response.json()['case']


def modify(case, action, criteria=None):
    control = {**case['controls'][0], 'action':action}
    if criteria is None: control.pop('verification_criteria', None)
    else: control['verification_criteria'] = criteria
    response = client.post(f"/api/cases/{case['case_id']}/review", json={'decision':'modify',
        'expected_case_version':case['version'], 'new_controls':[control]})
    assert response.status_code == 200, response.text
    return response.json()['case']


def verify(case, manual=False):
    response = client.post(f"/api/cases/{case['case_id']}/verify", json={
        'after_evidence_ids':['EV-010'], 'reviewer_confirmed':True,
        'manual_checks_confirmed':manual, 'expected_case_version':case['version'],
        'as_of':'2026-10-16T09:40:00+08:00'})
    assert response.status_code == 200, response.text
    return response.json()['case']


def test_height_task_changes_executed_tools_and_checks():
    case = request_case('只检查L05区域栏杆高度是否符合要求')
    case = analyze(case['case_id'])
    assert case['status'] == 'pending_review'
    assert case['task_spec']['focus'] == ['guardrail_height']
    assert 'spatial_check' not in case['task_spec']['selected_tools']
    run = client.get(f"/api/runs/{case['last_run_id']}").json()['run']
    assert not any(event['tool'] == 'spatial_check' for event in run['events'])
    assert any(event['status'] == 'skipped' for event in run['events'])
    assert not any(check['name'] == '人员暴露' for check in case['findings'][0]['checks'])
    assert case['decision_package']['evidence'] == ['EV-001']
    assert case['decision_package']['governing_rules']
    assert case['safety_state']['model']['version'] == case['model_version']
    comprehensive = analyze(request_case('全面检查L05临边风险')['case_id'])
    assert 'spatial_check' in comprehensive['task_spec']['selected_tools']
    assert comprehensive['task_spec']['retrieval_query'] != case['task_spec']['retrieval_query']


def test_out_of_scope_requires_clarification_without_tool_calls():
    case = analyze(request_case('检查L04区域栏杆高度')['case_id'])
    assert case['status'] == 'needs_evidence'
    assert case['task_spec']['needs_clarification']
    assert 'L05' in case['task_spec']['clarification']
    run = client.get(f"/api/runs/{case['last_run_id']}").json()['run']
    assert not any(event['tool'] in CORE_TOOLS for event in run['events'])
    assert not case['controls']


def test_followup_memory_is_case_and_actor_scoped():
    case = analyze(request_case('只检查栏杆高度')['case_id'])
    old_version = case['version']
    case = ask(case, '继续刚才的检查')
    assert case['task_spec']['focus'] == ['guardrail_height']
    assert case['task_spec']['context_inherited']
    assert case['task_spec']['zone_id'] == case['zone_id']
    path = f"/api/cases/{case['case_id']}"
    messages = client.get(path+'/messages?actor_id=test-user').json()['rows']
    assert [m['role'] for m in messages] == ['user','assistant','user','assistant']
    assert client.get(path+'/messages?actor_id=different-user').json()['rows'] == []
    other = request_case('全面检查')
    assert len(client.get(f"/api/cases/{other['case_id']}/messages?actor_id=test-user").json()['rows']) == 1
    stale = client.post(path+'/ask',json={'message':'全面检查','expected_case_version':old_version})
    assert stale.status_code == 409
    # A different local actor cannot inherit the previous actor's focused task.
    case = ask(case, '继续刚才的检查', actor='different-user')
    assert case['task_spec']['focus'] == ['all']


def test_context_budget_is_bounded():
    case = request_case('全面检查')
    with transaction() as tx:
        for _ in range(10):
            tx.execute('INSERT INTO case_messages(case_id,actor_id,role,content,created_at) VALUES(?,?,?,?,?)',
                (case['case_id'],'test-user','user','高'*1500,'2026-10-16T09:00:00+08:00'))
    case['task_actor_id']='test-user'
    context=build_context(case)
    assert len(context['messages']) <= 6
    assert context['context_bytes'] <= 6000
    assert context['context_bytes'] == sum(len(m['content'].encode()) for m in context['messages'])


def test_approved_height_increase_rejects_old_12m_evidence():
    case = analyze(create_case(['EV-001'])['case_id'])
    case = modify(case, '设置栏杆高度不低于1.5 m，固定且连续。')
    assert case['controls'][0]['verification_criteria']['min_height_m'] == 1.5
    case = approve_and_implement(case)
    assert next(iter(case['review']['verification_snapshot'].values()))['min_height_m'] == 1.5
    case = verify(case, manual=True)
    assert case['status'] == 'reopened'
    assert case['verification']['result'] == 'fail'
    assert any('1.5 m' in c['name'] and c['result']=='fail' for c in case['verification']['checks'])


@pytest.mark.parametrize('manual, expected', [(False,'reopened'),(True,'closed')])
def test_custom_text_requires_separate_manual_confirmation(manual, expected):
    case = analyze(create_case(['EV-001'])['case_id'])
    case = modify(case, '安装防护栏杆并调整材料通道。')
    case = verify(approve_and_implement(case), manual)
    assert case['status'] == expected


def test_invalid_criteria_and_authorized_stage_block_new_tasks():
    case = analyze(create_case(['EV-001'])['case_id'])
    invalid = normalize_criteria({})
    invalid['min_height_m'] = 1.0
    response=client.post(f"/api/cases/{case['case_id']}/review", json={'decision':'modify',
        'new_controls':[{'action':'低栏杆','verification_criteria':invalid}]})
    assert response.status_code == 422
    case = approve_and_implement(case)
    response=client.post(f"/api/cases/{case['case_id']}/ask",json={
        'message':'全面检查','expected_case_version':case['version']})
    assert response.status_code == 409


def test_live_planner_rejects_unknown_tools_and_changed_scope(monkeypatch):
    from app import live_model
    case = request_case('只检查栏杆高度')
    valid, _ = plan_task(case, '材料转运')
    monkeypatch.setattr(coordinator, 'DEMO_MODE', False)
    monkeypatch.setattr(live_model, 'live_task_plan', lambda context: {**valid,'selected_tools':CORE_TOOLS+['shell_exec']})
    with pytest.raises(ValidationError): plan_task(case, '材料转运')
    monkeypatch.setattr(live_model, 'live_task_plan', lambda context: {**valid,'zone_id':'OTHER'})
    from app.errors import APIError
    with pytest.raises(APIError): plan_task(case, '材料转运')
    monkeypatch.setattr(live_model, 'live_task_plan', lambda context: valid)
    spec, _ = plan_task(case, '材料转运')
    assert spec['mode'] == 'live_model'


def test_exports_include_decision_state_and_approved_parameters():
    case = analyze(request_case('全面检查临边风险')['case_id'])
    path = f"/api/cases/{case['case_id']}/export"
    data = client.get(path+'?format=json').json()['case']
    assert data['task_spec'] and data['safety_state'] and data['decision_package']
    markdown = client.get(path+'?format=md').text
    assert '决策包' in markdown and 'Safety State' in markdown and 'min_height_m' in markdown


def test_live_mode_executes_planning_narrative_and_control_adapter(monkeypatch):
    """Exercise real HTTP serialization/validation against an isolated mock provider."""
    import json
    import httpx
    from app import agent, live_model, services
    case = request_case('只检查栏杆高度')
    spec, _ = plan_task(case, '材料转运')
    client_class = httpx.Client
    calls = []

    def provider(request):
        payload = json.loads(request.content)
        system = payload['messages'][0]['content']
        calls.append(system)
        context = json.loads(payload['messages'][1]['content'])
        if '安全任务协调器' in system:
            output = {**spec, 'request':context['request'], 'as_of':context['as_of'],
                'zone_id':context['zone_id'], 'mode':'live_model'}
        elif '仅action和owner' in system:
            output = {'action':context['base_control']['action'], 'owner':context['base_control']['owner']}
        else:
            output = {'summary':'根据证据及工具检查形成待审核风险候选。',
                'reasoning_basis':[{'type':'evidence','id':'EV-001'}], 'uncertainties':['演示输入待现场核实']}
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(output,ensure_ascii=False)}}]})

    transport = httpx.MockTransport(provider)
    monkeypatch.setattr(live_model.httpx, 'Client', lambda **kwargs: client_class(transport=transport, **kwargs))
    for module in (coordinator, agent, services): monkeypatch.setattr(module, 'DEMO_MODE', False)
    monkeypatch.setattr(services, 'live_model_configured', lambda: True)
    monkeypatch.setattr(agent, 'live_model_configured', lambda: True)
    monkeypatch.setattr(live_model, 'MODEL_BASE_URL', 'https://mock.invalid/v1')
    monkeypatch.setattr(live_model, 'MODEL_API_KEY', 'isolated-test-key')
    monkeypatch.setattr(live_model, 'MODEL_NAME', 'test-model')
    case = analyze(case['case_id'])
    assert case['task_spec']['mode'] == 'live_model'
    assert case['status'] == 'pending_review'
    assert len(calls) == 3
    assert case['controls'][0]['provenance'] == 'live_model_candidate_checked_against_tool_results'
    assert '真实模型' in case['findings'][0]['narrative']['label']


def test_model_failure_is_explicit_without_fallback(monkeypatch):
    from app import live_model
    case = request_case('全面检查临边风险')
    monkeypatch.setattr(coordinator, 'DEMO_MODE', False)
    def failure(context): raise live_model.LiveModelError('test provider offline')
    monkeypatch.setattr(live_model, 'live_task_plan', failure)
    response = client.post(f"/api/cases/{case['case_id']}/analyze")
    assert response.status_code == 202
    run = client.get(f"/api/runs/{response.json()['run_id']}").json()['run']
    assert run['status'] == 'failed'
    case = client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert case['status'] == 'needs_evidence' and case['analysis_incomplete']
    assert not case['decision_package']


def test_model_control_cannot_invent_engineering_values_or_owners(monkeypatch):
    from app import live_model
    from app.live_model import LiveModelError, live_control_draft
    context = {'base_control':{'action':'设置防护栏杆。', 'owner':'演示班组',
        'verification_criteria':normalize_criteria({})}}
    monkeypatch.setattr(live_model, '_structured_call', lambda *_: {'action':'栏杆高度为0.9 m','owner':'演示班组'})
    with pytest.raises(LiveModelError): live_control_draft(context)
    monkeypatch.setattr(live_model, '_structured_call', lambda *_: {'action':'设置防护','owner':'未知单位'})
    with pytest.raises(LiveModelError): live_control_draft(context)
    monkeypatch.setattr(live_model, '_structured_call', lambda *_: {'action':'栏杆高度至少1200 mm','owner':'演示班组'})
    assert live_control_draft(context)['owner'] == '演示班组'


def test_missing_model_configuration_does_not_replace_existing_task(monkeypatch):
    from app import main
    case = analyze(request_case('只检查栏杆高度')['case_id'])
    monkeypatch.setattr(main, 'DEMO_MODE', False)
    monkeypatch.setattr(main, 'live_model_configured', lambda: False)
    response = client.post(f"/api/cases/{case['case_id']}/ask", json={
        'message':'全面检查', 'expected_case_version':case['version']})
    assert response.status_code == 503
    current = client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert current['version'] == case['version']
    assert current['decision_package'] == case['decision_package']


@pytest.mark.parametrize('action', ['将栏杆高度从1.2 m提高到1.5 m。', '设置高度不低于1500 mm的连续栏杆。'])
def test_modified_text_uses_strictest_explicit_height(action):
    criteria = normalize_criteria({'action':action}, modified=True)
    assert criteria['min_height_m'] == 1.5


def test_duplicate_control_ids_cannot_overwrite_approved_requirements():
    case = analyze(create_case(['EV-001'])['case_id'])
    control = case['controls'][0]
    response=client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'modify',
        'new_controls':[control,control]})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'duplicate_control_id'
