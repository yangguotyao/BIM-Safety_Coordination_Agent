from __future__ import annotations

import json
import threading
import uuid
import time
from datetime import datetime
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import DEMO_MODE, MODEL_NAME, live_model_configured
from .db import connect, dumps, loads, transaction
from .live_model import live_narrative
from .errors import APIError
from .coordinator import plan_task, scoped_inspection, safety_state as build_safety_state, decision_package
from .control_requirements import normalize_criteria
from .assurance import ToolResult,execution_plan,evidence_trace,audit_decision,assess_gaps,assert_snapshot,store_artifacts,cache_key
from .services import build_controls, demo_offset, save_analysis_result, serialize_case
from .tools import (
    bim_query,
    evidence_check,
    get_evidence,
    get_model,
    get_task,
    get_zone,
    now_iso,
    risk_assessment,
    rule_retrieval,
    schedule_query,
    spatial_check,
)

GLOBAL_RUN_LOCK = threading.Lock()


class AgentState(TypedDict, total=False):
    run_id: str
    case_id: str
    case: dict[str, Any]
    model: dict[str, Any]
    task: dict[str, Any]
    zone: dict[str, Any]
    bim: dict[str, Any]
    spatial: dict[str, Any]
    schedule: dict[str, Any]
    inspection: dict[str, Any]
    knowledge: dict[str, Any]
    risk: dict[str, Any]
    controls: list[dict[str, Any]]
    verification_plan: dict[str, Any]
    narrative: dict[str, Any]
    incomplete: bool
    fatal_error: str | None
    task_spec: dict[str, Any]
    context: dict[str, Any]
    coordination: dict[str,Any]
    site_text: dict[str,Any]
    execution_plan: dict[str,Any]
    evidence_trace: dict[str,Any]
    assurance: dict[str,Any]
    evidence_gaps: list[dict[str,Any]]


class Trace:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._seq = 0
        self._lock = threading.Lock()

    def emit(
        self,
        node: str,
        role: str,
        tool: str | None,
        input_summary: str,
        output: dict[str, Any] | None,
        status: str,
        rationale: str = "",
        error: str | None = None,
    ) -> None:
        conn = connect()
        try:
            with transaction() as tx:
                row = tx.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM agent_events WHERE run_id=?",
                    (self.run_id,),
                ).fetchone()
                seq = int(row["next_seq"])
                tx.execute(
                    """INSERT INTO agent_events
                       (run_id,seq,node,role,tool,input_summary,output_json,status,error,rationale,at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        self.run_id,
                        seq,
                        node,
                        role,
                        tool,
                        input_summary[:1500],
                        dumps(output or {}),
                        status,
                        error,
                        rationale[:1000],
                        now_iso(),
                    ),
                )
        finally:
            conn.close()

    def call(
        self,
        *,
        node: str,
        role: str,
        tool: str,
        input_summary: str,
        fn: Callable[[], dict[str, Any]],
        critical: bool,
        success_rationale: str = "",
    ) -> dict[str, Any]:
        from .durable import guard_run
        guard_run(self.run_id)
        cached_key=cache_key(self.run_id,tool,input_summary)
        if cached_key:
            conn=connect()
            try:cached=conn.execute('SELECT * FROM tool_cache WHERE case_id=? AND tool=? AND input_hash=?',(*cached_key[:1],tool,cached_key[1])).fetchone()
            finally:conn.close()
            if cached:
                result=loads(cached['result_json'])
                result['_execution']={'cache_hit':True,'source_run_id':cached['source_run_id'],'input_hash':cached_key[1],'elapsed_ms':0}
                self.emit(node,role,tool,input_summary,result,'cached','输入版本未改变，复用同一Case的只读计算；风险和现场观察仍重新校核。')
                return result
        last_error: Exception | None = None
        for attempt in (1, 2):
            started=time.monotonic()
            try:
                guard_run(self.run_id)
                result = ToolResult.model_validate(fn()).model_dump()
                result['_execution']={'elapsed_ms':round((time.monotonic()-started)*1000),'attempt':attempt,'cache_hit':False}
                if result.get("ok") is False:
                    raise APIError(
                        500,
                        "tool_failed",
                        f"{tool} 返回 ok=false",
                        result.get("error"),
                    )
                self.emit(
                    node,
                    role,
                    tool,
                    input_summary,
                    result,
                    "succeeded" if attempt == 1 else "succeeded_after_retry",
                    success_rationale,
                )
                if cached_key:
                    with transaction() as tx:tx.execute('INSERT OR REPLACE INTO tool_cache VALUES(?,?,?,?,?,?)',
                        (cached_key[0],tool,cached_key[1],dumps(result),self.run_id,now_iso()))
                return result
            except Exception as exc:  # noqa: BLE001 - recorded as tool failure
                last_error = exc
                permanent=isinstance(exc,APIError) and 400<=exc.status_code<500 and exc.status_code not in {408,429}
                self.emit(
                    node,
                    role,
                    tool,
                    input_summary,
                    {
                        "ok": False,
                        "error": type(exc).__name__,
                        "message": str(exc)[:500],
                    },
                    "retrying" if attempt == 1 and not permanent else "failed",
                    "工具失败，按合同最多重试一次。" if attempt == 1 else "重试后仍失败。",
                    str(exc),
                )
                if permanent:break
        if isinstance(last_error,APIError) and last_error.code in {'run_cancelled','run_budget_exceeded','stale_run_inputs'}:raise last_error
        if critical:
            raise APIError(500, "tool_failed", f"{tool} 重试后失败", str(last_error))
        return {
            "ok": False,
            "data": None,
            "provenance": "unknown",
            "model_version": None,
            "units": None,
            "method": tool,
            "evidence_ids": [],
            "rule_ids": [],
            "uncertainties": [f"{tool} 执行失败，分析不完整。"],
            "error": str(last_error),
        }


def _load_case(case_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise APIError(404, "case_not_found", f"案例不存在：{case_id}")
        return serialize_case(dict(row))
    finally:
        conn.close()


def _prepare(state: AgentState, trace: Trace) -> AgentState:
    case = _load_case(state["case_id"])
    if case["status"] != "analyzing":
        raise APIError(409, "transition_rejected", f"案例状态为 {case['status']}，不能分析")
    conn = connect()
    try:
        model = get_model(conn, case["model_id"])
        task = get_task(conn, case["task_id"])
        zone = get_zone(conn, case["zone_id"])
    finally:
        conn.close()
    trace.emit(
        "Safety Coordinator · 准备",
        "Safety Coordinator",
        None,
        f"case={case['case_id']} model={case['model_id']}@{case['model_version']} zone={case['zone_id']}",
        {
            "ok": True,
            "data": {
                "case_status": case["status"],
                "model": {"model_id": model["model_id"], "version": model["version"]},
                "task": {
                    "task_id": task["task_id"],
                    "activity": task["activity"],
                    "window": [task["planned_start"], task["planned_end"]],
                    "provenance": task["provenance"],
                },
                "zone": {
                    "zone_id": zone["zone_id"],
                    "storey_name": zone["storey_name"],
                    "target_guid": zone["target_guid"],
                },
            },
            "provenance": "real_source+simulated",
            "units": "m",
            "uncertainties": [],
        },
        "succeeded",
        "先固定案例边界：项目、模型版本、区域、检查时刻和任务。",
    )
    spec, context = plan_task(case, task['activity'])
    case['task_spec'] = spec
    trace.emit('任务理解与工具规划','Safety Coordinator',
        'live_task_plan' if spec['mode']=='live_model' else 'demo_task_plan',
        spec['request'], {'ok':True,'data':spec,'context_message_count':len(context['messages']),
                         'context_bytes':context['context_bytes'],'tool_catalog':list(context['tool_catalog'])},
        'needs_clarification' if spec['needs_clarification'] else 'succeeded',
        '固定区域与时刻，在工具白名单内按本次检查重点选择。')
    plan=execution_plan(case,spec)
    store_artifacts(state['run_id'],plan=plan)
    trace.emit('受约束执行计划','Safety Coordinator','policy_plan',spec['request'],{'ok':True,'data':plan},'succeeded',
        '工具参数与依赖由程序编译；核心安全步骤不可省略，所有工具均无审批权限。')
    return {**state, "case": case, "model": model, "task": task, "zone": zone,'execution_plan':plan,
            'task_spec':spec,'context':context,'incomplete':spec['needs_clarification']}


def _bim_context(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    conn = connect()
    try:
        bim = trace.call(
            node="BIM Context",
            role="BIM Tool",
            tool="bim_query",
            input_summary=f"model={case['model_id']} guids={case['bim_guids']}",
            fn=lambda: bim_query(conn, case),
            critical=True,
            success_rationale="构件存在且属于已索引的 05 层；几何可用状态已返回。",
        )
        if 'spatial_check' not in state['task_spec']['selected_tools']:
            spatial = {'ok':True,'data':None,'method':'not_requested','uncertainties':[]}
            trace.emit('BIM Context · 空间','BIM Tool',None,'本次任务不需要距离计算',
                       spatial,'skipped','按检查重点省略空间调用，不将省略展示为已执行。')
        else:
            spatial = trace.call(
                node="BIM Context · 空间",
                role="BIM Tool",
                tool="spatial_check",
                input_summary=f"zone={case['zone_id']} point=模拟人员位置 edge=人工标注边线",
                fn=lambda: spatial_check(conn, case),
                critical=False,
                success_rationale="仅计算与人工标注边线的距离，不推断真实坠落边缘。",
            )
    finally:
        conn.close()
    incomplete = bool(state.get("incomplete")) or not spatial.get("ok")
    return {**state, "bim": bim, "spatial": spatial, "incomplete": incomplete}


def _schedule(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    conn = connect()
    try:
        result = trace.call(
            node="Schedule",
            role="Schedule Tool",
            tool="schedule_query",
            input_summary=f"task={case['task_id']} as_of={case['as_of']}",
            fn=lambda: schedule_query(conn, case),
            critical=False,
            success_rationale="检查检查时刻是否落在模拟活动时间窗内。",
        )
        from .coordination import activity_conflict_check
        coordination={'ok':True,'data':{'configured':False,'complete':True,'conflicts':[]}}
        if 'activity_conflict_check' in state['task_spec']['selected_tools']:
            coordination=trace.call(node='Schedule · 多活动空间',role='Schedule Tool',tool='activity_conflict_check',
                input_summary=f"case={case['case_id']}；活动时间交集与三维作业范围",
                fn=lambda:activity_conflict_check(conn,case),critical=True)
    finally:
        conn.close()
    incomplete = bool(state.get("incomplete")) or not result.get("ok") or not result.get("data", {}).get("active") or not coordination['data']['complete']
    return {**state, "schedule": result,'coordination':coordination, "incomplete": incomplete}


def _inspection(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    conn = connect()
    try:
        if not DEMO_MODE:
            from .vision import inspect_image
            for evidence_id in case['evidence_ids']:
                item = get_evidence(conn,evidence_id)
                if item['source']=='upload' and item['stage']=='before' and item['file_path'].lower().endswith(('.png','.jpg','.jpeg')):
                    trace.call(node='Inspection · 图像观察',role='Inspection',tool='qwen_image_observation',
                        input_summary=f'evidence={evidence_id}；模型候选需人工确认，不测量真实高度',
                        fn=lambda eid=evidence_id:{'ok':True,'data':inspect_image(case['case_id'],eid,in_agent=True)},
                        critical=True,success_rationale='Qwen读取图像，候选持久化；已确认观察复用明确的证据版本。')
        result = trace.call(
            node="Inspection",
            role="Inspection",
            tool="evidence_check",
            input_summary=f"case={case['case_id']} evidence={case['evidence_ids']}",
            fn=lambda: scoped_inspection(evidence_check(conn, case),state['task_spec']),
            critical=True,
            success_rationale="证据与项目、模型版本、区域、任务时间窗逐项匹配，并检查观察字段完整性。",
        )
    finally:
        conn.close()
    text={'ok':True,'data':{'complete':True,'facts':[],'conflicts':[]}}
    if 'site_text_query' in state['task_spec']['selected_tools']:
        from .site_text import extract_site_note,text_context
        def read_text():
            conn=connect()
            try: pending=text_context(conn,case,result['data'])['pending_notes']
            finally: conn.close()
            for note_id in pending: extract_site_note(case['case_id'],note_id,in_agent=True)
            conn=connect()
            try: return {'ok':True,'data':text_context(conn,case,result['data'])}
            finally: conn.close()
        text=trace.call(node='Inspection · 现场文本',role='Inspection',tool='site_text_query',
            input_summary='原文段落引用；不覆盖人工确认的图像观察',fn=read_text,critical=True)
    incomplete = bool(state.get("incomplete")) or not result.get("data", {}).get("data_complete") or not text['data']['complete']
    return {**state, "inspection": result,'site_text':text, "incomplete": incomplete}


def _knowledge(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    query = state.get('task_spec', {}).get('retrieval_query') or (
        f"{state['task'].get('activity', '')} 临边 防护 栏杆 坠落 高度 人员 "
        "2m 1.2m 安全 作业 边沿 周边 围护 孔洞 楼层"
    )
    conn = connect()
    try:
        result = trace.call(
            node="Knowledge",
            role="Knowledge",
            tool="rule_retrieval",
            input_summary=f"query={query} as_of={case['as_of']} top_k=3",
            fn=lambda: rule_retrieval(conn, query, case["as_of"], 3),
            critical=False,
            success_rationale="只检索 active 的人工核对释义；retired 历史条款被排除。",
        )
    finally:
        conn.close()
    incomplete = bool(state.get("incomplete")) or not result.get("data", {}).get("results")
    return {**state, "knowledge": result, "incomplete": incomplete}


def _risk(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    conn = connect()
    try:
        result = trace.call(
            node="Risk",
            role="Risk",
            tool="risk_assessment",
            input_summary="task_active + evidence_match + observation + geometry + active rules",
            fn=lambda: risk_assessment(
                conn,
                case,
                state.get("bim", {}),
                state.get("spatial", {}),
                state.get("schedule", {}),
                state.get("inspection", {}),
                state.get("knowledge", {}),
            ),
            critical=True,
            success_rationale="确定性检查表给出 risk_candidate / no_issue_in_checked_items / needs_evidence。",
        )
    finally:
        conn.close()
    from .coordination import coordination_findings
    additional=coordination_findings(case,state.get('coordination',{}).get('data',{}))
    text=state.get('site_text',{}).get('data',{})
    if not text.get('complete',True):
        additional.append({'finding_id':'F-TEXT-001','kind':'text','hazard':'现场文本差异或候选资料待澄清',
            'result':'needs_evidence','risk_level':'待澄清','bim_guids':case['bim_guids'],
            'evidence_ids':list(dict.fromkeys(c['evidence_id'] for c in text.get('conflicts',[]) if c.get('evidence_id'))),
            'rule_ids':[],'checks':[{'name':'现场文本已核对','result':'unknown','source':'site_text_query'}],
            'uncertainties':['文本候选与已确认观察分开保存，需人工澄清。'],'inputs':text})
    result['data']['additional_findings']=additional
    if state.get('incomplete'): result['data']['result']='needs_evidence'
    elif any(f['result']=='risk_candidate' for f in additional): result['data']['result']='risk_candidate'
    return {**state, "risk": result}


def _intervention(state: AgentState, trace: Trace) -> AgentState:
    finding = state.get("risk", {}).get("data", {}).get("finding")
    from .coordination import coordination_control
    controls = build_controls(finding or {})
    controls += [coordination_control(item,state['task']['owner']) for item in state['risk']['data'].get('additional_findings',[]) if item.get('kind')=='coordination']
    for control in controls:
        control['owner'] = state['task']['owner']
    if controls and not DEMO_MODE:
        from .live_model import live_control_draft
        for base in controls:
            related=next((f for f in [finding]+state['risk']['data'].get('additional_findings',[]) if f['finding_id']==base['finding_id']),finding)
            result = trace.call(node='Intervention · 措施组织',role='Intervention',tool='live_control_draft',
                input_summary='基于已校核风险组织候选措施，验收阈值保持固定',
                fn=lambda:{'ok':True,'data':live_control_draft({'case_id':state['case_id'], 'task_spec':state['task_spec'],
                    'bim_context':state.get('bim',{}).get('data'), 'schedule':state.get('schedule',{}).get('data'),
                    'coordination':state.get('coordination',{}).get('data'),'finding':related,'base_control':base})}, critical=True)
            draft = result['data']
            check = normalize_criteria({**base,**draft},modified=True)
            if check['min_height_m'] != base['verification_criteria']['min_height_m']:
                raise APIError(422,'unverified_control_parameter','模型改变了未经批准的验收参数')
            base.update(draft)
            base['provenance']='live_model_candidate_checked_against_tool_results'
    trace.emit(
        "Intervention",
        "Intervention",
        "control_template",
        f"finding={finding.get('finding_id') if finding else None} result={finding.get('result') if finding else None}",
        {
            "ok": True,
            "data": {"controls": controls, "template": "demo_deterministic" if DEMO_MODE else "checked_model_draft"},
            "provenance": "demo_template" if DEMO_MODE else "live_model_candidate_checked_against_tool_results",
            "units": None,
            "uncertainties": ["候选措施需人工审核，不得写成已执行。"],
        },
        "succeeded",
        "由模板生成候选控制措施；批准与实施必须由人工记录。",
    )
    return {**state, "controls": controls}


def _llm_reasoning(state: AgentState, trace: Trace) -> AgentState:
    case = state["case"]
    finding = state.get("risk", {}).get("data", {}).get("finding") or {}
    knowledge = state.get("knowledge", {}).get("data", {}).get("results", [])
    context = {
        "case_id": case["case_id"],
        "model_id": case["model_id"],
        "model_version": case["model_version"],
        "zone_id": case["zone_id"],
        "as_of": case["as_of"],
        "task": {
            "activity": state.get("task", {}).get("activity"),
            "window": [
                state.get("task", {}).get("planned_start"),
                state.get("task", {}).get("planned_end"),
            ],
            "provenance": state.get("task", {}).get("provenance"),
        },
        'task_spec':state.get('task_spec'),
        'safety_state':build_safety_state(state),
        'additional_findings':state.get('risk',{}).get('data',{}).get('additional_findings',[]),
        'overall_result':state.get('risk',{}).get('data',{}).get('result'),
        'allowed_finding_ids':[f['finding_id'] for f in state.get('risk',{}).get('data',{}).get('additional_findings',[])],
        "rules": [
            {
                "rule_id": item.get("rule_id"),
                "standard": item.get("standard"),
                "clause": item.get("clause"),
                "text": item.get("text"),
                "text_kind": item.get("text_kind"),
            }
            for item in knowledge
        ],
        "finding": {
            "finding_id": finding.get("finding_id"),
            "hazard": finding.get("hazard"),
            "result": finding.get("result"),
            "checks": finding.get("checks"),
            "uncertainties": finding.get("uncertainties"),
        },
        "allowed_guids": case.get("bim_guids", []),
        "allowed_rule_ids": [item.get("rule_id") for item in knowledge],
        "allowed_evidence_ids": list(case.get("evidence_ids", [])),
        "finding_id": finding.get("finding_id"),
    }
    context["evidence"] = [
        {
            "evidence_id": item.get("evidence_id"),
            "label": item.get("label"),
            "captured_at": item.get("captured_at"),
            "stage": item.get("stage"),
            "provenance": item.get("provenance"),
            "observation": item.get("observation"),
        }
        for item in state.get("inspection", {}).get("data", {}).get("records", [])
    ]
    context['allowed_evidence_ids'] += [f['paragraph_id'] for f in state.get('site_text',{}).get('data',{}).get('facts',[])]

    if not DEMO_MODE:
        if not live_model_configured():
            raise APIError(503, "live_model_config_incomplete", "真实模型配置不完整")
        result = trace.call(
            node="LLM 归纳",
            role="Safety Coordinator",
            tool="openai_compatible_chat",
            input_summary=f"model={MODEL_NAME} case={case['case_id']} (key 不写入日志)",
            fn=lambda: {
                "ok": True,
                "data": live_narrative(context),
                "provenance": "live_model",
                "model_version": case["model_version"],
                "units": "m",
                "method": "OpenAI-compatible chat completions + Pydantic + 引用白名单",
                "evidence_ids": case.get("evidence_ids", []),
                "rule_ids": [item.get("rule_id") for item in knowledge],
                "uncertainties": [],
                "error": None,
            },
            critical=True,
            success_rationale="真实模型只在白名单证据、规则与工具结果内归纳；不产出几何数值或批准状态。",
        )
    else:
        summary = (
            f"{finding.get('hazard') or '待补证'}。"
            f"依据 {', '.join(item.get('rule_id') for item in knowledge) or '无现行条款'} 与 "
            f"{', '.join(case.get('evidence_ids', []))}，检查结果为 "
            f"{finding.get('result')}；结论只对已检查项成立。"
        )
        result = {
            "ok": True,
            "data": {
                "summary": summary[:600],
                "reasoning_basis": [
                    {"type": "evidence", "id": evidence_id}
                    for evidence_id in case.get("evidence_ids", [])
                ]
                + [{"type": "rule", "id": item.get("rule_id")} for item in knowledge]
                + [{"type": "finding", "id": finding.get("finding_id")}],
                "uncertainties": finding.get("uncertainties", []),
                "label": "演示模型输出（确定性模板）",
            },
            "provenance": "demo_template",
            "model_version": case["model_version"],
            "units": "m",
            "method": "确定性模板；DEMO_MODE=true，不调用外部模型",
            "evidence_ids": case.get("evidence_ids", []),
            "rule_ids": [item.get("rule_id") for item in knowledge],
            "uncertainties": finding.get("uncertainties", []),
            "error": None,
        }
        trace.emit(
            "LLM 归纳",
            "Safety Coordinator",
            "demo_template",
            f"case={case['case_id']} evidence={case.get('evidence_ids')}",
            result,
            "succeeded",
            "演示模式：用确定性模板归纳，不调用收费 API，界面标记“演示模型输出”。",
        )
    return {**state, "narrative": result.get("data", {})}


def _verification_plan(state: AgentState, trace: Trace) -> AgentState:
    controls = state.get("controls", [])
    finding = state.get("risk", {}).get("data", {}).get("finding") or {}
    plan = {
        "required_evidence": [
            "同项目、同模型版本、同区域、同构件的实施后证据",
            "证据时间晚于人工记录的实施时刻",
            "防护存在、高度 ≥ 1.2 m、固定与连续性标注",
            "演示安全员人工确认",
        ]
        if controls
        else ["需补齐或澄清资料后重新分析"] if state.get('incomplete') else ["无需整改；保留本次已检查项与证据边界说明"],
        "rule_ids": finding.get("rule_ids", []),
        "scope": "只验证演示中列明项目，不证明整个现场安全。",
    }
    trace.emit(
        "Verification · 计划",
        "Verification",
        "verification_plan",
        f"finding={finding.get('finding_id')} controls={len(controls)}",
        {
            "ok": True,
            "data": plan,
            "provenance": "agent_orchestration",
            "units": "m",
            "uncertainties": [plan["scope"]],
        },
        "succeeded",
        "在分析阶段明确关闭案例所需的人工复核证据，实际复核由 verify 接口执行。",
    )
    return {**state, "verification_plan": plan}


def _after_risk(state: AgentState) -> str:
    result = state.get("risk", {}).get("data", {}).get("result")
    if result == "risk_candidate":
        return "intervention"
    return "verification_plan"


def _request_evidence(state:AgentState,trace:Trace)->AgentState:
    gaps=assess_gaps(state)
    plan={**state['execution_plan'],'replanning':{'round':1,'reason':'evidence_gap','next_action':'await_human_evidence',
        'affected_tools':['evidence_check','risk_assessment'],'deferred_model_calls':['risk_summary','control_draft']}}
    store_artifacts(state['run_id'],plan=plan,gaps=gaps)
    text='本次检查需补充：'+'；'.join(gap['message'] for gap in gaps)+'。资料核对完成后继续分析，当前不形成可批准的整改结论。'
    narrative={'summary':text[:600],'reasoning_basis':[],'uncertainties':[g['message'] for g in gaps],
        'label':'补证要求（程序生成）','source':'deterministic_gap_planner'}
    from .run_stream import publish
    publish(state['run_id'],narrative['summary'],'validated')
    trace.emit('证据缺口驱动规划','Safety Coordinator','bounded_replan','必要信息不足，不调用模型猜测',
        {'ok':True,'data':{'replanning':plan['replanning'],'gaps':gaps}},'needs_evidence','按缺失字段生成定向补证，暂停风险文字和措施生成。')
    return {**state,'execution_plan':plan,'evidence_gaps':gaps,'narrative':narrative,'controls':[],'incomplete':True}


def _assurance(state:AgentState,trace:Trace)->AgentState:
    conn=connect()
    try:row=conn.execute('SELECT input_json FROM run_artifacts WHERE run_id=?',(state['run_id'],)).fetchone()
    finally:conn.close()
    snapshot=loads(row['input_json'])
    assert_snapshot(state['case_id'],snapshot)
    lineage=evidence_trace(state,snapshot)
    finding=state.get('risk',{}).get('data',{}).get('finding')
    findings=([finding] if finding else [])+state.get('risk',{}).get('data',{}).get('additional_findings',[])
    audit=audit_decision(state['case'],lineage,findings,state.get('controls',[]),state.get('knowledge',{}).get('data',{}).get('results',[]))
    gaps=assess_gaps(state)
    store_artifacts(state['run_id'],trace=lineage,audit=audit,gaps=gaps)
    trace.emit('证据与决策校核','Verification','decision_audit','来源、范围、单位、规则版本与工程约束',
        {'ok':True,'data':audit},'succeeded' if audit['status']=='passed' else 'blocked','确定性校核，不使用AI投票，也不授予批准权限。')
    if gaps:trace.emit('定向补证','Safety Coordinator','evidence_gap_plan','只请求当前缺失或冲突项',{'ok':True,'data':gaps},'needs_evidence','补证后重新规划，未知字段不自动补值。')
    if audit['status']=='blocked':raise APIError(422,'decision_audit_failed','决策未通过证据与工程约束校核',audit['issues'])
    return {**state,'evidence_trace':lineage,'assurance':audit,'evidence_gaps':gaps}


def _finalize(state: AgentState, trace: Trace) -> AgentState:
    conn=connect()
    try:artifact=conn.execute('SELECT input_json FROM run_artifacts WHERE run_id=?',(state['run_id'],)).fetchone()
    finally:conn.close()
    if artifact:assert_snapshot(state['case_id'],loads(artifact['input_json']))
    case = state["case"]
    risk = state.get("risk", {}).get("data", {})
    finding = risk.get("finding")
    narrative = state.get("narrative")
    if finding and narrative:
        finding = {**finding, "narrative": narrative}
    controls = state.get("controls", [])
    rule_ids = state.get("knowledge", {}).get("rule_ids", [])
    incomplete = bool(state.get("incomplete"))
    if incomplete or not finding:
        status = "needs_evidence"
        finding = finding or {
            "finding_id": "F-001",
            "hazard": (state.get('task_spec') or {}).get('clarification') or "分析不完整，需补充证据",
            "result": "needs_evidence",
            "risk_level": "未判定",
            "bim_guids": case.get("bim_guids", []),
            "evidence_ids": case.get("evidence_ids", []),
            "rule_ids": rule_ids,
            "checks": [],
            "uncertainties": ["关键工具或字段失败，系统没有自动判定为无风险。"],
            "provenance": "analysis_incomplete",
            "scope_note": "分析不完整，不形成确定结论。",
        }
    else:
        status = "pending_review" if finding.get("result") in {"risk_candidate", "no_issue_in_checked_items"} else "needs_evidence"

    save_analysis_result(
        state["run_id"],
        case["case_id"],
        finding,
        controls,
        rule_ids,
        status,
        incomplete,
        task_spec=state.get('task_spec'),
        safety_state=build_safety_state(state),
        decision_package=decision_package(state,finding,controls),
        additional_findings=risk.get('additional_findings',[]),
    )
    trace.emit(
        "Safety Coordinator · 收口",
        "Safety Coordinator",
        None,
        f"result={finding.get('result')} incomplete={incomplete}",
        {
            "ok": True,
            "data": {
                "status": status,
                "finding_result": finding.get("result"),
                "controls": len(controls),
                "rule_ids": rule_ids,
                "incomplete": incomplete,
            },
            "provenance": "agent_orchestration",
            "units": "m",
            "uncertainties": finding.get("uncertainties", []),
        },
        "succeeded",
        "按检查结果迁移状态；risk_candidate 进入 pending_review，证据不足进入 needs_evidence。",
    )
    return {**state, "controls": controls, "incomplete": incomplete}


def _build_graph(checkpointer=None,*,adaptive=True):
    graph = StateGraph(AgentState)
    graph.add_node("prepare", lambda state: _prepare(state, Trace(state["run_id"])))
    graph.add_node("bim_context", lambda state: _bim_context(state, Trace(state["run_id"])))
    graph.add_node("schedule", lambda state: _schedule(state, Trace(state["run_id"])))
    graph.add_node("inspection", lambda state: _inspection(state, Trace(state["run_id"])))
    graph.add_node("knowledge", lambda state: _knowledge(state, Trace(state["run_id"])))
    graph.add_node("risk", lambda state: _risk(state, Trace(state["run_id"])))
    graph.add_node("intervention", lambda state: _intervention(state, Trace(state["run_id"])))
    graph.add_node("llm_reasoning", lambda state: _llm_reasoning(state, Trace(state["run_id"])))
    graph.add_node("verification_plan", lambda state: _verification_plan(state, Trace(state["run_id"])))
    graph.add_node("finalize", lambda state: _finalize(state, Trace(state["run_id"])))
    graph.add_node('assurance',lambda state:_assurance(state,Trace(state['run_id'])))
    graph.add_node('request_evidence',lambda state:_request_evidence(state,Trace(state['run_id'])))

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges('prepare',lambda state:'assurance' if state.get('task_spec',{}).get('needs_clarification') else 'bim_context',
                                {'assurance':'assurance','bim_context':'bim_context'})
    graph.add_edge("bim_context", "schedule")
    graph.add_edge("schedule", "inspection")
    graph.add_edge("inspection", "knowledge")
    graph.add_edge("knowledge", "risk")
    graph.add_conditional_edges('risk',lambda state:'request_evidence' if adaptive and (state.get('incomplete') or state.get('risk',{}).get('data',{}).get('result')=='needs_evidence') else 'llm_reasoning',
        {'request_evidence':'request_evidence','llm_reasoning':'llm_reasoning'})
    graph.add_edge('request_evidence','verification_plan')
    graph.add_conditional_edges("llm_reasoning", _after_risk, {"intervention": "intervention", "verification_plan": "verification_plan"})
    graph.add_edge("intervention", "verification_plan")
    graph.add_edge("verification_plan", "assurance")
    graph.add_edge('assurance','finalize')
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


GRAPH = _build_graph()


def _update_run(run_id: str, status: str, error: str | None = None) -> None:
    conn = connect()
    try:
        with transaction() as tx:
            trace = [
                {
                    "seq": row["seq"],
                    "node": row["node"],
                    "role": row["role"],
                    "tool": row["tool"],
                    "status": row["status"],
                    "at": row["at"],
                }
                for row in tx.execute(
                    "SELECT seq,node,role,tool,status,at FROM agent_events WHERE run_id=? ORDER BY seq",
                    (run_id,),
                ).fetchall()
            ]
            tx.execute(
                "UPDATE runs SET status=?,started_at=COALESCE(started_at,?),finished_at=?,trace_json=?,error=? WHERE run_id=?",
                (
                    status,
                    now_iso(),
                    now_iso() if status in {"succeeded", "failed"} else None,
                    dumps(trace),
                    error,
                    run_id,
                ),
            )
    finally:
        conn.close()


def _mark_case_incomplete(case_id: str, run_id: str, error: str) -> None:
    conn = connect()
    try:
        with transaction() as tx:
            row = tx.execute("SELECT status,last_run_id FROM cases WHERE case_id=?", (case_id,)).fetchone()
            if row and row["status"] == "analyzing" and row['last_run_id']==run_id:
                tx.execute(
                    "UPDATE cases SET status='needs_evidence',analysis_incomplete=1,updated_at=?,version=version+1 WHERE case_id=?",
                    (now_iso(), case_id),
                )
                tx.execute(
                    """INSERT INTO case_events(case_id,at,status,event,actor,detail_json,provenance)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        case_id,
                        now_iso(),
                        "needs_evidence",
                        "analysis_incomplete",
                        "Safety Coordinator",
                        dumps({"run_id": run_id, "error": error}),
                        "agent",
                    ),
                )
    finally:
        conn.close()


def execute_run(run_id: str) -> None:
    from .durable import claim_run,checkpoints,guard_run,finish_run,heartbeat,flush_workflows
    if not claim_run(run_id):return
    conn = connect()
    try:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run:
            return
        if run["status"] not in {"queued", "running"}:
            return
        case_id = run["case_id"]
        with transaction() as tx:
            tx.execute(
                "UPDATE runs SET status='running',started_at=COALESCE(started_at,?) WHERE run_id=?",
                (now_iso(), run_id),
            )
    finally:
        conn.close()

    from .model_client import CURRENT_RUN
    done=threading.Event()
    keeper=threading.Thread(target=heartbeat,args=(run_id,done),daemon=True,name='lease-'+run_id)
    keeper.start()
    token = CURRENT_RUN.set(run_id)
    try:
        guard_run(run_id)
        conn=connect()
        try:
            artifact=conn.execute('SELECT input_json FROM run_artifacts WHERE run_id=?',(run_id,)).fetchone()
            case_row=conn.execute('SELECT status,last_run_id FROM cases WHERE case_id=?',(case_id,)).fetchone()
            committed=conn.execute("SELECT 1 FROM case_events WHERE case_id=? AND event='analysis_completed' AND json_extract(detail_json,'$.run_id')=?",(case_id,run_id)).fetchone()
        finally:conn.close()
        if case_row['last_run_id']!=run_id:raise APIError(409,'superseded_run','运行已被新的任务替代')
        if committed:
            _update_run(run_id,'succeeded');finish_run(run_id,'completed');return
        if artifact:assert_snapshot(case_id,loads(artifact['input_json']))
        else:
            from .assurance import input_snapshot
            snapshot=input_snapshot(case_id)
            with transaction() as tx:tx.execute('INSERT INTO run_artifacts(run_id,input_hash,input_json,created_at) VALUES(?,?,?,?)',
                (run_id,snapshot['input_hash'],dumps(snapshot),now_iso()))
        if case_row['status']!='analyzing':raise APIError(409,'transition_rejected','案例已离开当前分析阶段')
        with checkpoints() as saver:
            graph=_build_graph(saver);config={'configurable':{'thread_id':run_id}}
            saved=graph.get_state(config)
            graph.invoke(None if saved.next else {"run_id":run_id,"case_id":case_id,"incomplete":False},config=config,durability='sync')
        _update_run(run_id, "succeeded")
        finish_run(run_id,'completed')
    except Exception as exc:  # noqa: BLE001 - persisted for the operator
        message = f"{type(exc).__name__}: {exc}"
        _update_run(run_id, "failed", message)
        _mark_case_incomplete(case_id, run_id, message)
        from .run_stream import publish
        publish(run_id,'','rejected')
        trace = Trace(run_id)
        trace.emit(
            "Safety Coordinator · 失败",
            "Safety Coordinator",
            None,
            f"case={case_id} run={run_id}",
            {"ok": False, "error": message},
            "failed",
            "关键节点失败，案例标记为分析不完整，不自动判定无风险。",
            message,
        )
        finish_run(run_id,'cancelled' if isinstance(exc,APIError) and exc.code=='run_cancelled' else 'failed',exc.code if isinstance(exc,APIError) else type(exc).__name__)
    finally:
        CURRENT_RUN.reset(token)
        done.set();keeper.join(timeout=1)
        flush_workflows(case_id)


def start_background_run(run_id: str) -> None:
    thread = threading.Thread(target=execute_run, args=(run_id,), daemon=True, name=f"agent-{run_id}")
    thread.start()


def architecture() -> dict[str, Any]:
    return {
        "principle": "LLM understands and orchestrates; specialised tools perceive and compute.",
        'version':'2.0','planning':'typed_subtasks_and_policy_dependencies',
        'runtime':'checkpointed_analysis_and_human_gated_lifecycle',
        'authority':'business_state_machine_and_deterministic_rules',
        "six_roles": [
            {
                "role": "Safety Coordinator",
                "duty": "维护案例状态、拆解任务、协调节点、决定下一步",
                "tools": ["all tools", "state machine"],
                "color": "teal",
            },
            {
                "role": "Knowledge",
                "duty": "检索现行有效规范与条文释义，保留来源和页码",
                "tools": ["rule_retrieval / FTS5"],
                "color": "blue",
            },
            {
                "role": "Inspection",
                "duty": "读取现场证据并形成结构化观察，标记缺失字段",
                "tools": ["qwen_image_observation", "human observation confirmation", "evidence_check"],
                "color": "amber",
            },
            {
                "role": "Risk",
                "duty": "综合几何、活动、证据和规则，形成风险候选或 needs_evidence",
                "tools": ["spatial_check", "risk_assessment"],
                "color": "red",
            },
            {
                "role": "Intervention",
                "duty": "生成可审核控制措施、责任人和验证要求",
                "tools": ["live_control_draft", "approved criteria", "schedule context"],
                "color": "violet",
            },
            {
                "role": "Verification",
                "duty": "检查实施后证据、时间、区域、规则与残余风险",
                "tools": ["verification_check"],
                "color": "green",
            },
        ],
        "bim_tools": ["bim_query", "spatial_check", "schedule_query"],
        "nodes": [
            "Safety Coordinator · 准备",
            "BIM Context",
            "Schedule",
            "Inspection",
            "Knowledge",
            "Risk",
            "LLM 归纳",
            "Intervention",
            "Verification · 计划",
            '证据与决策校核',
            '定向补证（缺证分支）',
            "Safety Coordinator · 收口",
        ],
        "boundary": "BIM 几何、距离、时间匹配和规则阈值由确定性代码执行；LLM 不生成未经执行的工程数值。",
    }
