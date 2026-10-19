"""Version-checked Case input edits preserve history and invalidate stale decisions."""
from .db import dumps
from .errors import APIError
from .tools import now_iso


def editable_case(conn, case_id, expected, execution=False):
    from .services import serialize_case
    row = conn.execute('SELECT * FROM cases WHERE case_id=?',(case_id,)).fetchone()
    if row is None:
        raise APIError(404,'case_not_found','案例不存在')
    case = serialize_case(dict(row))
    if expected != case['version']:
        raise APIError(409,'version_conflict','案例版本已变化，请刷新')
    allowed = {'draft','needs_evidence','pending_review','reopened','rejected'}
    if execution:
        allowed |= {'approved','rectifying','pending_verification'}
    if case['status'] not in allowed:
        raise APIError(409,'case_inputs_locked','当前阶段的检查输入已锁定')
    return case


def record_edit(conn, case, event, detail, invalidate=True):
    from .services import append_event
    status = 'draft' if invalidate else case['status']
    if invalidate:
        controls = [{**item,'status':'superseded'} for item in case['controls']]
        conn.execute("UPDATE cases SET status=?,findings_json='[]',controls_json=?,review_json=NULL,"
                     "implementation_json=NULL,verification_json=NULL,safety_state_json=NULL,"
                     "decision_package_json=NULL,analysis_incomplete=0 WHERE case_id=?",
                     (status,dumps(controls),case['case_id']))
    conn.execute('UPDATE cases SET version=version+1,updated_at=? WHERE case_id=?',(now_iso(),case['case_id']))
    append_event(conn,case['case_id'],status,event,'演示安全员',detail,'human')
