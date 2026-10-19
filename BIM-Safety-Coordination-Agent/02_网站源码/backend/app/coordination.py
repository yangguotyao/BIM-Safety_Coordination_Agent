"""Deterministic time intersections and axis-aligned 3-D work-space intersections."""
import math
from itertools import combinations
from pydantic import BaseModel,Field,ConfigDict,model_validator

from .case_edits import editable_case,record_edit
from .db import dumps,loads,transaction
from .errors import APIError
from .tools import now_iso,parse_dt


class WorkVolume(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    min: list[float]=Field(min_length=3,max_length=3)
    max: list[float]=Field(min_length=3,max_length=3)

    @model_validator(mode='after')
    def positive_volume(self):
        if any(a>=b for a,b in zip(self.min,self.max)):
            raise ValueError('作业范围三个方向均须为正尺寸')
        return self


class Activity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    task_id: str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    activity: str=Field(min_length=1,max_length=200)
    trade: str=Field(default='',max_length=80)
    owner: str=Field(default='',max_length=80)
    planned_start: str | None=None
    planned_end: str | None=None
    bim_guids: list[str]=Field(default_factory=list,max_length=8)
    workspace: WorkVolume | None=None

    @model_validator(mode='after')
    def dates(self):
        for value in [self.planned_start,self.planned_end]:
            parsed=parse_dt(value)
            if value is not None and (parsed is None or parsed.utcoffset() is None):
                raise ValueError('活动时间必须为含时区的ISO时间或留空')
        if self.planned_start and self.planned_end and parse_dt(self.planned_start)>=parse_dt(self.planned_end):
            raise ValueError('计划结束必须晚于开始')
        return self


class ActivityPlanRequest(BaseModel):
    activities: list[Activity]=Field(min_length=2,max_length=8)
    reason: str=Field(min_length=1,max_length=500)
    expected_case_version: int=Field(ge=1)


def activity_plan(conn,case_id):
    row=conn.execute('SELECT * FROM activity_plans WHERE case_id=?',(case_id,)).fetchone()
    if row is None:
        return None
    result=dict(row)
    result['activities']=loads(result.pop('activities_json'),[])
    result['history']=[{**dict(r),'activities':loads(r['activities_json'],[])} for r in conn.execute(
        'SELECT revision,reason,at,activities_json FROM activity_plan_revisions WHERE case_id=? ORDER BY revision DESC',(case_id,))]
    for item in result['history']: item.pop('activities_json',None)
    return result


def check_activities(plan,as_of):
    if not plan:
        return {'configured':False,'complete':True,'conflicts':[],'pairs':[],'missing_fields':[],'activities':[]}
    values=plan['activities']; missing=[];ready=[]
    for item in values:
        fields=[key for key in ['trade','owner','planned_start','planned_end','bim_guids','workspace'] if not item.get(key)]
        missing.extend(f"{item['task_id']}.{key}" for key in fields)
        if not fields: ready.append(item)
    pairs=[];checked_at=parse_dt(as_of)
    for a,b in combinations(ready,2):
        start=max(parse_dt(a['planned_start']),parse_dt(b['planned_start']))
        end=min(parse_dt(a['planned_end']),parse_dt(b['planned_end']))
        time_overlap=start<end
        amin,amax=a['workspace']['min'],a['workspace']['max']
        bmin,bmax=b['workspace']['min'],b['workspace']['max']
        low=[max(x,y) for x,y in zip(amin,bmin)]; high=[min(x,y) for x,y in zip(amax,bmax)]
        spatial_overlap=all(y-x>1e-6 for x,y in zip(low,high))
        distance=math.sqrt(sum(max(0,amin[i]-bmax[i],bmin[i]-amax[i])**2 for i in range(3)))
        pairs.append({'pair_id':f"{a['task_id']}__{b['task_id']}",'task_ids':[a['task_id'],b['task_id']],
            'activities':[a['activity'],b['activity']],'owners':[a['owner'],b['owner']],
            'time_overlap':time_overlap,'overlap_start':start.isoformat() if time_overlap else None,
            'overlap_end':end.isoformat() if time_overlap else None,'spatial_overlap':spatial_overlap,
            'intersection_m':{'min':low,'max':high} if spatial_overlap else None,
            'distance_m':round(distance,3),'conflict':time_overlap and spatial_overlap,
            'active_at_check':bool(time_overlap and checked_at and start<=checked_at<end),
            'bim_guids':list(dict.fromkeys(a['bim_guids']+b['bim_guids']))})
    return {'configured':True,'revision':plan['revision'],'complete':not missing,
        'activities':values,'pairs':pairs,'conflicts':[p for p in pairs if p['conflict']],
        'missing_fields':missing,'method':'time_interval_intersection_and_axis_aligned_work_volumes',
        'provenance':'human_authored_demo_schedule','units':'m'}


def activity_conflict_check(conn,case):
    result=check_activities(activity_plan(conn,case['case_id']),case['as_of'])
    return {'ok':True,'data':result,'method':result.get('method'),'units':'m',
        'uncertainties':['活动资料缺失：'+','.join(result['missing_fields'])] if result['missing_fields'] else []}


def save_activity_plan(case_id,payload):
    from .services import case_bundle
    spec=ActivityPlanRequest.model_validate(payload)
    values=[item.model_dump() for item in spec.activities]
    if len({a['task_id'] for a in values})!=len(values):
        raise APIError(422,'duplicate_activity_id','活动ID不能重复')
    with transaction() as conn:
        case=editable_case(conn,case_id,spec.expected_case_version,execution=True)
        for item in values:
            if not set(item['bim_guids']).issubset(case['bim_guids']):
                raise APIError(422,'activity_scope_mismatch','活动构件必须属于本Case')
        previous=activity_plan(conn,case_id)
        execution=case['status'] in {'approved','rectifying','pending_verification'}
        if execution:
            snapshot=case.get('review') or {}
            if not snapshot.get('coordination_task_ids') or not previous or not any(
                value.get('coordination_required') for value in snapshot.get('verification_snapshot',{}).values()):
                raise APIError(409,'plan_not_authorized','当前批准措施未授权调整作业计划')
            if set(snapshot['coordination_task_ids'])!={a['task_id'] for a in values}:
                raise APIError(422,'approved_activities_required','批准的活动不得删除或替换')
            old={a['task_id']:a for a in previous['activities']}
            for item in values:
                if any(item[k]!=old[item['task_id']][k] for k in ['activity','trade','owner','bim_guids']):
                    raise APIError(422,'approved_activity_identity','实施阶段只能按批准措施调整时间与作业范围')
        revision=(previous['revision'] if previous else 0)+1
        conn.execute('INSERT INTO activity_plans VALUES(?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET '
            'revision=excluded.revision,activities_json=excluded.activities_json,updated_at=excluded.updated_at',
            (case_id,revision,dumps(values),now_iso()))
        conn.execute('INSERT INTO activity_plan_revisions VALUES(?,?,?,?,?)',
            (case_id,revision,dumps(values),spec.reason,now_iso()))
        record_edit(conn,case,'activity_plan_adjusted' if execution else 'activity_plan_updated',
            {'revision':revision,'reason':spec.reason,'activities':values},invalidate=not execution)
    return case_bundle(case_id)


def coordination_findings(case,result):
    return [{'finding_id':f"F-SPACE-{i+1:03d}",'kind':'coordination','hazard':f"作业空间冲突：{' / '.join(pair['activities'])}",
        'result':'risk_candidate','risk_level':'计划冲突待处置','bim_guids':pair['bim_guids'],
        'evidence_ids':[],'rule_ids':[],'task_ids':pair['task_ids'],'pair_id':pair['pair_id'],
        'checks':[{'name':'计划时间交叠','result':'fail','source':'activity_conflict_check'},
                  {'name':'三维作业范围交叠','result':'fail','source':'activity_conflict_check'}],
        'inputs':pair,'uncertainties':[],'provenance':'human_authored_demo_schedule',
        'scope_note':'基于编制的作业空间体与时间窗，不等同现场真实碰撞。'}
        for i,pair in enumerate(result.get('conflicts',[]))]


def coordination_control(finding,owner):
    return {'control_id':'CTRL-'+finding['finding_id'],'finding_id':finding['finding_id'],'kind':'coordination',
        'action':f"对{'、'.join(finding['inputs']['activities'])}实施错时作业或调整作业范围，保持人员与相邻作业隔离；复核时间及三维范围无交叠后开放作业。",
        'owner':owner,'verification_requirements':['保留批准活动及责任主体','复核调整后的时间窗和作业范围','提供实施后证据并人工确认'],
        'verification_criteria':{'guardrail_required':False,'min_height_m':1.2,'fixed_required':False,
            'continuous_required':False,'coordination_required':True,'manual_requirements':[]},
        'version':1,'status':'proposed','provenance':'deterministic_coordination_tool'}
