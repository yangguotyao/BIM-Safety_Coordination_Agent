from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import (
    DEMO_CLOCK,
    DEMO_MODE,
    live_model_configured,
    EXPORT_DIR,
    MODEL_ID,
    MODEL_VERSION,
    PROJECT_ID,
    TARGET_GUID,
    ZONE_ID,
    runtime_mode,
)
from .db import connect, dumps, loads, transaction
from .errors import APIError
from .control_requirements import normalize_criteria
from .tools import (
    get_evidence,
    get_model,
    get_task,
    get_zone,
    now_iso,
    parse_dt,
    rule_retrieval,
)

CASE_STATUSES = [
    "draft",
    "analyzing",
    "needs_evidence",
    "pending_review",
    "approved",
    "rectifying",
    "pending_verification",
    "closed",
    "reopened",
    "rejected",
]

ACTIVE_ANALYZE_STATUSES = {"draft", "needs_evidence", "reopened"}


def new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def demo_offset(as_of: str, minutes: int) -> str:
    base = parse_dt(as_of)
    if not base:
        return DEMO_CLOCK
    return (base + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def append_event(
    conn: sqlite3.Connection,
    case_id: str,
    status: str,
    event: str,
    actor: str,
    detail: dict[str, Any] | None = None,
    provenance: str = "system",
) -> None:
    cursor = conn.execute(
        """INSERT INTO case_events(case_id,at,status,event,actor,detail_json,provenance)
           VALUES (?,?,?,?,?,?,?)""",
        (
            case_id,
            now_iso(),
            status,
            event,
            actor,
            dumps(detail or {}),
            provenance,
        ),
    )
    conn.execute('INSERT INTO workflow_outbox(event_id,case_id) VALUES(?,?)',(cursor.lastrowid,case_id))


def _case_row(conn: sqlite3.Connection, case_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise APIError(404, "case_not_found", f"案例不存在：{case_id}")
    return dict(row)


def serialize_case(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for field in (
        "bim_guids",
        "evidence_ids",
        "rule_ids",
        "findings",
        "controls",
        "assumptions",
    ):
        data[field] = loads(data.pop(f"{field}_json", "[]"), [])
    for field in ("review", "implementation", "verification", "task_spec", "safety_state", "decision_package", "scope"):
        data[field] = loads(data.pop(f"{field}_json", None), None)
    data["schema_version"] = "1.0"
    data["versions"] = {
        "case": data.get("version", 1),
        "rules": "v1",
    }
    data["mode"] = data.get("mode", "demo")
    data["allowed_actions"] = allowed_actions(data)
    data["control_version"] = max(
        [int(control.get("version", 0)) for control in data.get("controls", [])] or [0]
    )
    return data


def allowed_actions(case: dict[str, Any]) -> list[str]:
    status = case.get("status")
    actions = ["export"]
    if status in ACTIVE_ANALYZE_STATUSES:
        actions.append("analyze")
        actions.append("add_evidence")
    if status == "needs_evidence":
        actions.append("add_evidence")
        actions.append("analyze")
    if status == "pending_review":
        actions.extend(["review", "add_evidence"])
    if status == "approved":
        actions.extend(["implement", "add_evidence"])
    if status == "rectifying":
        actions.append("add_evidence")
        actions.append("verify")
    if status == "pending_verification":
        actions.append("verify")
        actions.append("add_evidence")
    if status == "reopened":
        actions.append("analyze")
        actions.append("add_evidence")
    if status == "closed":
        actions.append("reopen")
    return sorted(set(actions))


def case_bundle(case_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        evidence = []
        for evidence_id in case["evidence_ids"]:
            try:
                evidence.append(get_evidence(conn, evidence_id))
            except APIError:
                continue
        rules = []
        for rule_id in case["rule_ids"]:
            rule = conn.execute("SELECT * FROM rules WHERE rule_id=?", (rule_id,)).fetchone()
            if rule:
                rules.append(dict(rule))
        events = [
            dict(event)
            for event in conn.execute(
                "SELECT * FROM case_events WHERE case_id=? ORDER BY id ASC", (case_id,)
            ).fetchall()
        ]
        for event in events:
            event["detail"] = loads(event.pop("detail_json"), {})
        runs = [
            dict(run)
            for run in conn.execute(
                "SELECT run_id,status,created_at,started_at,finished_at,error,mode FROM runs WHERE case_id=? ORDER BY created_at DESC, rowid DESC",
                (case_id,),
            ).fetchall()
        ]
        calls = [dict(item) for item in conn.execute('SELECT * FROM model_calls WHERE case_id=? ORDER BY id DESC LIMIT 30', (case_id,))]
        for item in calls:
            item['usage'] = loads(item.pop('usage_json'), {})
        from .coordination import activity_plan,check_activities
        from .site_text import site_notes,text_context
        from .tools import spatial_check
        zone=get_zone(conn,case['zone_id'])
        zone['data']={**zone['data'],**(case.get('scope') or {})}
        plan=activity_plan(conn,case_id)
        return {"case": case, "evidence": evidence, "rules": rules, "events": events, "runs": runs,
                'context':{'zone':zone, 'task':get_task(conn,case['task_id'])},
                'model_calls':calls,'activity_plan':plan,'coordination':check_activities(plan,case['as_of']),
                'site_notes':site_notes(conn,case_id),'site_text':text_context(conn,case),
                'spatial':spatial_check(conn,case)}
    finally:
        conn.close()


def list_cases(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn = connect()
    try:
        from .access import scoped_sql
        scope,params=scoped_sql()
        if status:
            rows = conn.execute(
                "SELECT * FROM cases WHERE "+scope+" AND status=? ORDER BY updated_at DESC, rowid DESC LIMIT ?",
                (*params,status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cases WHERE "+scope+" ORDER BY updated_at DESC, rowid DESC LIMIT ?", (*params,limit)
            ).fetchall()
        return [serialize_case(dict(row)) for row in rows]
    finally:
        conn.close()


def create_case(payload: dict[str, Any]) -> dict[str, Any]:
    title = (payload.get("title") or "L05 板边安全检查演示").strip()
    model_id = payload.get("model_id") or MODEL_ID
    task_id = payload.get("task_id") or "TASK-S1-001"
    zone_id = payload.get("zone_id") or ZONE_ID
    as_of = payload.get("as_of") or DEMO_CLOCK
    evidence_ids = list(dict.fromkeys(payload['evidence_ids'] if payload.get('evidence_ids') is not None else ['EV-001']))
    guids = list(dict.fromkeys(payload.get("bim_guids") or []))
    if not parse_dt(as_of):
        raise APIError(422, "invalid_as_of", "as_of 必须是含时区的 ISO8601 时间")
    prepared = None
    if payload.get('inspection_context'):
        from .bim_context import prepare_context
        if model_id != MODEL_ID:
            raise APIError(422, 'context_model', '选中构件上下文与当前模型不匹配')
        prepared = prepare_context(payload['inspection_context'], as_of)
        zone_id, task_id = prepared[0]['zone_id'], prepared[1]['task_id']
        guids = [prepared[0]['target_guid']]

    conn = connect()
    try:
        model = get_model(conn, model_id)
        zone, task = prepared if prepared else (get_zone(conn, zone_id), get_task(conn, task_id))
        if task["zone_id"] != zone["zone_id"]:
            raise APIError(422, "task_zone_mismatch", "施工任务与检查区域不匹配")
        if task["model_id"] != model_id:
            raise APIError(422, "task_model_mismatch", "施工任务与模型不匹配")
        if not guids:
            guids = [zone["target_guid"]]
        for guid in guids:
            row = conn.execute(
                "SELECT guid FROM elements WHERE model_id=? AND guid=?", (model_id, guid)
            ).fetchone()
            if not row:
                raise APIError(
                    422,
                    "unknown_guid",
                    f"构件 GUID 不在已索引范围内：{guid}",
                    {
                        "guid": guid,
                        "model_id": model_id,
                        "indexed_scope": "storey 05 (1247 elements)",
                        "hint": "T09 使用不存在的 GUID 时不会创建悬空案例。",
                    },
                )
        for evidence_id in evidence_ids:
            evidence = get_evidence(conn, evidence_id)
            if (evidence["model_id"] != model_id or evidence["zone_id"] != zone_id
                    or not set(guids).issubset(evidence['bim_guids'])):
                raise APIError(
                    422,
                    "evidence_scope_mismatch",
                    f"证据 {evidence_id} 与模型或区域不匹配",
                )

        case_id = payload.get("case_id") or new_id("CASE")
        existing = conn.execute("SELECT 1 FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if existing:
            case_id = new_id("CASE")
        assumptions = payload.get("assumptions") or [
            "板边已在演示中标注为需检查边界，不等于真实项目临空侧。",
            "坠落高度 2.5 m、人员作业和防护缺失均为模拟观察。",
            "17.3 m 是模型世界 Z 高程，不是坠落高度。",
        ]
        if prepared:
            assumptions = ['检查边线来自选定IFC构件上表面，临空性质需人工确认。',
                           '施工时间窗、人员点和责任主体为人工编制的演示输入。',
                           '图像观察及测量参数需人工确认，不把模型绝对标高当作坠落高度。']
        with transaction() as tx:
            if prepared:
                from .bim_context import store_context
                store_context(tx, zone, task)
            tx.execute(
                """INSERT INTO cases
                   (case_id,title,project_id,model_id,model_version,task_id,zone_id,as_of,status,version,
                    bim_guids_json,evidence_ids_json,rule_ids_json,findings_json,controls_json,review_json,
                    implementation_json,verification_json,assumptions_json,provenance,mode,last_run_id,
                    analysis_incomplete,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    case_id,
                    title,
                    PROJECT_ID,
                    model_id,
                    model["version"],
                    task_id,
                    zone_id,
                    as_of,
                    "draft",
                    1,
                    dumps(guids),
                    dumps(evidence_ids),
                    dumps([]),
                    dumps([]),
                    dumps([]),
                    None,
                    None,
                    None,
                    dumps(assumptions),
                    "mixed_real_bim_simulated_site_state",
                    runtime_mode(),
                    None,
                    0,
                    now_iso(),
                    now_iso(),
                ),
            )
            append_event(
                tx,
                case_id,
                "draft",
                "case_created",
                payload.get("actor") or "演示安全员",
                {
                    "task_id": task_id,
                    "zone_id": zone_id,
                    "evidence_ids": evidence_ids,
                    "bim_guids": guids,
                    "data_nature": "真实 IFC 构件 + 模拟现场证据",
                },
                "api",
            )
            request_text = (payload.get('request_text') or '').strip()
            actor_id = payload.get('actor_id') or 'demo-user'
            tx.execute('UPDATE cases SET request_text=?,task_actor_id=? WHERE case_id=?',
                       (request_text, actor_id, case_id))
            if request_text:
                tx.execute('INSERT INTO case_messages(case_id,actor_id,role,content,created_at) VALUES(?,?,?,?,?)',
                           (case_id,actor_id,'user',request_text,now_iso()))
        return case_bundle(case_id)
    finally:
        conn.close()


def record_task_request(case_id: str, message: str, actor_id: str, expected_version: int) -> None:
    message = message.strip()
    if not message:
        raise APIError(422, 'empty_task', '请填写检查任务')
    with transaction() as tx:
        case = _case_row(tx, case_id)
        if case['version'] != expected_version:
            raise APIError(409, 'version_conflict', 'Case已更新，请刷新后提交任务')
        if case['status'] not in {'draft','needs_evidence','pending_review','rejected','reopened'}:
            raise APIError(409, 'transition_rejected', '当前Case已进入授权或实施阶段，请完成当前流程后再发起新检查')
        status = case['status'] if case['status'] in ACTIVE_ANALYZE_STATUSES else 'draft'
        if case.get('task_actor_id') != actor_id:
            tx.execute('UPDATE cases SET task_spec_json=NULL WHERE case_id=?', (case_id,))
        tx.execute("UPDATE cases SET request_text=?,task_actor_id=?,status=?,review_json=NULL,"
                   "decision_package_json=NULL,safety_state_json=NULL,updated_at=?,version=version+1 WHERE case_id=?",
                   (message,actor_id,status,now_iso(),case_id))
        tx.execute('INSERT INTO case_messages(case_id,actor_id,role,content,created_at) VALUES(?,?,?,?,?)',
                   (case_id,actor_id,'user',message,now_iso()))
        append_event(tx,case_id,status,'task_requested',actor_id,{'request':message},'human')


def start_analysis(case_id: str) -> tuple[dict[str, Any], str]:
    if not DEMO_MODE and not live_model_configured():
        raise APIError(
            503,
            "live_model_config_incomplete",
            "DEMO_MODE=false，但 MODEL_BASE_URL / MODEL_API_KEY / MODEL_NAME 不完整。",
            {
                "required": ["MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME"],
                "hint": "补齐配置后重启，或设置 DEMO_MODE=true 使用演示模式。系统不会静默降级。",
            },
        )
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] not in ACTIVE_ANALYZE_STATUSES:
            raise APIError(
                409,
                "transition_rejected",
                f"当前状态 {case['status']} 不允许发起分析",
                {"allowed_statuses": sorted(ACTIVE_ANALYZE_STATUSES)},
            )
        from .assurance import input_snapshot
        snapshot=input_snapshot(case_id)
        run_id = new_id("RUN")
        with transaction() as tx:
            changed=tx.execute(
                "UPDATE cases SET status='analyzing',last_run_id=?,updated_at=?,version=version+1 WHERE case_id=? AND version=?",
                (run_id, now_iso(), case_id,case['version']),
            )
            if changed.rowcount!=1:raise APIError(409,'version_conflict','案例已更新，请刷新后重试')
            tx.execute(
                """INSERT INTO runs(run_id,case_id,status,created_at,trace_json,error,mode)
                   VALUES (?,?,?,?,?,?,?)""",
                (run_id, case_id, "queued", now_iso(), dumps([]), None, runtime_mode()),
            )
            tx.execute('INSERT INTO run_artifacts(run_id,input_hash,input_json,created_at) VALUES(?,?,?,?)',
                (run_id,snapshot['input_hash'],dumps(snapshot),now_iso()))
            tx.execute("INSERT INTO run_jobs(run_id,state) VALUES(?,'queued')",(run_id,))
            append_event(
                tx,
                case_id,
                "analyzing",
                "analysis_started",
                "演示安全员",
                {"run_id": run_id, "evidence_ids": case["evidence_ids"]},
                "api",
            )
        return case_bundle(case_id), run_id
    finally:
        conn.close()


def save_analysis_result(
    run_id: str,
    case_id: str,
    finding: dict[str, Any] | None,
    controls: list[dict[str, Any]],
    rule_ids: list[str],
    status: str,
    incomplete: bool,
    error: str | None = None,
    task_spec: dict[str, Any] | None = None,
    safety_state: dict[str, Any] | None = None,
    decision_package: dict[str, Any] | None = None,
    additional_findings: list[dict[str,Any]] | None = None,
) -> None:
    conn = connect()
    try:
        with transaction() as tx:
            row = tx.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                return
            case = dict(row)
            if case['last_run_id']!=run_id:
                raise APIError(409,'superseded_run','该次分析已被新的任务替代')
            if case['status']!='analyzing':
                completed=tx.execute("SELECT 1 FROM case_events WHERE case_id=? AND event='analysis_completed' AND json_extract(detail_json,'$.run_id')=?",(case_id,run_id)).fetchone()
                if completed:return
                raise APIError(409,'transition_rejected','案例已离开分析阶段，不能覆盖现有结果')
            previous_controls = loads(case.get("controls_json"), [])
            max_version = max([int(c.get("version", 0)) for c in previous_controls] or [0])
            if previous_controls and status in {"pending_review", "needs_evidence"}:
                for control in controls:
                    control["version"] = max_version + 1
            tx.execute(
                """UPDATE cases SET findings_json=?,controls_json=?,rule_ids_json=?,status=?,
                   analysis_incomplete=?,review_json=NULL,implementation_json=NULL,verification_json=NULL,
                   updated_at=?,version=version+1 WHERE case_id=?""",
                (
                    dumps(([finding] if finding else [])+(additional_findings or [])),
                    dumps(controls),
                    dumps(rule_ids),
                    status,
                    (1 if incomplete else 0),
                    now_iso(),
                    case_id,
                ),
            )
            append_event(
                tx,
                case_id,
                status,
                "analysis_failed" if error else "analysis_completed",
                "Safety Coordinator",
                {
                    "run_id": run_id,
                    "result": finding.get("result") if finding else None,
                    "incomplete": incomplete,
                    "error": error,
                    "rule_ids": rule_ids,
                    "control_count": len(controls),
                },
                "agent",
            )
            if task_spec is not None:
                if decision_package:
                    decision_package['controls'] = controls
                tx.execute('UPDATE cases SET task_spec_json=?,safety_state_json=?,decision_package_json=? WHERE case_id=?',
                           (dumps(task_spec),dumps(safety_state),dumps(decision_package),case_id))
                summary = f"检查重点：{', '.join(task_spec['focus'])}。{finding.get('hazard') if finding else '待补充资料'}。状态：{status}。"
                tx.execute('INSERT OR IGNORE INTO case_messages(case_id,actor_id,role,content,run_id,created_at) VALUES(?,?,?,?,?,?)',
                           (case_id,case.get('task_actor_id') or 'demo-user','assistant',summary[:1200],run_id,now_iso()))
    finally:
        conn.close()


def build_controls(finding: dict[str, Any]) -> list[dict[str, Any]]:
    if not finding or finding.get("result") != "risk_candidate":
        return []
    observation = finding.get("inputs", {})
    guardrail = observation.get("guardrail_state")
    height = observation.get("guardrail_height_m")
    action = "由演示班组设置连续的临边防护栏杆，并限制无防护区域进入。"
    if guardrail == "present" and height is not None and float(height) < 1.2:
        action = "将模拟临边栏杆加高至 1.2 m，检查横杆、立杆、挡脚板、固定与连续性，并限制无防护区域进入。"
    elif guardrail == "present":
        action = "检查并补强模拟临边栏杆的固定与连续性，复核挡脚板与横杆构造，并限制无防护区域进入。"
    return [
        {
            "control_id": "CTRL-001",
            "finding_id": finding.get("finding_id", "F-001"),
            "action": action,
            "owner": "演示机电班组",
            "verification_requirements": [
                "同项目、同模型版本、同区域、同构件的实施后证据",
                "证据时间晚于人工记录的实施时刻",
                "防护存在、高度 ≥ 1.2 m、固定与连续性标注",
                "演示安全员人工复核确认",
            ],
            "status": "proposed",
            "version": 1,
            "provenance": "demo_template",
            "verification_criteria": normalize_criteria({}),
            "scope_note": "仅为演示候选措施，不替代施工单位专项方案。",
        }
    ]


def review_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision")
    if decision not in {"approve", "reject", "modify"}:
        raise APIError(422, "invalid_decision", "decision 必须是 approve/reject/modify")
    expected = payload.get("expected_case_version")
    reviewer = (payload.get("reviewer") or "演示安全员").strip()
    comment = (payload.get("comment") or "").strip()
    if not reviewer:
        raise APIError(422, "reviewer_required", "必须填写复核人")
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] != "pending_review":
            raise APIError(
                409,
                "transition_rejected",
                f"当前状态 {case['status']} 不允许审核",
                {"allowed": ["pending_review"]},
            )
        if expected is not None and int(expected) != int(case["version"]):
            raise APIError(
                409,
                "version_conflict",
                "案例版本已变化，请刷新后重新审核",
                {"expected": expected, "actual": case["version"]},
            )
        controls = case["controls"]
        max_control_version = max([int(c.get("version", 0)) for c in controls] or [0])
        reviewed_at = payload.get("reviewed_at") or demo_offset(case["as_of"], 10)
        if not parse_dt(reviewed_at):
            raise APIError(422, "invalid_time", "reviewed_at 必须是 ISO8601 时间")

        if decision == "modify":
            new_controls = payload.get("new_controls") or []
            if not new_controls:
                raise APIError(422, "controls_required", "修改措施必须提供 new_controls")
            next_version = max_control_version + 1
            controls = []
            for index, item in enumerate(new_controls):
                try:
                    criteria = normalize_criteria(item, modified=True)
                except ValueError as exc:
                    raise APIError(422, 'invalid_verification_criteria', '验收参数无效；高度不得低于演示基线1.20m', str(exc)) from exc
                controls.append(
                    {
                        "control_id": item.get("control_id") or f"CTRL-{next_version:03d}-{index + 1}",
                        "finding_id": item.get("finding_id") or "F-001",
                        "action": item.get("action") or "",
                        "owner": item.get("owner") or "演示机电班组",
                        "verification_requirements": item.get("verification_requirements")
                        or ["同区同构件新证据", "人工复核确认"],
                        "status": "proposed",
                        "version": next_version,
                        "provenance": "human_modified_demo",
                        "verification_criteria": criteria,
                    }
                )
            review = {
                "decision": "modify",
                "reviewer": reviewer,
                "reviewed_at": reviewed_at,
                "control_version": next_version,
                "comment": comment or "演示安全员修改控制措施，等待重新审核。",
            }
            if len({control['control_id'] for control in controls}) != len(controls):
                raise APIError(422, 'duplicate_control_id', '同一版本的控制措施ID不得重复')
            if any(c.get('verification_criteria',{}).get('coordination_required') for c in case['controls']) and not any(
                c['verification_criteria'].get('coordination_required') for c in controls):
                raise APIError(422,'coordination_criteria_required','时空冲突的验收要求不能删除')
            with transaction() as tx:
                tx.execute(
                    "UPDATE cases SET controls_json=?,review_json=?,status='pending_review',updated_at=?,version=version+1 WHERE case_id=?",
                    (dumps(controls), dumps(review), now_iso(), case_id),
                )
                append_event(
                    tx,
                    case_id,
                    "pending_review",
                    "controls_modified",
                    reviewer,
                    {"control_version": next_version, "comment": review["comment"]},
                    "human",
                )
            return case_bundle(case_id)

        control_version = payload.get("control_version")
        if decision == "approve" and controls:
            if control_version is None:
                raise APIError(422, "control_version_required", "批准前必须确认控制措施版本")
            if int(control_version) != max_control_version:
                raise APIError(
                    409,
                    "control_version_conflict",
                    "控制措施版本已变化，请刷新后重新审核",
                    {"expected": control_version, "actual": max_control_version},
                )

        review = {
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "control_version": max_control_version if controls else 0,
            "comment": comment
            or ("同意进入演示实施。" if decision == "approve" else "演示审批拒绝。"),
        }
        if decision == 'approve':
            from .assurance import assert_snapshot
            artifact=conn.execute('SELECT input_json,audit_json FROM run_artifacts WHERE run_id=?',(case.get('last_run_id'),)).fetchone()
            if artifact:
                assert_snapshot(case_id,loads(artifact['input_json']))
                if loads(artifact['audit_json'],{}).get('status')!='passed':raise APIError(409,'analysis_audit_required','本次分析尚未通过规则与证据校核')
                review['analysis_input_hash']=loads(artifact['input_json'])['input_hash']
            from .access import PRINCIPAL
            principal=PRINCIPAL.get()
            if principal:review['authorization']={key:principal[key] for key in ['label','role','mode']}
            review['verification_snapshot'] = {
                c['control_id']: normalize_criteria(c) for c in controls
            }
            from .coordination import activity_plan,check_activities
            from .site_text import text_context
            plan=activity_plan(conn,case_id)
            if not text_context(conn,case)['complete']:
                raise APIError(422,'text_clarification_required','现场文本仍有未澄清的差异或缺失项')
            if plan:
                check=check_activities(plan,case['as_of'])
                if not check['complete']:
                    raise APIError(422,'activity_data_incomplete','施工活动资料未补齐')
                if check['conflicts'] and not any(c.get('verification_criteria',{}).get('coordination_required') for c in controls):
                    raise APIError(422,'coordination_control_required','施工时空冲突需要对应控制措施')
                review['activity_plan_revision']=plan['revision']
                review['coordination_task_ids']=[a['task_id'] for a in plan['activities']]
        if decision == "approve":
            if controls:
                new_status = "approved"
                for control in controls:
                    control["status"] = "approved"
            else:
                new_status = "closed"
                review["comment"] = comment or "已检查项未发现问题，无需整改，演示中直接关闭。"
        else:
            new_status = "rejected"

        with transaction() as tx:
            tx.execute(
                """UPDATE cases SET controls_json=?,review_json=?,status=?,verification_json=?,
                   implementation_json=NULL,updated_at=?,version=version+1 WHERE case_id=?""",
                (
                    dumps(controls),
                    dumps(review),
                    new_status,
                    None if new_status != "closed" else dumps(None),
                    now_iso(),
                    case_id,
                ),
            )
            append_event(
                tx,
                case_id,
                new_status,
                "review_approved" if decision == "approve" else "review_rejected",
                reviewer,
                {
                    "decision": decision,
                    "control_version": review["control_version"],
                    "comment": review["comment"],
                },
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def implement_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] != "approved":
            raise APIError(
                409,
                "transition_rejected",
                f"当前状态 {case['status']} 不允许记录实施；必须先人工批准。",
                {"allowed": ["approved"]},
            )
        expected = payload.get("expected_case_version")
        if expected is not None and int(expected) != int(case["version"]):
            raise APIError(409, "version_conflict", "案例版本已变化，请刷新", {"actual": case["version"]})
        implemented_at = payload.get("implemented_at") or demo_offset(case["as_of"], 20)
        implemented_dt = parse_dt(implemented_at)
        if not implemented_dt:
            raise APIError(422, "invalid_time", "implemented_at 必须是 ISO8601 时间")
        review = case.get("review") or {}
        reviewed_at = parse_dt(review.get("reviewed_at"))
        if reviewed_at and implemented_dt < reviewed_at:
            raise APIError(422, "time_order", "实施时刻不能早于审核时刻")
        owner = (payload.get("owner") or "演示机电班组").strip()
        comment = (payload.get("comment") or "模拟实施记录，不代表现场实际施工。").strip()
        implementation = {
            "owner": owner,
            "implemented_at": implemented_at,
            "comment": comment,
            "provenance": "simulated_human_record",
        }
        controls = case["controls"]
        for control in controls:
            control["status"] = "implementing"
        with transaction() as tx:
            tx.execute(
                "UPDATE cases SET status='rectifying',implementation_json=?,controls_json=?,updated_at=?,version=version+1 WHERE case_id=?",
                (dumps(implementation), dumps(controls), now_iso(), case_id),
            )
            append_event(
                tx,
                case_id,
                "rectifying",
                "implementation_recorded",
                owner,
                implementation,
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def add_evidence(case_id: str, evidence_ids: list[str], actor: str = "演示安全员") -> dict[str, Any]:
    if not evidence_ids:
        raise APIError(422, "evidence_required", "至少选择一条证据")
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] == "closed":
            raise APIError(409, "transition_rejected", "案例已关闭；如条件变化请使用重开接口")
        if case["status"] == "analyzing":
            raise APIError(409, "transition_rejected", "分析运行中，暂不能追加证据")
        existing = list(case["evidence_ids"])
        for evidence_id in evidence_ids:
            evidence = get_evidence(conn, evidence_id)
            if (evidence["model_id"] != case["model_id"] or evidence["zone_id"] != case["zone_id"]
                    or evidence['model_version'] != case['model_version']
                    or not set(case['bim_guids']).issubset(evidence['bim_guids'])):
                raise APIError(422, "evidence_scope_mismatch", f"证据 {evidence_id} 与案例范围不匹配")
        merged = list(dict.fromkeys(existing + evidence_ids))
        new_status = case["status"]
        if case["status"] == "rectifying":
            after_exists = False
            for evidence_id in evidence_ids:
                evidence = get_evidence(conn, evidence_id)
                captured = parse_dt(evidence["captured_at"])
                implemented = parse_dt((case.get("implementation") or {}).get("implemented_at"))
                if captured and implemented and captured > implemented:
                    after_exists = True
            if after_exists:
                new_status = "pending_verification"
        with transaction() as tx:
            tx.execute(
                "UPDATE cases SET evidence_ids_json=?,status=?,updated_at=?,version=version+1 WHERE case_id=?",
                (dumps(merged), new_status, now_iso(), case_id),
            )
            append_event(
                tx,
                case_id,
                new_status,
                "evidence_added",
                actor,
                {"evidence_ids": evidence_ids, "status_changed": new_status != case["status"]},
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def verify_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    try:
        from .tools import verification_check

        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] != "pending_verification":
            raise APIError(
                409,
                "transition_rejected",
                f"当前状态 {case['status']} 不允许复核；必须先完成人工实施并提交实施后证据。",
                {"allowed": ["pending_verification"]},
            )
        expected = payload.get("expected_case_version")
        if expected is not None and int(expected) != int(case["version"]):
            raise APIError(409, "version_conflict", "案例版本已变化，请刷新", {"actual": case["version"]})
        evidence_ids = list(dict.fromkeys(payload.get("after_evidence_ids") or []))
        if not evidence_ids:
            raise APIError(422, "after_evidence_required", "必须选择实施后证据")
        as_of = payload.get("as_of") or demo_offset(case["as_of"], 40)
        if not parse_dt(as_of):
            raise APIError(422, "invalid_time", "as_of 必须是 ISO8601 时间")
        reviewer = (payload.get("reviewer") or "演示安全员").strip()
        confirmed = bool(payload.get("reviewer_confirmed"))
        result = verification_check(conn, case, evidence_ids, as_of, confirmed,
                                    bool(payload.get('manual_checks_confirmed')))
        verification = result["data"]
        from .assurance import input_snapshot,digest,file_reference
        verification['input_hash']=digest({'case_input':input_snapshot(case_id)['input_hash'],'verified_at':as_of,
            'criteria':verification.get('approved_criteria'),
            'evidence':[{'record':record,'file':file_reference(record.get('file_path'))} for record in verification.get('evidence_records',[])]})
        verification['review_input_hash']=(case.get('review') or {}).get('analysis_input_hash')
        from .access import PRINCIPAL
        principal=PRINCIPAL.get()
        if principal:verification['authorization']={key:principal[key] for key in ['label','role','mode']}
        new_status = "closed" if verification["result"] == "pass_in_demo_scope" else "reopened"
        controls = case["controls"]
        for control in controls:
            control["status"] = "verified" if new_status == "closed" else "verification_failed"
        merged_evidence = list(dict.fromkeys(case["evidence_ids"] + evidence_ids))
        with transaction() as tx:
            tx.execute(
                """UPDATE cases SET status=?,verification_json=?,controls_json=?,evidence_ids_json=?,
                   updated_at=?,version=version+1 WHERE case_id=?""",
                (
                    new_status,
                    dumps(verification),
                    dumps(controls),
                    dumps(merged_evidence),
                    now_iso(),
                    case_id,
                ),
            )
            append_event(
                tx,
                case_id,
                new_status,
                "verification_passed" if new_status == "closed" else "verification_failed",
                reviewer,
                {
                    "verification_result": verification["result"],
                    "checks": verification["checks"],
                    "remaining_risk": verification["remaining_risk"],
                    "evidence_ids": evidence_ids,
                },
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def reopen_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        if case["status"] not in {"closed", "pending_verification"}:
            raise APIError(
                409,
                "transition_rejected",
                f"当前状态 {case['status']} 不允许重开",
                {"allowed": ["closed", "pending_verification"]},
            )
        reason = (payload.get("reason") or "").strip()
        if not reason:
            raise APIError(422, "reason_required", "重开必须说明条件变化")
        evidence_ids = list(dict.fromkeys(payload.get("evidence_ids") or []))
        if not evidence_ids:
            raise APIError(422, "evidence_required", "重开必须提供新证据")
        for evidence_id in evidence_ids:
            evidence = get_evidence(conn, evidence_id)
            if evidence["model_id"] != case["model_id"] or evidence["zone_id"] != case["zone_id"]:
                raise APIError(422, "evidence_scope_mismatch", f"证据 {evidence_id} 与案例范围不匹配")
        previous_status = case["status"]
        merged = list(dict.fromkeys(case["evidence_ids"] + evidence_ids))
        with transaction() as tx:
            tx.execute(
                "UPDATE cases SET status='reopened',evidence_ids_json=?,updated_at=?,version=version+1 WHERE case_id=?",
                (dumps(merged), now_iso(), case_id),
            )
            append_event(
                tx,
                case_id,
                "reopened",
                "case_reopened",
                payload.get("actor") or "演示安全员",
                {
                    "previous_status": previous_status,
                    "reason": reason,
                    "evidence_ids": evidence_ids,
                    "previous_verification": case.get("verification"),
                    "note": "保留此前 closed / verification 事件，不覆盖历史。",
                },
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def add_uploaded_evidence(
    case_id: str,
    filename: str,
    stored_path: Path,
    captured_at: str,
    stage: str = "after",
    note: str = "",
) -> dict[str, Any]:
    conn = connect()
    try:
        row = _case_row(conn, case_id)
        case = serialize_case(row)
        evidence_id = new_id("EV-UP")
        if case['status'] in {'closed','analyzing'}:
            raise APIError(409,'upload_locked','当前状态不能上传新证据')
        if stage not in {'before','after'} or not parse_dt(captured_at):
            raise APIError(422,'evidence_metadata','请提供有效证据阶段和拍摄时间')
        if stage=='before' and case['status'] in {'approved','rectifying','pending_verification'}:
            raise APIError(409,'approved_observation_locked','审批后的检查时证据已冻结，请提交实施后证据')
        new_status = case['status']
        if stage=='after' and case['status']=='rectifying':
            implemented = parse_dt((case.get('implementation') or {}).get('implemented_at'))
            if implemented and parse_dt(captured_at) > implemented:
                new_status = 'pending_verification'
        elif stage=='before' and case['status']=='pending_review':
            new_status = 'draft'
        observation = {
            "guardrail_state": "unknown",
            "guardrail_height_m": None,
            "worker_present": None,
            "drop_height_m": None,
            "boundary_is_exposed": None,
            "guardrail_fixed": None,
            "guardrail_continuous": None,
            "ppe_confirmed": None,
            "simulated": False,
        }
        relative = str(stored_path.resolve())
        with transaction() as tx:
            tx.execute(
                """INSERT INTO evidence
                   (evidence_id,project_id,model_id,model_version,zone_id,bim_guids_json,file_path,kind,
                    captured_at,stage,provenance,observation_json,label,source,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidence_id,
                    case["project_id"],
                    case["model_id"],
                    case["model_version"],
                    case["zone_id"],
                    dumps(case["bim_guids"]),
                    relative,
                    "uploaded_inspection",
                    captured_at,
                    stage,
                    "用户上传文件；未做视觉识别，观察字段为 unknown",
                    dumps(observation),
                    note or filename,
                    "upload",
                    now_iso(),
                ),
            )
            merged = list(dict.fromkeys(case["evidence_ids"] + [evidence_id]))
            tx.execute(
                "UPDATE cases SET evidence_ids_json=?,status=?,updated_at=?,version=version+1 WHERE case_id=?",
                (dumps(merged), new_status, now_iso(), case_id),
            )
            append_event(
                tx,
                case_id,
                case["status"],
                "evidence_uploaded",
                "演示安全员",
                {
                    "evidence_id": evidence_id,
                    "filename": filename,
                    "note": note,
                    "analysis": "未自动识别；关键字段为 unknown",
                },
                "human",
            )
        return case_bundle(case_id)
    finally:
        conn.close()


def export_case(case_id: str, fmt: str) -> tuple[str | bytes, str, str]:
    bundle = case_bundle(case_id)
    case = bundle["case"]
    if fmt=='docx':
        from .word_report import report
        return report(bundle),f'{case_id}.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    if fmt == "json":
        payload = {
            "schema_version": "1.0",
            "exported_at": now_iso(),
            "data_nature": "真实 IFC 几何 + 模拟现场观察 + 演示 Agent 输出",
            **bundle,
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        return content, f"{case_id}.json", "application/json"
    if fmt != "md":
        raise APIError(422, "invalid_format", "format 只支持 json 或 md")
    lines = [
        f"# Safety Case {case['case_id']}",
        "",
        f"- 标题：{case['title']}",
        f"- 状态：`{case['status']}`",
        f"- 检查时刻：{case['as_of']}",
        f"- 项目 / 模型 / 区域：{case['project_id']} / {case['model_id']} @ {case['model_version']} / {case['zone_id']}",
        f"- 数据性质：{case['provenance']}",
        f"- 模式：{case['mode']}",
        "",
        "> 本案例用于研究与文献综述展示。板边为人工标注检查边界；现场观察、施工活动和防护状态为模拟输入。",
        "",
        "## 1. 构件与证据",
        "",
        "| 构件 GUID | 证据 | 规范 |",
        "|---|---|---|",
        f"| {', '.join(case['bim_guids'])} | {', '.join(case['evidence_ids'])} | {', '.join(case['rule_ids'])} |",
        "",
        "## 2. Findings",
        "",
    ]
    if not case["findings"]:
        lines.append("尚未分析。")
    for finding in case["findings"]:
        lines.extend(
            [
                f"### {finding.get('finding_id')} {finding.get('hazard')}",
                "",
                f"- 结果：`{finding.get('result')}`",
                f"- 风险级别：{finding.get('risk_level')}",
                f"- 适用条款：{', '.join(finding.get('rule_ids') or [])}",
                f"- 范围说明：{finding.get('scope_note')}",
                "",
                "| 检查项 | 结果 | 来源 |",
                "|---|---|---|",
            ]
        )
        for check in finding.get("checks", []):
            lines.append(f"| {check['name']} | {check['result']} | {check.get('source', '')} |")
        lines.append("")
        if finding.get("uncertainties"):
            lines.append("不确定性：")
            for item in finding["uncertainties"]:
                lines.append(f"- {item}")
            lines.append("")
    lines.extend(["## 3. 控制措施", ""])
    if not case["controls"]:
        lines.append("无控制措施。")
    for control in case["controls"]:
        lines.extend(
            [
                f"### {control.get('control_id')}（v{control.get('version')}）",
                "",
                f"- 措施：{control.get('action')}",
                f"- 责任人：{control.get('owner')}",
                f"- 状态：`{control.get('status')}`",
                f"- 验证要求：{'；'.join(control.get('verification_requirements') or [])}",
                f"- 验收参数：{json.dumps(control.get('verification_criteria'), ensure_ascii=False)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 4. 审核、实施与复核",
            "",
            f"- 审核：{json.dumps(case.get('review'), ensure_ascii=False)}",
            f"- 实施：{json.dumps(case.get('implementation'), ensure_ascii=False)}",
            f"- 复核：{json.dumps(case.get('verification'), ensure_ascii=False)}",
            "",
            "## 5. 事件日志",
            "",
            "| 时间 | 状态 | 事件 | 操作者 |",
            "|---|---|---|---|",
        ]
    )
    for event in bundle["events"]:
        lines.append(f"| {event['at']} | `{event['status']}` | {event['event']} | {event['actor']} |")
    lines.extend(["", "## 6. 边界与假设", ""])
    for item in case["assumptions"]:
        lines.append(f"- {item}")
    for title, field in [('7. 任务理解与工具计划', 'task_spec'), ('8. Safety State', 'safety_state'), ('9. 决策包（分析时快照）', 'decision_package')]:
        if case.get(field):
            lines.extend(['', f'## {title}', '', '```json', json.dumps(case[field], ensure_ascii=False, indent=2), '```'])
    for title,value in [('10. 范围与人员标注',case.get('scope') or bundle.get('context',{}).get('zone',{}).get('data')),
                        ('11. 作业计划与版本',bundle.get('activity_plan')),
                        ('12. 现场文本、段落引用与澄清',{'notes':bundle.get('site_notes'),'context':bundle.get('site_text')})]:
        if value:
            lines.extend(['',f'## {title}','','```json',json.dumps(value,ensure_ascii=False,indent=2),'```'])
    lines.extend(
        [
            "",
            "---",
            "",
            "本导出不替代真实安全审批，不证明现场合规，不构成事故概率判断。",
            "",
        ]
    )
    return "\n".join(lines), f"{case_id}.md", "text/markdown"


def dashboard_summary() -> dict[str, Any]:
    conn = connect()
    try:
        model = dict(conn.execute("SELECT * FROM models LIMIT 1").fetchone())
        from .access import scoped_sql
        scope,params=scoped_sql()
        case_rows = conn.execute("SELECT * FROM cases WHERE "+scope,params).fetchall()
        all_cases = [serialize_case(dict(row)) for row in case_rows]
        cases = [case for case in all_cases if not case["title"].startswith("验收 ")]
        acceptance_cases = len(all_cases) - len(cases)
        status_counts: dict[str, int] = {}
        for case in cases:
            status_counts[case["status"]] = status_counts.get(case["status"], 0) + 1
        active_rules = conn.execute("SELECT COUNT(*) AS n FROM rules WHERE status='active'").fetchone()["n"]
        retired_rules = conn.execute("SELECT COUNT(*) AS n FROM rules WHERE status='retired'").fetchone()["n"]
        evidence_count = conn.execute("SELECT COUNT(*) AS n FROM evidence WHERE "+scope,params).fetchone()["n"]
        storey = conn.execute(
            "SELECT * FROM storeys WHERE model_id=? AND guid=?",
            (model["model_id"], "1Vhy2b2Mj9FRewx9CZZoux"),
        ).fetchone()
        latest_acceptance = conn.execute(
            "SELECT COUNT(*) AS total, SUM(passed) AS passed FROM acceptance_results"
        ).fetchone()
        latest_runs = [
            dict(row)
            for row in conn.execute(
                "SELECT run_id,case_id,status,created_at,finished_at,error FROM runs WHERE case_id IN (SELECT case_id FROM cases WHERE "+scope+") ORDER BY created_at DESC, rowid DESC LIMIT 5",params
            ).fetchall()
        ]
        return {
            "model": model,
            "storey": dict(storey) if storey else None,
            "element_count": model["element_count"],
            "storey_element_count": storey["element_count"] if storey else 0,
            "preview_mesh_count": 35,
            "cases_total": len(cases),
            "acceptance_cases": acceptance_cases,
            "status_counts": status_counts,
            "active_rules": active_rules,
            "retired_rules": retired_rules,
            "evidence_count": evidence_count,
            "open_cases": sum(1 for case in cases if case["status"] not in {"closed", "rejected"}),
            "risk_candidates": sum(
                1
                for case in cases
                for finding in case["findings"]
                if finding.get("result") == "risk_candidate"
            ),
            "acceptance": {
                "total": latest_acceptance["total"] or 0,
                "passed": latest_acceptance["passed"] or 0,
            },
            "latest_runs": latest_runs,
            "recent_cases": cases[:5],
            "demo_clock": DEMO_CLOCK,
            "mode": runtime_mode(),
        }
    finally:
        conn.close()


def latest_acceptance_results() -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM acceptance_results ORDER BY test_id").fetchall()
        return [
            {
                **dict(row),
                "passed": bool(row["passed"]),
                "details": loads(row["details_json"], {}),
            }
            for row in rows
        ]
    finally:
        conn.close()


def save_acceptance_result(
    test_id: str,
    name: str,
    expected: str,
    actual: str,
    passed: bool,
    details: dict[str, Any],
    case_id: str | None,
) -> None:
    conn = connect()
    try:
        with transaction() as tx:
            tx.execute(
                """INSERT OR REPLACE INTO acceptance_results
                   (test_id,name,expected,actual,passed,details_json,case_id,run_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    test_id,
                    name,
                    expected,
                    actual,
                    1 if passed else 0,
                    dumps(details),
                    case_id,
                    now_iso(),
                ),
            )
    finally:
        conn.close()


def get_run(run_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise APIError(404, "run_not_found", f"运行不存在：{run_id}")
        run = dict(row)
        events = [
            dict(event)
            for event in conn.execute(
                "SELECT * FROM agent_events WHERE run_id=? ORDER BY seq ASC", (run_id,)
            ).fetchall()
        ]
        for event in events:
            event["output"] = loads(event.pop("output_json"), {})
        run["events"] = events
        run["trace"] = loads(run.pop("trace_json"), [])
        artifact=conn.execute('SELECT input_hash,plan_json,trace_json,audit_json,gaps_json FROM run_artifacts WHERE run_id=?',(run_id,)).fetchone()
        if artifact:
            run.update(input_hash=artifact['input_hash'],execution_plan=loads(artifact['plan_json'],{}),
                evidence_trace=loads(artifact['trace_json'],{}),assurance=loads(artifact['audit_json'],{}),evidence_gaps=loads(artifact['gaps_json'],[]))
        job=conn.execute('SELECT state,attempts,recoveries,heartbeat_at,error_code,cancel_requested FROM run_jobs WHERE run_id=?',(run_id,)).fetchone()
        if job:
            run['runtime']=dict(job)
            run['runtime']['can_resume']=job['state']=='failed' and job['attempts']<3 and job['error_code'] not in {'stale_run_inputs','decision_audit_failed','run_budget_exceeded','run_cancelled'}
        run['model_calls'] = [dict(item) for item in conn.execute('SELECT * FROM model_calls WHERE run_id=? ORDER BY id', (run_id,))]
        for item in run['model_calls']:
            item['usage'] = loads(item.pop('usage_json'), {})
        return run
    finally:
        conn.close()


def list_runs(case_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    from .access import scoped_sql
    scope,params=scoped_sql()
    conn = connect()
    try:
        if case_id:
            rows = conn.execute(
                "SELECT * FROM runs WHERE case_id=? AND case_id IN (SELECT case_id FROM cases WHERE "+scope+") ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (case_id,*params,limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM runs WHERE case_id IN (SELECT case_id FROM cases WHERE "+scope+") ORDER BY created_at DESC, rowid DESC LIMIT ?", (*params,limit)
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def rules_list(query: str = "", include_retired: bool = False, top_k: int = 3, as_of: str = DEMO_CLOCK) -> dict[str, Any]:
    conn = connect()
    try:
        if include_retired:
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM rules ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, standard, clause"
                ).fetchall()
            ]
            if query:
                result = rule_retrieval(conn, query, as_of, 100)
                matched_ids = {item["rule_id"] for item in result["data"]["results"]}
                matched_ids.update(result["data"]["retired_excluded"])
                rows = [row for row in rows if row["rule_id"] in matched_ids]
            return {"results": rows, "retired_excluded": [], "query": query}
        result = rule_retrieval(conn, query or "临边 防护 坠落 高度 人员 1.2m", as_of, top_k)
        return result["data"]
    finally:
        conn.close()


def task_list(zone_id: str | None = None, as_of: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        from .access import scoped_sql
        scope,params=scoped_sql()
        if zone_id:
            rows = conn.execute("SELECT * FROM tasks WHERE zone_id=? AND "+scope, (zone_id,*params)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks WHERE "+scope,params).fetchall()
        tasks = []
        for row in rows:
            task = dict(row)
            task["bim_guids"] = loads(task.pop("bim_guids_json"), [])
            if as_of:
                at = parse_dt(as_of)
                start = parse_dt(task["planned_start"])
                end = parse_dt(task["planned_end"])
                task["active"] = bool(at and start and end and start <= at <= end)
            tasks.append(task)
        return tasks
    finally:
        conn.close()
