from __future__ import annotations

import csv
import json
import re
import sqlite3
from pathlib import Path

from .config import (
    DATA_ROOT,
    DEMO_CLOCK,
    MODEL_ID,
    MODEL_VERSION,
    PROJECT_ID,
    STOREY_GUID,
    TARGET_GUID,
    TASK_ID,
    ZONE_ID,
)
from .db import dumps

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
ALNUM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def bigram_tokens(text: str) -> str:
    """Chinese bigram + latin tokenizer used by both FTS5 indexing and queries."""
    tokens: list[str] = []
    for run in CJK_RE.findall(text or ""):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    tokens.extend(word.lower() for word in ALNUM_RE.findall(text or ""))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return " ".join(ordered)


def fts_match_query(text: str) -> str:
    tokens = [token for token in bigram_tokens(text).split(" ") if token]
    if not tokens:
        return ""
    return " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:80])


def read_json(relative: str):
    path = DATA_ROOT / relative
    if not path.exists():
        raise FileNotFoundError(f"资料文件缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def seed_all(conn: sqlite3.Connection) -> None:
    model_check = read_json("03_数据集/S1/解析结果/模型检查结果.json")
    zone = read_json("07_案例与验收模板/检查区域.json")
    tasks = read_json("07_案例与验收模板/施工任务样例.json")
    evidence = read_json("07_案例与验收模板/证据样例.json")
    rules = read_json("04_安全规范/规范条款种子.json")

    conn.execute(
        "INSERT OR REPLACE INTO projects(project_id,name,description) VALUES (?,?,?)",
        (
            PROJECT_ID,
            "S1 参考工程项目（研究演示）",
            "S1 公开 IFC 样例模型 + 模拟现场观察，用于 BIM 施工安全协同 Agent 案例展示。",
        ),
    )

    source_path = "03_数据集/S1/bSDD_references_example.ifc"
    byte_size = 394_697_402
    if (DATA_ROOT / source_path).exists():
        byte_size = (DATA_ROOT / source_path).stat().st_size
    conn.execute(
        """INSERT OR REPLACE INTO models
           (model_id,version,schema_name,source_path,source_sha256,byte_size,element_count,storey_count,units)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            MODEL_ID,
            MODEL_VERSION,
            model_check.get("schema", "IFC2X3"),
            source_path,
            model_check.get("source_sha256", ""),
            byte_size,
            model_check.get("counts", {}).get("IfcElement", 0),
            model_check.get("counts", {}).get("IfcBuildingStorey", 0),
            "m",
        ),
    )

    for storey in model_check.get("storeys", []):
        conn.execute(
            """INSERT OR REPLACE INTO storeys
               (model_id,guid,name,elevation_m,placement_z_m,element_count,slab_count)
               VALUES (?,?,?,?,?,?,?)""",
            (
                MODEL_ID,
                storey["guid"],
                storey["name"],
                storey.get("elevation_attribute_m"),
                storey.get("placement_z_m"),
                storey.get("elements", 0),
                storey.get("slabs", 0),
            ),
        )

    index_path = DATA_ROOT / "03_数据集/S1/解析结果/选定楼层构件索引.csv"
    if not index_path.exists():
        raise FileNotFoundError(f"楼层索引缺失：{index_path}")
    with index_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        batch = []
        for row in reader:
            batch.append(
                (
                    row.get("model_id") or MODEL_ID,
                    row["guid"],
                    row.get("ifc_class") or "IfcElement",
                    row.get("name") or row["guid"],
                    row.get("storey_guid") or STOREY_GUID,
                    row.get("storey_name") or "05 vijfde verdieping",
                )
            )
        conn.executemany(
            """INSERT OR REPLACE INTO elements(model_id,guid,ifc_class,name,storey_guid,storey_name)
               VALUES (?,?,?,?,?,?)""",
            batch,
        )

    conn.execute(
        """INSERT OR REPLACE INTO zones(zone_id,model_id,storey_guid,storey_name,target_guid,data_json)
           VALUES (?,?,?,?,?,?)""",
        (
            zone["zone_id"],
            zone["model_id"],
            zone["storey_guid"],
            zone["storey_name"],
            zone["target_guid"],
            dumps(zone),
        ),
    )

    for task in tasks:
        conn.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id,project_id,model_id,zone_id,activity,planned_start,planned_end,owner,provenance,note,bim_guids_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task["task_id"],
                task["project_id"],
                task["model_id"],
                task["zone_id"],
                task["activity"],
                task["planned_start"],
                task["planned_end"],
                task["owner"],
                task.get("provenance", "simulated"),
                task.get("note", ""),
                dumps(task.get("bim_guids", [])),
            ),
        )

    for item in evidence:
        conn.execute(
            """INSERT OR REPLACE INTO evidence
               (evidence_id,project_id,model_id,model_version,zone_id,bim_guids_json,file_path,kind,
                captured_at,stage,provenance,observation_json,label,source,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["evidence_id"],
                item["project_id"],
                item["model_id"],
                item["model_version"],
                item["zone_id"],
                dumps(item.get("bim_guids", [])),
                item.get("file_path"),
                item.get("kind", "simulated_inspection_diagram"),
                item["captured_at"],
                item.get("stage", "before"),
                item.get("provenance", "模拟"),
                dumps(item.get("observation", {})),
                item.get("label", item["evidence_id"]),
                "seed",
                DEMO_CLOCK,
            ),
        )

    for rule in rules:
        conn.execute(
            """INSERT OR REPLACE INTO rules
               (rule_id,standard,clause,text,text_kind,source_path,pdf_page,source_url,status,
                effective_from,checked_on,jurisdiction,applicability,version,human_page_checked)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rule["rule_id"],
                rule["standard"],
                rule["clause"],
                rule["text"],
                rule.get("text_kind", "条文释义"),
                rule["source_path"],
                rule.get("pdf_page"),
                rule["source_url"],
                rule["status"],
                rule.get("effective_from"),
                rule.get("checked_on"),
                rule.get("jurisdiction"),
                rule.get("applicability"),
                rule.get("version", "v1"),
                1 if rule.get("human_page_checked") else 0,
            ),
        )
        tokens = bigram_tokens(
            " ".join(
                [
                    rule.get("standard", ""),
                    rule.get("clause", ""),
                    rule.get("text", ""),
                    rule.get("applicability", "") or "",
                ]
            )
        )
        conn.execute(
            "INSERT INTO rules_fts(rule_id,tokens) VALUES (?,?)",
            (rule["rule_id"], tokens),
        )

    case_id = "CASE-S1-DEMO-001"
    assumptions = [
        "板边已在演示中标注为需检查边界，不等于真实项目临空侧。",
        "坠落高度 2.5 m、人员作业和防护缺失均为模拟观察。",
        "17.3 m 是模型世界 Z 高程，不是坠落高度。",
    ]
    conn.execute(
        """INSERT OR REPLACE INTO cases
           (case_id,title,project_id,model_id,model_version,task_id,zone_id,as_of,status,version,
            bim_guids_json,evidence_ids_json,rule_ids_json,findings_json,controls_json,review_json,
            implementation_json,verification_json,assumptions_json,provenance,mode,last_run_id,
            analysis_incomplete,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            case_id,
            "L05 板边安全检查演示（预置）",
            PROJECT_ID,
            MODEL_ID,
            MODEL_VERSION,
            TASK_ID,
            ZONE_ID,
            DEMO_CLOCK,
            "draft",
            1,
            dumps([TARGET_GUID]),
            dumps(["EV-001"]),
            dumps([]),
            dumps([]),
            dumps([]),
            None,
            None,
            None,
            dumps(assumptions),
            "mixed_real_bim_simulated_site_state",
            "demo",
            None,
            0,
            DEMO_CLOCK,
            DEMO_CLOCK,
        ),
    )
    conn.execute(
        """INSERT INTO case_events(case_id,at,status,event,actor,detail_json,provenance)
           VALUES (?,?,?,?,?,?,?)""",
        (
            case_id,
            DEMO_CLOCK,
            "draft",
            "case_created",
            "演示安全员",
            dumps({"note": "预置演示案例，可直接点击“开始分析”。", "evidence_ids": ["EV-001"]}),
            "seed",
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
        ("demo_clock", DEMO_CLOCK),
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
        ("seed_version", "1.0"),
    )


def count_seed_rows() -> dict[str, int]:
    """Used by the health endpoint without opening the 376MB IFC."""
    result: dict[str, int] = {}
    for key, rel in {
        "rules": "04_安全规范/规范条款种子.json",
        "evidence": "07_案例与验收模板/证据样例.json",
    }.items():
        try:
            result[key] = len(read_json(rel))
        except Exception:
            result[key] = 0
    return result


def resolve_data_path(relative: str) -> Path:
    root = DATA_ROOT.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("非法资料路径") from exc
    return path
