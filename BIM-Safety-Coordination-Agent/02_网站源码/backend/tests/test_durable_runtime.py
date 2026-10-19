import os
import subprocess
import sys
import json
import pytest
from app import agent,durable
from app.db import reset_db,connect,transaction
from app.errors import APIError
from app.services import start_analysis
from test_api import client,create_case,analyze


@pytest.fixture(autouse=True)
def isolated():reset_db()


def test_expired_worker_recovers_checkpoint_without_repeating_completed_tools():
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id'])
    code="from app import agent; import os; agent._schedule=lambda *args:os._exit(77); agent.execute_run("+repr(run_id)+")"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=30,env=os.environ.copy())
    assert result.returncode==77,result.stderr.decode(errors='replace')
    conn=connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM agent_events WHERE run_id=? AND tool='bim_query'",(run_id,)).fetchone()[0]==1
        assert conn.execute('SELECT state FROM run_jobs WHERE run_id=?',(run_id,)).fetchone()[0]=='running'
    finally:conn.close()
    with transaction() as tx:tx.execute('UPDATE run_jobs SET lease_until=0 WHERE run_id=?',(run_id,))
    result=subprocess.run([sys.executable,'-c',"from app.agent import execute_run; execute_run("+repr(run_id)+")"],capture_output=True,timeout=30,env=os.environ.copy())
    assert result.returncode==0,result.stderr.decode(errors='replace')
    case=client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert case['status']=='pending_review'
    conn=connect()
    try:
        assert conn.execute("SELECT COUNT(*) FROM agent_events WHERE run_id=? AND tool='bim_query'",(run_id,)).fetchone()[0]==1
        job=conn.execute('SELECT * FROM run_jobs WHERE run_id=?',(run_id,)).fetchone()
        assert job['state']=='completed' and job['recoveries']==1
    finally:conn.close()


def test_input_tampering_during_analysis_blocks_commit(monkeypatch):
    original=agent._knowledge
    def tamper(state,trace):
        result=original(state,trace)
        with transaction() as tx:tx.execute("UPDATE cases SET as_of='2026-10-16T10:30:00+08:00' WHERE case_id=?",(state['case_id'],))
        return result
    monkeypatch.setattr(agent,'_knowledge',tamper)
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id']);agent.execute_run(run_id)
    case=client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert case['status']=='needs_evidence' and not case['controls']
    assert client.post(f'/api/runs/{run_id}/resume').status_code==409


def test_transient_failure_resumes_at_failed_node(monkeypatch):
    original=agent._knowledge
    monkeypatch.setattr(agent,'_knowledge',lambda *_:(_ for _ in ()).throw(RuntimeError('temporary outage')))
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id']);agent.execute_run(run_id)
    assert client.get(f'/api/runs/{run_id}').json()['run']['status']=='failed'
    monkeypatch.setattr(agent,'_knowledge',original)
    response=client.post(f'/api/runs/{run_id}/resume')
    assert response.status_code==200,response.text
    run=client.get(f'/api/runs/{run_id}').json()['run']
    assert run['status']=='succeeded'
    assert len([e for e in run['events'] if e['tool']=='bim_query'])==1


def test_cancelled_job_cannot_analyze_or_authorize():
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id'])
    durable.cancel_run(run_id);agent.execute_run(run_id)
    assert client.get(f'/api/runs/{run_id}').json()['run']['status']=='failed'
    assert client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'approve'}).status_code==409
    with pytest.raises(APIError):durable.resume_run(run_id)


def test_budget_is_enforced_before_additional_model_calls():
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id'])
    with transaction() as tx:tx.execute('UPDATE run_artifacts SET plan_json=? WHERE run_id=?',(json.dumps({'budget':{'max_model_calls':0}}),run_id))
    with pytest.raises(APIError) as err:durable.guard_run(run_id,model_call=True)
    assert err.value.code=='run_budget_exceeded'


def test_lifecycle_resume_cannot_grant_approval():
    case=analyze(create_case(['EV-003'])['case_id'])
    state=durable.sync_workflow(case['case_id'])
    assert state['waiting_for']=='review'
    with durable.checkpoints() as saver:
        graph=durable.lifecycle_graph(saver)
        graph.invoke(durable.Command(resume={'case_version':case['version'],'approved':True}),
            config={'configurable':{'thread_id':state['thread_id']}})
    current=client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert current['status']=='pending_review' and current['review'] is None


def test_crash_after_business_commit_does_not_write_analysis_twice():
    case=create_case(['EV-003']);_,run_id=start_analysis(case['case_id'])
    code="from app import agent; import os; original=agent._update_run; agent._update_run=lambda rid,status,*a:os._exit(78) if status=='succeeded' else original(rid,status,*a); agent.execute_run("+repr(run_id)+")"
    first=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=30,env=os.environ.copy())
    assert first.returncode==78,first.stderr.decode(errors='replace')
    before=client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert before['status']=='pending_review'
    with transaction() as tx:tx.execute('UPDATE run_jobs SET lease_until=0 WHERE run_id=?',(run_id,))
    agent.execute_run(run_id)
    after=client.get(f"/api/cases/{case['case_id']}").json()['case']
    assert after==before
    assert client.get(f'/api/runs/{run_id}').json()['run']['status']=='succeeded'
    conn=connect()
    try:assert conn.execute("SELECT COUNT(*) FROM case_events WHERE case_id=? AND event='analysis_completed'",(case['case_id'],)).fetchone()[0]==1
    finally:conn.close()
