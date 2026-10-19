"""Author the self-contained S1 demonstration inputs. No original S1 file is changed."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/demo/s1_case_001'
S1 = ROOT / 'data/external/s1'
CASE = 'DEMO-S1-001'


def write_json(name, data):
    target = OUT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_asset(row, purpose):
    return {'id': row['id'], 'path': (Path('data/external/s1') / row['local_path']).as_posix(),
            'sha256': row['sha256'], 'size': row['size'], 'name': row['name'],
            'origin': 'real_s1', 'purpose': purpose}


def make_evidence(stage, title, rail, toe, net, route, index):
    """Vector evidence has known geometry; it is never presented as a camera photo."""
    color = '#25845d' if all([rail, toe, net, route]) else '#bd3e3e'
    # X -> 70+100*(X-24), Y -> 680-90*(Y-47). Explicit schematic, not equal aspect.
    fence = '<rect x="300" y="346" width="200" height="164" fill="none" stroke="#19815a" stroke-width="8"/>' if rail else '<path d="M300 510V346H500" fill="none" stroke="#bd3e3e" stroke-width="6" stroke-dasharray="12 8"/>'
    net_svg = '<path d="M310 356L490 500M310 500L490 356M350 356V500M410 356V500M470 356V500" stroke="#8fc9b0" stroke-width="3"/>' if net else ''
    toe_svg = '<rect x="305" y="351" width="190" height="154" fill="none" stroke="#b48148" stroke-width="4"/>' if toe else ''
    route_svg = '<path d="M110 590H630V212" fill="none" stroke="#2977b6" stroke-width="16"/>' if route else '<path d="M110 428H630" fill="none" stroke="#d58622" stroke-width="18"/>'
    checks = [('防护栏杆完整', rail), ('挡脚板完整', toe), ('安全网完整', net), ('通道与危险区分离', route)]
    check_svg = ''.join(f'<text x="740" y="{260+i*48}" fill="{("#19815a" if ok else "#bd3e3e")}">{label}：{("是" if ok else "否")}</text>' for i, (label, ok) in enumerate(checks))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="800" viewBox="0 0 1180 800">
<rect width="1180" height="800" fill="#f5f7fa"/><g font-family="Microsoft YaHei,Arial,sans-serif" fill="#15263b">
<text x="45" y="48" font-size="27" font-weight="bold">{CASE}　{title}</text>
<text x="45" y="83" font-size="17">演示合成示意图 · 非现场照片 · 同一 L4 A 区 · 米制 BIM 局部坐标 · 示意非等比例</text>
<rect x="70" y="140" width="600" height="540" fill="#e3e9f0" stroke="#768a9d" stroke-width="2"/>
<text x="80" y="168" font-size="17">工作区 [24,47] 至 [30,53]，楼面 Z=14.10 m</text>
<rect x="260" y="311" width="280" height="234" fill="none" stroke="#c97c6a" stroke-dasharray="5 5"/>
{route_svg}<rect x="310" y="356" width="180" height="144" fill="#34475a"/>{net_svg}{fence}{toe_svg}
<text x="325" y="418" fill="white" font-size="18">补编洞口</text><text x="324" y="450" fill="white" font-size="17">1.8 × 1.6 m</text>
<circle cx="270" cy="446" r="14" fill="#e0a22a"/><text x="90" y="570" font-size="17">初始人员参考点距洞口 0.40 m</text>
<text x="740" y="150" font-size="22" fill="{color}">{stage}</text><g font-size="19">{check_svg}</g>
<text x="740" y="505" font-size="17">栏杆目标 1.20 m</text><text x="740" y="537" font-size="17">挡脚板目标 0.18 m</text>
<text x="740" y="577" font-size="16">以上尺寸为本演示项目验收值</text>
<text x="70" y="710" font-size="17">蓝色：改线后通道　橙色：原冲突通道　绿色：完整栏杆　棕色：挡脚板　虚线：防护缺口</text>
<text x="70" y="752" font-size="16">证据 EV-{index:02d}　用于结构化规则与流程验证；不声称由视觉模型识别。</text></g></svg>'''
    path = f'evidence/EV-{index:02d}.svg'
    (OUT / 'evidence').mkdir(exist_ok=True)
    (OUT / path).write_text(svg, encoding='utf-8')
    return {'id': f'EV-{index:02d}', 'case_id': CASE, 'area_id': 'AREA-L4-A',
            'origin': 'authored_demo', 'kind': 'synthetic_diagram', 'path': path,
            'title': title, 'stage': stage, 'scenario_time': f'2026-10-18T{["08:10", "09:10", "09:30", "11:00", "12:10"][index-1]}:00+08:00',
            'source_capture_time': None, 'coordinate_frame': 's1_bim_local_m',
            'observations': {'guardrail_complete': rail, 'toe_board_complete': toe,
                             'safety_net_complete': net, 'route_separated': route,
                             'top_rail_height_m': 1.2 if rail else 0.0,
                             'toe_board_height_m': 0.18 if toe else 0.0},
            'observation_method': 'authored_fixture_not_model_inference',
            'usable_as_field_verification': False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((S1 / 'download_manifest.json').read_text(encoding='utf-8'))
    photos = json.loads((S1 / 'prepared/photos.json').read_text(encoding='utf-8'))
    by_id = {x['id']: x for x in manifest}
    chosen = []
    for photo_id in ['h1Uyxi7HkkM', '3TjCX8-BUFU', 'p8c3Ku9a6rw']:
        item = source_asset(by_id[photo_id], 'historical_project_context_only')
        meta = next(x for x in photos if x['source_file_id'] == photo_id)
        item.update({'source_capture_time': meta['exif_datetime'], 'timezone': None,
                     'camera': meta['camera'], 'maps_to_case_opening': False})
        chosen.append(item)
    for name, purpose in [('BIM 4D Blok S1_IFC.ifc', 'historical_schedule_and_geometry_anchor'),
                          ('Overallplanning Blok S1.pp', 'historical_native_schedule'),
                          ('O-S1-BWK-BIM architectural - BIM bouwkundig.ifc', 'original_architectural_model'),
                          ('O-S1-CON-Structural engineering - Constructie.ifc', 'original_structural_context'),
                          ('O-S1-INS-W Installatie.ifc', 'original_mep_context'),
                          ('UO104 Plattegrond verdieping 4.pdf', 'same_storey_design_context_not_case_opening'),
                          ('MM16169_U-0400_2019-02-11.pdf', 'same_storey_structural_design_context'),
                          ('S1-W57-04-INS - Ventilatie 4e Verdieping P=+14100.pdf', 'same_storey_mep_design_context')]:
        chosen.append(source_asset(next(x for x in manifest if x['name'] == name), purpose))
    # Keep a small, traceable architectural source + exact original GUID from the audited crosswalk.
    write_json('source_assets.json', chosen)
    actors = [
        ('coordinator', '陈工', 'coordinator', '任务协调和责任分配'),
        ('approver', '王经理', 'approver', '批准或驳回控制方案以及关闭 Case'),
        ('foreman', '李班长', 'implementer', '防护安装和整改执行'),
        ('mep_lead', '周工', 'trade_lead', '调整机电及材料周转作业'),
        ('inspector', '赵安全员', 'verifier', '独立检查及复核'),
        ('agent', '安全协同 Agent', 'agent', '检索评估与决策包生成')]
    write_json('actors.json', [{'id': a, 'name': b + ('（演示角色）' if a != 'agent' else ''),
                               'role': c, 'responsibility': d, 'origin': 'authored_demo'} for a,b,c,d in actors])
    anchor_guid = '2qf$VfMpX9$fUCQwyJJ$VP'
    geo = next(x for x in json.loads((S1 / 'prepared/geometry_checks.json').read_text(encoding='utf-8')) if x['guid'] == anchor_guid)
    geometry = {'coordinate_frame': 's1_bim_local_m', 'unit': 'm',
        'bim_anchor': {'id': 'BIM-ANCHOR-01', 'planning_guid': anchor_guid,
            'original_guid': '0ivh2zDnQwPF47OIKLJLHb', 'source_task_id': 'ST00340',
            'original_storey': '04 vierde verdieping', 'type': 'IfcSlab',
            'bbox_min': geo['minimum_m'], 'bbox_max': geo['maximum_m'],
            'origin': 'real_s1', 'use': 'visual_spatial_anchor_only',
            'warning': '该构件为非承重饰面层代理。演示洞口与防护为叠加对象，不由此层推断结构承载或真实洞口。',
            'crosswalk_path': 'data/external/s1/prepared/focused_product_crosswalk.json'},
        'area': {'id': 'AREA-L4-A', 'name': '演示四层 A 区', 'origin': 'authored_demo',
            'bbox_min': [24,47,14.10], 'bbox_max': [30,53,17.10],
            'storey_alias_basis': 'display_alias_of_original_storey_not_source_task_floor_equivalence'},
        'opening': {'id': 'OPEN-01', 'origin': 'authored_demo', 'area_id': 'AREA-L4-A',
            'bbox_min': [26.4,49,14.10], 'bbox_max': [28.2,50.6,14.10], 'fall_height_m': 3.2,
            'hazard_buffer_m': 0.5},
        'worker_point': [26.0,49.6,14.10],
        'original_route': [[24.4,49.8,14.10],[29.6,49.8,14.10]],
        'alternative_route': [[24.4,48.0,14.10],[29.6,48.0,14.10],[29.6,52.2,14.10]],
        'scene_objects': [{'id':'GUARD-01','kind':'guardrail_overlay','opening_id':'OPEN-01','height_m':1.2},
                          {'id':'TOE-01','kind':'toe_board_overlay','opening_id':'OPEN-01','height_m':0.18},
                          {'id':'NET-01','kind':'safety_net_overlay','opening_id':'OPEN-01'}]}
    write_json('geometry.json', geometry)
    activities = [
      ('ACT-01','机电预留洞口复核与清理','mep_lead','08:00','10:00',[], '09:45','10:30'),
      ('ACT-02','材料周转与通行','foreman','08:30','10:00',[], '10:30','11:00'),
      ('ACT-03','洞口隔离及防护安装','foreman','08:20','09:30',[], '08:40','09:30'),
      ('ACT-04','安全复核与区域交接','inspector','09:30','09:45',['ACT-03'], '09:30','09:45')]
    rows = []
    for aid,name,owner,start,end,deps,new_start,new_end in activities:
        rows.append({'id':aid,'case_id':CASE,'area_id':'AREA-L4-A','name':name,'owner_id':owner,
            'origin':'authored_demo','source_task_reference':'ST00340',
            'source_task_relation':'historical_context_not_same_activity_or_dates',
            'baseline_start':f'2026-10-18T{start}:00+08:00','baseline_finish':f'2026-10-18T{end}:00+08:00',
            'controlled_start':f'2026-10-18T{new_start}:00+08:00','controlled_finish':f'2026-10-18T{new_end}:00+08:00',
            'depends_on':deps,'release_gate':'approved_and_verified_before_ACT-01_ACT-02',
            'planned_status':'scheduled','actual_status':'not_started'})
    write_json('schedule.json', rows)
    with (OUT/'schedule.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer=csv.DictWriter(fh, fieldnames=['id','name','area_id','owner_id','baseline_start','baseline_finish','controlled_start','controlled_finish','origin'])
        writer.writeheader(); writer.writerows({k:r[k] for k in writer.fieldnames} for r in rows)
    evidence = [make_evidence('initial','初始隐患',False,False,False,False,1),
                make_evidence('incomplete','首轮整改但挡脚板缺失',True,False,True,True,2),
                make_evidence('pass','整改完成待复核',True,True,True,True,3),
                make_evidence('changed','关闭后防护被移除',False,False,True,True,4),
                make_evidence('pass_v2','重开后重新整改完成',True,True,True,True,5)]
    write_json('evidence.json', evidence)
    pdf = OUT/'sources/GB55034-2022.pdf'
    rules = []
    for clause,page,text,tags in [
        ('3.1.2',6,'应在主要施工部位、作业点、危险区域和主要通道等位置设置相应安全标志。',['警示','通道']),
        ('3.1.3',6,'安全问题和隐患的整改应明确责任人、整改时间和整改措施。',['责任人','期限','整改']),
        ('3.2.1',6,'在坠落高度基准面2m及以上的高处进行施工作业，应按规定采取安全防护措施。',['高处','防护']),
        ('3.2.2',6,'应合理安排作业顺序；存在安全风险的多工种垂直交叉作业应设置上下层间防护，不得无防护进行多层垂直作业。',['交叉作业','作业顺序']),
        ('3.2.3',6,'施工预留洞口、通道口等孔洞以及相关临边应采取安全防护措施，防护设施不得随意拆除。',['洞口','临边','拆除']),
        ('3.3.3',7,'物料平台堆放应控制在承载能力范围，堆放高度不得影响稳定性。',['材料','堆放'])]:
        rules.append({'id':f'GB-{clause}', 'origin':'official_standard_paraphrase','title':f'GB 55034—2022 第{clause}条',
            'text':text,'tags':tags,'source_path':'sources/GB55034-2022.pdf','source_page':page,
            'source_url':'https://www.mohurd.gov.cn/file/2022/20221117/cf9bdbb5-5423-4e81-accf-e636ddfc2615.pdf',
            'effective_from':'2023-06-01','applicability':'2026年中国规则演示场景，不用于判断2019年荷兰现场法律合规',
            'transcription':'human_visual_checked_paraphrase_of_scanned_pdf', 'source_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()})
    for rid,title,text,tags in [
        ('PR-01','演示风险矩阵','采用严重度S与可能性L各1至5级，分值S×L；1至5低、6至11中、12至19高、20至25极高。高及极高风险隔离停工，提交人工审批。此分级为演示项目自定。',['风险','矩阵']),
        ('PR-02','洞口防护验收','OPEN-01本演示验收要求：栏杆连续完整，顶部高度不低于1.20m；挡脚板完整且不低于0.18m；安全网完整；替代通道避开0.50m危险缓冲区。尺寸为项目自定验收值，非本数据包对国家条文数值的转录。',['洞口','栏杆','挡脚板','验收']),
        ('PR-03','审批与责任','控制方案绑定Case及版本。王经理审批；陈工分派；李班长执行；周工调整工序；赵安全员独立复核。未批准禁止实施。脚本审批仅为演示事件，不代表现实授权。',['审批','责任','授权']),
        ('PR-04','复核与重开','执行人提交证据后由独立复核人逐项检查。任一必检项不通过不得关闭。关闭后防护变化即重开并增加版本，旧审批、实施证据、复核结论失效，重新审批实施复核。',['复核','重开','版本'])]:
        rules.append({'id':rid,'origin':'authored_demo_project_rule','title':title,'text':text,'tags':tags,
                      'source_path':'documents/项目演示规则.md','source_page':None})
    write_json('rules.json', rules)
    risks = [
        {'id':'RISK-01','title':'无完整防护的洞口存在坠落风险','severity':5,'likelihood':3,'rule_ids':['GB-3.2.1','GB-3.2.3','PR-02'],'control_ids':['CTRL-01','CTRL-02'],'residual_likelihood':1},
        {'id':'RISK-02','title':'材料通道与洞口危险缓冲区冲突','severity':4,'likelihood':3,'rule_ids':['GB-3.1.2','PR-02'],'control_ids':['CTRL-01','CTRL-03'],'residual_likelihood':1},
        {'id':'RISK-03','title':'同区域作业时段重叠需协调','severity':3,'likelihood':4,'rule_ids':['PR-03'],'control_ids':['CTRL-03','CTRL-04'],'residual_likelihood':1}]
    # No unsupported vertical multi-level conflict: this scene only proves same-area temporal overlap.
    for r in risks:
        r.update({'case_id':CASE,'area_id':'AREA-L4-A','opening_id':'OPEN-01','evidence_ids':['EV-01'],
                  'origin':'authored_demo','score':r['severity']*r['likelihood'],
                  'residual_score':r['severity']*r['residual_likelihood'],
                  'residual_basis':'conditional_estimate_only_until_all_controls_verified'})
    write_json('risks.json', risks)
    controls = [
        ('CTRL-01','隔离危险区并设置警示','foreman','08:45','危险区封闭，禁止通行和相关作业'),
        ('CTRL-02','安装并检查栏杆挡脚板及安全网','foreman','09:30','满足PR-02全部检查项'),
        ('CTRL-03','调整通道并错开机电与周转作业','mep_lead','09:30','采用替代路线和受控计划'),
        ('CTRL-04','交底并移交复核','foreman','09:30','班组签收交底且提交检查证据')]
    write_json('controls.json', [{'id':cid,'case_id':CASE,'area_id':'AREA-L4-A','title':title,
        'owner_id':owner,'deadline':f'2026-10-18T{deadline}:00+08:00','acceptance':acc,
        'verifier_id':'inspector','origin':'authored_demo','required_evidence':['diagram','checklist','work_log']}
        for cid,title,owner,deadline,acc in controls])
    write_json('briefings.json', [{'id':f'BRIEF-{rev:02d}','case_id':CASE,'revision':rev,
        'origin':'scripted_demo','at':f'2026-10-18T{time}:00+08:00','leader_id':'inspector',
        'document_path':'documents/班前安全交底.md','acknowledged_actor_ids':['foreman','mep_lead'],
        'acknowledgement_type':'scripted_demo_not_real_signature',
        'topics':['危险区隔离','洞口防护','替代通道','错峰作业','禁止擅拆','复核前禁止恢复作业']}
        for rev,time in [(1,'08:32'),(2,'11:22')]])
    write_json('schedule_revisions.json', [{'revision':1,'schedule_path':'schedule.json'},
        {'revision':2,'origin':'authored_demo','reason':'11:00巡查发现防护变化，禁止后续进入，重新隔离整改复核',
         'intervals':[{'activity_id':'ACT-03','start':'2026-10-18T11:25:00+08:00','finish':'2026-10-18T12:10:00+08:00'},
                      {'activity_id':'ACT-04','start':'2026-10-18T12:15:00+08:00','finish':'2026-10-18T12:25:00+08:00'}],
         'area_access_until_closed':'blocked','original_ACT01_ACT02':'historical_first_cycle_do_not_rewrite'}])
    write_json('control_revisions.json', [{'revision':1,'controls_path':'controls.json'},
        {'revision':2,'origin':'authored_demo','control_updates':[
            {'control_id':cid,'deadline':f'2026-10-18T{time}:00+08:00','scope':scope}
            for cid,time,scope in [('CTRL-01','11:35','重新隔离并警示'),('CTRL-02','12:10','重新恢复完整防护'),
                                  ('CTRL-03','12:10','确认原改线仍有效，后续进入保持禁止'),('CTRL-04','12:10','重新交底并提交本轮证据')]]}])
    write_json('risk_assessments.json', [{'revision':rev,'case_id':CASE,'origin':'authored_demo',
        'evidence_id':eid,'assessments':[
            {'risk_id':'RISK-01','status':'active','score':15},
            {'risk_id':'RISK-02','status':'active' if rev==1 else 'controlled','score':12 if rev==1 else 4},
            {'risk_id':'RISK-03','status':'active' if rev==1 else 'not_currently_applicable','score':12 if rev==1 else None}],
        'basis':'首轮同区并行活动' if rev==1 else '防护移除造成坠落风险重现；路线仍分离，原机电与材料计划已结束，不沿用原重叠判断'}
        for rev,eid in [(1,'EV-01'),(2,'EV-04')]])
    case = {'id':CASE,'title':'四层A区机电预留洞口与材料周转安全协同', 'origin':'authored_demo_on_real_s1',
        'project_id':'DEMO-S1','area_id':'AREA-L4-A','revision':1,'status':'DRAFT',
        'created_at':'2026-10-18T08:10:00+08:00','request':'检查四层A区洞口防护与并行作业，形成控制方案，经人工批准后整改并独立复核。',
        'initial_evidence_id':'EV-01','activity_ids':[x['id'] for x in rows],
        'source_task_reference':'ST00340','historical_source_period':'2019-05-22/2019-06-03',
        'scenario_period':'2026-10-18','approvals':[], 'implementation_records':[],
        'live_mode_initial_state':'DRAFT_no_human_approval',
        'provenance_notice':'S1原件为真实历史输入；洞口、作业计划、方案、人员、风险标注、审批和整改记录为可控演示补编。'}
    write_json('case.json', case)
    docs = OUT/'documents'; docs.mkdir(exist_ok=True)
    rule_md = '# 项目演示规则\n\n适用 Case：DEMO-S1-001。以下 PR 条款为本演示项目自定。\n\n'
    rule_md += '\n\n'.join(f"## {r['id']} {r['title']}\n\n{r['text']}" for r in rules if r['id'].startswith('PR'))
    (docs/'项目演示规则.md').write_text(rule_md+'\n', encoding='utf-8')
    official = '# 规范摘编与来源\n\nGB 55034—2022，自2023年6月1日实施。适用于本2026年中国规则演示设定。原PDF为扫描件，以下为逐条目视核对后的释义，页码为PDF物理页码。\n\n'
    official += '\n\n'.join(f"## {r['title']}\n\n{r['text']}\n\n来源：PDF第{r['source_page']}页，{r['source_url']}" for r in rules if r['id'].startswith('GB'))
    (docs/'规范摘编与来源.md').write_text(official+'\n', encoding='utf-8')
    write_json('provenance.json', {'case_id':CASE,'real_inputs':'source_assets.json',
        'authored_inputs':['case.json','actors.json','geometry.json (除bim_anchor)','schedule.json','evidence.json','risks.json','controls.json','documents','scenarios.json'],
        'normative_source':'GB55034-2022 official PDF; clauses visually checked; project thresholds separate',
        'licensing':'保留S1来源与原仓库说明；公开展示前按原数据提供方条款核对。未将下载行为等同于任意再分发许可。',
        'time_policy':'2019真实照片时间无时区不转换；2026演示事件统一+08:00；上传时间不得代替拍摄时间。',
        'spatial_policy':'真实楼板代理作坐标锚点，演示洞口和路线为局部坐标叠加，未进行照片像素到BIM精确配准。',
        'approval_policy':'预置回放全部scripted_demo；实时Case无预置批准，后续Web须由操作者主动点击审批。'})
    print(json.dumps({'output':str(OUT),'source_assets':len(chosen),'evidence':len(evidence),'rules':len(rules),'risks':len(risks)},ensure_ascii=False))


if __name__ == '__main__':
    main()
