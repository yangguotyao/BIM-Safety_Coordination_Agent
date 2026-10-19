"""Download and verify the publicly shared S1 data using Trimble's documented API."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / "data" / "external" / "s1"
API = "https://app21.connect.trimble.com/tc/api/2.0"
CATEGORIES = [
    "design_models", "engineering_models", "site_models", "environment_models",
    "coordination_models", "architectural_drawings", "structural_drawings",
    "mep_drawings", "bim_agreements", "ground_control_points", "photos_2019_05_29",
    "photos_2019_06_03", "photos_2019_06_05", "point_clouds", "mesh", "planning_4d",
    "explanation_video",
]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(url, token=None):
    headers = {"Accept": "application/json", "User-Agent": "S1-case-data-audit/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"HTTP {e.code}") from None
        except (OSError, ValueError):
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)


def sources():
    readme = (ROOT / "README.source.md").read_text(encoding="utf-8")
    links = re.findall(r"\[download\]\((https://[^)]+)\)", readme)
    assert len(links) == len(CATEGORIES), "Upstream README structure changed"
    return dict(zip(CATEGORIES, links))


def share(category, source):
    public_token = source.rstrip("/").split("/")[-2]
    data = get_json(API + "/shares/token/" + public_token)
    if data.get("mode") != "PUBLIC" or data.get("permission") != "DOWNLOAD":
        raise RuntimeError("The source is not a public downloadable share")
    clean = {k: data.get(k) for k in ("id", "mode", "permission", "projectId", "createdOn", "modifiedOn", "objects")}
    clean.update(category=category, source_url=source)
    return clean, data["accessToken"]


def inventory():
    catalog = {"categories": [], "errors": []}
    tokens = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(share, category, source): category for category, source in sources().items()}
        for future in concurrent.futures.as_completed(pending):
            category = pending[future]
            try:
                clean, token = future.result()
                catalog["categories"].append(clean)
                tokens[category] = token
                print("SHARE", category, len(clean["objects"]), flush=True)
            except Exception as e:
                catalog["errors"].append({"category": category, "error": str(e)})
                print("SHARE_ERROR", category, type(e).__name__, flush=True)
    save(ROOT / "catalog.json", catalog)
    tasks = [(c["category"], obj) for c in catalog["categories"] for obj in c["objects"]]
    files = []

    def details(item):
        category, obj = item
        if obj["type"] != "FILE":
            return {"category": category, **obj, "error": "Folder requires explicit expansion"}
        try:
            info = get_json(API + "/files/" + obj["id"], tokens[category])
            keys = ("id", "name", "versionId", "size", "hash", "projectId", "createdOn", "modifiedOn", "path", "revision")
            return {"category": category, **{k: info.get(k) for k in keys}}
        except Exception as e:
            return {"category": category, "id": obj["id"], "name": obj.get("name"), "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for i, item in enumerate(pool.map(details, tasks), 1):
            files.append(item)
            if i % 100 == 0:
                save(ROOT / "file_inventory.json", files)
                print("METADATA", i, "/", len(tasks), flush=True)
    save(ROOT / "file_inventory.json", files)
    for category in CATEGORIES:
        group = [f for f in files if f["category"] == category]
        print("TOTAL", category, len(group), round(sum(f.get("size", 0) or 0 for f in group) / 1024**2, 2), "MiB", flush=True)


def hashes(path):
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha256.hexdigest()


def download(categories, workers, inventory_path=None):
    files = json.loads((inventory_path or ROOT / "file_inventory.json").read_text(encoding="utf-8"))
    wanted = [f for f in files if f["category"] in categories]
    tokens = {c: share(c, sources()[c])[1] for c in categories}
    results = []

    def one(info):
        if info.get("error"):
            return {**info, "status": "metadata_error"}
        category, name = info["category"], info["name"]
        if name != Path(name).name or any(c in name for c in '<>:"/\\|?*'):
            return {**info, "status": "invalid_filename"}
        parent = info.get("path", [])[-1:]
        folder = re.sub(r'[<>:"/\\|?*]', "_", parent[0]["name"]) if parent else "files"
        target = ROOT / "raw" / category / folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = info["size"]
        if target.exists() and target.stat().st_size == expected:
            md5, sha256 = hashes(target)
            if not info.get("hash") or md5 == info["hash"].lower().zfill(32):
                return {**info, "status": "verified", "local_path": str(target.relative_to(ROOT)), "sha256": sha256, "md5": md5}
        part = target.with_name(target.name + ".part")
        for attempt in range(3):
            try:
                link = get_json(API + "/files/fs/" + info["id"] + "/downloadurl?versionId=" + info["versionId"], tokens[category])
                offset = part.stat().st_size if part.exists() else 0
                headers = {"User-Agent": "S1-case-data-audit/1.0"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                with urllib.request.urlopen(urllib.request.Request(link["url"], headers=headers), timeout=60) as response:
                    if offset and response.status != 206:
                        offset = 0
                    with part.open("ab" if offset else "wb") as f:
                        for chunk in iter(lambda: response.read(1024 * 1024), b""):
                            f.write(chunk)
                if part.stat().st_size != expected:
                    raise ValueError("Downloaded size differs from source metadata")
                md5, sha256 = hashes(part)
                if info.get("hash") and md5 != info["hash"].lower().zfill(32):
                    raise ValueError("Downloaded MD5 differs from source metadata")
                part.replace(target)
                print("VERIFIED", category, name, expected, flush=True)
                return {**info, "status": "verified", "local_path": str(target.relative_to(ROOT)), "sha256": sha256, "md5": md5}
            except Exception as e:
                if attempt == 2:
                    print("DOWNLOAD_ERROR", category, name, type(e).__name__, flush=True)
                    return {**info, "status": "failed", "error": type(e).__name__ + ": " + str(e).split("https:")[0]}
                time.sleep(2 ** attempt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for i, result in enumerate(pool.map(one, wanted), 1):
            results.append(result)
            if i % 10 == 0:
                save(ROOT / ("download_" + "_".join(categories) + ".json"), results)
    save(ROOT / ("download_" + "_".join(categories) + ".json"), results)
    print("FINISHED", len(results), "verified", sum(r["status"] == "verified" for r in results), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inventory", "download"])
    parser.add_argument("--categories", nargs="+", choices=CATEGORIES)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if args.action == "inventory":
        inventory()
    else:
        if not args.categories:
            parser.error("download requires --categories")
        download(args.categories, args.workers, args.inventory)
