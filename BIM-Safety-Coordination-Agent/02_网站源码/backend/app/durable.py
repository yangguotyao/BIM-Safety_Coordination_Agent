"""Local durable execution. Business services alone authorize and close Cases."""
from __future__ import annotations
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import TypedDict
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph,START,END
from langgraph.types import interrupt,Command
from .config import RUNTIME_DIR
from .db import connect,transaction,loads
from .errors import APIError
from .tools import now_iso,parse_dt
from .assurance import assert_snapshot

LOG=logging.getLogger(__name__)
OWNER=f'{os.getpid()}-{uuid.uuid4().hex}'
LEASE_SECONDS=18
_stop=threading.Event();_wake=threading.Event();_worker=None
_workflow_lock=threading.RLock()
WAITING={'draft':'analysis','analyzing':'analysis','needs_evidence':'evidence','pending_review':'review',
    'approved':'implementation','rectifying':'after_evidence','pending_verification':'verification','reopened':'analysis',
    'closed':'complete','rejected':'rejected'}


@contextmanager
def checkpoints():
    with SqliteSaver.from_conn_string(str(RUNTIME_DIR/'agent-checkpoints.sqlite')) as saver:
        saver.conn.execute('PRAGMA journal_mode=WAL')
        saver.conn.execute('PRAGMA busy_timeout=30000')
        yield saver


def guard_run(run_id:str|None,*,model_call=False):
    if not run_id:return
    conn=connect()
    try:
        job=conn.execute('SELECT * FROM run_jobs WHERE run_id=?',(run_id,)).fetchone()
        artifact=conn.execute('SELECT plan_json FROM run_artifacts WHERE run_id=?',(run_id,)).fetchone()
        run=conn.execute('SELECT started_at FROM runs WHERE run_id=?',(run_id,)).fetchone()
        budget=(loads(artifact['plan_json'],{}) if artifact else {}).get('budget',{})
        if job and job['cancel_requested']:raise APIError(409,'run_cancelled','分析已取消，保留现有资料和人工记录。')
        if model_call and conn.execute('SELECT COUNT(*) FROM model_calls WHERE run_id=?',(run_id,)).fetchone()[0]>=budget.get('max_model_calls',12):
            raise APIError(429,'run_budget_exceeded','本次模型调用达到预算，请人工检查后重试。')
        started=parse_dt(run['started_at']) if run else None
        if started and time.time()-started.timestamp()>budget.get('deadline_seconds',480):
            raise APIError(408,'run_budget_exceeded','本次分析超过时间预算，请人工检查后重试。')
    finally:conn.close()


def claim_run(run_id:str)->bool:
    with transaction() as tx:
        row=tx.execute('SELECT * FROM runs WHERE run_id=?',(run_id,)).fetchone()
        if not row or row['status'] not in {'queued','running'}:return False
        tx.execute("INSERT OR IGNORE INTO run_jobs(run_id,state) VALUES(?,'queued')",(run_id,))
        changed=tx.execute("UPDATE run_jobs SET state='running',recoveries=recoveries+CASE WHEN attempts>0 THEN 1 ELSE 0 END,attempts=attempts+1,lease_owner=?,lease_until=?,heartbeat_at=? WHERE run_id=? AND cancel_requested=0 AND attempts<3 AND (state='queued' OR (state='running' AND COALESCE(lease_until,0)<?))",
            (OWNER,time.time()+LEASE_SECONDS,now_iso(),run_id,time.time()))
        return changed.rowcount==1


def heartbeat(run_id:str,done:threading.Event):
    while not done.wait(3) and not _stop.is_set():
        with transaction() as tx:tx.execute("UPDATE run_jobs SET lease_until=?,heartbeat_at=? WHERE run_id=? AND lease_owner=? AND state='running'",
            (time.time()+LEASE_SECONDS,now_iso(),run_id,OWNER))


def finish_run(run_id:str,state:str,error_code:str|None=None):
    with transaction() as tx:tx.execute('UPDATE run_jobs SET state=?,error_code=?,lease_owner=NULL,lease_until=NULL,heartbeat_at=? WHERE run_id=? AND lease_owner=?',
        (state,error_code,now_iso(),run_id,OWNER))


def _case(case_id):
    from .services import serialize_case
    conn=connect()
    try:
        row=conn.execute('SELECT * FROM cases WHERE case_id=?',(case_id,)).fetchone()
        if not row:raise APIError(404,'case_not_found','检查记录不存在')
        return serialize_case(dict(row))
    finally:conn.close()


class LifecycleState(TypedDict,total=False):
    case_id:str
    status:str
    case_version:int


def _await_human(state:LifecycleState):
    case=_case(state['case_id']);waiting=WAITING[case['status']]
    if waiting in {'complete','rejected'}:return {'status':case['status'],'case_version':case['version']}
    answer=interrupt({'case_id':case['case_id'],'waiting_for':waiting,'case_version':case['version'],
        'control_version':case['control_version'],'authority':'business_state_machine'})
    current=_case(state['case_id'])
    if answer.get('case_version')!=current['version']:raise APIError(409,'workflow_version_conflict','恢复信号与当前案例版本不一致')
    return {'status':current['status'],'case_version':current['version']}


def lifecycle_graph(saver):
    graph=StateGraph(LifecycleState);graph.add_node('await_business_action',_await_human)
    graph.add_edge(START,'await_business_action')
    graph.add_conditional_edges('await_business_action',lambda state:'end' if state['status'] in {'closed','rejected'} else 'wait',
        {'end':END,'wait':'await_business_action'})
    return graph.compile(checkpointer=saver)


def sync_workflow(case_id:str)->dict:
    with _workflow_lock:
        case=_case(case_id)
        with transaction() as tx:
            tx.execute('INSERT OR IGNORE INTO case_workflows(case_id,thread_id,updated_at) VALUES(?,?,?)',
                (case_id,'case-'+case_id+'-'+uuid.uuid4().hex[:8],now_iso()))
            row=dict(tx.execute('SELECT * FROM case_workflows WHERE case_id=?',(case_id,)).fetchone())
        if row['case_version']!=case['version'] or not row['checkpointed'] or row['error']:
            try:
                with checkpoints() as saver:
                    graph=lifecycle_graph(saver);config={'configurable':{'thread_id':row['thread_id']}}
                    old=graph.get_state(config)
                    signal=Command(resume={'case_version':case['version']}) if old.next else {'case_id':case_id,'status':case['status'],'case_version':case['version']}
                    graph.invoke(signal,config=config,durability='sync')
                    saved=bool(graph.get_state(config).config.get('configurable',{}).get('checkpoint_id'))
                with transaction() as tx:tx.execute('UPDATE case_workflows SET case_version=?,waiting_for=?,checkpointed=?,error=NULL,updated_at=? WHERE case_id=?',
                    (case['version'],WAITING[case['status']],int(saved),now_iso(),case_id))
            except Exception as exc:
                with transaction() as tx:tx.execute('UPDATE case_workflows SET error=?,updated_at=? WHERE case_id=?',(type(exc).__name__,now_iso(),case_id))
                raise
        conn=connect()
        try:result=dict(conn.execute('SELECT * FROM case_workflows WHERE case_id=?',(case_id,)).fetchone())
        finally:conn.close()
        return {**result,'checkpointed':bool(result['checkpointed']),'authority':'business_state_machine'}


def flush_workflows(case_id:str|None=None):
    conn=connect()
    try:rows=conn.execute("SELECT case_id,MAX(event_id) AS event_id FROM workflow_outbox WHERE state='pending'"+(' AND case_id=?' if case_id else '')+' GROUP BY case_id LIMIT 8',
        (case_id,) if case_id else ()).fetchall()
    finally:conn.close()
    for row in rows:
        try:sync_workflow(row['case_id']);state,error='delivered',None
        except Exception as exc:state,error='error',type(exc).__name__
        with transaction() as tx:tx.execute("UPDATE workflow_outbox SET state=?,error=? WHERE case_id=? AND event_id<=? AND state='pending'",
            (state,error,row['case_id'],row['event_id']))


def resume_run(run_id:str):
    conn=connect()
    try:
        run=conn.execute('SELECT * FROM runs WHERE run_id=?',(run_id,)).fetchone()
        job=conn.execute('SELECT * FROM run_jobs WHERE run_id=?',(run_id,)).fetchone()
        artifact=conn.execute('SELECT input_json FROM run_artifacts WHERE run_id=?',(run_id,)).fetchone()
    finally:conn.close()
    if not run or not job or not artifact:raise APIError(404,'run_not_found','没有可恢复的运行记录')
    if run['status']!='failed' or job['attempts']>=3 or job['error_code'] in {'stale_run_inputs','decision_audit_failed','run_budget_exceeded','run_cancelled'}:
        raise APIError(409,'run_resume_rejected','当前运行不可恢复，请保留资料后重新分析')
    assert_snapshot(run['case_id'],loads(artifact['input_json']))
    with transaction() as tx:
        case=tx.execute('SELECT * FROM cases WHERE case_id=?',(run['case_id'],)).fetchone()
        if case['last_run_id']!=run_id or case['status']!='needs_evidence':raise APIError(409,'run_resume_rejected','案例已进入新的流程，不能恢复旧运行')
        tx.execute("UPDATE cases SET status='analyzing',updated_at=?,version=version+1 WHERE case_id=?",(now_iso(),run['case_id']))
        tx.execute("UPDATE runs SET status='queued',error=NULL,finished_at=NULL WHERE run_id=?",(run_id,))
        tx.execute("UPDATE run_jobs SET state='queued',error_code=NULL,cancel_requested=0 WHERE run_id=?",(run_id,))
        from .services import append_event
        append_event(tx,run['case_id'],'analyzing','analysis_resumed','演示安全员',{'run_id':run_id},'human')
    dispatch(run_id)
    return {'run_id':run_id,'status':'queued'}


def cancel_run(run_id:str):
    with transaction() as tx:
        row=tx.execute('SELECT * FROM runs WHERE run_id=?',(run_id,)).fetchone()
        if not row:raise APIError(404,'run_not_found','运行不存在')
        if row['status'] not in {'queued','running'}:raise APIError(409,'run_cancel_rejected','当前运行已结束')
        tx.execute('UPDATE run_jobs SET cancel_requested=1 WHERE run_id=?',(run_id,))
        if row['status']=='queued':
            tx.execute("UPDATE runs SET status='failed',error='run_cancelled',finished_at=? WHERE run_id=?",(now_iso(),run_id))
            tx.execute("UPDATE run_jobs SET state='cancelled',error_code='run_cancelled' WHERE run_id=?",(run_id,))
            tx.execute("UPDATE cases SET status='needs_evidence',analysis_incomplete=1,updated_at=?,version=version+1 WHERE case_id=? AND status='analyzing' AND last_run_id=?",(now_iso(),row['case_id'],run_id))
    return {'run_id':run_id,'cancel_requested':True}


def dispatch(run_id:str):
    if _worker and _worker.is_alive():_wake.set()
    else:
        # Synchronous adapter preserves the offline/demo and TestClient behavior.
        from .agent import execute_run
        execute_run(run_id)


def _loop():
    from .agent import execute_run
    while not _stop.is_set():
        try:
            with transaction() as tx:
                exhausted=tx.execute("SELECT j.run_id,r.case_id FROM run_jobs j JOIN runs r ON r.run_id=j.run_id WHERE j.state='running' AND j.attempts>=3 AND j.lease_until<?",(time.time(),)).fetchall()
                for job in exhausted:
                    tx.execute("UPDATE run_jobs SET state='failed',error_code='recovery_budget_exceeded',lease_owner=NULL,lease_until=NULL WHERE run_id=?",(job['run_id'],))
                    tx.execute("UPDATE runs SET status='failed',error='recovery_budget_exceeded',finished_at=? WHERE run_id=?",(now_iso(),job['run_id']))
                    tx.execute("UPDATE cases SET status='needs_evidence',analysis_incomplete=1,updated_at=?,version=version+1 WHERE case_id=? AND status='analyzing' AND last_run_id=?",(now_iso(),job['case_id'],job['run_id']))
            conn=connect()
            try:rows=conn.execute("SELECT j.run_id FROM run_jobs j JOIN runs r ON r.run_id=j.run_id WHERE r.status IN ('queued','running') AND j.cancel_requested=0 AND j.attempts<3 AND (j.state='queued' OR (j.state='running' AND COALESCE(j.lease_until,0)<?)) ORDER BY r.created_at LIMIT 1",(time.time(),)).fetchall()
            finally:conn.close()
            for row in rows:execute_run(row['run_id'])
            flush_workflows()
        except Exception as exc:LOG.error('Worker iteration failed: %s',type(exc).__name__)
        _wake.wait(.7);_wake.clear()


def start_worker():
    global _worker
    if _worker and _worker.is_alive():return
    _stop.clear();_worker=threading.Thread(target=_loop,name='bim-durable-worker',daemon=True);_worker.start()


def stop_worker():
    _stop.set();_wake.set()
    if _worker:_worker.join(timeout=2)


def runtime_status():
    conn=connect()
    try:
        jobs={r['state']:r['n'] for r in conn.execute('SELECT state,COUNT(*) AS n FROM run_jobs GROUP BY state')}
        errors=conn.execute("SELECT COUNT(*) FROM workflow_outbox WHERE state='error'").fetchone()[0]
        return {'mode':'durable_local_worker' if _worker and _worker.is_alive() else 'synchronous_adapter',
            'worker_alive':bool(_worker and _worker.is_alive()),'jobs':jobs,'workflow_delivery_errors':errors,
            'checkpoint_backend':'sqlite','max_parallel_analyses':1,'lease_seconds':LEASE_SECONDS}
    finally:conn.close()
