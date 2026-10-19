"""Reconcile source selection, completed download receipts and local file sizes."""
from collections import defaultdict
import csv
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "external" / "s1"
inventory = json.loads((ROOT / "file_inventory.json").read_text(encoding="utf-8"))
receipts = {}
for path in ROOT.glob("download_*.json"):
    for item in json.loads(path.read_text(encoding="utf-8")):
        if item.get("status") == "verified":
            receipts[item["category"], item["id"]] = item
sources = {c["category"]: c["source_url"] for c in
           json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))["categories"]}
selection, manifest = [], []
for item in inventory:
    selected = (item["category"] != "explanation_video" and
                (item["category"] != "environment_models" or item["name"].lower().endswith(".ifc")))
    selection.append({"category": item["category"], "id": item["id"], "name": item["name"],
                      "selected": selected, "reason": "case_data_or_open_format" if selected else
                      "optional_explanation_video" if item["category"] == "explanation_video" else
                      "optional_native_environment_or_executable_not_needed_for_case"})
    if not selected:
        continue
    receipt = receipts.get((item["category"], item["id"]))
    row = {**item, "source_share_url": sources[item["category"]], "status": "unverified"}
    if receipt:
        path = ROOT / receipt["local_path"]
        if (path.is_file() and path.stat().st_size == item["size"] and
                receipt["md5"] == item["hash"].lower().zfill(32) and len(receipt["sha256"]) == 64):
            row.update(status="verified", local_path=receipt["local_path"], md5=receipt["md5"],
                       sha256=receipt["sha256"], hash_verification="performed_after_download")
    manifest.append(row)
groups = defaultdict(lambda: {"expected": 0, "verified": 0, "bytes": 0})
for item in manifest:
    group = groups[item["category"]]
    group["expected"] += 1
    group["verified"] += item["status"] == "verified"
    group["bytes"] += item["size"]
summary = {"checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
           "published_source_files": len(inventory), "selected_files": len(manifest),
           "verified_files": sum(x["status"] == "verified" for x in manifest),
           "excluded_optional_files": len(inventory) - len(manifest),
           "selected_bytes": sum(x["size"] for x in manifest),
           "groups": dict(groups), "verification": "download-time source MD5 and SHA256; final receipt and local size reconciliation"}
summary["selected_GiB"] = round(summary["selected_bytes"] / 1024**3, 3)
for path, value in [(ROOT / "selection.json", selection), (ROOT / "download_manifest.json", manifest),
                    (ROOT / "prepared" / "download_summary.json", summary)]:
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
with (ROOT / "download_manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
    columns = ["category", "name", "id", "versionId", "size", "md5", "sha256", "status", "local_path"]
    writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(manifest)
print(json.dumps(summary, ensure_ascii=False, indent=2))
assert summary["selected_files"] == summary["verified_files"], "Some selected source files remain unverified"
