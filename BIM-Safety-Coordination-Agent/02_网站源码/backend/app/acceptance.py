from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable

from .agent import execute_run
from .config import MODEL_ID, ZONE_ID
from .db import connect
from .errors import APIError
from .services import (
    add_evidence,
    case_bundle,
    create_case,
    implement_case,
    latest_acceptance_results,
    reopen_case,
    review_case,
    save_acceptance_result,
    start_analysis,
    verify_case,
)
from .tools import rule_retrieval, unit_check

DEMO_AS_OF = "2026-10-16T09:00:00+08:00"
REVIEW_AT = "2026-10-16T09:10:00+08:00"
IMPLEMENT_AT = "2026-10-16T09:20:00+08:00"
VERIFY_AT = "2026-10-16T09:40:00+08:00"

TEST_DEFS = [
    ("T01", "正常样例", "no_issue_in_checked_items"),
    ("T02", "无防护风险", "risk_candidate"),
    ("T03", "栏杆高度不足", "risk_candidate"),
    ("T04", "证据不足", "needs_evidence"),
    ("T05", "时间不匹配", "needs_evidence"),
    ("T06", "失效条款", "retired_rule_excluded"),
    ("T07", "整改复核失败", "reopened"),
    ("T08", "整改复核通过", "closed"),
    ("T09", "无效构件GUID", "validation_error"),
    ("T10", "单位与标高", "unit_normalized"),
    ("T11", "未经审批", "transition_rejected"),
    ("T12", "关闭后条件变化", "reopened"),
]
TEST_NAMES = {test_id: name for test_id, name, _ in TEST_DEFS}
TEST_EXPECTED = {test_id: expected for test_id, _, expected in TEST_DEFS}


def _new_case(test_id: str, evidence_ids: list[str], guid: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": f"验收 {test_id} · {TEST_NAMES[test_id]}",
        "model_id": MODEL_ID,
        "zone_id": ZONE_ID,
        "task_id": "TASK-S1-001",
        "as_of": DEMO_AS_OF,
        "evidence_ids": evidence_ids,
        "actor": "演示安全员（验收）",
    }
    if guid:
        payload["bim_guids"] = [guid]
    return create_case(payload)["case"]


def _analyze(case_id: str) -> dict[str, Any]:
    _, run_id = start_analysis(case_id)
    execute_run(run_id)
    for _ in range(2400):
        conn=connect()
        try:status=conn.execute('SELECT status FROM runs WHERE run_id=?',(run_id,)).fetchone()['status']
        finally:conn.close()
        if status not in {'queued','running'}:break
        time.sleep(.2)
    bundle = case_bundle(case_id)
    return bundle


def _finding(bundle: dict[str, Any]) -> dict[str, Any]:
    findings = bundle["case"].get("findings") or []
    return findings[0] if findings else {}


def _approve_and_implement(case_id: str) -> dict[str, Any]:
    bundle = case_bundle(case_id)
    case = bundle["case"]
    bundle = review_case(
        case_id,
        {
            "decision": "approve",
            "reviewer": "演示安全员",
            "reviewed_at": REVIEW_AT,
            "control_version": case["control_version"],
            "expected_case_version": case["version"],
            "comment": "验收用例：批准演示控制措施。",
        },
    )
    case = bundle["case"]
    return implement_case(
        case_id,
        {
            "owner": "演示机电班组",
            "implemented_at": IMPLEMENT_AT,
            "comment": "验收用例：模拟实施记录。",
            "expected_case_version": case["version"],
        },
    )


def _close_case(case_id: str, after_evidence_id: str) -> dict[str, Any]:
    bundle = _approve_and_implement(case_id)
    bundle = add_evidence(case_id, [after_evidence_id], "演示安全员")
    case = bundle["case"]
    return verify_case(
        case_id,
        {
            "after_evidence_ids": [after_evidence_id],
            "reviewer": "演示安全员",
            "reviewer_confirmed": True,
            "as_of": VERIFY_AT,
            "expected_case_version": case["version"],
        },
    )


def _run_single(test_id: str) -> dict[str, Any]:
    case_id: str | None = None
    details: dict[str, Any] = {}
    try:
        if test_id == "T01":
            case = _new_case("T01", ["EV-007"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            finding = _finding(bundle)
            actual = finding.get("result", "missing")
            passed = actual == "no_issue_in_checked_items"
            details = {
                "finding": finding,
                "status": bundle["case"]["status"],
                "note": "仅表示已检查项目未发现问题，不宣布整个现场安全。",
            }
        elif test_id == "T02":
            case = _new_case("T02", ["EV-001"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            finding = _finding(bundle)
            actual = finding.get("result", "missing")
            passed = (
                actual == "risk_candidate"
                and "GB-3.2.3" in (finding.get("rule_ids") or [])
                and bundle["case"]["status"] == "pending_review"
            )
            details = {"finding": finding, "status": bundle["case"]["status"]}
        elif test_id == "T03":
            case = _new_case("T03", ["EV-003"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            finding = _finding(bundle)
            actual = finding.get("result", "missing")
            rules = finding.get("rule_ids") or []
            passed = (
                actual == "risk_candidate"
                and "GB-3.2.3" in rules
                and "JGJ-4.3.1" in rules
            )
            details = {"finding": finding, "rule_ids": rules}
        elif test_id == "T04":
            case = _new_case("T04", ["EV-004"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            finding = _finding(bundle)
            actual = finding.get("result", "missing")
            passed = actual == "needs_evidence"
            details = {
                "finding": finding,
                "missing_fields": (finding.get("checks") or []),
                "status": bundle["case"]["status"],
            }
        elif test_id == "T05":
            case = _new_case("T05", ["EV-005"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            finding = _finding(bundle)
            actual = finding.get("result", "missing")
            passed = actual == "needs_evidence"
            details = {
                "finding": finding,
                "note": "EV-005 属于前一天，不用于当前施工状态。",
            }
        elif test_id == "T06":
            conn = connect()
            try:
                result = rule_retrieval(conn, "JGJ 4.1.1", DEMO_AS_OF, 3)
            finally:
                conn.close()
            retired = result["data"].get("retired_excluded", [])
            active_ids = [item["rule_id"] for item in result["data"].get("results", [])]
            passed = bool(retired) and not any("RETIRED" in rule_id for rule_id in active_ids)
            actual = "retired_rule_excluded" if passed else "retired_rule_leaked"
            details = {"active_results": active_ids, "retired_excluded": retired}
        elif test_id == "T07":
            case = _new_case("T07", ["EV-001"])
            case_id = case["case_id"]
            bundle = _analyze(case_id)
            bundle = _approve_and_implement(case_id)
            bundle = add_evidence(case_id, ["EV-006"], "演示安全员")
            case = bundle["case"]
            bundle = verify_case(
                case_id,
                {
                    "after_evidence_ids": ["EV-006"],
                    "reviewer": "演示安全员",
                    "reviewer_confirmed": True,
                    "as_of": VERIFY_AT,
                    "expected_case_version": case["version"],
                },
            )
            actual = bundle["case"]["status"]
            passed = actual == "reopened" and (bundle["case"].get("verification") or {}).get("result") == "fail"
            details = {
                "status": actual,
                "verification": bundle["case"].get("verification"),
                "events": [event["event"] for event in bundle["events"]],
            }
        elif test_id == "T08":
            case = _new_case("T08", ["EV-001"])
            case_id = case["case_id"]
            _analyze(case_id)
            bundle = _close_case(case_id, "EV-010")
            actual = bundle["case"]["status"]
            passed = actual == "closed" and (bundle["case"].get("verification") or {}).get("result") == "pass_in_demo_scope"
            details = {
                "status": actual,
                "verification": bundle["case"].get("verification"),
                "events": [event["event"] for event in bundle["events"]],
            }
        elif test_id == "T09":
            try:
                _new_case("T09", ["EV-001"], guid="INVALID-GUID-NOT-IN-INDEX")
                actual = "unexpected_success"
                passed = False
            except APIError as exc:
                actual = "validation_error" if exc.status_code == 422 else f"http_{exc.status_code}"
                passed = exc.status_code == 422
                details = {"status_code": exc.status_code, "code": exc.code, "message": exc.message}
        elif test_id == "T10":
            result = unit_check(17300, "mm", 17.3)["data"]
            actual = "unit_normalized" if result["value_m"] == 17.3 and result["fall_height_m"] == 2.5 else "unit_error"
            passed = actual == "unit_normalized"
            details = result
        elif test_id == "T11":
            case = _new_case("T11", ["EV-001"])
            case_id = case["case_id"]
            _analyze(case_id)
            bundle = case_bundle(case_id)
            try:
                verify_case(
                    case_id,
                    {
                        "after_evidence_ids": ["EV-010"],
                        "reviewer": "演示安全员",
                        "reviewer_confirmed": True,
                        "as_of": VERIFY_AT,
                        "expected_case_version": bundle["case"]["version"],
                    },
                )
                actual = "unexpected_success"
                passed = False
            except APIError as exc:
                actual = "transition_rejected" if exc.status_code == 409 else f"http_{exc.status_code}"
                passed = exc.status_code == 409
                details = {"status_code": exc.status_code, "code": exc.code, "message": exc.message}
        elif test_id == "T12":
            case = _new_case("T12", ["EV-001"])
            case_id = case["case_id"]
            _analyze(case_id)
            bundle = _close_case(case_id, "EV-010")
            if bundle["case"]["status"] != "closed":
                raise RuntimeError("T12 前置关闭未成功")
            bundle = reopen_case(
                case_id,
                {
                    "reason": "新证据显示模拟防护被撤除，条件变化。",
                    "evidence_ids": ["EV-011"],
                    "actor": "演示安全员",
                },
            )
            actual = bundle["case"]["status"]
            events = [event["event"] for event in bundle["events"]]
            passed = actual == "reopened" and "verification_passed" in events and "case_reopened" in events
            details = {"status": actual, "events": events}
        else:
            raise APIError(404, "test_not_found", f"未知验收用例：{test_id}")
    except Exception as exc:  # noqa: BLE001 - result persisted
        actual = f"error:{type(exc).__name__}"
        passed = False
        details = {
            "error": str(exc),
            "status_code": getattr(exc, "status_code", None),
            "code": getattr(exc, "code", None),
        }

    save_acceptance_result(
        test_id,
        TEST_NAMES[test_id],
        TEST_EXPECTED[test_id],
        str(actual),
        passed,
        details,
        case_id,
    )
    return {
        "test_id": test_id,
        "name": TEST_NAMES[test_id],
        "expected": TEST_EXPECTED[test_id],
        "actual": str(actual),
        "passed": passed,
        "details": details,
        "case_id": case_id,
    }


def run_acceptance(test_id: str) -> dict[str, Any]:
    if test_id not in TEST_NAMES:
        raise APIError(404, "test_not_found", f"未知验收用例：{test_id}")
    return _run_single(test_id)


def run_all_acceptance() -> list[dict[str, Any]]:
    return [_run_single(test_id) for test_id, _, _ in TEST_DEFS]


def acceptance_summary() -> dict[str, Any]:
    results = latest_acceptance_results()
    passed = sum(1 for result in results if result["passed"])
    return {
        "total": len(TEST_DEFS),
        "executed": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
