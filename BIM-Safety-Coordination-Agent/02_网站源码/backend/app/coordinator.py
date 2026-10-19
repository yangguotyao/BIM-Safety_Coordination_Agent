"""Bounded task planning and case-scoped context for the existing workflow."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .config import DEMO_MODE
from .db import connect
from .errors import APIError

Focus = Literal['all', 'guardrail_height', 'guardrail_integrity', 'worker_exposure']
ToolName = Literal['bim_query', 'schedule_query', 'evidence_check', 'spatial_check', 'rule_retrieval', 'risk_assessment','activity_conflict_check','site_text_query']
TOOL_CATALOG = {
    'bim_query': '读取当前模型与区域构件，保留GUID和版本',
    'schedule_query': '检查施工任务时间窗',
    'evidence_check': '读取本Case证据及结构化观察',
    'spatial_check': '计算模拟人员点至标注边线距离',
    'rule_retrieval': '检索有效规范，保留来源与页码',
    'risk_assessment': '按本次检查重点执行确定性风险检查',
    'activity_conflict_check':'检查多活动时间交集及三维作业范围',
    'site_text_query':'读取现场文本候选、原文段落及人工澄清',
}
CORE_TOOLS = ['bim_query', 'schedule_query', 'evidence_check', 'rule_retrieval', 'risk_assessment']
FOCUS_LABELS = {'all': '临边综合检查', 'guardrail_height': '栏杆高度',
                'guardrail_integrity': '防护固定与连续性', 'worker_exposure': '人员暴露与距离'}
DEFAULT_REQUEST = '全面检查L05区域临边防护及人员暴露风险，提出需要人工审核的控制措施。'


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: str = Field(min_length=1, max_length=1500)
    zone_id: str
    as_of: str
    focus: list[Focus] = Field(min_length=1, max_length=4)
    selected_tools: list[ToolName] = Field(min_length=1, max_length=8)
    retrieval_query: str = Field(min_length=2, max_length=500)
    needs_clarification: bool = False
    clarification: str = Field(default='', max_length=500)
    assumptions: list[str] = Field(default_factory=list, max_length=6)
    context_inherited: bool = False
    mode: Literal['demo_rules', 'live_model'] = 'demo_rules'

    @model_validator(mode='after')
    def validate_plan(self):
        self.focus = list(dict.fromkeys(self.focus))
        if 'all' in self.focus:
            self.focus = ['all']
        self.selected_tools = list(dict.fromkeys(self.selected_tools))
        if not set(CORE_TOOLS).issubset(self.selected_tools):
            raise ValueError('必须保留构件、计划、证据、规范和风险工具')
        if ('all' in self.focus or 'worker_exposure' in self.focus) and 'spatial_check' not in self.selected_tools:
            raise ValueError('人员暴露检查必须选择空间校核工具')
        if self.needs_clarification and not self.clarification:
            raise ValueError('范围待澄清时必须说明缺失内容')
        return self


def messages_for_case(case_id: str, actor_id: str, limit: int = 6) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            'SELECT role,content,created_at FROM case_messages WHERE case_id=? AND actor_id=? ORDER BY id DESC LIMIT ?',
            (case_id, actor_id, min(limit, 12)),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
    finally:
        conn.close()


def build_context(case: dict[str, Any]) -> dict[str, Any]:
    """Only compact metadata enters model context; never raw IFC/image bytes."""
    messages = messages_for_case(case['case_id'], case.get('task_actor_id') or 'demo-user')
    # A conservative UTF-8 byte budget also bounds tokens without a provider-specific tokenizer.
    selected = []
    used = 0
    for item in reversed(messages):
        cost = len(item['content'].encode('utf-8'))
        if used + cost > 6000:
            continue
        selected.append(item)
        used += cost
    conn=connect()
    try:
        context_tools=[]
        if conn.execute('SELECT 1 FROM activity_plans WHERE case_id=?',(case['case_id'],)).fetchone(): context_tools.append('activity_conflict_check')
        if conn.execute('SELECT 1 FROM site_notes WHERE case_id=?',(case['case_id'],)).fetchone(): context_tools.append('site_text_query')
    finally: conn.close()
    from .assurance import project_memory
    return {'case_id': case['case_id'], 'zone_id': case['zone_id'], 'as_of': case['as_of'],'required_context_tools':context_tools,
            'project_examples':project_memory(case),'experience_policy':'历史案例只辅助流程，不构成当前现场证据；模拟来源不得变为实测事实。',
            'model_id': case['model_id'], 'model_version': case['model_version'],
            'evidence_ids': case['evidence_ids'], 'messages': list(reversed(selected)),
            'previous_task': case.get('task_spec'), 'context_bytes': used,
            'context_budget_bytes': 6000, 'tool_catalog': TOOL_CATALOG}


def _scope_error(request: str) -> str:
    levels = re.findall(r'(?:L(?:evel)?\s*0?(\d{1,2})(?!\d))|(\d{1,2})\s*层', request, re.I)
    if any(int(a or b) != 5 for a, b in levels):
        return '当前演示只索引L05区域，请选择该区域或补充目标区域数据。'
    if any(level != '五' for level in re.findall(r'([一二三四五六七八九十]+)层', request)):
        return '当前演示只索引五层（L05），其他楼层需要补充数据。'
    if any(word in request for word in ['地下室', '四层', '三层', '六层', '其他项目']):
        return '当前演示范围为S1的L05区域，其他区域需要另行提供数据。'
    if any(word in request for word in ['结构承载', '吊装计算', '火灾', '洞口尺寸']):
        return '当前工具只支持本区域临边防护与人员暴露检查，所请求的专业计算或对象尚无输入。'
    return ''


def plan_task(case: dict[str, Any], activity: str) -> tuple[dict[str, Any], dict[str, Any]]:
    request = case.get('request_text') or DEFAULT_REQUEST
    context = build_context(case)
    scope_error = _scope_error(request)
    if not DEMO_MODE and not scope_error:
        from .live_model import live_task_plan
        prompt={**context,'request':request,'activity':activity,'schema':TaskSpec.model_json_schema()}
        for attempt in range(2):
            raw=live_task_plan(prompt)
            try:
                spec=TaskSpec.model_validate({**raw,'mode':'live_model'})
                break
            except ValidationError as exc:
                if attempt: raise
                prompt={**prompt,'validation_feedback':str(exc)[:1200]}
        if spec.zone_id != case['zone_id'] or spec.as_of != case['as_of'] or spec.request != request:
            raise APIError(422, 'task_scope_mismatch', '模型改变了固定区域、时刻或原始任务，请重新澄清')
    else:
        focus = []
        if any(word in request for word in ['高度', '多高', 'height']): focus.append('guardrail_height')
        if any(word in request for word in ['固定', '连续', '完整', '锚固']): focus.append('guardrail_integrity')
        if any(word in request for word in ['人员', '距离', '暴露', '接近']): focus.append('worker_exposure')
        inherited = False
        if not focus and any(word in request for word in ['继续', '刚才', '同一区域', '接着']):
            previous = context.get('previous_task') or {}
            focus = previous.get('focus', [])
            inherited = bool(focus)
        if not focus or any(word in request for word in ['全面', '综合', '全部']): focus = ['all']
        tools = list(CORE_TOOLS)
        if 'all' in focus or 'worker_exposure' in focus: tools.insert(3, 'spatial_check')
        terms = {'all': '临边 防护 栏杆 坠落 高度 人员 2m 1.2m 安全 作业 边沿 周边 围护 孔洞 楼层',
                 'guardrail_height': '临边 栏杆 防护 高度 1.2m',
                 'guardrail_integrity': '临边 防护 栏杆 固定 连续 构造',
                 'worker_exposure': '高处 人员 暴露 临边 坠落 防护'}
        query = activity + ' ' + ' '.join(terms[key] for key in focus)
        spec = TaskSpec(request=request, zone_id=case['zone_id'], as_of=case['as_of'], focus=focus,
            selected_tools=tools, retrieval_query=query[:500], needs_clarification=bool(scope_error),
            clarification=scope_error, context_inherited=inherited or bool(context['messages'][:-1]),
            assumptions=['现场观察来自明确标注的演示输入；只判断本次选定检查项。'])
    spec.selected_tools=list(dict.fromkeys(spec.selected_tools+context['required_context_tools']))
    return spec.model_dump(), context


def safety_state(state: dict[str, Any]) -> dict[str, Any]:
    case = state['case']
    inspection = state.get('inspection', {}).get('data', {})
    return {'case_id': case['case_id'], 'zone_id': case['zone_id'], 'as_of': case['as_of'],
        'model': {'id': case['model_id'], 'version': case['model_version'], 'guids': case['bim_guids']},
        'task_spec': state.get('task_spec'), 'activity': state.get('task', {}).get('activity'),
        'schedule': state.get('schedule', {}).get('data'), 'evidence_ids': inspection.get('evidence_ids', []),
        'observations': inspection.get('observation'), 'missing_fields': inspection.get('missing_fields', []),
        'bim_context':state.get('bim',{}).get('data'),
        'perception_candidates':[item.get('perception') for item in inspection.get('records',[]) if item.get('perception')],
        'spatial': state.get('spatial', {}).get('data'),
        'coordination':state.get('coordination',{}).get('data'),
        'site_text':state.get('site_text',{}).get('data'),
        'provenance': 'real_bim_and_simulated_site_observations',
        'incomplete': bool(state.get('incomplete'))}


def scoped_inspection(result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Keep existing evidence selection; only check fields relevant to this task."""
    if 'all' in spec['focus']:
        return result
    data = result['data']; observation = data.get('observation') or {}
    fields = {'boundary_is_exposed'}
    for focus in spec['focus']:
        if focus == 'worker_exposure': fields.add('worker_present')
        else:
            fields.add('guardrail_state')
            if observation.get('guardrail_state') == 'present':
                fields.update(['guardrail_height_m'] if focus == 'guardrail_height' else ['guardrail_fixed','guardrail_continuous'])
    missing = sorted(key for key in fields if observation.get(key) is None or observation.get(key) == 'unknown')
    data['missing_fields'] = missing
    data['data_complete'] = not missing and bool(data.get('primary'))
    data['required_fields'] = sorted(fields)
    result['uncertainties'] = [x for x in result.get('uncertainties', []) if not x.startswith('关键观察字段缺失')]
    if missing: result['uncertainties'].append('本次检查缺少字段：'+'、'.join(missing))
    return result


def decision_package(state: dict[str, Any], finding: dict[str, Any], controls: list) -> dict[str, Any]:
    case = state['case']
    return {'case_id': case['case_id'], 'run_id': state['run_id'], 'status': 'candidate',
        'execution_plan':state.get('execution_plan'),'evidence_trace':state.get('evidence_trace'),
        'assurance':state.get('assurance'),'evidence_gaps':state.get('evidence_gaps',[]),
        'memory':{'working':{'focus':state.get('task_spec',{}).get('focus',[]),'gaps':state.get('evidence_gaps',[])},
                  'case_messages':len(state.get('context',{}).get('messages',[])),
                  'project_examples':state.get('context',{}).get('project_examples',[]),
                  'policy':'历史经验仅用于流程参考，不替代当前证据'},
        'task': state.get('task_spec'), 'finding': finding,
        'evidence': finding.get('evidence_ids', []),
        'governing_rules': state.get('knowledge', {}).get('data', {}).get('results', []),
        'risk': {'level': finding.get('risk_level'), 'result': finding.get('result')},
        'controls': controls, 'owners': list(dict.fromkeys(c['owner'] for c in controls)),
        'additional_findings':state.get('risk',{}).get('data',{}).get('additional_findings',[]),
        'assumptions': case.get('assumptions', []) + (state.get('task_spec') or {}).get('assumptions', []),
        'reviewer': '演示安全员（待人工审核）', 'approval_required': True,
        'scope': '仅对选定检查项成立；审批和实施由人工操作',
        'mode': 'demo_rules' if DEMO_MODE else 'live_model'}
