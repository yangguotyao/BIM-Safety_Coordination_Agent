"""Prepare traceable S1 case inputs. Requires IfcOpenShell, Pillow and PyMuPDF."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sqlite3
import struct
import zipfile

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np
from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parents[1] / "data" / "external" / "s1"
OUT = ROOT / "prepared"
OUT.mkdir(exist_ok=True)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def find(name):
    return next((ROOT / "raw").rglob(name))


def timestamp(value):
    if value is None:
        return None
    date, clock = value.DateComponent, value.TimeComponent
    return (f"{date.YearComponent:04d}-{date.MonthComponent:02d}-{date.DayComponent:02d}"
            f"T{int(clock.HourComponent):02d}:{int(clock.MinuteComponent or 0):02d}:"
            f"{int(clock.SecondComponent or 0):02d}")


def prepare_models():
    source = find("BIM 4D Blok S1_IFC.ifc")
    model = ifcopenshell.open(str(source))
    print("4D model parsed", flush=True)
    parents = {}
    for rel in model.by_type("IfcRelNests"):
        for child in rel.RelatedObjects:
            parents[child.id()] = rel.RelatingObject
    times = {}
    for rel in model.by_type("IfcRelAssignsTasks"):
        if rel.TimeForTask:
            for task in rel.RelatedObjects:
                times[task.id()] = {key: timestamp(getattr(rel.TimeForTask, key)) for key in
                                    ["ScheduleStart", "ScheduleFinish", "ActualStart", "ActualFinish"]}
    tasks = []
    for task in model.by_type("IfcTask"):
        chain, current, seen = [], task, set()
        while current.id() in parents and current.id() not in seen:
            seen.add(current.id())
            current = parents[current.id()]
            chain.append(current.Name)
        tasks.append({"guid": task.GlobalId, "task_id": task.TaskId, "name": task.Name,
                      "wbs": task.Description, "hierarchy": list(reversed(chain)),
                      **times.get(task.id(), {})})
    save("ifc_schedule_tasks.json", tasks)
    links = []
    for rel in model.by_type("IfcRelAssignsToProcess"):
        task = rel.RelatingProcess
        links.append({"relation_guid": rel.GlobalId, "task_guid": task.GlobalId,
                      "task_id": task.TaskId, "objects": [
                          {"guid": obj.GlobalId, "type": obj.is_a(), "name": obj.Name}
                          for obj in rel.RelatedObjects]})
    save("ifc_task_product_links.json", links)
    architecture = ifcopenshell.open(str(find("O-S1-BWK-BIM architectural - BIM bouwkundig.ifc")))
    structure = ifcopenshell.open(str(find("O-S1-CON-Structural engineering - Constructie.ifc")))
    tag_index = defaultdict(list)
    for obj in structure.by_type("IfcElement"):
        tag_index[obj.Tag].append(obj)
    focused_ids = {"ST00330", "ST00340", "ST00390"}
    crosswalk = []
    geometry = []
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    for link in links:
        if link["task_id"] not in focused_ids:
            continue
        for item in link["objects"]:
            obj = model.by_guid(item["guid"])
            props = ifcopenshell.util.element.get_psets(obj).get("SynchroResourceProperty", {})
            original_guid = props.get("[ArchiCADProperties]ARCHICAD IFC ID")
            matches, basis = [], None
            if original_guid:
                try:
                    matches = [architecture.by_guid(original_guid)]
                    basis = "retained_original_ARCHICAD_IFC_ID"
                except RuntimeError:
                    pass
            elif obj.Tag:
                matches = [x for x in tag_index.get(obj.Tag, []) if x.is_a() == obj.is_a()]
                basis = "unique_source_Revit_tag_and_IFC_class" if len(matches) == 1 else None
            row = {"planning_guid": obj.GlobalId, "task_id": link["task_id"], "name": obj.Name,
                   "type": obj.is_a(), "original_guid_property": original_guid,
                   "original_storey": props.get("IfcBuildingStorey"),
                   "load_bearing_property": props.get("[Pset_SlabCommon]LoadBearing"),
                   "source_layer": props.get("IfcPresentationLayerAssignment"),
                   "source_guids": [x.GlobalId for x in matches], "mapping_basis": basis,
                   "mapping_status": "unique_match" if len(matches) == 1 else "needs_review"}
            crosswalk.append(row)
            if len(geometry) < 6 or link["task_id"] not in {g["task_id"] for g in geometry}:
                try:
                    shape = ifcopenshell.geom.create_shape(settings, obj)
                    vertices = np.array(shape.geometry.verts).reshape(-1, 3)
                    geometry.append({"guid": obj.GlobalId, "task_id": link["task_id"],
                                     "minimum_m": vertices.min(axis=0).tolist(),
                                     "maximum_m": vertices.max(axis=0).tolist(),
                                     "triangle_count": len(shape.geometry.faces) // 3,
                                     "status": "geometry_created"})
                except Exception as e:
                    geometry.append({"guid": obj.GlobalId, "task_id": link["task_id"],
                                     "status": "geometry_failed", "error": str(e)[:200]})
    save("focused_product_crosswalk.json", crosswalk)
    save("geometry_checks.json", geometry)
    save("model_summary.json", {"ifc_schedule_tasks": len(tasks), "task_product_relations": len(links),
                               "linked_unique_products": len({x["guid"] for l in links for x in l["objects"]}),
                               "focused_crosswalk": dict(Counter(x["mapping_status"] for x in crosswalk)),
                               "architecture_counts": {t: len(architecture.by_type(t)) for t in
                                   ["IfcProduct", "IfcBuildingStorey", "IfcSpace", "IfcOpeningElement"]},
                               "direct_structural_GUID_overlap": len({x.GlobalId for x in structure.by_type("IfcProduct")} &
                                                                     {x.GlobalId for x in model.by_type("IfcProduct")})})
    print("Model links and geometry checked", flush=True)


def prepare_schedule():
    db = sqlite3.connect(find("Overallplanning Blok S1.pp").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    # Full rows retain source field names, native IDs and timestamps for later adapters.
    for table, name in [("TASK", "native_schedule_tasks.json"), ("BAR", "native_schedule_bars.json"),
                        ("EXPANDED_TASK", "native_schedule_summaries.json"), ("LINK", "native_schedule_links.json")]:
        save(name, [dict(row) for row in db.execute("SELECT * FROM " + table)])
    bars = {r["ID"]: dict(r) for r in db.execute("SELECT ID,NAME,EXPANDED_TASK FROM BAR")}
    summaries = {r["ID"]: dict(r) for r in db.execute("SELECT ID,NAME,BAR FROM EXPANDED_TASK")}
    native = []
    for row in db.execute("SELECT ID,NAME,UNIQUE_TASK_ID,BAR,LINKABLE_START,LINKABLE_FINISH FROM TASK"):
        task, chain, seen = dict(row), [], set()
        bar = bars.get(row["BAR"])
        while bar and bar["ID"] not in seen:
            seen.add(bar["ID"])
            summary = summaries.get(bar["EXPANDED_TASK"])
            if not summary:
                break
            chain.append(summary["NAME"])
            bar = bars.get(summary["BAR"])
        task["hierarchy"] = list(reversed(chain))
        native.append(task)
    ifc_tasks = json.loads((OUT / "ifc_schedule_tasks.json").read_text(encoding="utf-8"))
    normalize = lambda value: " ".join((value or "").split()).casefold()
    crosswalk = []
    for task in native:
        path = [normalize(x) for x in task["hierarchy"] if normalize(x) != "hoofdkaart"]
        candidates = [x for x in ifc_tasks if normalize(x["name"]) == normalize(task["NAME"])
                      and [normalize(p) for p in x["hierarchy"]] == path
                      and (x.get("ScheduleStart") or "")[:10] == (task["LINKABLE_START"] or "")[:10]
                      and (x.get("ScheduleFinish") or "")[:10] == (task["LINKABLE_FINISH"] or "")[:10]]
        crosswalk.append({"native_id": task["ID"], "native_task_id": task["UNIQUE_TASK_ID"],
                          "ifc_task_ids": [x["task_id"] for x in candidates],
                          "status": "unique_match" if len(candidates) == 1 else "needs_review",
                          "basis": "normalized_name_hierarchy_and_start_finish_dates"})
    save("schedule_crosswalk.json", crosswalk)
    print("Native schedule exported", dict(Counter(x["status"] for x in crosswalk)), flush=True)


def prepare_files():
    inventory = json.loads((ROOT / "file_inventory.json").read_text(encoding="utf-8"))
    photos, mosaics, documents, archives = [], [], [], []
    for info in inventory:
        folder = re.sub(r'[<>:"/\\|?*]', "_", info["path"][-1]["name"])
        path = ROOT / "raw" / info["category"] / folder / info["name"]
        if not path.exists():
            continue
        if info["category"].startswith("photos_") and path.suffix.lower() == ".tif":
            with Image.open(path) as image:
                tags = image.tag_v2
                keys = list(tags.get(34735, []))
                epsg = next((keys[i+3] for i in range(4, len(keys), 4)
                             if keys[i] == 3072 and keys[i+1] == 0), None)
                mosaics.append({"source_file_id": info["id"], "path": str(path.relative_to(ROOT)),
                                "width": image.width, "height": image.height, "epsg": epsg,
                                "pixel_scale": list(tags.get(33550, [])),
                                "tiepoint": list(tags.get(33922, [])),
                                "geo_keys": keys, "geo_description": tags.get(34737),
                                "pixel_to_world_status": "geotags_present_BIM_registration_unverified"})
        elif info["category"].startswith("photos_") and path.suffix.lower() == ".jpg":
            with Image.open(path) as image:
                exif = image.getexif()
                gps = exif.get_ifd(34853)
                def decimal(value, ref):
                    degrees = float(value[0]) + float(value[1]) / 60 + float(value[2]) / 3600
                    return -degrees if ref in ["S", "W"] else degrees
                filename_time = re.search(r"_(\d{8})T(\d{6})", path.name)
                photo = {"source_file_id": info["id"], "path": str(path.relative_to(ROOT)),
                         "width": image.width, "height": image.height, "camera": path.name.split("_")[0],
                         "filename_timestamp": "".join(filename_time.groups()) if filename_time else None,
                         "exif_datetime": exif.get(306), "timezone": None,
                         "image_description": exif.get(270), "gps_status": gps.get(9),
                         "latitude": decimal(gps[2], gps.get(1)) if 2 in gps else None,
                         "longitude": decimal(gps[4], gps.get(3)) if 4 in gps else None,
                         "component_mapping_status": "not_annotated", "safety_labels": None}
                photos.append(photo)
        elif path.suffix.lower() == ".pdf":
            try:
                with pymupdf.open(path) as doc:
                    text = "\n".join(page.get_text() for page in doc)
                    documents.append({"source_file_id": info["id"], "path": str(path.relative_to(ROOT)),
                                      "pages": len(doc), "text_characters": len(text),
                                      "status": "readable", "first_page_excerpt": text[:800]})
            except Exception as e:
                documents.append({"path": str(path.relative_to(ROOT)), "status": "failed", "error": str(e)})
        elif path.suffix.lower() in [".zip", ".smc"]:
            try:
                with zipfile.ZipFile(path) as archive:
                    archives.append({"path": str(path.relative_to(ROOT)), "members": archive.namelist(),
                                     "bad_crc_member": archive.testzip()})
            except zipfile.BadZipFile:
                archives.append({"path": str(path.relative_to(ROOT)), "status": "proprietary_non_zip"})
    save("photos.json", photos)
    save("orthomosaics.json", mosaics)
    save("pdf_inventory.json", documents)
    save("archive_inventory.json", archives)
    print("Files inspected", len(photos), "photos", len(documents), "PDFs", len(archives), "archives", flush=True)


def prepare_crs():
    from pyproj import CRS, Transformer
    headers = []
    for path in (ROOT / "raw" / "point_clouds").rglob("*.las"):
        with path.open("rb") as f:
            header = f.read(227)
            f.seek(struct.unpack_from("<H", header, 94)[0])
            wkt = None
            for _ in range(struct.unpack_from("<I", header, 100)[0]):
                _, _, record_id, length, _ = struct.unpack("<H16sHH32s", f.read(54))
                data = f.read(length)
                if record_id == 2112:
                    wkt = data.rstrip(b"\0").decode()
        headers.append({"path": str(path.relative_to(ROOT)), "wkt": wkt,
                        "points": struct.unpack_from("<I", header, 107)[0],
                        "scale": struct.unpack_from("<3d", header, 131),
                        "offset": struct.unpack_from("<3d", header, 155),
                        "bounds_max_min_xyz": struct.unpack_from("<6d", header, 179)})
    save("pointcloud_metadata.json", headers)
    source = CRS.from_wkt(headers[0]["wkt"])
    target = CRS.from_epsg(28992)
    transform = Transformer.from_crs(source, target, always_xy=True)
    offsets = []
    for path in (ROOT / "raw" / "mesh").rglob("*.xyz"):
        x, y, z = map(float, path.read_text().split())
        offsets.append({"path": str(path.relative_to(ROOT)), "source_offset": [x, y, z],
                        "transformed_RD_xy": transform.transform(x, y)})
    save("crs_diagnostic.json", {"source_wkt": headers[0]["wkt"], "target_epsg": 28992,
                                "source_projection_method": source.coordinate_operation.method_name,
                                "target_projection_method": target.coordinate_operation.method_name,
                                "mesh_offsets": offsets, "height_transform": "not_applied",
                                "status": "offset_transformation_tested_BIM_registration_unverified"})
    points = []
    for line in find("GCP S1 RD Amersfoort.csv").read_text(encoding="utf-8").splitlines():
        fields = line.split(",")
        if len(fields) == 5 and fields[1] == "GCP":
            points.append((fields[0], float(fields[2]), float(fields[3]), float(fields[4])))
    rasters = json.loads((OUT / "orthomosaics.json").read_text(encoding="utf-8"))
    pixels = []
    for raster in rasters:
        xy = Transformer.from_crs(28992, raster["epsg"], always_xy=True)
        tie, scale = raster["tiepoint"], raster["pixel_scale"]
        for name, x, y, z in points:
            rx, ry = xy.transform(x, y)
            column, row = (rx - tie[3]) / scale[0], (tie[4] - ry) / scale[1]
            pixels.append({"raster": raster["path"], "gcp": name,
                           "pixel_corner_coordinates": [column, row],
                           "within_raster_extent": 0 <= column < raster["width"] and 0 <= row < raster["height"],
                           "status": "computed_from_geotags_not_visually_identified_or_accuracy_checked"})
    save("gcp_raster_pixels.json", pixels)
    print("CRS checked", len(headers), "point clouds", len(offsets), "mesh offsets", len(pixels), "GCP pixel candidates", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("part", choices=["models", "schedule", "files", "crs", "all"])
    part = parser.parse_args().part
    if part in ["models", "all"]:
        prepare_models()
    if part in ["schedule", "all"]:
        prepare_schedule()
    if part in ["files", "all"]:
        prepare_files()
    if part in ["crs", "all"]:
        prepare_crs()
