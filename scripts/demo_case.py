"""Build/query/replay the demo data layer with Python's standard library only."""
import argparse
import copy
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/demo/s1_case_001'


def load(name):
    return json.loads((PACKAGE / name).read_text(encoding='utf-8'))


def save(name, value):
    path = PACKAGE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def segment_hits_box(p, q, low, high):
    """Liang-Barsky interval test in XY; boundary contact counts as conflict."""
    t0, t1 = 0.0, 1.0
    for axis in (0, 1):
        delta = q[axis] - p[axis]
        if abs(delta) < 1e-12:
            if not low[axis] <= p[axis] <= high[axis]:
                return False
        else:
            a, b = sorted(((low[axis]-p[axis])/delta, (high[axis]-p[axis])/delta))
            t0, t1 = max(t0, a), min(t1, b)
            if t0 > t1:
                return False
    return True


def geometry_checks():
    g = load('geometry.json')
    hole = g['opening']; p = g['worker_point']
    low, high = hole['bbox_min'], hole['bbox_max']
    distance = math.hypot(*[max(low[i]-p[i], 0, p[i]-high[i]) for i in (0, 1)])
    buffer = hole['hazard_buffer_m']
    a, b = [v-buffer for v in low[:2]], [v+buffer for v in high[:2]]
    hits = lambda route: any(segment_hits_box(x, y, a, b) for x, y in zip(route, route[1:]))
    schedule = {x['id']: x for x in load('schedule.json')}
    def overlap(first, second, prefix):
        x,y = schedule[first], schedule[second]
        key1,key2 = (('baseline_start','baseline_finish') if prefix=='baseline' else ('controlled_start','controlled_finish'))
        start = max(datetime.fromisoformat(x[key1]), datetime.fromisoformat(y[key1]))
        finish = min(datetime.fromisoformat(x[key2]), datetime.fromisoformat(y[key2]))
        return max(0, int((finish-start).total_seconds()/60))
    return {'origin':'computed_from_authored_geometry_and_schedule','unit':'m',
        'worker_opening_distance_m':round(distance, 6),
        'worker_within_buffer':distance < buffer,
        'original_route_conflict':hits(g['original_route']),
        'alternative_route_conflict':hits(g['alternative_route']),
        'baseline_ACT01_ACT02_overlap_minutes':overlap('ACT-01','ACT-02','baseline'),
        'controlled_ACT01_ACT02_overlap_minutes':overlap('ACT-01','ACT-02','controlled'),
        'vertical_cross_trade_conflict':'not_inferred_from_same_level_overlap',
        'structural_capacity':'not_calculated'}


def evaluate_evidence(evidence):
    if evidence['kind'] != 'synthetic_diagram' or evidence['origin'] != 'authored_demo':
        raise ValueError('Historical context cannot be used as controlled verification evidence')
    o = evidence['observations']
    checks = {'guardrail_complete':o['guardrail_complete'],
        'top_rail_height':o['top_rail_height_m'] >= 1.2,
        'toe_board_complete':o['toe_board_complete'],
        'toe_board_height':o['toe_board_height_m'] >= 0.18,
        'safety_net_complete':o['safety_net_complete'],
        'route_separated':o['route_separated']}
    return {'checks':checks,'passed':all(checks.values()),'method':'deterministic_PR02_check_of_fixture_observations'}


def new_state():
    return {'case_id':load('case.json')['id'],'revision':1,'status':'DRAFT',
            'decision_id':None,'approval':None,'assignments':{},'implementation':None,
            'verification':None,'active_evidence_id':'EV-01','history':[],
            'work_release':False,'approval_is_real':False}


def apply_event(state, event, actors=None, evidence=None):
    actors = actors or {x['id']:x for x in load('actors.json')}
    evidence = evidence or {x['id']:x for x in load('evidence.json')}
    s = copy.deepcopy(state)
    if event['case_id'] != s['case_id'] or event['revision'] != s['revision']:
        raise ValueError('Case or revision mismatch; stale authorization is invalid')
    if event['actor_id'] not in actors:
        raise ValueError('Unknown actor')
    if event.get('origin') != 'scripted_demo':
        raise ValueError('This replay engine accepts scripted_demo events only')
    timestamp = datetime.fromisoformat(event['at'])
    if timestamp.utcoffset() != timedelta(hours=8):
        raise ValueError('Demo event time must use +08:00')
    if s['history'] and timestamp <= datetime.fromisoformat(s['history'][-1]['at']):
        raise ValueError('Events must have strictly increasing times')
    if any(e['id'] == event['id'] for e in s['history']):
        raise ValueError('Duplicate event')
    action = event['action']; role = actors[event['actor_id']]['role']; payload=event.get('payload',{})
    allowed = {'ANALYZE':('agent',),'SUBMIT':('coordinator',),'APPROVE':('approver',),
        'REJECT':('approver',),'ASSIGN':('coordinator',),'START':('implementer',),
        'COMPLETE':('implementer',),'VERIFY':('verifier',),'CLOSE':('approver',),'REOPEN':('verifier',)}
    if action not in allowed or role not in allowed[action]:
        raise ValueError('Actor role cannot perform this action')
    def require(*statuses):
        if s['status'] not in statuses:
            raise ValueError(f"{action} not allowed from {s['status']}")
    if action=='ANALYZE':
        require('DRAFT','REOPENED')
        if payload.get('decision_id') != f"DEC-{s['revision']:02d}":
            raise ValueError('Decision must be bound to current revision')
        s.update(status='ASSESSED', decision_id=payload['decision_id'])
    elif action=='SUBMIT':
        require('ASSESSED'); s['status']='AWAITING_APPROVAL'
    elif action in ('APPROVE','REJECT'):
        require('AWAITING_APPROVAL')
        if payload.get('decision_id') != s['decision_id'] or not payload.get('reason'):
            raise ValueError('Approval/rejection requires exact decision and a reason')
        s['approval']={'revision':s['revision'],'decision_id':s['decision_id'],
                       'actor_id':event['actor_id'],'event_id':event['id'],
                       'at':event['at'],'approved':action=='APPROVE','origin':'scripted_demo',
                       'reason':payload['reason']}
        s['status']='APPROVED' if action=='APPROVE' else 'REJECTED'
    elif action=='ASSIGN':
        require('APPROVED')
        expected={x['id']:x['owner_id'] for x in load('controls.json')}
        if payload.get('assignments') != expected:
            raise ValueError('Every required control must be assigned to its specified owner')
        s['assignments']=expected; s['status']='ASSIGNED'
    elif action=='START':
        require('ASSIGNED','REWORK')
        if not s['approval'] or not s['approval']['approved'] or s['approval']['revision']!=s['revision']:
            raise ValueError('Current approval required before implementation')
        if event['actor_id'] not in s['assignments'].values():
            raise ValueError('Implementation actor must be assigned')
        brief=next(x for x in load('briefings.json') if x['revision']==s['revision'])
        if datetime.fromisoformat(brief['at'])>timestamp or not {'foreman','mep_lead'}<=set(brief['acknowledged_actor_ids']):
            raise ValueError('Required participants must acknowledge briefing before work starts')
        s.update(status='IMPLEMENTING',implementation=None,verification=None)
    elif action=='COMPLETE':
        require('IMPLEMENTING')
        eid=payload.get('evidence_id')
        if eid not in evidence or eid==s['active_evidence_id']:
            raise ValueError('A new implementation evidence record is required')
        if evidence[eid]['case_id']!=s['case_id'] or evidence[eid]['area_id']!='AREA-L4-A':
            raise ValueError('Evidence must refer to this Case and area')
        if s['revision']>1 and evidence[eid]['stage']!='pass_v2':
            raise ValueError('Reopened Case requires new evidence for its revision')
        evaluate_evidence(evidence[eid])
        if datetime.fromisoformat(evidence[eid]['scenario_time']) > timestamp:
            raise ValueError('Evidence cannot be submitted before its scenario capture time')
        logs=payload.get('work_log',[])
        expected={x['id']:x['owner_id'] for x in load('controls.json')}
        if len(logs)!=len(expected) or {x['control_id']:x['owner_id'] for x in logs}!=expected or not all(x.get('note') for x in logs):
            raise ValueError('Implementation log must cover each control with owner and note')
        brief=next((x for x in load('briefings.json') if x['id']==payload.get('briefing_id')), None)
        if not brief or brief['revision']!=s['revision'] or datetime.fromisoformat(brief['at'])>timestamp:
            raise ValueError('A current briefing acknowledged before submission is required')
        s['implementation']={'evidence_id':eid,'actor_id':event['actor_id'],'revision':s['revision'],
                             'work_log':logs,'briefing_id':brief['id'],'at':event['at'],'origin':'scripted_demo'}
        s.update(status='AWAITING_VERIFICATION', active_evidence_id=eid)
    elif action=='VERIFY':
        require('AWAITING_VERIFICATION')
        if event['actor_id']==s['implementation']['actor_id']:
            raise ValueError('Verifier must be independent from implementer')
        if payload.get('evidence_id')!=s['implementation']['evidence_id']:
            raise ValueError('Verification must use latest submitted evidence')
        result=evaluate_evidence(evidence[payload['evidence_id']])
        s['verification']={**result,'revision':s['revision'],'evidence_id':payload['evidence_id'],
                           'actor_id':event['actor_id'],'at':event['at'],'origin':'scripted_demo'}
        s['status']='VERIFIED' if result['passed'] else 'REWORK'
    elif action=='CLOSE':
        require('VERIFIED')
        if not s['verification']['passed'] or s['verification']['revision']!=s['revision']:
            raise ValueError('Successful current verification required')
        s.update(status='CLOSED',work_release=True)
    elif action=='REOPEN':
        require('CLOSED')
        eid=payload.get('evidence_id')
        if eid not in evidence or evidence[eid]['stage']!='changed' or not payload.get('reason'):
            raise ValueError('Condition-change evidence and reason are required')
        s.update(status='REOPENED',revision=s['revision']+1,decision_id=None,approval=None,
                 assignments={},implementation=None,verification=None,active_evidence_id=eid,work_release=False)
    s['history'].append(copy.deepcopy(event))
    return s


def scenarios():
    specs=[('normal_close','正常审批整改复核关闭','CLOSED'),('verification_rework','复核失败返工后关闭','CLOSED'),
           ('changed_reopen','关闭后条件变化重开再闭环','CLOSED'),('approval_rejected','审批驳回且禁止实施','REJECTED')]
    output=[]
    for run_id,title,expected in specs:
        events=[]; revision=1
        clock=datetime.fromisoformat('2026-10-18T08:15:00+08:00')
        def add(action, actor, **payload):
            nonlocal clock
            events.append({'id':f'{run_id}-E{len(events)+1:02d}','run_id':run_id,'case_id':'DEMO-S1-001',
                'revision':revision,'at':clock.isoformat(),'actor_id':actor,'action':action,
                'payload':payload,'origin':'scripted_demo'})
            clock+=timedelta(minutes=5)
        def decision():
            add('ANALYZE','agent',decision_id=f'DEC-{revision:02d}'); add('SUBMIT','coordinator')
        def approve_assign():
            reason=('同意隔离整改、调整通道和工序；复核通过前禁止恢复作业。演示点击。' if revision==1
                    else '同意重新隔离、恢复完整防护并确认通道；本轮复核通过前禁止进入。演示点击。')
            add('APPROVE','approver',decision_id=f'DEC-{revision:02d}',reason=reason)
            add('ASSIGN','coordinator',assignments={x['id']:x['owner_id'] for x in load('controls.json')})
        def complete(eid):
            nonlocal clock
            if revision==1:
                clock=max(clock,datetime.fromisoformat('2026-10-18T08:40:00+08:00'))
            add('START','foreman')
            capture = next(x['scenario_time'] for x in load('evidence.json') if x['id']==eid)
            clock = max(clock, datetime.fromisoformat(capture))
            log=[{'control_id':x['id'],'owner_id':x['owner_id'],'note':x['title']+'，已提交本轮记录。'} for x in load('controls.json')]
            if revision==2:
                scopes={x['control_id']:x['scope'] for x in load('control_revisions.json')[1]['control_updates']}
                for row in log: row['note']=scopes[row['control_id']]+'，已提交本轮记录。'
            briefing=next(x for x in load('briefings.json') if x['revision']==revision)
            clock=max(clock,datetime.fromisoformat(briefing['at']))
            add('COMPLETE','foreman',evidence_id=eid,work_log=log,briefing_id=briefing['id'])
            add('VERIFY','inspector',evidence_id=eid)
        decision()
        if run_id=='approval_rejected':
            add('REJECT','approver',decision_id='DEC-01',reason='演示驳回：作业协调条件未确认，补充方案后重新提交。')
        else:
            approve_assign()
            if run_id=='verification_rework':
                complete('EV-02')
            complete('EV-03'); add('CLOSE','approver')
            if run_id=='changed_reopen':
                clock=datetime.fromisoformat('2026-10-18T11:00:00+08:00')
                add('REOPEN','inspector',evidence_id='EV-04',reason='巡查发现已验收防护被移除，原条件失效。')
                revision=2
                decision(); approve_assign(); complete('EV-05'); add('CLOSE','approver')
        output.append({'id':run_id,'title':title,'case_id':'DEMO-S1-001','origin':'scripted_demo',
                       'expected_status':expected,'events':events})
    return output


def replay(scenario):
    state=new_state(); snapshots=[]
    for event in scenario['events']:
        state=apply_event(state,event)
        snapshots.append({k:v for k,v in state.items() if k!='history'})
    if state['status']!=scenario['expected_status']:
        raise ValueError('Unexpected scenario outcome')
    return {'id':scenario['id'],'title':scenario['title'],'origin':'scripted_demo',
            'final_state':state,'snapshots':snapshots}


def decision_package(revision, evidence_id):
    evidence=next(x for x in load('evidence.json') if x['id']==evidence_id)
    terms=['洞口','高处','警示','整改','矩阵','审批','复核','重开']
    retrieved=[r['id'] for r in load('rules.json')
               if any(t in r['text']+' '+' '.join(r['tags']) for t in terms)]
    tools=geometry_checks()
    if revision==2:
        intervals=load('schedule_revisions.json')[1]['intervals']
        overlap=max(0,int((min(datetime.fromisoformat(x['finish']) for x in intervals)-
                           max(datetime.fromisoformat(x['start']) for x in intervals)).total_seconds()/60))
        tools={'alternative_route_conflict':tools['alternative_route_conflict'],
               'current_worker_position':'not_observed_do_not_reuse_initial_point',
               'ACT03_ACT04_overlap_minutes':overlap,'schedule_source':'schedule_revisions.json',
               'structural_capacity':'not_calculated'}
    return {'id':f'DEC-{revision:02d}','case_id':'DEMO-S1-001','revision':revision,
        'origin':'computed_demo','agent_execution_mode':'deterministic_fixture_no_live_llm',
        'inputs':{'geometry':'geometry.json','evidence_id':evidence_id,
                  'schedule':'schedule.json' if revision==1 else 'schedule_revisions.json','plan':'PLAN-01'},
        'safety_state':{'area_id':'AREA-L4-A','activity_ids':['ACT-01','ACT-02'] if revision==1 else ['ACT-03','ACT-04'],
            'observations':evidence['observations'],'rules_context':'2026中国规则演示'},
        'risk_ids':[x['id'] for x in load('risks.json')] if revision==1 else ['RISK-01'],
        'risk_assessment_revision':revision,'control_revision':revision,'schedule_revision':revision,
        'retrieved_rule_ids':retrieved,'retrieval':{'method':'lexical_term_match','queries':terms},
        'excluded_conditional_rules':[{'id':'GB-3.2.2','reason':'同层重叠不能证明多层垂直交叉作业，待新增证据后再适用'},
                                      {'id':'GB-3.3.3','reason':'尚无材料平台承载和实际载荷输入，不能输出超载结论'}],
        'tool_results':tools,'alternatives':([
            {'id':'ALT-A','name':'保持原路线直接施工','accepted':False,'reason':'洞口防护和路线冲突未解除'},
            {'id':'ALT-B','name':'隔离整改并改线错峰','accepted':True,'reason':'满足可检查控制项，仍须人工审批及复核'}] if revision==1 else [
            {'id':'ALT-A','name':'沿用首轮关闭结论继续进入','accepted':False,'reason':'防护变化导致旧授权失效'},
            {'id':'ALT-B','name':'重新隔离恢复防护并复核','accepted':True,'reason':'确认通道仍有效，按新版本重新批准和复核'}]),
        'recommended_control_ids':[x['id'] for x in load('controls.json')],
        'approval_required':True,'approver_id':'approver','verifier_id':'inspector',
        'conditional_residual_risk':('全部控制项通过后，RISK-01/02/03预计分别降至5/4/3；未通过前保持高风险和禁行。' if revision==1
                                    else '重新验收全部控制项后，RISK-01预计降至5；本轮不重复声称已结束活动仍有时间冲突。'),
        'approval_status':'not_approved','limits':['未进行结构承载计算','未对原照片执行视觉推理','风险矩阵和具体防护尺寸为项目演示规则']}


def build_database(runs):
    db=PACKAGE/'demo.sqlite'
    con=sqlite3.connect(db)
    con.execute('PRAGMA foreign_keys=ON')
    # Only this derived database is recreated. It contains no live user sessions.
    tables=['event_log','runs','decisions','briefings','risk_assessments','schedule_revisions','control_revisions',
            'risk_controls','risk_rules','risk_evidence','risks','controls','activities',
            'cases','evidence','areas','actors','documents','rules','source_assets','knowledge_fts']
    for name in tables:
        con.execute(f'DROP TABLE IF EXISTS {name}')
    con.executescript('''
        CREATE TABLE actors(id TEXT PRIMARY KEY, role TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE areas(id TEXT PRIMARY KEY, data_json TEXT NOT NULL);
        CREATE TABLE evidence(id TEXT PRIMARY KEY, area_id TEXT REFERENCES areas(id), kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE cases(id TEXT PRIMARY KEY, area_id TEXT REFERENCES areas(id), status TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE activities(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), owner_id TEXT REFERENCES actors(id), data_json TEXT NOT NULL);
        CREATE TABLE controls(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), owner_id TEXT REFERENCES actors(id), verifier_id TEXT REFERENCES actors(id), data_json TEXT NOT NULL);
        CREATE TABLE rules(id TEXT PRIMARY KEY, origin TEXT NOT NULL, text TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE risks(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), score INTEGER NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE risk_controls(risk_id TEXT REFERENCES risks(id), control_id TEXT REFERENCES controls(id), PRIMARY KEY(risk_id,control_id));
        CREATE TABLE risk_rules(risk_id TEXT REFERENCES risks(id), rule_id TEXT REFERENCES rules(id), PRIMARY KEY(risk_id,rule_id));
        CREATE TABLE risk_evidence(risk_id TEXT REFERENCES risks(id), evidence_id TEXT REFERENCES evidence(id), PRIMARY KEY(risk_id,evidence_id));
        CREATE TABLE documents(id TEXT PRIMARY KEY, path TEXT NOT NULL, text TEXT NOT NULL);
        CREATE TABLE source_assets(id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE decisions(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), revision INTEGER NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE briefings(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), revision INTEGER NOT NULL, leader_id TEXT REFERENCES actors(id), data_json TEXT NOT NULL);
        CREATE TABLE risk_assessments(case_id TEXT REFERENCES cases(id), revision INTEGER, data_json TEXT NOT NULL, PRIMARY KEY(case_id,revision));
        CREATE TABLE schedule_revisions(case_id TEXT REFERENCES cases(id), revision INTEGER, data_json TEXT NOT NULL, PRIMARY KEY(case_id,revision));
        CREATE TABLE control_revisions(case_id TEXT REFERENCES cases(id), revision INTEGER, data_json TEXT NOT NULL, PRIMARY KEY(case_id,revision));
        CREATE TABLE runs(id TEXT PRIMARY KEY, case_id TEXT REFERENCES cases(id), final_status TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE event_log(run_id TEXT REFERENCES runs(id), seq INTEGER, event_id TEXT UNIQUE, actor_id TEXT REFERENCES actors(id), revision INTEGER, action TEXT NOT NULL, at TEXT NOT NULL, data_json TEXT NOT NULL, PRIMARY KEY(run_id,seq));
        CREATE VIRTUAL TABLE knowledge_fts USING fts5(id UNINDEXED, title, text, tags);
    ''')
    js=lambda x:json.dumps(x,ensure_ascii=False)
    for x in load('actors.json'): con.execute('INSERT INTO actors VALUES(?,?,?)',(x['id'],x['role'],js(x)))
    x=load('geometry.json')['area']; con.execute('INSERT INTO areas VALUES(?,?)',(x['id'],js(x)))
    for x in load('evidence.json'): con.execute('INSERT INTO evidence VALUES(?,?,?,?)',(x['id'],x['area_id'],x['kind'],js(x)))
    x=load('case.json'); con.execute('INSERT INTO cases VALUES(?,?,?,?)',(x['id'],x['area_id'],x['status'],js(x)))
    for x in load('schedule.json'): con.execute('INSERT INTO activities VALUES(?,?,?,?)',(x['id'],x['case_id'],x['owner_id'],js(x)))
    for x in load('controls.json'): con.execute('INSERT INTO controls VALUES(?,?,?,?,?)',(x['id'],x['case_id'],x['owner_id'],x['verifier_id'],js(x)))
    for x in load('rules.json'):
        con.execute('INSERT INTO rules VALUES(?,?,?,?)',(x['id'],x['origin'],x['text'],js(x)))
        con.execute('INSERT INTO knowledge_fts VALUES(?,?,?,?)',(x['id'],x['title'],x['text'],' '.join(x['tags'])))
    for x in load('risks.json'):
        con.execute('INSERT INTO risks VALUES(?,?,?,?)',(x['id'],x['case_id'],x['score'],js(x)))
        for table,key in [('risk_controls','control_ids'),('risk_rules','rule_ids'),('risk_evidence','evidence_ids')]:
            con.executemany(f'INSERT INTO {table} VALUES(?,?)',[(x['id'],v) for v in x[key]])
    for path in sorted((PACKAGE/'documents').glob('*.md')):
        doc_id='PLAN-01' if '施工方案' in path.stem else path.stem
        text=path.read_text(encoding='utf-8')
        con.execute('INSERT INTO documents VALUES(?,?,?)',(doc_id,path.relative_to(PACKAGE).as_posix(),text))
        con.execute('INSERT INTO knowledge_fts VALUES(?,?,?,?)',(doc_id,path.stem,text,'方案 交底 责任 流程'))
    for x in load('source_assets.json'): con.execute('INSERT INTO source_assets VALUES(?,?,?,?)',(x['id'],x['path'],x['sha256'],js(x)))
    for x in load('decisions.json'): con.execute('INSERT INTO decisions VALUES(?,?,?,?)',(x['id'],x['case_id'],x['revision'],js(x)))
    for x in load('briefings.json'): con.execute('INSERT INTO briefings VALUES(?,?,?,?,?)',(x['id'],x['case_id'],x['revision'],x['leader_id'],js(x)))
    for table in ['risk_assessments','schedule_revisions','control_revisions']:
        for x in load(table+'.json'): con.execute(f'INSERT INTO {table} VALUES(?,?,?)',('DEMO-S1-001',x['revision'],js(x)))
    for run in runs:
        con.execute('INSERT INTO runs VALUES(?,?,?,?)',(run['id'],'DEMO-S1-001',run['final_state']['status'],js(run)))
        for i,e in enumerate(run['final_state']['history'],1):
            con.execute('INSERT INTO event_log VALUES(?,?,?,?,?,?,?,?)',(run['id'],i,e['id'],e['actor_id'],e['revision'],e['action'],e['at'],js(e)))
    if con.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Foreign key check failed')
    con.commit(); con.close()


def search(query):
    with sqlite3.connect(PACKAGE/'demo.sqlite') as con:
        # FTS handles tokenized titles/tags; LIKE supports arbitrary Chinese substrings.
        return con.execute('SELECT id,title,substr(text,1,180) FROM knowledge_fts WHERE text LIKE ? OR tags LIKE ? OR title LIKE ? LIMIT 12', ('%'+query+'%',)*3).fetchall()


def validate():
    issues=[]; references=0
    for item in load('source_assets.json'):
        p=ROOT/item['path']; references+=1
        if not p.is_file() or p.stat().st_size!=item['size'] or digest(p)!=item['sha256']:
            issues.append('source_asset:'+item['id'])
    for item in load('evidence.json'):
        references+=1
        if not (PACKAGE/item['path']).is_file(): issues.append('evidence:'+item['id'])
    ids={x['id'] for x in load('rules.json')}
    for rule in load('rules.json'):
        path=PACKAGE/rule['source_path']; references+=1
        if not path.is_file(): issues.append('rule_source:'+rule['id'])
        if rule.get('source_sha256') and digest(path)!=rule['source_sha256']: issues.append('rule_hash:'+rule['id'])
    for decision in load('decisions.json'):
        if not set(decision['retrieved_rule_ids'])<=ids: issues.append('decision_rules')
    for step in load('readiness.json')['steps']:
        references+=1
        if not (PACKAGE/step['input']).is_file(): issues.append('step_input:'+str(step['step']))
    for brief in load('briefings.json'):
        references+=1
        if not (PACKAGE/brief['document_path']).is_file(): issues.append('briefing_document')
    with sqlite3.connect(PACKAGE/'demo.sqlite') as con:
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok': issues.append('sqlite_integrity')
        if con.execute('PRAGMA foreign_key_check').fetchall(): issues.append('sqlite_foreign_keys')
        counts={t:con.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ['actors','cases','activities','evidence','rules','risks','controls','runs','event_log','documents','decisions','briefings','risk_assessments']}
    computed=geometry_checks()
    if not (computed['original_route_conflict'] and not computed['alternative_route_conflict']): issues.append('route_geometry')
    if computed['controlled_ACT01_ACT02_overlap_minutes']!=0: issues.append('schedule_overlap')
    return {'passed':not issues,'issues':issues,'verified_file_references':references,'database_counts':counts,
            'geometry_checks':computed,'readiness_scope':'controlled_demo_data_layer_only; no live LLM/vision/API/UI implemented'}


def build():
    specs=scenarios(); save('scenarios.json',specs)
    runs=[replay(x) for x in specs]
    for run in runs: save(f"runs/{run['id']}.json",run)
    actors={x['id']:x['name'] for x in load('actors.json')}
    records=['# 审批实施复核演示记录','',
             'Case：DEMO-S1-001。以下记录由固定脚本回放生成，全部为演示角色及事件，不代表真实审批或签字。实时案例初始状态仍为DRAFT。','']
    for run in runs:
        records.extend([f"## {run['title']}",'',f"运行ID：{run['id']}；最终状态：{run['final_state']['status']}；版本：{run['final_state']['revision']}。",'',
                        '| 时间 | 版本 | 动作 | 演示角色 | 内容 |','| --- | --- | --- | --- | --- |'])
        for e in run['final_state']['history']:
            p=e['payload']; note=p.get('reason') or p.get('evidence_id') or p.get('decision_id') or '按当前版本执行'
            if e['action']=='ASSIGN': note='CTRL-01/02/04：李班长；CTRL-03：周工'
            if e['action']=='COMPLETE': note+=f"；4项措施日志；交底{p['briefing_id']}"
            if e['action']=='VERIFY':
                result=evaluate_evidence(next(x for x in load('evidence.json') if x['id']==p['evidence_id']))
                note+='；'+('全部检查项通过' if result['passed'] else '挡脚板完整性及高度不通过，返工')
            records.append(f"| {e['at'][11:16]} | {e['revision']} | {e['action']} | {actors[e['actor_id']]} | {note} |")
        records.append('')
    (PACKAGE/'documents/审批实施复核演示记录.md').write_text('\n'.join(records)+'\n',encoding='utf-8')
    save('decisions.json',[decision_package(1,'EV-01'),decision_package(2,'EV-04')])
    save('geometry_checks.json',geometry_checks())
    steps=[
        ('create_task','case.json','Coordinator','Case request and active revision'),
        ('bim_context','geometry.json','Coordinator','Real anchor and authored area/opening'),
        ('site_evidence','evidence.json','Inspection','Five labeled synthetic stages and real photo context'),
        ('schedule_state','schedule.json','Coordinator','Baseline and controlled intervals'),
        ('unified_safety_state','decisions.json','Coordinator','Area activity observations time and provenance'),
        ('knowledge_retrieval','rules.json','Knowledge','Official clause anchors plus project rules; SQLite retrieval'),
        ('risk_assessment','risks.json','Risk','Three risks and explicit demo scoring'),
        ('geometry_rule_validation','geometry_checks.json','Risk','Actual route distance and schedule calculations'),
        ('intervention','controls.json','Intervention','Isolation protection rerouting and briefing'),
        ('decision_package','decisions.json','Coordinator','Alternatives controls owners and approval gate'),
        ('human_authorization','scenarios.json','Human approver','Scripted approval and rejection; live seed has no approval'),
        ('implementation','runs/normal_close.json','Human implementers','Assignments and control work logs'),
        ('verification','runs/changed_reopen.json','Verification','Independent checklist close/rework/reopen and stale approval reset')]
    save('readiness.json',{'case_id':'DEMO-S1-001','controlled_demo_data_ready':True,
        'real_project_complete_case':False,'live_web_ready':False,
        'steps':[{'step':i,'name':a,'input':b,'responsible':c,'output':d,'demo_data_ready':True}
                 for i,(a,b,c,d) in enumerate(steps,1)]})
    build_database(runs)
    result=validate(); save('validation_report.json',result)
    if not result['passed']: raise ValueError(result['issues'])
    files=[]
    for p in sorted(PACKAGE.rglob('*')):
        if p.is_file() and p.name!='manifest.json' and 'qa' not in p.relative_to(PACKAGE).parts:
            files.append({'path':p.relative_to(PACKAGE).as_posix(),'size':p.stat().st_size,'sha256':digest(p)})
    save('manifest.json',{'schema_version':'1.0','case_id':'DEMO-S1-001','generated_files':files,
        'source_assets':'source_assets.json','path_policy':'package paths relative to data/demo/s1_case_001; source_asset paths relative to workspace root'})
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','validate','replay','search'])
    parser.add_argument('value',nargs='?')
    args=parser.parse_args()
    if args.command=='build': build()
    elif args.command=='validate':
        result=validate(); print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0 if result['passed'] else 1)
    elif args.command=='search': print(json.dumps(search(args.value or '洞口'),ensure_ascii=False,indent=2))
    else:
        spec=next(x for x in load('scenarios.json') if x['id']==(args.value or 'normal_close'))
        result=replay(spec); print(json.dumps({'run_id':result['id'],'status':result['final_state']['status'],
            'revision':result['final_state']['revision'],'trace':[s['status'] for s in result['snapshots']]},ensure_ascii=False,indent=2))
