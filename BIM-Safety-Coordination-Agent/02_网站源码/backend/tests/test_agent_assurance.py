"""Safety remains deterministic while planning, evidence lineage and recovery improve."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import reset_db,connect,transaction
from test_api import analyze,create_case

client=TestClient(app)


@pytest.fixture(autouse=True)
def isolated():
    reset_db()


def test_plan_has_typed_dependencies_and_safety_steps():
    case=client.post('/api/cases',json={'evidence_ids':['EV-003'],'request_text':'只检查L05栏杆高度'}).json()['case']
    case=analyze(case['case_id'])
    package=case['decision_package'];plan=package['execution_plan']
    names=[s['tool'] for s in plan['steps']]
    assert {'bim_query','schedule_query','evidence_check','rule_retrieval','risk_assessment'}<=set(names)
    assert 'spatial_check' not in names
    for step in plan['steps']:
        assert step['arguments']['case_id']==case['case_id']
        assert step['arguments']['model_version']==case['model_version']
        assert step['permission']=='read'
        assert all(names.index(dep)<names.index(step['tool']) for dep in step['depends_on'])
    assert plan['budget']['max_replans']==2
    assert package['assurance']['status']=='passed'


def test_evidence_lineage_keeps_simulation_units_and_rule_sources():
    case=analyze(create_case(['EV-003'])['case_id'])
    trace=case['decision_package']['evidence_trace']
    fact=next(f for f in trace['facts'] if f['property']=='guardrail_height_m')
    assert fact['value']==1.0 and fact['unit']=='m' and fact['source_id']=='EV-003'
    assert fact['source_kind']=='simulation' and fact['bim_guids']==case['bim_guids']
    assert any(n['kind']=='rule' and n['source']['pdf_page'] for n in trace['nodes'])
    assert all(edge['from'] in {n['id'] for n in trace['nodes']} and edge['to'] in {n['id'] for n in trace['nodes']} for edge in trace['edges'])
    assert trace['input_hash']


def test_missing_height_creates_targeted_gap_and_cannot_authorize():
    from app.assurance import assess_gaps
    case=create_case(['EV-003'])
    from app.tools import evidence_check
    conn=connect()
    try: inspected=evidence_check(conn,case)
    finally:conn.close()
    inspected['data']['missing_fields']=['guardrail_height_m'];inspected['data']['data_complete']=False
    gaps=assess_gaps({'case':case,'inspection':inspected,'task_spec':{'focus':['guardrail_height']}})
    assert len(gaps)==1 and gaps[0]['field']=='guardrail_height_m'
    assert gaps[0]['action']=='confirm_observation' and gaps[0]['blocking']
    missing=analyze(create_case(['EV-004'])['case_id'])
    assert missing['status']=='needs_evidence' and not missing['controls']
    assert missing['decision_package']['evidence_gaps']
    assert client.post(f"/api/cases/{missing['case_id']}/review",json={'decision':'approve'}).status_code==409


def test_structured_auditor_blocks_changed_fact_without_model_vote():
    from app.assurance import audit_decision
    case=analyze(create_case(['EV-003'])['case_id'])
    package=case['decision_package']
    trace=package['evidence_trace']
    next(f for f in trace['facts'] if f['property']=='guardrail_height_m')['value']=1.8
    result=audit_decision(case,trace,case['findings'],case['controls'],package['governing_rules'])
    assert result['status']=='blocked'
    assert any(c['code']=='fact_value_mismatch' for c in result['issues'])


def test_input_change_invalidates_snapshot_and_prevents_resume():
    from app.assurance import input_snapshot,assert_snapshot
    from app.errors import APIError
    case=create_case(['EV-003']);snapshot=input_snapshot(case['case_id'])
    with transaction() as tx:tx.execute("UPDATE cases SET as_of='2026-10-16T10:00:00+08:00' WHERE case_id=?",(case['case_id'],))
    with pytest.raises(APIError) as err:assert_snapshot(case['case_id'],snapshot)
    assert err.value.code=='stale_run_inputs'


def test_completed_analysis_is_idempotent_and_waits_for_human():
    from app.agent import execute_run
    case=analyze(create_case(['EV-003'])['case_id'])
    before=client.get(f"/api/cases/{case['case_id']}").json()
    execute_run(case['last_run_id'])
    after=client.get(f"/api/cases/{case['case_id']}").json()
    assert before['case']==after['case']
    workflow=client.get(f"/api/cases/{case['case_id']}/workflow").json()
    assert workflow['waiting_for']=='review' and workflow['checkpointed']
    assert workflow['authority']=='business_state_machine'


def test_same_case_followup_reuses_only_unchanged_read_tools():
    case=analyze(create_case(['EV-003'])['case_id'])
    response=client.post(f"/api/cases/{case['case_id']}/ask",json={'message':'只检查栏杆高度','expected_case_version':case['version']})
    assert response.status_code==202,response.text
    case=client.get(f"/api/cases/{case['case_id']}").json()['case']
    run=client.get(f"/api/runs/{case['last_run_id']}").json()['run']
    assert any(e['status']=='cached' and e['tool']=='bim_query' for e in run['events'])
    assert not any(e['status']=='cached' and e['tool']=='risk_assessment' for e in run['events'])


def test_changed_rule_after_analysis_cannot_be_approved():
    case=analyze(create_case(['EV-003'])['case_id'])
    with transaction() as tx:tx.execute("UPDATE rules SET version='changed' WHERE rule_id='JGJ-4.3.1'")
    response=client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'approve',
        'control_version':case['control_version'],'expected_case_version':case['version']})
    assert response.status_code==409
    assert response.json()['error']['code']=='stale_run_inputs'
    assert client.get(f"/api/cases/{case['case_id']}").json()['case']['status']=='pending_review'


def test_gap_path_does_not_request_model_risk_or_controls():
    case=analyze(create_case(['EV-004'])['case_id'])
    run=client.get(f"/api/runs/{case['last_run_id']}").json()['run']
    assert any(e['tool']=='bounded_replan' for e in run['events'])
    assert not any(e['tool'] in {'openai_compatible_chat','live_control_draft','demo_template'} for e in run['events'])
    assert case['decision_package']['execution_plan']['replanning']['next_action']=='await_human_evidence'


@pytest.mark.parametrize('evidence_id,status',[('EV-003','pending_review'),('EV-004','needs_evidence')])
def test_optional_tools_without_material_do_not_break_analysis(monkeypatch,evidence_id,status):
    from app import agent
    original=agent.plan_task
    def choose_optional(case,activity):
        spec,context=original(case,activity)
        spec['selected_tools']=list(dict.fromkeys(spec['selected_tools']+['activity_conflict_check','site_text_query']))
        return spec,context
    monkeypatch.setattr(agent,'plan_task',choose_optional)
    case=analyze(create_case([evidence_id])['case_id'])
    assert case['status']==status
    run=client.get(f"/api/runs/{case['last_run_id']}").json()['run']
    optional=[e for e in run['events'] if e['tool'] in {'activity_conflict_check','site_text_query'}]
    assert len(optional)==2 and all(e['status']=='succeeded' for e in optional)
    assert next(e for e in optional if e['tool']=='activity_conflict_check')['output']['data']['configured'] is False
