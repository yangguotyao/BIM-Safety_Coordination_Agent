"""Portable Word reports using OOXML; no Office or extra runtime dependency."""
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.sax.saxutils import escape

NS='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
STATUS={'draft':'待检查','analyzing':'分析中','needs_evidence':'待补充资料','pending_review':'待审核','approved':'待整改',
        'rectifying':'整改中','pending_verification':'待复核','closed':'已关闭','reopened':'重新处理','rejected':'未批准',
        'risk_candidate':'风险候选','no_issue_in_checked_items':'已检查项无问题','pass_in_demo_scope':'复核通过','fail':'未通过','pass':'通过','unknown':'未知'}


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


def label(value):return STATUS.get(value,value or '未记录')


def report(bundle):
    case=bundle['case'];context=bundle.get('context') or {};task=context.get('task') or {};zone=context.get('zone') or {}
    parts=[p('BIM 施工安全检查报告','Title'),p(case['title'],'Subtitle'),
        p('本报告汇总本次检查的对象、分析依据、整改措施与复核记录。结论仅适用于本案列明的检查项。'),
        table(['报告信息','内容'],[['案例编号',case['case_id']],['当前状态',label(case['status'])],['检查时刻',case['as_of']],
            ['模型及版本',f"{case['model_id']} / {case['model_version']}"],['检查范围',zone.get('storey_name',case['zone_id'])],['任务描述',case.get('request_text') or task.get('activity')]])]
    verification=case.get('verification') or {};review=case.get('review') or {};implementation=case.get('implementation') or {}
    parts.append(p('检查结论','Heading1'))
    if verification:
        parts.extend([p(f"复核结果：{label(verification.get('result'))}。复核时刻：{verification.get('verified_at','未记录')}。"),p(verification.get('remaining_risk',''))])
    elif case['status']=='closed':parts.append(p('本次已检查项经人工确认后关闭，无需整改。'))
    else:parts.append(p(f"本案当前为{label(case['status'])}，尚未形成最终复核关闭记录。"))
    parts.append(p('检查对象与规范依据','Heading1'))
    scope=case.get('scope') or zone.get('data') or {}
    parts.append(table(['项目','记录'],[['施工活动',task.get('activity')],['责任主体',task.get('owner')],
        ['构件 GUID','；'.join(case['bim_guids'])],['人员点来源',scope.get('worker_point_provenance','人工模拟标注')],
        ['距标注边线',f"{(bundle.get('spatial') or {}).get('data',{}).get('distance_m','未知')} m"]]))
    for rule in bundle.get('rules',[]):
        parts.append(p(f"{rule.get('standard','')} {rule.get('clause','')}  {rule.get('rule_id','')}",'Heading2'))
        parts.append(p(rule.get('text','')))
        parts.append(p(f"来源页码：{rule.get('pdf_page','未记录')}；生效日期：{rule.get('effective_from','未记录')}。",'Secondary'))
    parts.append(p('分析时问题与检查项','Heading1'))
    for finding in case['findings']:
        parts.append(p(f"{finding['finding_id']}  {finding['hazard']}",'Heading2'))
        parts.append(p(f"分析时结果：{label(finding['result'])}。证据：{'、'.join(finding.get('evidence_ids') or []) or '活动计划数据'}。"))
        narrative=finding.get('narrative') or {}
        if narrative.get('summary'):parts.append(p(narrative['summary']))
        if finding.get('checks'):parts.append(table(['检查项','分析时结果'],[[c['name'],label(c['result'])] for c in finding['checks']],widths=(7600,1760)))
    parts.append(p('整改措施与人工审核','Heading1'))
    for control in case['controls']:
        parts.append(p(f"{control['control_id']}  版本 {control.get('version',1)}",'Heading2'))
        parts.extend([p(control['action']),p(f"责任主体：{control['owner']}。"),p('验收要求：'+'；'.join(control.get('verification_requirements') or []))])
    if not case['controls']:parts.append(p('本次没有待执行的整改措施。'))
    reviewer=verification.get('reviewer') or next((e['actor'] for e in reversed(bundle.get('events',[])) if e['event'] in {'verification_passed','verification_failed'}),'未记录')
    parts.append(table(['流程记录','内容'],[['审核',f"{review.get('reviewer','未记录')} / {review.get('reviewed_at','未记录')} / {review.get('comment','')}"],
        ['隐患整改',f"{implementation.get('owner','未记录')} / {implementation.get('implemented_at','未记录')} / {implementation.get('comment','')}"],
        ['复核',f"{reviewer} / {verification.get('verified_at','未记录')} / {label(verification.get('result'))}"]]))
    if verification.get('checks'):parts.append(table(['复核项目','结果'],[[c['name'].replace('已记录人工实施','整改记录已提交').replace('人工实施时刻','整改完成时刻'),label(c['result'])] for c in verification['checks']],widths=(7600,1760)))
    parts.append(p('现场证据与观察来源','Heading1'))
    for item in bundle.get('evidence',[]):
        parts.append(p(f"{item['evidence_id']}  {'整改后' if item['stage']=='after' else '检查时'}资料",'Heading2'))
        parts.append(p(f"记录时刻：{item['captured_at']}。来源：{item.get('provenance','未记录')}。"))
        parts.append(p(item.get('label','')))
        perception=item.get('perception') or {}
        if perception.get('summary'):parts.append(p(f"图像候选（{perception.get('model','')}）：{perception['summary']}"))
        if perception.get('human_note'):parts.append(p('人工核对说明：'+perception['human_note']))
        obs=item.get('observation') or {}
        fields={'guardrail_state':'防护状态','guardrail_height_m':'防护高度 m','worker_present':'人员在场','drop_height_m':'坠落高度 m','guardrail_fixed':'防护固定','guardrail_continuous':'防护连续'}
        def value(v):return '未知' if v is None else '是' if v is True else '否' if v is False else {'present':'已设置','absent':'未设置','unknown':'未知'}.get(str(v),str(v))
        parts.append(table(['观察项目','确认值'],[[name,value(obs.get(key))] for key,name in fields.items()]))
    plan=bundle.get('activity_plan')
    if plan:
        parts.append(p('作业计划及版本','Heading1'))
        parts.append(p(f"当前计划 v{plan['revision']}，审批时计划 v{review.get('activity_plan_revision','未审批')}。当前计划冲突 {len((bundle.get('coordination') or {}).get('conflicts',[]))} 组。"))
        for activity in plan['activities']:
            parts.append(p(f"{activity['task_id']}  {activity['activity']}",'Heading2'))
            parts.append(p(f"工种：{activity['trade']}；责任主体：{activity['owner']}。"))
            parts.append(p(f"作业时段：{activity['planned_start']} 至 {activity['planned_end']}。"))
        for revision in reversed(plan['history']):parts.append(p(f"v{revision['revision']}  {revision['at']}  {revision['reason']}",'Secondary'))
    if bundle.get('site_notes'):
        parts.append(p('现场文本及人工澄清','Heading1'))
        for note in bundle['site_notes']:
            parts.append(p(f"{note['title']}  v{note['version']}",'Heading2'))
            parts.append(p(f"来源：{note['source']}；记录时刻：{note['captured_at']}。"))
            for paragraph in note['paragraphs']:parts.extend([p(paragraph['id'],'Secondary'),p(paragraph['text'])])
        for conflict in (bundle.get('site_text') or {}).get('conflicts',[]):
            parts.append(p('差异引用：'+conflict['paragraph_id']))
            parts.append(p('原文：'+conflict['quote']))
            resolution=conflict.get('resolution') or {}
            parts.append(p('人工澄清：'+resolution.get('reason','尚未澄清')))
    parts.append(p('处置时间线','Heading1'))
    event_names={'case_created':'发起任务','analysis_started':'开始分析','analysis_completed':'分析完成','analysis_incomplete':'待补充资料','review_approved':'批准措施','implementation_recorded':'隐患整改','evidence_uploaded':'上传证据','verification_passed':'复核通过','activity_plan_adjusted':'调整计划','text_conflict_resolved':'澄清文本'}
    event_names.update(scope_updated='更新范围标注',observation_confirmed='确认现场观察',activity_plan_updated='编制作业计划',site_note_added='保存现场文本',analysis_failed='分析未完成',site_text_extracted='提取文本候选')
    for event in bundle.get('events',[]):parts.append(p(f"{event['at']}  {event_names.get(event['event'],event['event'])}  {event['actor']}",'Secondary'))
    parts.append(p('数据来源与适用边界','Heading1'))
    for assumption in case.get('assumptions',[]):parts.append(p(assumption))
    parts.append(p('IFC 几何与人工标注、图像候选、现场确认分别保留来源。演示输入与人工模拟记录不证明原项目实际施工状态；本报告不替代真实现场审批。'))
    styles=f'''<w:styles xmlns:w="{NS}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="宋体"/><w:sz w:val="22"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'''
    for name,size,color,bold,after,before in [('Normal',22,'1F2937',False,100,0),('Title',36,'000000',True,180,0),('Subtitle',24,'475569',False,220,0),('Heading1',28,'183B56',True,140,220),('Heading2',23,'243F55',True,100,150),('Secondary',20,'526171',False,80,0),('TableText',21,'1F2937',False,20,0),('TableHeader',21,'FFFFFF',True,20,0)]:
        keep='<w:keepNext/>' if name in ['Title','Subtitle','Heading1','Heading2'] else ''
        styles+=f'<w:style w:type="paragraph" w:styleId="{name}"><w:name w:val="{name}"/><w:pPr>{keep}<w:spacing w:after="{after}" w:before="{before}"/></w:pPr><w:rPr><w:sz w:val="{size}"/><w:color w:val="{color}"/>'+('<w:b/>' if bold else '')+'</w:rPr></w:style>'
    styles+='</w:styles>'
    section='<w:sectPr><w:footerReference w:type="default" r:id="rId2"/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1200" w:right="1440" w:bottom="1200" w:left="1440" w:footer="550"/></w:sectPr>'
    document=f'<w:document xmlns:w="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'+''.join(parts)+section+'</w:body></w:document>'
    footer=f'<w:ftr xmlns:w="{NS}"><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>{text(case["case_id"])}　 第 </w:t></w:r><w:fldSimple w:instr="PAGE"/><w:r><w:t> 页</w:t></w:r></w:p></w:ftr>'
    content_types='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(f'<Override PartName="/word/{part}.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.{kind}+xml"/>' for part,kind in [('document','document.main'),('styles','styles'),('footer1','footer')])+'</Types>'
    relationships='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for name,body in {'[Content_Types].xml':content_types,'_rels/.rels':relationships+'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            'word/document.xml':document,'word/styles.xml':styles,'word/footer1.xml':footer,
            'word/_rels/document.xml.rels':relationships+'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>'}.items():z.writestr(name,'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+body)
    return output.getvalue()
