from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PACKAGE_ROOT = Path(__file__).resolve().parents[3]
TEST_RUNTIME = tempfile.mkdtemp(prefix="bim-safety-test-")
os.environ["RUNTIME_DIR"] = TEST_RUNTIME
os.environ["DATA_ROOT"] = str(PACKAGE_ROOT / "01_资料与依据")
os.environ["DEMO_MODE"] = "true"

from app.main import app  # noqa: E402
from app.db import reset_db  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def _clean_database():
    reset_db()
    yield


def create_case(evidence_ids: list[str], title: str = "pytest case") -> dict:
    response = client.post(
        "/api/cases",
        json={
            "title": title,
            "model_id": "S1-bSDD-example",
            "task_id": "TASK-S1-001",
            "zone_id": "ZONE-S1-L05-EDGE",
            "as_of": "2026-10-16T09:00:00+08:00",
            "evidence_ids": evidence_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["case"]


def analyze(case_id: str) -> dict:
    response = client.post(f"/api/cases/{case_id}/analyze")
    assert response.status_code == 202, response.text
    run_id = response.json()["run_id"]
    for _ in range(60):
        run = client.get(f"/api/runs/{run_id}").json()["run"]
        if run["status"] in {"succeeded", "failed"}:
            break
    assert run["status"] == "succeeded", run
    return client.get(f"/api/cases/{case_id}").json()["case"]


def test_health_and_demo_mode():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["mode"] == "demo"
    assert body["live_config_complete"] is False
    assert body["db"]["ok"] is True
    assert "api_key" not in str(body).lower()


def test_model_storeys_and_mesh():
    storeys = client.get("/api/models/S1-bSDD-example/storeys").json()
    assert storeys["total"] == 19
    assert any(item["name"].startswith("05 ") for item in storeys["rows"])
    mesh = client.get("/api/models/S1-bSDD-example/mesh?scope=target").json()
    assert len(mesh["meshes"]) == 35
    assert mesh["units"] == "m"
    assert mesh["target"]["guid"] == "0FOHK4aT910wgskSbVHn0U"
    assert len(mesh["zone"]["edge_segment_m"]) == 2


def test_elements_and_rules():
    elements = client.get(
        "/api/models/S1-bSDD-example/elements",
        params={"storey_guid": "1Vhy2b2Mj9FRewx9CZZoux", "limit": 10},
    ).json()
    assert elements["total"] == 1247
    assert len(elements["rows"]) == 10
    assert elements["loaded_scope"]["preview_meshes"] == 35

    rules = client.get("/api/rules", params={"q": "临边 防护 栏杆 坠落 高度 1.2m", "top_k": 3}).json()
    ids = [item["rule_id"] for item in rules["results"]]
    assert "GB-3.2.3" in ids
    assert "JGJ-4.3.1" in ids
    assert all(not rule_id.endswith("RETIRED") for rule_id in ids)

    retired = client.get("/api/rules", params={"q": "JGJ 4.1.1", "top_k": 3}).json()
    assert "JGJ-4.1.1-RETIRED" in retired["retired_excluded"]
    assert not any(item["rule_id"].endswith("RETIRED") for item in retired["results"])


def test_invalid_guid_returns_422_and_no_dangling_case():
    response = client.post(
        "/api/cases",
        json={
            "title": "invalid guid",
            "model_id": "S1-bSDD-example",
            "task_id": "TASK-S1-001",
            "zone_id": "ZONE-S1-L05-EDGE",
            "as_of": "2026-10-16T09:00:00+08:00",
            "evidence_ids": ["EV-001"],
            "bim_guids": ["NOT-A-REAL-GUID"],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "unknown_guid"
    assert "NOT-A-REAL-GUID" in body["error"]["message"]


def test_full_closed_loop_and_reopen():
    case = create_case(["EV-001"], "pytest full loop")
    case = analyze(case["case_id"])
    assert case["status"] == "pending_review"
    assert case["findings"][0]["result"] == "risk_candidate"

    review = client.post(
        f"/api/cases/{case['case_id']}/review",
        json={
            "decision": "approve",
            "reviewer": "演示安全员",
            "reviewed_at": "2026-10-16T09:10:00+08:00",
            "control_version": case["control_version"],
            "expected_case_version": case["version"],
            "comment": "pytest approve",
        },
    )
    assert review.status_code == 200, review.text
    case = review.json()["case"]
    assert case["status"] == "approved"

    implementation = client.post(
        f"/api/cases/{case['case_id']}/implementation",
        json={
            "owner": "演示机电班组",
            "implemented_at": "2026-10-16T09:20:00+08:00",
            "comment": "pytest implementation",
            "expected_case_version": case["version"],
        },
    )
    assert implementation.status_code == 200, implementation.text
    case = implementation.json()["case"]
    assert case["status"] == "rectifying"

    evidence = client.post(
        f"/api/cases/{case['case_id']}/evidence",
        json={"evidence_ids": ["EV-010"], "actor": "演示安全员"},
    )
    assert evidence.status_code == 200, evidence.text
    case = evidence.json()["case"]
    assert case["status"] == "pending_verification"

    verify = client.post(
        f"/api/cases/{case['case_id']}/verify",
        json={
            "after_evidence_ids": ["EV-010"],
            "reviewer": "演示安全员",
            "reviewer_confirmed": True,
            "as_of": "2026-10-16T09:40:00+08:00",
            "expected_case_version": case["version"],
        },
    )
    assert verify.status_code == 200, verify.text
    case = verify.json()["case"]
    assert case["status"] == "closed"
    assert case["verification"]["result"] == "pass_in_demo_scope"

    reopen = client.post(
        f"/api/cases/{case['case_id']}/reopen",
        json={
            "reason": "pytest condition change",
            "evidence_ids": ["EV-011"],
            "actor": "演示安全员",
        },
    )
    assert reopen.status_code == 200, reopen.text
    bundle = reopen.json()
    assert bundle["case"]["status"] == "reopened"
    events = [event["event"] for event in bundle["events"]]
    assert "verification_passed" in events
    assert "case_reopened" in events


def test_unauthorized_verify_returns_409():
    case = create_case(["EV-001"], "pytest unauthorized")
    case = analyze(case["case_id"])
    assert case["status"] == "pending_review"
    response = client.post(
        f"/api/cases/{case['case_id']}/verify",
        json={
            "after_evidence_ids": ["EV-010"],
            "reviewer": "演示安全员",
            "reviewer_confirmed": True,
            "as_of": "2026-10-16T09:40:00+08:00",
            "expected_case_version": case["version"],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transition_rejected"


def test_upload_rejects_unsupported_file():
    case = create_case(["EV-001"], "pytest upload")
    response = client.post(
        f"/api/cases/{case['case_id']}/evidence/upload",
        files={"file": ("malware.exe", b"not-an-image", "application/octet-stream")},
        data={"captured_at": "2026-10-16T09:30:00+08:00", "stage": "after"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_type"


def test_upload_rejects_fake_png_signature():
    case = create_case(["EV-001"], "pytest fake png")
    response = client.post(
        f"/api/cases/{case['case_id']}/evidence/upload",
        files={"file": ("fake.png", b"this is not a png", "image/png")},
        data={"captured_at": "2026-10-16T09:30:00+08:00", "stage": "after"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "file_signature"


def test_all_acceptance_cases():
    response = client.post("/api/demo/acceptance/run-all")
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 12
    failures = [item for item in results if not item["passed"]]
    assert not failures, failures
    latest = client.get("/api/demo/acceptance/latest").json()
    assert latest["passed"] == 12
