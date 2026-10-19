from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import DATA_ROOT, MESH_CACHE_DIR, MODEL_ID, MODEL_VERSION
from .errors import APIError
from .tools import region_geometry

_MODEL = None
_MODEL_LOCK = threading.Lock()
_LAST_ERROR: str | None = None
_OPENED_AT: str | None = None


def cache_status() -> dict[str, Any]:
    return {
        "loaded": _MODEL is not None,
        "last_error": _LAST_ERROR,
        "opened_at": _OPENED_AT,
        "ifc_path": str(DATA_ROOT / "03_数据集/S1/bSDD_references_example.ifc"),
        "cache_dir": str(MESH_CACHE_DIR),
    }


def _load_model():
    global _MODEL, _LAST_ERROR, _OPENED_AT
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            import ifcopenshell

            path = DATA_ROOT / "03_数据集/S1/bSDD_references_example.ifc"
            if not path.exists():
                raise FileNotFoundError(f"IFC 原件缺失：{path}")
            _MODEL = ifcopenshell.open(str(path))
            _OPENED_AT = __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds")
            return _MODEL
        except Exception as exc:  # noqa: BLE001
            _LAST_ERROR = f"{type(exc).__name__}: {exc}"
            raise APIError(
                503,
                "ifc_unavailable",
                "原始 IFC 暂不可按需打开；首屏 35 个预览网格仍可用。",
                {"error": _LAST_ERROR},
            ) from exc


def cached_mesh(guid: str) -> dict[str, Any] | None:
    preview = {mesh["guid"]: mesh for mesh in region_geometry().get("meshes", [])}
    if guid in preview:
        return {**preview[guid], "source": "pre_extracted_preview", "units": "m"}
    cached = MESH_CACHE_DIR / f"{guid}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    return None


def mesh_for_guid(guid: str) -> dict[str, Any]:
    cached = cached_mesh(guid)
    if cached is not None:
        return cached

    model = _load_model()
    element = model.by_guid(guid)
    if element is None:
        raise APIError(404, "element_not_found", f"IFC 中没有该 GUID：{guid}")
    try:
        import ifcopenshell.geom

        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        settings.set(settings.WELD_VERTICES, True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = list(shape.geometry.verts)
        faces = list(shape.geometry.faces)
    except Exception as exc:  # noqa: BLE001
        raise APIError(
            422,
            "geometry_unavailable",
            f"该构件无法生成几何：{guid}",
            {"error": f"{type(exc).__name__}: {exc}"},
        ) from exc

    vertices = [
        [round(verts[index], 6), round(verts[index + 1], 6), round(verts[index + 2], 6)]
        for index in range(0, len(verts), 3)
    ]
    triangles = [
        [faces[index], faces[index + 1], faces[index + 2]]
        for index in range(0, len(faces), 3)
    ]
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    payload = {
        "guid": guid,
        "ifc_class": element.is_a(),
        "name": element.Name or guid,
        "vertices": vertices,
        "triangles": triangles,
        "bbox_m": {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        },
        "source": "ifcopenshell_lazy",
        "units": "m",
        "model_version": MODEL_VERSION,
    }
    MESH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload


def target_payload() -> dict[str, Any]:
    geometry = region_geometry()
    zone = {}
    zone_path = DATA_ROOT / "07_案例与验收模板/检查区域.json"
    if zone_path.exists():
        zone = json.loads(zone_path.read_text(encoding="utf-8"))
    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "coordinate_system": geometry.get("coordinate_system"),
        "target": geometry.get("target"),
        "zone": zone,
        "meshes": geometry.get("meshes", []),
        "scope": {
            "loaded_objects": len(geometry.get("meshes", [])),
            "storey_element_count": 1247,
            "note": "首屏只加载 35 个区域预览对象；选择其他对象时按 GUID 懒加载。",
        },
        "units": "m",
    }
