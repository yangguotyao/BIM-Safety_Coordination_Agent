import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import reset_db
from test_api import analyze

client = TestClient(app)
GUID = '0FOHK4aT910wgskSbVHn0U'


@pytest.fixture(autouse=True)
def isolated():
    reset_db()


def new_case(evidence='EV-007'):
    return client.post('/api/cases', json={'evidence_ids':[evidence]}).json()['case']


def activities():
    return [dict(task_id=key, activity=name, trade=trade, owner=owner,
        planned_start='2026-10-16T08:00:00+08:00', planned_end='2026-10-16T12:00:00+08:00',
        bim_guids=[GUID], workspace={'min':[18,20,17.3], 'max':[21,24,19.3]})
        for key,name,trade,owner in [('A','材料转运','机电','机电班组'),('B','相邻墙面作业','装修','装修班组')]]


def save_plan(case, values, reason='演示计划'):
    result = client.put(f"/api/cases/{case['case_id']}/activity-plan", json={
        'activities':values, 'reason':reason, 'expected_case_version':case['version']})
    assert result.status_code==200,result.text
    return result.json()


@pytest.mark.parametrize('scenario,conflicts', [('overlap',1),('time_separated',0),('space_separated',0),('different_height',0),('touching',0)])
def test_time_and_volume_both_required(scenario,conflicts):
    case=new_case(); values=activities()
    if scenario=='time_separated': values[1].update(planned_start='2026-10-16T12:00:00+08:00',planned_end='2026-10-16T14:00:00+08:00')
    if scenario=='space_separated': values[1]['workspace']={'min':[25,20,17.3],'max':[28,24,19.3]}
    if scenario=='different_height': values[1]['workspace']={'min':[18,20,20],'max':[21,24,22]}
    if scenario=='touching': values[1]['workspace']={'min':[21,20,17.3],'max':[23,24,19.3]}
    result=save_plan(case,values)
    assert len(result['coordination']['conflicts'])==conflicts
    assert result['coordination']['complete'] is True
    assert result['activity_plan']['revision']==1
    stale=client.put(f"/api/cases/{case['case_id']}/activity-plan",json={'activities':values,'reason':'stale','expected_case_version':case['version']})
    assert stale.status_code==409


def test_incomplete_activity_is_not_no_conflict():
    values=activities();values[1]['workspace']=None;values[1]['owner']=''
    result=save_plan(new_case(),values)
    assert result['coordination']['complete'] is False
    assert result['coordination']['missing_fields']
    case=analyze(result['case']['case_id'])
    assert case['status']=='needs_evidence'


def test_scope_point_and_edge_are_authoritative_and_case_local():
    case=new_case('EV-001'); other=new_case('EV-001')
    options=client.get('/api/inspection-context',params={'guid':GUID}).json()
    a,b=options['edge_options'][1]
    point=[(a[0]+b[0])/2+1,(a[1]+b[1])/2+.5,a[2]]
    payload={'guid':GUID,'edge_index':1,'worker_point_m':point,'worker_point_source':'simulated',
             'boundary_confirmed':True,'expected_case_version':case['version']}
    result=client.put(f"/api/cases/{case['case_id']}/scope",json=payload)
    assert result.status_code==200,result.text
    value=result.json()
    assert value['context']['zone']['data']['edge_segment_m']==options['edge_options'][1]
    assert value['context']['zone']['data']['worker_point_m']==point
    assert not client.get(f"/api/cases/{other['case_id']}").json()['case'].get('scope')
    assert value['spatial']['data']['point_m']==point
    payload.update(guid='wrong-guid',expected_case_version=value['case']['version'])
    assert client.put(f"/api/cases/{case['case_id']}/scope",json=payload).status_code==422


@pytest.mark.parametrize('adjust,expected',[(False,'reopened'),(True,'closed')])
def test_coordination_control_is_approved_and_rechecked(adjust,expected):
    result=save_plan(new_case(),activities()); case=analyze(result['case']['case_id'])
    assert case['status']=='pending_review'
    assert any(f['kind']=='coordination' and f['result']=='risk_candidate' for f in case['findings'] if 'kind' in f)
    assert any(c['verification_criteria'].get('coordination_required') for c in case['controls'])
    result=client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'approve',
        'control_version':case['control_version'],'expected_case_version':case['version']})
    assert result.status_code==200,result.text
    case=result.json()['case']
    if adjust:
        values=activities();values[1].update(planned_start='2026-10-16T12:00:00+08:00',planned_end='2026-10-16T14:00:00+08:00')
        case=save_plan(case,values,'按批准的隔离/错时措施调整作业时间')['case']
        assert case['status']=='approved'
        assert case['review']['activity_plan_revision']==1
    result=client.post(f"/api/cases/{case['case_id']}/implementation",json={'implemented_at':'2026-10-16T09:20:00+08:00','expected_case_version':case['version']})
    assert result.status_code==200,result.text
    result=client.post(f"/api/cases/{case['case_id']}/evidence",json={'evidence_ids':['EV-010']})
    case=result.json()['case']
    result=client.post(f"/api/cases/{case['case_id']}/verify",json={'after_evidence_ids':['EV-010'],
        'reviewer_confirmed':True,'as_of':'2026-10-16T09:40:00+08:00','expected_case_version':case['version']})
    assert result.status_code==200,result.text
    assert result.json()['case']['status']==expected


def test_text_citations_conflicts_and_human_resolution(monkeypatch):
    from app import site_text
    monkeypatch.setattr(site_text,'DEMO_MODE',False)
    case=new_case('EV-001')
    result=client.post(f"/api/cases/{case['case_id']}/site-notes",json={'title':'巡检记录','source':'安全员巡检',
        'captured_at':'2026-10-16T08:55:00+08:00','body':'临边防护已设置。\n待复核固定情况。','expected_case_version':case['version']})
    assert result.status_code==201,result.text
    bundle=result.json();note=bundle['site_notes'][0]; paragraph=note['paragraphs'][0]
    monkeypatch.setattr(site_text,'chat_json',lambda **kwargs:{'summary':'防护已设置',
        'facts':[{'field':'guardrail_state','value':'present','paragraph_id':paragraph['id'],'quote':'临边防护已设置'}], 'uncertainties':[]})
    result=client.post(f"/api/cases/{case['case_id']}/site-notes/{note['note_id']}/extract")
    assert result.status_code==200,result.text
    bundle=result.json(); conflicts=bundle['site_text']['conflicts']
    assert conflicts[0]['observation_value']=='absent'
    assert conflicts[0]['text_value']=='present'
    assert bundle['evidence'][0]['observation']['guardrail_state']=='absent'
    assert bundle['site_text']['complete'] is False
    result=client.post(f"/api/cases/{case['case_id']}/site-notes/resolve",json={
        'conflict_id':conflicts[0]['conflict_id'],'observation_hash':conflicts[0]['observation_hash'],
        'decision':'retain_observation','reason':'已核对原始照片，本条文字记录错误，保留照片观察。',
        'expected_case_version':bundle['case']['version']})
    assert result.status_code==200,result.text
    bundle=result.json()
    assert bundle['site_text']['complete'] is True
    assert bundle['site_text']['conflicts'][0]['resolution']['reason']
    assert bundle['evidence'][0]['observation']['guardrail_state']=='absent'


@pytest.mark.parametrize('kind',['invented_quote','unmentioned_height'])
def test_text_facts_need_verbatim_sources_and_numeric_units(monkeypatch,kind):
    from app import site_text
    monkeypatch.setattr(site_text,'DEMO_MODE',False)
    case=new_case();bundle=client.post(f"/api/cases/{case['case_id']}/site-notes",json={
        'title':'巡检','source':'现场记录','captured_at':case['as_of'],'body':'临边防护已设置。','expected_case_version':case['version']}).json()
    note=bundle['site_notes'][0]
    fact={'field':'guardrail_state','value':'absent','paragraph_id':note['paragraphs'][0]['id'],'quote':'临边防护未设置'}
    if kind=='unmentioned_height':fact.update(field='guardrail_height_m',value=1.2,quote='临边防护已设置')
    monkeypatch.setattr(site_text,'chat_json',lambda **kwargs:{'summary':'候选','facts':[fact],'uncertainties':[]})
    response=client.post(f"/api/cases/{case['case_id']}/site-notes/{note['note_id']}/extract")
    assert response.status_code==422
    assert client.get(f"/api/cases/{case['case_id']}").json()['site_notes'][0]['analysis'] is None


def test_undetermined_text_and_revision_do_not_overwrite_observation(monkeypatch):
    from app import site_text
    monkeypatch.setattr(site_text,'DEMO_MODE',False)
    case=new_case();bundle=client.post(f"/api/cases/{case['case_id']}/site-notes",json={
        'title':'交底','source':'班前记录','captured_at':case['as_of'],'body':'具体防护情况待核实。','expected_case_version':case['version']}).json()
    note=bundle['site_notes'][0]
    monkeypatch.setattr(site_text,'chat_json',lambda **kwargs:{'summary':'缺少明确观察','facts':[],'uncertainties':['防护状态待核实']})
    bundle=client.post(f"/api/cases/{case['case_id']}/site-notes/{note['note_id']}/extract").json()
    assert bundle['site_text']['complete'] is False
    assert bundle['site_text']['conflicts'][0]['field']=='record_relevance'
    bundle=client.post(f"/api/cases/{case['case_id']}/site-notes",json={'title':'交底修订','source':'班前记录',
        'captured_at':case['as_of'],'body':'临边防护已设置。','supersedes_note_id':note['note_id'],'expected_case_version':bundle['case']['version']}).json()
    assert sorted(n['version'] for n in bundle['site_notes'])==[1,2]
    assert sum(n['current'] for n in bundle['site_notes'])==1
    assert bundle['evidence'][0]['observation']['guardrail_state']=='present'


def test_future_text_does_not_enter_current_safety_state(monkeypatch):
    case=new_case();bundle=client.post(f"/api/cases/{case['case_id']}/site-notes",json={'title':'未来记录','source':'时间校验',
        'captured_at':'2026-10-17T09:00:00+08:00','body':'临边防护缺失。','expected_case_version':case['version']}).json()
    assert bundle['site_text']['complete'] is True
    assert len(bundle['site_text']['excluded_notes'])==1
    result=analyze(case['case_id'])
    assert result['status']=='pending_review'
    assert result['safety_state']['site_text']['facts']==[]


@pytest.mark.parametrize('resource',['activity-plan','site-notes'])
def test_new_time_inputs_require_timezone(resource):
    case=new_case()
    if resource=='activity-plan':
        values=activities();values[0]['planned_start']='2026-10-16T08:00:00'
        response=client.put(f"/api/cases/{case['case_id']}/{resource}",json={
            'activities':values,'reason':'时间校验','expected_case_version':case['version']})
    else:
        response=client.post(f"/api/cases/{case['case_id']}/{resource}",json={
            'title':'时间校验','source':'现场记录','captured_at':'2026-10-16T08:00:00',
            'body':'临边防护已设置。','expected_case_version':case['version']})
    assert response.status_code==422


@pytest.mark.parametrize('recover',[True,False])
def test_planner_retries_invalid_shape_once(monkeypatch,recover):
    from app import coordinator,live_model
    from pydantic import ValidationError
    monkeypatch.setattr(coordinator,'DEMO_MODE',False)
    case=new_case();calls=[]
    def model(context):
        calls.append(context)
        raw={'request':context['request'],'zone_id':context['zone_id'],'as_of':context['as_of'],
            'focus':['all'],'selected_tools':coordinator.CORE_TOOLS+['spatial_check'],'retrieval_query':'临边防护'}
        if len(calls)==1 or not recover: raw['type']='json_object'
        return raw
    monkeypatch.setattr(live_model,'live_task_plan',model)
    if recover:
        spec,_=coordinator.plan_task(case,'材料转运')
        assert spec['mode']=='live_model'
    else:
        with pytest.raises(ValidationError): coordinator.plan_task(case,'材料转运')
    assert len(calls)==2
    assert calls[1]['validation_feedback']


def test_workspace_records_are_exported():
    case=new_case();bundle=save_plan(case,activities())
    bundle=client.post(f"/api/cases/{case['case_id']}/site-notes",json={'title':'演示巡检','source':'演示编制',
        'captured_at':case['as_of'],'body':'防护固定情况待核实。','expected_case_version':bundle['case']['version']}).json()
    data=client.get(f"/api/cases/{case['case_id']}/export?format=json").json()
    assert data['activity_plan']['revision']==1
    assert data['site_notes'][0]['body']=='防护固定情况待核实。'
    report=client.get(f"/api/cases/{case['case_id']}/export?format=md").text
    assert '作业计划与版本' in report
    assert bundle['site_notes'][0]['paragraphs'][0]['id'] in report
