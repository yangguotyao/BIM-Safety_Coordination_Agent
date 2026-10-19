"""Portable Word reports using OOXML; no Office or extra runtime dependency.

固定文案按语言分支；案例动态文本由 services.export_case 在调用前完成翻译投影。
"""
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape

NS='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
STATUS_ZH={'draft':'待检查','analyzing':'分析中','needs_evidence':'待补充资料','pending_review':'待审核','approved':'待整改',
        'rectifying':'整改中','pending_verification':'待复核','closed':'已关闭','reopened':'重新处理','rejected':'未批准',
        'risk_candidate':'风险候选','no_issue_in_checked_items':'已检查项无问题','pass_in_demo_scope':'复核通过','fail':'未通过','pass':'通过','unknown':'未知'}
STATUS_EN={'draft':'Draft','analyzing':'Analyzing','needs_evidence':'Evidence Required','pending_review':'Pending Review','approved':'Pending Rectification',
        'rectifying':'Under Rectification','pending_verification':'Pending Verification','closed':'Closed','reopened':'Reopened','rejected':'Rejected',
        'risk_candidate':'Risk Candidate','no_issue_in_checked_items':'No issue in checked items','pass_in_demo_scope':'Passed within demo scope','fail':'Failed','pass':'Passed','unknown':'Unknown'}
STATUS={'zh':STATUS_ZH,'en':STATUS_EN}


def text(value):
    return escape('' if value is None else str(value))


def p(value,style=None,center=False):
    props=f'<w:pStyle w:val="{style}"/>' if style else ''
    if center:props+='<w:jc w:val="center"/>'
    return f'<w:p><w:pPr>{props}</w:pPr><w:r><w:t xml:space="preserve">{text(value)}</w:t></w:r></w:p>'


def table(headers,rows,widths=(2600,6760)):
    result=['<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>']
    result.extend(f'<w:{side} w:val="single" w:sz="5" w:color="D9D9D9"/>' for side in ['top','left','bottom','right','insideH','insideV'])
    result.append('</w:tblBorders><w:tblCellMar><w:top w:w="100" w:type="dxa"/><w:bottom w:w="100" w:type="dxa"/><w:left w:w="130" w:type="dxa"/><w:right w:w="130" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>')
    result.extend(f'<w:gridCol w:w="{width}"/>' for width in widths);result.append('</w:tblGrid>')
    for index,row in enumerate([headers]+rows):
        result.append('<w:tr>'+('<w:trPr><w:tblHeader/></w:trPr>' if index==0 else ''))
        for width,value in zip(widths,row):
            fill='233F5D' if index==0 else 'F3F6F9' if index%2==0 else 'FFFFFF'
            result.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:shd w:fill="{fill}"/><w:vAlign w:val="center"/></w:tcPr>')
            style='TableHeader' if index==0 else 'TableText'
            result.append(p(value,style,center=width<=2000));result.append('</w:tc>')
        result.append('</w:tr>')
    result.append('</w:tbl>');result.append(p('','TableText'))
    return ''.join(result)


def label(value,lang='zh'):return STATUS.get(lang,STATUS_ZH).get(value,value or ('未记录' if lang!='en' else 'Not recorded'))


def report(bundle,lang='zh'):
    en = lang == 'en'

    def L(zh,en_text=None):
        if not en:return zh
        return en_text if en_text is not None else zh

    case=bundle['case'];context=bundle.get('context') or {};task=context.get('task') or {};zone=context.get('zone') or {}
    parts=[p(L('BIM 施工安全检查报告','BIM Construction Safety Inspection Report'),'Title'),p(case['title'],'Subtitle'),
        p(L('本报告汇总本次检查的对象、分析依据、整改措施与复核记录。结论仅适用于本案列明的检查项。',
            'This report consolidates the inspection target, analysis basis, control measures and verification records. '
            'The conclusion applies only to the check items listed in this case.')),
        table([L('报告信息','Report Information'),L('内容','Content')],
            [[L('案例编号','Case ID'),case['case_id']],[L('当前状态','Current Status'),label(case['status'],lang)],
             [L('检查时刻','Inspection Time'),case['as_of']],
            [L('模型及版本','Model and Version'),f"{case['model_id']} / {case['model_version']}"],
            [L('检查范围','Inspection Scope'),zone.get('storey_name',case['zone_id'])],
            [L('任务描述','Task Description'),case.get('request_text') or task.get('activity')]])]
    verification=case.get('verification') or {};review=case.get('review') or {};implementation=case.get('implementation') or {}
    parts.append(p(L('检查结论','Inspection Conclusion'),'Heading1'))
    if verification:
        parts.extend([p(f"{L('复核结果：','Verification result: ')}{label(verification.get('result'),lang)}。{L('复核时刻：','Verified at: ')}{verification.get('verified_at',L('未记录','Not recorded'))}。"),p(verification.get('remaining_risk',''))])
    elif case['status']=='closed':parts.append(p(L('本次已检查项经人工确认后关闭，无需整改。',
            'All checked items were confirmed by a human reviewer and the case was closed without rectification.')))
    else:parts.append(p(L(f"本案当前为{label(case['status'])}，尚未形成最终复核关闭记录。",
            f"This case is currently {label(case['status'],'en')} and has no final verification closure record.")))
    parts.append(p(L('检查对象与规范依据','Inspection Target and Regulatory Basis'),'Heading1'))
    scope=case.get('scope') or zone.get('data') or {}
    parts.append(table([L('项目','Item'),L('记录','Record')],
        [[L('施工活动','Construction Activity'),task.get('activity')],[L('责任主体','Responsible Party'),task.get('owner')],
        [L('构件 GUID','Element GUID'),'；'.join(case['bim_guids']) if not en else '; '.join(case['bim_guids'])],
        [L('人员点来源','Worker Point Source'),scope.get('worker_point_provenance',L('人工模拟标注','Simulated annotation'))],
        [L('距标注边线','Distance to annotated edge'),f"{(bundle.get('spatial') or {}).get('data',{}).get('distance_m',L('未知','Unknown'))} m"]]))
    for rule in bundle.get('rules',[]):
        parts.append(p(f"{rule.get('standard','')} {rule.get('clause','')}  {rule.get('rule_id','')}",'Heading2'))
        parts.append(p(rule.get('text','')))
        parts.append(p(L(f"来源页码：{rule.get('pdf_page','未记录')}；生效日期：{rule.get('effective_from','未记录')}。",
            f"Source page: {rule.get('pdf_page','Not recorded')}; effective from: {rule.get('effective_from','Not recorded')}."),'Secondary'))
    parts.append(p(L('分析时问题与检查项','Findings and Check Items at Analysis'),'Heading1'))
    for finding in case['findings']:
        parts.append(p(f"{finding['finding_id']}  {finding['hazard']}",'Heading2'))
        evidence_text='；'.join(finding.get('evidence_ids') or []) if not en else '; '.join(finding.get('evidence_ids') or [])
        parts.append(p(f"{L('分析时结果：','Analysis result: ')}{label(finding['result'],lang)}。{L('证据：','Evidence: ')}{evidence_text or L('活动计划数据','activity plan data')}。"))
        narrative=finding.get('narrative') or {}
        if narrative.get('summary'):parts.append(p(narrative['summary']))
        if finding.get('checks'):parts.append(table([L('检查项','Check Item'),L('分析时结果','Analysis Result')],
            [[c['name'],label(c['result'],lang)] for c in finding['checks']],widths=(7600,1760)))
    parts.append(p(L('整改措施与人工审核','Control Measures and Human Review'),'Heading1'))
    for control in case['controls']:
        parts.append(p(f"{control['control_id']}  {L('版本','Version')} {control.get('version',1)}",'Heading2'))
        parts.extend([p(control['action']),p(f"{L('责任主体：','Responsible party: ')}{control['owner']}。"),
            p(L('验收要求：','Verification requirements: ')+('；'.join(control.get('verification_requirements') or []) if not en else '; '.join(control.get('verification_requirements') or [])))])
    if not case['controls']:parts.append(p(L('本次没有待执行的整改措施。','No control measures are pending in this case.')))
    reviewer=verification.get('reviewer') or next((e['actor'] for e in reversed(bundle.get('events',[])) if e['event'] in {'verification_passed','verification_failed'}),L('未记录','Not recorded'))
    parts.append(table([L('流程记录','Process Record'),L('内容','Content')],
        [[L('审核','Review'),f"{review.get('reviewer',L('未记录','Not recorded'))} / {review.get('reviewed_at',L('未记录','Not recorded'))} / {review.get('comment','')}"],
        [L('隐患整改','Rectification'),f"{implementation.get('owner',L('未记录','Not recorded'))} / {implementation.get('implemented_at',L('未记录','Not recorded'))} / {implementation.get('comment','')}"],
        [L('复核','Verification'),f"{reviewer} / {verification.get('verified_at',L('未记录','Not recorded'))} / {label(verification.get('result'),lang)}"]]))
    if verification.get('checks'):
        rename=lambda name:name.replace('已记录人工实施','整改记录已提交').replace('人工实施时刻','整改完成时刻') if not en else name
        parts.append(table([L('复核项目','Verification Item'),L('结果','Result')],
            [[rename(c['name']),label(c['result'],lang)] for c in verification['checks']],widths=(7600,1760)))
    parts.append(p(L('现场证据与观察来源','Site Evidence and Observation Sources'),'Heading1'))
    for item in bundle.get('evidence',[]):
        stage_text=(L('整改后','Post-rectification') if item['stage']=='after' else L('检查时','At inspection'))
        parts.append(p(f"{item['evidence_id']}  {stage_text} {L('资料','material')}",'Heading2'))
        parts.append(p(L(f"记录时刻：{item['captured_at']}。来源：{item.get('provenance','未记录')}。",
            f"Recorded at: {item['captured_at']}. Source: {item.get('provenance','Not recorded')}.")))
        parts.append(p(item.get('label','')))
        perception=item.get('perception') or {}
        if perception.get('summary'):parts.append(p(f"{L('图像候选','Image candidate')}（{perception.get('model','')}）：{perception['summary']}"))
        if perception.get('human_note'):parts.append(p(L('人工核对说明：','Human review note: ')+perception['human_note']))
        obs=item.get('observation') or {}
        fields={'guardrail_state':L('防护状态','Guardrail state'),'guardrail_height_m':L('防护高度 m','Guardrail height (m)'),
                'worker_present':L('人员在场','Worker present'),'drop_height_m':L('坠落高度 m','Drop height (m)'),
                'guardrail_fixed':L('防护固定','Guardrail fixed'),'guardrail_continuous':L('防护连续','Guardrail continuous')}
        def value(v):
            if v is None:return L('未知','Unknown')
            if v is True:return L('是','Yes')
            if v is False:return L('否','No')
            return {'present':L('已设置','Set'),'absent':L('未设置','Not set'),'unknown':L('未知','Unknown')}.get(str(v),str(v))
        parts.append(table([L('观察项目','Observation Item'),L('确认值','Confirmed Value')],[[name,value(obs.get(key))] for key,name in fields.items()]))
    plan=bundle.get('activity_plan')
    if plan:
        parts.append(p(L('作业计划及版本','Activity Plan and Versions'),'Heading1'))
        conflicts=len((bundle.get('coordination') or {}).get('conflicts',[]))
        parts.append(p(L(f"当前计划 v{plan['revision']}，审批时计划 v{review.get('activity_plan_revision','未审批')}。当前计划冲突 {conflicts} 组。",
            f"Current plan v{plan['revision']}; plan at approval v{review.get('activity_plan_revision','not approved')}. Current conflicts: {conflicts}.")))
        for activity in plan['activities']:
            parts.append(p(f"{activity['task_id']}  {activity['activity']}",'Heading2'))
            parts.append(p(L(f"工种：{activity['trade']}；责任主体：{activity['owner']}。",f"Trade: {activity['trade']}; responsible party: {activity['owner']}.")))
            parts.append(p(L(f"作业时段：{activity['planned_start']} 至 {activity['planned_end']}。",f"Work window: {activity['planned_start']} to {activity['planned_end']}.")))
        for revision in reversed(plan['history']):parts.append(p(f"v{revision['revision']}  {revision['at']}  {revision['reason']}",'Secondary'))
    if bundle.get('site_notes'):
        parts.append(p(L('现场文本及人工澄清','Site Text and Human Clarification'),'Heading1'))
        for note in bundle['site_notes']:
            parts.append(p(f"{note['title']}  v{note['version']}",'Heading2'))
            parts.append(p(L(f"来源：{note['source']}；记录时刻：{note['captured_at']}。",f"Source: {note['source']}; recorded at: {note['captured_at']}.")))
            for paragraph in note['paragraphs']:parts.extend([p(paragraph['id'],'Secondary'),p(paragraph['text'])])
        for conflict in (bundle.get('site_text') or {}).get('conflicts',[]):
            parts.append(p(L('差异引用：','Discrepancy reference: ')+conflict['paragraph_id']))
            parts.append(p(L('原文：','Source text: ')+conflict['quote']))
            resolution=conflict.get('resolution') or {}
            parts.append(p(L('人工澄清：','Human clarification: ')+resolution.get('reason',L('尚未澄清','not yet clarified'))))
    parts.append(p(L('处置时间线','Disposition Timeline'),'Heading1'))
    event_names_zh={'case_created':'发起任务','analysis_started':'开始分析','analysis_completed':'分析完成','analysis_incomplete':'待补充资料','review_approved':'批准措施','implementation_recorded':'隐患整改','evidence_uploaded':'上传证据','verification_passed':'复核通过','activity_plan_adjusted':'调整计划','text_conflict_resolved':'澄清文本'}
    event_names_zh.update(scope_updated='更新范围标注',observation_confirmed='确认现场观察',activity_plan_updated='编制作业计划',site_note_added='保存现场文本',analysis_failed='分析未完成',site_text_extracted='提取文本候选')
    event_names_en={'case_created':'Case created','analysis_started':'Analysis started','analysis_completed':'Analysis completed','analysis_incomplete':'Evidence required','review_approved':'Measures approved','implementation_recorded':'Rectification recorded','evidence_uploaded':'Evidence uploaded','verification_passed':'Verification passed','activity_plan_adjusted':'Plan adjusted','text_conflict_resolved':'Text clarified'}
    event_names_en.update(scope_updated='Scope annotation updated',observation_confirmed='Site observation confirmed',activity_plan_updated='Activity plan created',site_note_added='Site note saved',analysis_failed='Analysis incomplete',site_text_extracted='Text candidates extracted')
    event_names=event_names_en if en else event_names_zh
    for event in bundle.get('events',[]):parts.append(p(f"{event['at']}  {event_names.get(event['event'],event['event'])}  {event['actor']}",'Secondary'))
    parts.append(p(L('数据来源与适用边界','Data Sources and Applicable Boundaries'),'Heading1'))
    for assumption in case.get('assumptions',[]):parts.append(p(assumption))
    parts.append(p(L('IFC 几何与人工标注、图像候选、现场确认分别保留来源。演示输入与人工模拟记录不证明原项目实际施工状态；本报告不替代真实现场审批。',
        'IFC geometry, human annotations, image candidates and site confirmations retain their sources separately. '
        'Demonstrative inputs and simulated human records do not prove the actual construction state of the original project; '
        'this report does not replace real site approval.')))
    styles=f'''<w:styles xmlns:w="{NS}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'''
    for name,size,color,bold,after,before in [('Normal',22,'1F2937',False,100,0),('Title',36,'000000',True,180,0),('Subtitle',24,'475569',False,220,0),('Heading1',28,'183B56',True,140,220),('Heading2',23,'243F55',True,100,150),('Secondary',20,'526171',False,80,0),('TableText',21,'1F2937',False,20,0),('TableHeader',21,'FFFFFF',True,20,0)]:
        keep='<w:keepNext/>' if name in ['Title','Subtitle','Heading1','Heading2'] else ''
        styles+=f'<w:style w:type="paragraph" w:styleId="{name}"><w:name w:val="{name}"/><w:pPr>{keep}<w:spacing w:after="{after}" w:before="{before}"/></w:pPr><w:rPr><w:sz w:val="{size}"/><w:color w:val="{color}"/>'+('<w:b/>' if bold else '')+'</w:rPr></w:style>'
    styles+='</w:styles>'
    section='<w:sectPr><w:footerReference w:type="default" r:id="rId2"/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1200" w:right="1440" w:bottom="1200" w:left="1440" w:footer="550"/></w:sectPr>'
    document=f'<w:document xmlns:w="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'+''.join(parts)+section+'</w:body></w:document>'
    footer=f'<w:ftr xmlns:w="{NS}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>{text(case["case_id"])}　 {L("第","Page ")} </w:t></w:r><w:fldSimple w:instr="PAGE"/><w:r><w:t> {L("页","")}</w:t></w:r></w:p></w:ftr>'
    content_types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(f'<Override PartName="/word/{part}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>' for part,kind in [('document','document.main'),('styles','styles'),('footer1','footer')])+'</Types>'
    relationships='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for name,body in {'[Content_Types].xml':content_types,'_rels/.rels':relationships+'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            'word/document.xml':document,'word/styles.xml':styles,'word/footer1.xml':footer,
            'word/_rels/document.xml.rels':relationships+'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>'}.items():z.writestr(name,'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+body)
    return output.getvalue()
