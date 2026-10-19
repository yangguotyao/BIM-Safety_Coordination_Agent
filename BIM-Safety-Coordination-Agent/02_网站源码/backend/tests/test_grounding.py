import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import connect, reset_db
from app import tools

client = TestClient(app)
OTHER_GUID = '0BGfqjCPX70uXXKLeh5fKj'


@pytest.fixture(scope='module', autouse=True)
def seeded_database():
    reset_db()


def test_unknown_geometry_is_not_another_elements_bbox():
    element = client.get(f'/api/models/S1-bSDD-example/elements/{OTHER_GUID}').json()['element']
    assert element['geometry_available'] is False
    assert element['bbox_m'] is None


def test_rules_are_not_effective_before_their_start_date():
    conn = connect()
    try:
        result = tools.rule_retrieval(conn, '临边 栏杆 防护', '1900-01-01T09:00:00+08:00')
        assert result['data']['results'] == []
    finally:
        conn.close()


def test_wrong_element_evidence_does_not_match(monkeypatch):
    conn = connect()
    try:
        evidence = tools.get_evidence(conn, 'EV-001')
        case = {'case_id':'isolated', 'project_id':evidence['project_id'], 'model_id':evidence['model_id'],
                'model_version':evidence['model_version'], 'zone_id':evidence['zone_id'],
                'task_id':'TASK-S1-001', 'bim_guids':evidence['bim_guids'], 'evidence_ids':['EV-001']}
        wrong = {**copy.deepcopy(evidence), 'bim_guids':[OTHER_GUID]}
        monkeypatch.setattr(tools, 'get_evidence', lambda *_: wrong)
        result = tools.evidence_check(conn, case)
        assert result['data']['matched'] is False
        assert result['data']['records'][0]['checks']['guid_match'] is False
    finally:
        conn.close()
