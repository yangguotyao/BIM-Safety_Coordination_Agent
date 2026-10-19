import io
import json
import zipfile
import xml.etree.ElementTree as ET

import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import reset_db
from test_api import analyze

client=TestClient(app)


@pytest.fixture(autouse=True)
def isolated():
    reset_db()


def test_word_report_is_real_docx_and_keeps_case_evidence():
    case=client.post('/api/cases',json={'title':'05层检查 & 复核报告','evidence_ids':['EV-001']}).json()['case']
    case=analyze(case['case_id'])
    response=client.get(f"/api/cases/{case['case_id']}/export?format=docx")
    assert response.status_code==200,response.text
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert '.docx' in response.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for name in ['[Content_Types].xml','word/document.xml','word/styles.xml','word/footer1.xml']:
            ET.fromstring(z.read(name))
        text=''.join(ET.fromstring(z.read('word/document.xml')).itertext())
    assert '05层检查 & 复核报告' in text
    assert case['case_id'] in text and 'EV-001' in text
    assert case['bim_guids'][0] in text
    assert '整改措施' in text and '复核' in text


def test_stream_unknown_run_is_404():
    assert client.get('/api/runs/UNKNOWN/stream').status_code==404


def test_task_can_start_before_evidence_and_cannot_be_approved():
    case=client.post('/api/cases',json={'evidence_ids':[],'request_text':'全面检查L05楼板安全，列出需补充的现场依据。'}).json()['case']
    case=analyze(case['case_id'])
    assert case['status']=='needs_evidence'
    assert case['evidence_ids']==[] and case['controls']==[]
    assert case['safety_state']['incomplete'] is True
    assert client.post(f"/api/cases/{case['case_id']}/review",json={'decision':'approve'}).status_code==409


def test_completed_run_stream_finishes_and_replays_validated_output():
    from app.run_stream import publish
    case=analyze(client.post('/api/cases',json={}).json()['case']['case_id'])
    publish(case['last_run_id'],'已校核的检查结论','validated')
    response=client.get(f"/api/runs/{case['last_run_id']}/stream")
    assert response.status_code==200
    assert 'text/event-stream' in response.headers['content-type']
    assert '已校核的检查结论' in response.text
    assert '"status": "validated"' in response.text
    assert 'event: complete' in response.text


@pytest.mark.parametrize('broken',[False,True])
def test_real_stream_chunks_are_candidates_until_grounding_passes(monkeypatch,broken):
    from app import live_model,model_client,run_stream
    case=analyze(client.post('/api/cases',json={}).json()['case']['case_id'])
    snapshots=[];original=run_stream.publish;client_class=httpx.Client
    def publish(run_id,text,status):
        snapshots.append((text,status));original(run_id,text,status)
    monkeypatch.setattr(run_stream,'publish',publish)
    result={'summary':'已读取现场证据，等待人工审核。','reasoning_basis':[{'type':'evidence','id':'WRONG' if broken else 'EV-001'}],'uncertainties':[]}
    raw=json.dumps(result,ensure_ascii=False)
    def provider(request):
        payload=json.loads(request.content)
        assert payload['stream'] is True
        packets=[{'choices':[{'delta':{'content':raw[i:i+7]}}]} for i in range(0,len(raw),7)]
        packets.append({'choices':[],'usage':{'total_tokens':42}})
        data=''.join('data: '+json.dumps(p,ensure_ascii=False)+'\n\n' for p in packets)+'data: [DONE]\n\n'
        return httpx.Response(200,headers={'content-type':'text/event-stream'},text=data)
    monkeypatch.setattr(model_client.httpx,'Client',lambda **kw:client_class(transport=httpx.MockTransport(provider),**kw))
    for key,value in [('MODEL_BASE_URL','https://mock.invalid/v1'),('MODEL_API_KEY','test-key'),('MODEL_NAME','test-model')]:
        monkeypatch.setattr(live_model,key,value)
    token=model_client.CURRENT_RUN.set(case['last_run_id'])
    try:
        context={'case_id':case['case_id'],'allowed_evidence_ids':['EV-001']}
        if broken:
            with pytest.raises(live_model.LiveModelError):live_model.live_narrative(context)
        else:
            assert live_model.live_narrative(context)['summary']==result['summary']
    finally:model_client.CURRENT_RUN.reset(token)
    assert any(0<len(text)<len(result['summary']) and state=='generating' for text,state in snapshots)
    assert snapshots[-1][1]==('rejected' if broken else 'validated')
    if broken: assert snapshots[-1][0]==''
