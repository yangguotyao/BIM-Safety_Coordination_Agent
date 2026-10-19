from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import DATA_ROOT, TARGET_GUID, ZONE_ID
from .db import dumps, loads
from .errors import APIError
from .seed import fts_match_query

DEMO_CLOCK = "2026-10-16T09:00:00+08:00"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@lru_cache(maxsize=1)
def region_geometry() -> dict[str, Any]:
    path = DATA_ROOT / "03_数据集/S1/解析结果/区域几何预览.json"
    if not path.exists():
        raise APIError(500, "data_missing", f"区域几何文件缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def preview_mesh_map() -> dict[str, dict[str, Any]]:
    return {mesh["guid"]: mesh for mesh in region_geometry().get("meshes", [])}


def get_model(conn: sqlite3.Connection, model_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM models WHERE model_id=?", (model_id,)).fetchone()
    if not row:
        raise APIError(404, "model_not_found", f"模型不存在：{model_id}")
    return dict(row)


def get_zone(conn: sqlite3.Connection, zone_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM zones WHERE zone_id=?", (zone_id,)).fetchone()
    if not row:
        raise APIError(404, "zone_not_found", f"区域不存在：{zone_id}")
    data = dict(row)
    data["data"] = loads(data.pop("data_json"), {})
    return data


def get_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        raise APIError(404, "task_not_found", f"施工任务不存在：{task_id}")
    data = dict(row)
    data["bim_guids"] = loads(data.pop("bim_guids_json"), [])
    return data


def get_evidence(conn: sqlite3.Connection, evidence_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
    if not row:
        raise APIError(404, "evidence_not_found", f"证据不存在：{evidence_id}")
    data = dict(row)
    data["bim_guids"] = loads(data.pop("bim_guids_json"), [])
    data["observation"] = loads(data.pop("observation_json"), {})
    data['perception'] = loads(data.pop('perception_json', '{}'), {})
    return data


def get_element(conn: sqlite3.Connection, model_id: str, guid: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM elements WHERE model_id=? AND guid=?", (model_id, guid)
    ).fetchone()
    if not row:
        raise APIError(
            422,
            "unknown_guid",
            f"构件 GUID 不在已索引范围内：{guid}",
            {"model_id": model_id, "guid": guid, "indexed_scope": "storey 05 (1247 elements)"},
        )
    return dict(row)


def bim_query(conn: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    model = get_model(conn, case["model_id"])
    zone = get_zone(conn, case["zone_id"])
    zone['data']={**zone['data'],**(case.get('scope') or {})}
    guids = case.get("bim_guids") or [zone["target_guid"]]
    elements = []
    for guid in guids:
        element = get_element(conn, case["model_id"], guid)
        from .mesh import cached_mesh
        geometry = cached_mesh(guid)
        element['geometry_available'] = geometry is not None
        element['bbox_m'] = geometry.get('bbox_m') if geometry else None
        elements.append(element)

    meshes = region_geometry().get("meshes", [])
    class_counts: dict[str, int] = {}
    for mesh in meshes:
        class_counts[mesh["ifc_class"]] = class_counts.get(mesh["ifc_class"], 0) + 1

    neighbors = []
    target_box = next((element.get('bbox_m') for element in elements if element.get('bbox_m')), None)
    if target_box:
        for candidate in meshes:
            box = candidate.get('bbox_m')
            if not box or candidate['guid'] in guids:
                continue
            distance = math.sqrt(sum(max(0, box['min'][i]-target_box['max'][i],
                                           target_box['min'][i]-box['max'][i])**2 for i in range(3)))
            if distance <= 5:
                neighbors.append({'guid':candidate['guid'], 'ifc_class':candidate['ifc_class'],
                                  'distance_m':round(distance,3),
                                  'relation':'bbox_overlap_candidate' if distance==0 else 'nearby_bbox'})
        neighbors.sort(key=lambda item:item['distance_m'])

    return {
        "ok": True,
        "data": {
            "model_id": model["model_id"],
            "model_version": model["version"],
            "schema": model["schema_name"],
            "storey_guid": zone["storey_guid"],
            "storey_name": zone["storey_name"],
            "zone_id": zone["zone_id"],
            "target_guid": zone["target_guid"],
            "target_bbox_m": zone["data"].get("target", {}).get("bbox_m"),
            "elements": elements,
            'nearby_elements':neighbors[:8],
            'spatial_context_method':'已加载区域几何的包围盒邻近候选；不是精确碰撞或全模型拓扑',
            "preview_scope": {
                "mesh_count": len(meshes),
                "element_count_on_storey": 1247,
                "class_counts": class_counts,
                "note": "首屏只加载 35 个区域预览对象；原始 IFC 仍为查询源，可按需提取选中构件。",
            },
            "geometry_source": zone["data"].get("geometry_source"),
        },
        "provenance": "derived_geometry",
        "model_version": model["version"],
        "units": "m",
        "method": "IfcOpenShell 预提取网格 + 楼层构件索引查询",
        "evidence_ids": [],
        "rule_ids": [],
        "uncertainties": [
            "35 个预览对象不是模型全量显示。",
            "板边是人工标注的检查边界，不证明它是真实建筑临空侧。",
        ],
        "error": None,
    }


def _point_segment_distance_2d(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> tuple[float, float, float]:
    abx, aby = bx - ax, by - ay
    apx, apy = px - ax, py - ay
    denom = abx * abx + aby * aby
    t = 0.0 if denom == 0 else max(0.0, min(1.0, (apx * abx + apy * aby) / denom))
    cx, cy = ax + t * abx, ay + t * aby
    return math.hypot(px - cx, py - cy), cx, cy


def spatial_check(conn: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    zone = get_zone(conn, case["zone_id"])
    data = {**zone['data'],**(case.get('scope') or {})}
    point = data.get("worker_point_m")
    inspection = evidence_check(conn,case)
    if inspection['data']['matched'] and not case.get('scope'):
        point = (inspection['data'].get('observation') or {}).get('worker_point_m') or point
    edge = data.get("edge_segment_m")
    if not point or not edge or len(edge) != 2:
        return {
            "ok": False,
            "data": None,
            "provenance": "derived_geometry_with_simulated_inspection_zone",
            "model_version": case["model_version"],
            "units": "m",
            "method": "缺少已标注边线或模拟人员点，无法计算距离",
            "evidence_ids": [],
            "rule_ids": [],
            "uncertainties": ["空间关系未知，不能据此判断无风险。"],
            "error": {"code": "missing_geometry", "message": "缺少边线或人员点"},
        }
    a, b = edge[0], edge[1]
    distance, cx, cy = _point_segment_distance_2d(point[0], point[1], a[0], a[1], b[0], b[1])
    threshold = float(data.get("exposure_threshold_m", 1.0))
    bbox = data.get("target", {}).get("bbox_m") or {}
    bmin, bmax = bbox.get("min"), bbox.get("max")
    aabb_candidate = True
    if bmin and bmax:
        margin = threshold
        aabb_candidate = (
            bmin[0] - margin <= point[0] <= bmax[0] + margin
            and bmin[1] - margin <= point[1] <= bmax[1] + margin
            and bmin[2] - margin <= point[2] <= bmax[2] + margin
        )
    return {
        "ok": True,
        "data": {
            "zone_id": zone["zone_id"],
            "point_m": point,
            "edge_segment_m": edge,
            "distance_m": round(distance, 3),
            "nearest_point_m": [round(cx, 3), round(cy, 3), round(point[2], 3)],
            "exposure_threshold_m": threshold,
            "within_threshold": distance <= threshold,
            "aabb_candidate": aabb_candidate,
            "aabb_note": "AABB 只用于候选筛选，不作为碰撞或风险结论。",
            "drop_height_m": data.get("drop_height_m"),
            "drop_height_note": data.get("fall_reference_note"),
        },
        "provenance": "derived_geometry_with_simulated_inspection_zone",
        "model_version": case["model_version"],
        "units": "m",
        "method": "点到已标注二维边线线段的欧氏距离；仅证明与标注边线的关系",
        "evidence_ids": [],
        "rule_ids": [],
        "uncertainties": [
            "该边线不是经现场确认的坠落边缘。",
            "1.0 m 是演示项目策略阈值，不是国家规范距离限值。",
        ],
        "error": None,
    }


def schedule_query(conn: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    task = get_task(conn, case["task_id"])
    as_of = parse_dt(case["as_of"])
    start = parse_dt(task["planned_start"])
    end = parse_dt(task["planned_end"])
    active = bool(as_of and start and end and start <= as_of <= end)
    return {
        "ok": True,
        "data": {
            "task_id": task["task_id"],
            "activity": task["activity"],
            "planned_start": task["planned_start"],
            "planned_end": task["planned_end"],
            "as_of": case["as_of"],
            "active": active,
            "owner": task["owner"],
            "provenance": task["provenance"],
            "note": task["note"],
        },
        "provenance": task["provenance"],
        "model_version": case["model_version"],
        "units": "m",
        "method": "开始时间 ≤ 检查时刻 ≤ 结束时间",
        "evidence_ids": [],
        "rule_ids": [],
        "uncertainties": [] if active else ["检查时刻不在任务时间窗内，不能假定该活动正在进行。"],
        "error": None,
    }


REQUIRED_OBSERVATION_FIELDS = [
    "guardrail_state",
    "worker_present",
    "drop_height_m",
    "boundary_is_exposed",
    "guardrail_fixed",
    "guardrail_continuous",
    "ppe_confirmed",
]


def _missing_fields(observation: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_OBSERVATION_FIELDS:
        if observation.get(field) is None or observation.get(field) == "unknown":
            missing.append(field)
    if observation.get("guardrail_state") == "present" and observation.get("guardrail_height_m") is None:
        missing.append("guardrail_height_m")
    return missing


def evidence_check(
    conn: sqlite3.Connection,
    case: dict[str, Any],
    evidence_ids: list[str] | None = None,
    phase: str = "before",
) -> dict[str, Any]:
    task = get_task(conn, case["task_id"])
    start = parse_dt(task["planned_start"])
    end = parse_dt(task["planned_end"])
    ids = evidence_ids if evidence_ids is not None else case.get("evidence_ids", [])
    records = []
    for evidence_id in ids:
        item = get_evidence(conn, evidence_id)
        captured = parse_dt(item["captured_at"])
        project_match = item["project_id"] == case["project_id"]
        model_match = item["model_id"] == case["model_id"]
        version_match = item["model_version"] == case["model_version"]
        zone_match = item["zone_id"] == case["zone_id"]
        guid_match = bool(case.get('bim_guids')) and set(case['bim_guids']).issubset(item['bim_guids'])
        time_match = bool(captured and start and end and start <= captured <= end)
        missing = _missing_fields(item["observation"])
        if item.get('source') == 'upload' and not item.get('perception',{}).get('confirmed'):
            missing.append('human_observation_confirmation')
        eligible = all([project_match, model_match, version_match, zone_match, time_match, guid_match])
        records.append(
            {
                **item,
                "checks": {
                    "project_match": project_match,
                    "model_match": model_match,
                    "version_match": version_match,
                    "zone_match": zone_match,
                    "guid_match": guid_match,
                    "time_match": time_match,
                },
                "missing_fields": missing,
                "eligible": eligible,
                "data_complete": not missing,
            }
        )

    eligible = [record for record in records if record["eligible"]]
    if phase == "before":
        preferred = [record for record in eligible if record["stage"] == "before"]
        primary = (preferred or eligible or records or [None])[0]
    else:
        preferred = [record for record in eligible if record["stage"] == "after"]
        primary = (preferred or eligible or records or [None])[0]

    complete = bool(primary and primary["data_complete"])
    matched = bool(primary and primary["eligible"])
    missing_fields = primary["missing_fields"] if primary else list(REQUIRED_OBSERVATION_FIELDS)
    uncertainties: list[str] = []
    if not matched:
        uncertainties.append("没有同时满足项目、模型版本、区域和时间窗的现场证据。")
    if missing_fields:
        uncertainties.append("关键观察字段缺失：" + "、".join(missing_fields) + "。")
    if primary and primary["stage"] != phase:
        uncertainties.append(f"当前选中的证据阶段为 {primary['stage']}，与请求阶段 {phase} 不一致。")

    return {
        "ok": True,
        "data": {
            "case_id": case["case_id"],
            "evidence_ids": ids,
            "phase": phase,
            "records": records,
            "primary": primary,
            "matched": matched,
            "data_complete": complete,
            "missing_fields": missing_fields,
            "task_window": {"start": task["planned_start"], "end": task["planned_end"]},
            "observation": primary["observation"] if primary else None,
        },
        "provenance": "mixed",
        "model_version": case["model_version"],
        "units": "m",
        "method": "项目/模型版本/区域/任务时间窗匹配 + 观察字段完整性检查",
        "evidence_ids": ids,
        "rule_ids": [],
        "uncertainties": uncertainties,
        "error": None,
    }


KEYWORD_BOOSTS = {
    "临边": 2.2,
    "防护": 1.8,
    "栏杆": 1.8,
    "坠落": 1.8,
    "高度": 1.4,
    "人员": 1.2,
    "洞口": 1.6,
    "安全": 1.0,
    "作业": 0.8,
    "1.2": 2.4,
    "2m": 1.2,
    "围护": 1.8,
    "边沿": 1.6,
    "周边": 1.4,
    "孔洞": 1.6,
    "楼层": 1.2,
}


def rule_retrieval(
    conn: sqlite3.Connection, query: str, as_of: str | None = None, top_k: int = 3
) -> dict[str, Any]:
    checked_at = parse_dt(as_of or DEMO_CLOCK)
    if checked_at is None:
        raise APIError(422, 'invalid_time', '规范检索时刻无效')
    active_rows = conn.execute("SELECT * FROM rules WHERE status='active' AND (effective_from IS NULL OR effective_from<=?)", (checked_at.date().isoformat(),)).fetchall()
    active = [dict(row) for row in active_rows]
    active_ids = {row['rule_id'] for row in active}
    retired_rows = conn.execute("SELECT * FROM rules WHERE status='retired'").fetchall()
    retired = [dict(row) for row in retired_rows]

    clause_match = None
    import re

    found = re.search(r"\b\d+\.\d+\.\d+\b", query or "")
    if found:
        clause_match = found.group(0)

    ranked: list[tuple[float, dict[str, Any]]] = []
    expanded_query = query
    if any(keyword in (query or "") for keyword in ("临边", "防护", "栏杆", "边沿")):
        expanded_query = f"{query} 边沿 周边 围护 孔洞 楼层"
    match_expr = fts_match_query(expanded_query)
    candidates: list[dict[str, Any]] = []
    if match_expr:
        try:
            phrase_rows = conn.execute(
                """
                SELECT r.*, bm25(rules_fts) AS bm
                FROM rules_fts JOIN rules r ON r.rule_id = rules_fts.rule_id
                WHERE rules_fts MATCH ? AND r.status = 'active'
                ORDER BY bm ASC
                LIMIT 20
                """,
                (match_expr,),
            ).fetchall()
            candidates = [dict(row) for row in phrase_rows if row['rule_id'] in active_ids]
        except sqlite3.OperationalError:
            candidates = []

    if not candidates:
        candidates = active

    for row in candidates:
        text = f"{row['standard']} {row['clause']} {row['text']} {row.get('applicability') or ''}"
        score = 0.0
        for keyword, boost in KEYWORD_BOOSTS.items():
            if keyword in expanded_query and keyword in text:
                score += boost
        if clause_match:
            score += 6.0 if row["clause"] == clause_match else 0.0
        if row["clause"] in expanded_query:
            score += 2.0
        if row["standard"].lower() in expanded_query.lower():
            score += 1.5
        score += -float(row.get("bm") or 0.0)
        ranked.append((score, row))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if clause_match:
        exact = [item for item in ranked if item[1]["clause"] == clause_match]
        ranked = exact

    results = []
    for score, row in ranked[:top_k]:
        item = dict(row)
        item.pop("bm", None)
        item["score"] = round(score, 3)
        item["text_kind"] = item.get("text_kind") or "条文释义"
        results.append(item)

    retired_excluded = []
    for row in retired:
        if any(token and token in f"{row['standard']} {row['clause']} {row['text']}" for token in (query or "").split()):
            retired_excluded.append(row["rule_id"])
        elif clause_match and row["clause"] == clause_match:
            retired_excluded.append(row["rule_id"])

    return {
        "ok": True,
        "data": {
            "query": query,
            "as_of": as_of,
            "top_k": top_k,
            "results": results,
            "retired_excluded": sorted(set(retired_excluded)),
            "note": (
                "仅检索 status=active 的人工核对条文释义；retired 历史记录不进入现行依据。"
                if results
                else "未找到匹配的现行条款，需要补充依据。"
            ),
        },
        "provenance": "real_source",
        "model_version": None,
        "units": None,
        "method": "SQLite FTS5 中文二元组 + 关键词重排；top-k=3",
        "evidence_ids": [],
        "rule_ids": [item["rule_id"] for item in results],
        "uncertainties": [] if results else ["没有匹配的现行条款。"],
        "error": None,
    }


def risk_assessment(
    conn: sqlite3.Connection,
    case: dict[str, Any],
    bim: dict[str, Any],
    spatial: dict[str, Any],
    schedule: dict[str, Any],
    inspection: dict[str, Any],
    knowledge: dict[str, Any],
) -> dict[str, Any]:
    observation = inspection.get("data", {}).get("observation") or {}
    matched = bool(inspection.get("data", {}).get("matched"))
    complete = bool(inspection.get("data", {}).get("data_complete"))
    task_active = bool(schedule.get("data", {}).get("active"))
    guardrail = observation.get("guardrail_state")
    height = observation.get("guardrail_height_m")
    worker = observation.get("worker_present")
    fixed = observation.get("guardrail_fixed")
    continuous = observation.get("guardrail_continuous")
    boundary = observation.get("boundary_is_exposed")
    distance = (spatial.get("data") or {}).get("distance_m") if spatial.get("ok") else None
    threshold = (spatial.get("data") or {}).get("exposure_threshold_m") if spatial.get("ok") else None
    rules = knowledge.get("data", {}).get("results", [])

    checks: list[dict[str, Any]] = []

    def add(name: str, result: str, source: str, note: str = "") -> None:
        checks.append({"name": name, "result": result, "source": source, "note": note})

    add("任务时间窗", "pass" if task_active else "fail", "schedule_query", "检查时刻是否落在模拟活动时间内")
    add("证据匹配", "pass" if matched else "fail", "evidence_check", "项目/模型版本/区域/任务时间窗")
    add(
        "观察字段完整性",
        "pass" if complete else "unknown",
        "evidence_check",
        "未知字段不落为 false，也不输出无风险。",
    )
    add(
        "标注边界暴露",
        "pass" if boundary is True else ("fail" if boundary is False else "unknown"),
        "检查区域标注",
        "人工标注边界，不等同经现场确认的坠落边缘。",
    )
    add(
        "防护存在性",
        "pass" if guardrail == "present" else ("fail" if guardrail == "absent" else "unknown"),
        "模拟观察",
    )
    if guardrail == "present":
        height_pass = height is not None and float(height) >= 1.2
        add(
            "防护高度 ≥ 1.2 m",
            "pass" if height_pass else ("fail" if height is not None else "unknown"),
            "模拟观察（演示策略阈值）",
            "1.2 m 只是一项检查，不证明锚固、强度、连续性和全部安全要求合格。",
        )
    else:
        add("防护高度 ≥ 1.2 m", "unknown" if guardrail == "unknown" else "fail", "模拟观察")
    fixed_pass = fixed is True and continuous is True
    add(
        "固定与连续性",
        "pass" if fixed_pass else ("fail" if (fixed is False or continuous is False) else "unknown"),
        "模拟观察",
    )
    add(
        "人员暴露",
        "pass" if worker is True else ("fail" if worker is False else "unknown"),
        "模拟观察",
    )
    if distance is not None and threshold is not None:
        add(
            "与标注边线距离 ≤ 演示阈值",
            "pass" if float(distance) <= float(threshold) else "fail",
            "spatial_check",
            f"{distance} m ≤ {threshold} m 为演示项目策略，不是国家规范距离限值。",
        )

    rule_ids = [rule["rule_id"] for rule in rules]
    uncertainties: list[str] = []
    if not task_active:
        uncertainties.append("检查时刻不在任务时间窗内。")
    if not matched:
        uncertainties.append("没有时间、区域、项目、模型版本均匹配的证据。")
    if not complete:
        uncertainties.append("观察字段不完整，不能形成确定结论。")
    if not rules:
        uncertainties.append("没有检索到现行适用条款。")
    uncertainties.append("真实临边、防护高度、人员状态和坠落基准面未经现场确认。")

    result = "needs_evidence"
    hazard = "待补充证据的施工安全案例"
    risk_level = "未判定"
    if task_active and matched and complete:
        if boundary is False:
            result = "needs_evidence"
            hazard = "标注边界暴露状态为否，需人工确认检查范围"
        elif worker is False:
            result = "no_issue_in_checked_items"
            hazard = "已检查项未发现人员暴露"
        elif guardrail == "absent":
            result = "risk_candidate"
            hazard = "模拟临边无防护且有人员暴露"
            risk_level = "演示管理策略：高（非事故概率）"
        elif guardrail == "present" and height is not None and float(height) < 1.2:
            result = "risk_candidate"
            hazard = "模拟临边防护高度不足且有人员暴露"
            risk_level = "演示管理策略：中（非事故概率）"
        elif guardrail == "present" and not fixed_pass:
            result = "risk_candidate"
            hazard = "模拟临边防护固定或连续性不足且有人员暴露"
            risk_level = "演示管理策略：中（非事故概率）"
        else:
            result = "no_issue_in_checked_items"
            hazard = "已检查项未发现防护缺失或高度不足"

    focus = (case.get('task_spec') or {}).get('focus', ['all'])
    if 'all' not in focus:
        names = {'任务时间窗','证据匹配','观察字段完整性','标注边界暴露'}
        if 'guardrail_height' in focus: names.update(['防护存在性','防护高度 ≥ 1.2 m'])
        if 'guardrail_integrity' in focus: names.update(['防护存在性','固定与连续性'])
        if 'worker_exposure' in focus: names.update(['人员暴露','与标注边线距离 ≤ 演示阈值'])
        checks = [check for check in checks if check['name'] in names]
        result = 'needs_evidence'; hazard = '本次检查信息不足'; risk_level = '未判定'
        if task_active and matched and complete and boundary is True:
            issues = []
            if 'guardrail_height' in focus and (guardrail=='absent' or (height is not None and float(height)<1.2)):
                issues.append('防护缺失或高度不足')
            if 'guardrail_integrity' in focus and (guardrail=='absent' or not fixed_pass):
                issues.append('防护固定或连续性不足')
            if 'worker_exposure' in focus and worker is True and distance is not None and threshold is not None and distance<=threshold:
                issues.append('人员处于标注边线的演示暴露范围')
            if 'worker_exposure' in focus and distance is None:
                hazard = '人员暴露检查缺少距离校核结果'
            else:
                result = 'risk_candidate' if issues else 'no_issue_in_checked_items'
                hazard = '；'.join(issues) if issues else '本次选定检查项未发现问题'
                risk_level = '演示管理策略：中（非事故概率）' if issues else '仅限本次检查项'

    finding = {
        "finding_id": "F-001",
        "hazard": hazard,
        "result": result,
        "risk_level": risk_level,
        "bim_guids": case.get("bim_guids", []),
        "evidence_ids": inspection.get("data", {}).get("evidence_ids", []),
        "rule_ids": rule_ids,
        "checks": checks,
        "uncertainties": list(dict.fromkeys(uncertainties)),
        "provenance": "mixed_real_bim_simulated_site_observation",
        "scope_note": "只对已检查项目和演示输入成立，不代表整个现场安全。",
        "inputs": {
            'focus':focus,
            "guardrail_state": guardrail,
            "guardrail_height_m": height,
            "worker_present": worker,
            "boundary_is_exposed": boundary,
            "guardrail_fixed": fixed,
            "guardrail_continuous": continuous,
            "drop_height_m": observation.get("drop_height_m"),
        },
    }

    return {
        "ok": True,
        "data": {
            "result": result,
            "finding": finding,
            "risk_level": risk_level,
            "rule_ids": rule_ids,
            "checks": checks,
            "inputs": {
                "task_active": task_active,
                "evidence_matched": matched,
                "observation_complete": complete,
                "distance_m": distance,
                "threshold_m": threshold,
                "guardrail_state": guardrail,
                "guardrail_height_m": height,
                "worker_present": worker,
                "boundary_is_exposed": boundary,
                "drop_height_m": observation.get("drop_height_m"),
            },
            "note": "风险等级是演示管理策略，不是校准的事故概率。",
        },
        "provenance": "mixed",
        "model_version": case["model_version"],
        "units": "m",
        "method": "确定性检查表：任务时间 × 证据匹配 × 观察完整性 × 防护/高度/固定/暴露",
        "evidence_ids": inspection.get("data", {}).get("evidence_ids", []),
        "rule_ids": rule_ids,
        "uncertainties": list(dict.fromkeys(uncertainties)),
        "error": None,
    }


def verification_check(
    conn: sqlite3.Connection,
    case: dict[str, Any],
    after_evidence_ids: list[str],
    as_of: str,
    reviewer_confirmed: bool,
    manual_checks_confirmed: bool = False,
) -> dict[str, Any]:
    from .control_requirements import approved_criteria
    criteria = approved_criteria(case)
    guardrail_required = any(c['guardrail_required'] for c in criteria)
    minimum_height = max(c['min_height_m'] for c in criteria)
    manual_items = [item for c in criteria for item in c.get('manual_requirements', [])]
    implementation = case.get("implementation") or {}
    implemented_at = parse_dt(implementation.get("implemented_at"))
    verified_at = parse_dt(as_of)
    checks: list[dict[str, Any]] = []
    evidence_records = []
    remaining: list[str] = []

    if not implementation or not implemented_at:
        checks.append({"name": "已记录人工实施", "result": "fail", "source": "cases.implementation"})
    else:
        checks.append({"name": "已记录人工实施", "result": "pass", "source": "cases.implementation"})

    for evidence_id in after_evidence_ids:
        try:
            item = get_evidence(conn, evidence_id)
        except APIError:
            checks.append({"name": f"证据存在：{evidence_id}", "result": "fail", "source": "evidence"})
            continue
        captured = parse_dt(item["captured_at"])
        match = all(
            [
                item["project_id"] == case["project_id"],
                item["model_id"] == case["model_id"],
                item["model_version"] == case["model_version"],
                item["zone_id"] == case["zone_id"],
                bool(case.get('bim_guids')) and set(case['bim_guids']).issubset(item['bim_guids']),
                item['stage'] == 'after',
            ]
        )
        after_impl = bool(captured and implemented_at and captured > implemented_at)
        before_review = bool(captured and verified_at and captured <= verified_at)
        observation = item["observation"]
        guardrail_ok = not guardrail_required or observation.get("guardrail_state") == "present"
        height = observation.get("guardrail_height_m")
        height_ok = not guardrail_required or (height is not None and float(height) >= minimum_height)
        fixed_ok = (not any(c['fixed_required'] for c in criteria) or observation.get('guardrail_fixed') is True) and (
            not any(c['continuous_required'] for c in criteria) or observation.get('guardrail_continuous') is True)
        boundary_ok = not guardrail_required or observation.get("boundary_is_exposed") is True
        item_checks = [
            ('新观察已人工确认', item.get('source')!='upload' or item.get('perception',{}).get('confirmed') is True, 'evidence.perception'),
            ("项目/模型版本/区域匹配", match, "evidence_check"),
            ("证据晚于人工实施时刻", after_impl, "时间比较"),
            ("证据不晚于复核时刻", before_review, "时间比较"),
            ("模拟防护存在", guardrail_ok, "after 证据观察"),
            (f"模拟防护高度 ≥ {minimum_height:g} m", height_ok, "批准措施版本的验收参数"),
            ("模拟固定与连续性", fixed_ok, "after 证据观察"),
            ("标注边界仍暴露（检查范围成立）", boundary_ok, "检查区域"),
        ]
        if not guardrail_required:
            item_checks=item_checks[:4]
        for name, passed, source in item_checks:
            checks.append(
                {
                    "name": f"{name}：{evidence_id}",
                    "result": "pass" if passed else "fail",
                    "source": source,
                }
            )
        if not all(passed for _, passed, _ in item_checks):
            remaining.append(f"{evidence_id} 未满足全部复核检查项。")
        evidence_records.append({**item, "checks": {name: passed for name, passed, _ in item_checks}})

    checks.append(
        {
            "name": "演示安全员人工确认",
            "result": "pass" if reviewer_confirmed else "fail",
            "source": "verify 请求",
        }
    )
    if not reviewer_confirmed:
        remaining.append("复核人未确认。")
    if manual_items:
        checks.append({'name':'修改措施的人工核验项逐项确认',
                       'result':'pass' if manual_checks_confirmed else 'fail','source':'批准措施及独立人工核验'})
        if not manual_checks_confirmed:
            remaining.append('自定义文字要求尚未逐项人工核验。')
    if not after_evidence_ids:
        remaining.append("未提交实施后证据。")

    from .coordination import activity_plan,check_activities
    from .site_text import text_context
    plan=activity_plan(conn,case['case_id'])
    if plan or any(c.get('coordination_required') for c in criteria):
        checked=check_activities(plan,as_of)
        required=set((case.get('review') or {}).get('coordination_task_ids',[]))
        current={a['task_id'] for a in checked['activities']}
        valid=bool(plan and checked['complete'] and not checked['conflicts'] and required.issubset(current))
        checks.append({'name':'批准活动的时空冲突已消除','result':'pass' if valid else 'fail','source':'activity_conflict_check'})
        if not valid: remaining.append('仍有施工时空冲突或活动数据不足。')
    if not text_context(conn,case)['complete']:
        checks.append({'name':'现场文本差异已澄清','result':'fail','source':'site_text_query'})
        remaining.append('现场文本差异未澄清。')

    passed = all(check["result"] == "pass" for check in checks)
    if passed:
        remaining = ["只验证演示中列明项目，真实现场未检查。"]

    return {
        "ok": True,
        "data": {
            "verified_at": as_of,
            "evidence_ids": after_evidence_ids,
            "checks": checks,
            "reviewer_confirmed": reviewer_confirmed,
            "manual_checks_confirmed": manual_checks_confirmed,
            "approved_criteria": criteria,
            "control_version": (case.get('review') or {}).get('control_version'),
            "result": "pass_in_demo_scope" if passed else "fail",
            "remaining_risk": " ".join(dict.fromkeys(remaining)) if remaining else "无（仅限已检查项）",
            "evidence_records": evidence_records,
        },
        "provenance": "mixed",
        "model_version": case["model_version"],
        "units": "m",
        "method": "实施后证据时间/项目/模型版本/区域/防护检查项 + 人工确认",
        "evidence_ids": after_evidence_ids,
        "rule_ids": case.get("rule_ids", []),
        "uncertainties": [] if passed else ["复核未通过，案例应重新打开并保留残余风险。"],
        "error": None,
    }


def unit_check(raw_value: float, source_unit: str, world_z_m: float = 17.3) -> dict[str, Any]:
    factor = {"mm": 0.001, "cm": 0.01, "m": 1.0}.get(source_unit)
    if factor is None:
        raise APIError(422, "unit_not_supported", "只支持 mm/cm/m")
    value_m = raw_value * factor
    return {
        "ok": True,
        "data": {
            "raw_value": raw_value,
            "source_unit": source_unit,
            "value_m": round(value_m, 3),
            "world_z_m": world_z_m,
            "fall_height_m": 2.5,
            "note": "17.3 m 是模型世界 Z 高程；演示坠落高度为 2.5 m，两者不可等同。",
            "unit_normalized": True,
        },
        "provenance": "derived_geometry",
        "model_version": "4075c44a6e47",
        "units": "m",
        "method": "单位换算；绝对高程不自动当作坠落高度",
        "evidence_ids": [],
        "rule_ids": [],
        "uncertainties": ["坠落高度为演示假设，不是现场测量。"],
        "error": None,
    }
