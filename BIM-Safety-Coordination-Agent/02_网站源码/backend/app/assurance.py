"""Deterministic planning contracts, bounded evidence gaps and decision lineage.

LLMs propose task focus and wording. This module owns scope, dependencies,
provenance, input consistency and the structural audit; it never grants approval.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from functools import lru_cache
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field
from .config import DATA_ROOT,MODEL_NAME,VISION_MODEL
from .db import connect,transaction,dumps,loads
from .errors import APIError
from .tools import get_evidence,parse_dt,now_iso


def digest(value:Any)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@lru_cache(maxsize=128)
def _file_hash(path:str,size:int,mtime:int)->str:
    with open(path,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def file_reference(raw:str|None)->dict:
    if not raw:return {'available':False}
    path=Path(raw)
    if not path.is_absolute():path=DATA_ROOT/path
    if not path.is_file():return {'available':False,'path':str(path)}
    stat=path.stat()
    return {'available':True,'path':str(path),'bytes':stat.st_size,
            'sha256':_file_hash(str(path),stat.st_size,stat.st_mtime_ns)}


def input_snapshot(case_id:str)->dict:
    from .services import serialize_case
    from .tools import get_task,get_zone
    from .coordination import activity_plan
    conn=connect()
    try:
        row=conn.execute('SELECT * FROM cases WHERE case_id=?',(case_id,)).fetchone()
        if row is None:raise APIError(404,'case_not_found','检查记录不存在')
        case=serialize_case(dict(row));evidence=[]
        for eid in case['evidence_ids']:
            item=get_evidence(conn,eid)
            evidence.append({**{key:item.get(key) for key in ['evidence_id','project_id','model_id','model_version','zone_id','bim_guids','captured_at','stage','source','kind','observation']},
                'confirmed':item.get('perception',{}).get('confirmed',False),
                'confirmation_source':item.get('perception',{}).get('source'),
                'human_note':item.get('perception',{}).get('human_note'),'file':file_reference(item.get('file_path'))})
        zone=get_zone(conn,case['zone_id'])
        logical={'case':{key:case.get(key) for key in ['case_id','project_id','model_id','model_version','task_id','zone_id','as_of','bim_guids','scope','evidence_ids','request_text','task_actor_id','assumptions']},
            'model':dict(conn.execute('SELECT * FROM models WHERE model_id=?',(case['model_id'],)).fetchone()),
            'zone':zone,'task':get_task(conn,case['task_id']),'evidence':evidence,
            'rules':[dict(r) for r in conn.execute('SELECT * FROM rules ORDER BY rule_id')],
            'activity_plan':activity_plan(conn,case_id),
            'site_notes':[dict(r) for r in conn.execute('SELECT note_id,version,body,paragraphs_json,zone_id,model_version,bim_guids_json,captured_at FROM site_notes WHERE case_id=? ORDER BY note_id',(case_id,))],
            'text_resolutions':[dict(r) for r in conn.execute('SELECT * FROM text_resolutions WHERE case_id=? ORDER BY conflict_id',(case_id,))],
            'models':{'coordinator':MODEL_NAME,'vision':VISION_MODEL},
            'policy_version':'safety-policy-2.0'}
        return {'case_version':case['version'],'input_hash':digest(logical),'inputs':logical}
    finally:conn.close()


def assert_snapshot(case_id:str,snapshot:dict)->None:
    current=input_snapshot(case_id)
    if current['input_hash']!=snapshot['input_hash']:
        raise APIError(409,'stale_run_inputs','分析输入已变化，请重新分析；旧结果不会写入当前案例。')


class ToolArguments(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id:str
    model_id:str
    model_version:str
    zone_id:str
    as_of:str
    bim_guids:list[str]=Field(min_length=1)
    focus:list[str]
    query:str=''


class PlanStep(BaseModel):
    model_config=ConfigDict(extra='forbid')
    tool:Literal['bim_query','schedule_query','spatial_check','evidence_check','activity_conflict_check','site_text_query','rule_retrieval','risk_assessment']
    arguments:ToolArguments
    depends_on:list[str]
    permission:Literal['read']='read'
    expected_output:str
    mandatory:bool


class ToolResult(BaseModel):
    model_config=ConfigDict(extra='allow')
    ok:bool
    data:Any=None
    provenance:str='structured_tool'
    method:str|None=None
    model_version:str|None=None
    units:str|None=None
    evidence_ids:list[str]=Field(default_factory=list)
    rule_ids:list[str]=Field(default_factory=list)
    uncertainties:list[str]=Field(default_factory=list)


def execution_plan(case:dict,spec:dict)->dict:
    from .coordinator import TaskSpec,CORE_TOOLS
    spec=TaskSpec.model_validate(spec).model_dump()
    order=['bim_query','spatial_check','schedule_query','activity_conflict_check','evidence_check','site_text_query','rule_retrieval','risk_assessment']
    dependencies={'bim_query':[],'spatial_check':['bim_query'],'schedule_query':['bim_query'],
        'activity_conflict_check':['schedule_query'],'evidence_check':['schedule_query'],
        'site_text_query':['evidence_check'],'rule_retrieval':['evidence_check']}
    args={key:case[key] for key in ['case_id','model_id','model_version','zone_id','as_of','bim_guids']}
    args.update(focus=spec['focus'],query=spec['retrieval_query'])
    steps=[]
    for tool in order:
        if tool not in spec['selected_tools']:continue
        deps=dependencies.get(tool,[s['tool'] for s in steps])
        steps.append(PlanStep(tool=tool,arguments=ToolArguments(**args),depends_on=deps,
            mandatory=tool in CORE_TOOLS,expected_output=tool+'_result').model_dump())
    goals=[{'goal_id':'scope','title':'固定模型、区域与活动时段','tools':['bim_query','schedule_query']},
           {'goal_id':'evidence','title':'核对现场资料与适用规范','tools':['evidence_check','rule_retrieval']}]
    labels={'guardrail_height':'检查栏杆高度','guardrail_integrity':'检查防护固定与连续性','worker_exposure':'检查人员暴露与距离'}
    for focus in (list(labels) if 'all' in spec['focus'] else spec['focus']):
        goals.append({'goal_id':focus,'title':labels[focus],'tools':(['spatial_check'] if focus=='worker_exposure' else [])+['risk_assessment']})
    if 'activity_conflict_check' in spec['selected_tools']:goals.append({'goal_id':'coordination','title':'检查多活动时空冲突','tools':['activity_conflict_check']})
    if 'site_text_query' in spec['selected_tools']:goals.append({'goal_id':'text','title':'核对现场文本与已确认观察','tools':['site_text_query']})
    return {'version':'2.0','strategy':'policy_constrained_plan','focus':spec['focus'],'steps':steps,'subtasks':goals,
        'budget':{'max_replans':2,'max_tool_attempts':2,'max_model_calls':12,'deadline_seconds':480},
        'termination':['evidence_gap','human_review','failed_or_cancelled'],
        'authority':'deterministic_policy','approval_tools':[]}


FIELD_LABELS={'guardrail_state':'确认临边防护状态','guardrail_height_m':'补录栏杆高度及量测来源',
    'worker_present':'确认人员是否在场','drop_height_m':'补录坠落基准面高度及来源',
    'boundary_is_exposed':'确认检查边界是否属于临空边界','guardrail_fixed':'确认防护固定情况',
    'guardrail_continuous':'确认防护连续情况','ppe_confirmed':'核对人员个体防护',
    'human_observation_confirmation':'人工核对图像候选与观察来源'}


def assess_gaps(state:dict)->list[dict]:
    gaps=[]
    def add(field,message,action,evidence_id=None):
        gaps.append({'gap_id':'GAP-'+digest([field,evidence_id])[:10],'field':field,'message':message,
            'action':action,'evidence_id':evidence_id,'blocking':True,'status':'pending'})
    spec=state.get('task_spec') or {}
    if spec.get('needs_clarification'):
        add('task_scope',spec.get('clarification') or '请明确支持的检查范围','clarify_task');return gaps
    inspection=state.get('inspection',{}).get('data') or {}
    primary=inspection.get('primary')
    if not primary:
        add('site_evidence','添加同一检查区域与时段的现场资料','add_evidence')
    else:
        if not inspection.get('matched',True):add('evidence_scope','补充项目、构件、版本和时间匹配的资料','add_evidence',primary['evidence_id'])
        for field in inspection.get('missing_fields',[]):
            add(field,FIELD_LABELS.get(field,'补充'+field),'confirm_observation',primary['evidence_id'])
    schedule=state.get('schedule',{}).get('data')
    if schedule and not schedule.get('active'):add('task_window','核对活动时间窗与检查时刻','edit_scope')
    text=state.get('site_text',{}).get('data') or {}
    if not text.get('complete',True):add('site_text','核对现场文字候选并澄清与已确认观察的差异','resolve_text')
    coordination=state.get('coordination',{}).get('data') or {}
    if not coordination.get('complete',True):add('activities','补齐施工活动的时间、责任与作业范围','edit_activities')
    if 'knowledge' in state and not (state['knowledge'].get('data') or {}).get('results'):
        add('applicable_rules','补充当前检查时刻有效的适用规范','review_rules')
    return gaps[:12]


def evidence_trace(state:dict,snapshot:dict)->dict:
    case=state['case'];inspection=state.get('inspection',{}).get('data') or {}
    nodes=[];edges=[];facts=[];known=set()
    def node(key,kind,label,**extra):
        if key not in known:nodes.append({'id':key,'kind':kind,'label':label,**extra});known.add(key)
        return key
    def edge(a,b,relation):edges.append({'from':a,'to':b,'relation':relation})
    scope=node('SCOPE','scope','检查范围',model_version=case['model_version'],bim_guids=case['bim_guids'],as_of=case['as_of'])
    spatial=state.get('spatial',{}).get('data')
    if spatial:
        node('GEOMETRY','calculation','人员点至标注边线距离',value=spatial.get('distance_m'),unit='m',source=spatial)
        edge('GEOMETRY',scope,'computed_in')
    schedule=state.get('schedule',{}).get('data')
    if schedule:node('SCHEDULE','activity','活动时间窗',source=schedule);edge('SCHEDULE',scope,'scheduled_in')
    for fact in state.get('site_text',{}).get('data',{}).get('facts',[]):
        pid=fact['paragraph_id'];node(pid,'text','现场原文段落',source=fact)
        edge(pid,scope,'reported_in')
    for item in inspection.get('records',[]):
        eid=item['evidence_id'];source=node(eid,'evidence',item['label'],source={'captured_at':item['captured_at'],'provenance':item['provenance'],
            'confirmed':item.get('source')!='upload' or item.get('perception',{}).get('confirmed') is True})
        edge(source,scope,'located_in')
        for key,value in item['observation'].items():
            if key=='simulated':continue
            fact={'id':eid+':'+key,'property':key,'value':value,'unit':'m' if key.endswith('_m') else None,
                'source_id':eid,'source_kind':'simulation' if item['observation'].get('simulated') else 'human_confirmed' if item.get('perception',{}).get('confirmed') else 'candidate',
                'bim_guids':item['bim_guids'],'model_version':item['model_version'],'captured_at':item['captured_at'],
                'confirmation_note':item.get('perception',{}).get('human_note'),
                'status':'unknown' if value is None or value=='unknown' else 'recorded'}
            facts.append(fact);node(fact['id'],'fact',FIELD_LABELS.get(key,key),fact=fact);edge(fact['id'],eid,'observed_in')
    rules=state.get('knowledge',{}).get('data',{}).get('results',[])
    for rule in rules:
        node(rule['rule_id'],'rule',rule['standard']+' '+rule['clause'],source={key:rule.get(key) for key in ['source_path','source_url','pdf_page','version','effective_from','text_kind','applicability']})
    finding=state.get('risk',{}).get('data',{}).get('finding')
    findings=([finding] if finding else [])+state.get('risk',{}).get('data',{}).get('additional_findings',[])
    for finding in findings:
        fid=node(finding['finding_id'],'finding',finding['hazard'],result=finding['result'])
        edge(fid,scope,'assessed_at')
        for eid in finding.get('evidence_ids',[]):
            if eid in known:edge(fid,eid,'uses_evidence')
        for rid in finding.get('rule_ids',[]):
            if rid in known:edge(fid,rid,'retrieved_basis')
        for index,check in enumerate(finding.get('checks',[])):
            cid=node(f"{fid}:check:{index}",'check',check['name'],result=check['result'],source=check.get('source'),note=check.get('note'))
            edge(fid,cid,'determined_by')
            fields=None
            for term,used in [('防护高度',{'guardrail_state','guardrail_height_m'}),('存在性',{'guardrail_state'}),('固定',{'guardrail_fixed','guardrail_continuous'}),('人员暴露',{'worker_present'}),('边界暴露',{'boundary_is_exposed'})]:
                if term in check['name']:fields=used;break
            for fact in facts:
                if fact['source_id'] in finding.get('evidence_ids',[]) and (fields is None or fact['property'] in fields):edge(cid,fact['id'],'input_reference')
            if '距离' in check['name'] and 'GEOMETRY' in known:edge(cid,'GEOMETRY','computed_from')
            if '时间窗' in check['name'] and 'SCHEDULE' in known:edge(cid,'SCHEDULE','computed_from')
    for control in state.get('controls',[]):
        cid=node(control['control_id'],'control','候选整改措施',owner=control['owner'],criteria=control.get('verification_criteria'))
        if control['finding_id'] in known:edge(cid,control['finding_id'],'addresses')
    return {'version':'2.0','input_hash':snapshot['input_hash'],'nodes':nodes,'edges':edges,'facts':facts,
        'gaps':assess_gaps(state),'note':'引用关系用于追溯，不将检索相关性或模拟观察等同真实现场证明。'}


def audit_decision(case:dict,trace:dict,findings:list,controls:list,rules:list)->dict:
    issues=[];checks=[]
    def issue(code,message):issues.append({'code':code,'message':message})
    conn=connect()
    try:
        evidence={eid:get_evidence(conn,eid) for eid in case['evidence_ids']}
        for fact in trace['facts']:
            source=evidence.get(fact['source_id'])
            if not source:issue('unknown_fact_source','观察引用未绑定当前案例');continue
            if fact['value']!=source['observation'].get(fact['property']):issue('fact_value_mismatch','观察值与证据记录不一致')
            if fact['unit']!=('m' if fact['property'].endswith('_m') else None):issue('fact_unit_mismatch','观察单位不一致')
        for rule in rules:
            row=conn.execute('SELECT * FROM rules WHERE rule_id=?',(rule['rule_id'],)).fetchone()
            if not row or row['status']!='active' or (row['effective_from'] and row['effective_from']>case['as_of'][:10]):
                issue('inapplicable_rule','规范不存在、已失效或在检查时刻尚未生效')
            elif row['version']!=rule.get('version') or row['text']!=rule.get('text'):issue('rule_version_mismatch','规范引用版本不一致')
        ids=set(evidence);rule_ids={r['rule_id'] for r in rules};finding_ids={f['finding_id'] for f in findings}
        for finding in findings:
            if not set(finding.get('evidence_ids',[])).issubset(ids):issue('unknown_evidence_reference','风险项引用了未绑定的证据')
            if not set(finding.get('rule_ids',[])).issubset(rule_ids):issue('unknown_rule_reference','风险项引用了未检索的规范')
            if finding.get('result')=='no_issue_in_checked_items' and any(c['result'] in {'fail','unknown'} for c in finding.get('checks',[])):
                issue('unsupported_clearance','检查仍有未通过或未知项，不能输出已检查项无问题')
        if trace.get('gaps') and controls:issue('missing_evidence_control','证据未齐全，不得形成可批准的措施')
        for control in controls:
            if control.get('finding_id') not in finding_ids:issue('unknown_finding_reference','措施未对应本次风险项')
            criteria=control.get('verification_criteria') or {}
            if criteria.get('guardrail_required') and criteria.get('min_height_m',0)<1.2:issue('weakened_safety_parameter','候选措施降低了防护高度检查阈值')
        checks=['事实与原始观察一致','单位一致','规范状态与版本有效','风险与措施引用闭合','缺证时禁止授权','工程阈值未被模型降低']
    finally:conn.close()
    return {'version':'2.0','status':'blocked' if issues else 'passed','method':'deterministic_structural_audit',
        'checks':checks,'issues':issues,'input_hash':trace['input_hash'],'approval_required':True,
        'scope':'校核结构化依据与工程约束；文字解释仍需人工审核，不以模型投票替代工程规则。'}


def store_artifacts(run_id:str,*,plan=None,trace=None,audit=None,gaps=None)->None:
    values={k:dumps(v) for k,v in [('plan_json',plan),('trace_json',trace),('audit_json',audit),('gaps_json',gaps)] if v is not None}
    if values:
        with transaction() as conn:conn.execute('UPDATE run_artifacts SET '+','.join(k+'=?' for k in values)+' WHERE run_id=?',(*values.values(),run_id))


CACHEABLE={'bim_query','spatial_check','schedule_query','rule_retrieval'}
def cache_key(run_id:str,tool:str,input_summary:str)->tuple[str,str]|None:
    if tool not in CACHEABLE:return None
    conn=connect()
    try:row=conn.execute('SELECT input_json FROM run_artifacts WHERE run_id=?',(run_id,)).fetchone()
    finally:conn.close()
    if not row:return None
    inputs=loads(row['input_json'])['inputs'];case=inputs['case']
    keys={'bim_query':['model','zone'],'spatial_check':['model','zone'],
        'schedule_query':['task'],'rule_retrieval':['rules']}[tool]
    relevant={key:inputs[key] for key in keys}
    relevant['case']={key:case[key] for key in ['case_id','model_id','model_version','zone_id','bim_guids','scope','as_of']}
    relevant['input_summary']=input_summary
    return case['case_id'],digest(relevant)


def project_memory(case:dict)->list[dict]:
    """Reviewed examples, scoped to project/model/actor; never current observations."""
    conn=connect()
    try:
        rows=conn.execute("SELECT case_id,title,zone_id,bim_guids_json,verification_json,provenance FROM cases WHERE project_id=? AND model_id=? AND model_version=? AND task_actor_id=? AND status='closed' AND case_id<>? ORDER BY updated_at DESC LIMIT 12",
            (case['project_id'],case['model_id'],case['model_version'],case.get('task_actor_id') or 'demo-user',case['case_id'])).fetchall()
        result=[]
        for row in rows:
            verified=loads(row['verification_json'],{})
            if verified.get('result')!='pass_in_demo_scope':continue
            if not set(case['bim_guids']).intersection(loads(row['bim_guids_json'],[])):continue
            result.append({'case_id':row['case_id'],'title':row['title'][:100],'zone_id':row['zone_id'],
                'source_kind':'reviewed_demo_case','use':'procedure_reference_only','current_evidence':False})
            if len(result)==3:break
        return result
    finally:conn.close()
