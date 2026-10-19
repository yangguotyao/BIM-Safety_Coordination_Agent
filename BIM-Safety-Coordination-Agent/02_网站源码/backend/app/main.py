from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, mesh
from .translation import translate_payload
from .acceptance import acceptance_summary, run_acceptance, run_all_acceptance
from .config import (
    ALLOWED_UPLOAD_EXT,
    ALLOWED_UPLOAD_MIME,
    DATA_ROOT,
    DEMO_CLOCK,
    DEMO_MODE,
    FRONTEND_DIST,
    MAX_UPLOAD_BYTES,
    MODEL_ID,
    PACKAGE_ROOT,
    UPLOAD_DIR,
    live_model_configured,
    runtime_mode,
    vision_model_configured,
    MODEL_NAME,
    VISION_MODEL,
)
from .db import connect, init_db, loads, reset_db
from .errors import APIError
from .seed import resolve_data_path
from .services import (
    add_evidence,
    add_uploaded_evidence,
    case_bundle,
    create_case,
    dashboard_summary,
    export_case,
    get_run,
    implement_case,
    latest_acceptance_results,
    list_cases,
    list_runs,
    reopen_case,
    record_task_request,
    review_case,
    rules_list,
    task_list,
    verify_case,
)
from .tools import get_element, get_evidence, get_model, get_zone, unit_check
from .bim_context import InspectionContext,ScopeAnnotation,save_scope
from .coordination import ActivityPlanRequest,save_activity_plan
from .site_text import SiteNoteRequest,TextResolutionRequest,add_site_note,extract_site_note,resolve_text_conflict
from .vision import SiteObservation
from . import durable
from . import access

init_db()

@asynccontextmanager
async def lifespan(_:FastAPI):
    durable.start_worker()
    try:yield
    finally:durable.stop_worker()


app = FastAPI(
    title="BIM 施工安全协同平台 API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get('/api/agent/runtime')
def agent_runtime():
    return durable.runtime_status()


@app.middleware('http')
async def access_policy(request:Request,call_next):
    protected=request.url.path.startswith(('/api/','/bim/'))
    if not protected or request.url.path=='/api/health':return await call_next(request)
    principal=None;token=None
    try:
        principal=access.authenticate(request);access.authorize(request,principal)
        token=access.PRINCIPAL.set(principal)
        response=await call_next(request)
        access.record_access(principal,request,response.status_code)
        return response
    except APIError as exc:
        if principal:access.record_access(principal,request,exc.status_code)
        return JSONResponse(status_code=exc.status_code,content={'error':{'code':exc.code,'message':exc.message,'details':exc.details}})
    finally:
        if token is not None:access.PRINCIPAL.reset(token)


@app.get('/api/access/session')
def access_session(request:Request,response:Response):
    header=request.headers.get('Authorization','')
    if header.startswith('Bearer '):response.set_cookie('bim_access',header[7:],httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
    return access.PRINCIPAL.get()


@app.post('/api/access/logout')
def access_logout(response:Response):
    response.delete_cookie('bim_access',path='/');return {'signed_out':True}


@app.get('/api/cases/{case_id}/workflow')
def cases_workflow(case_id:str):
    return durable.sync_workflow(case_id)


@app.post('/api/runs/{run_id}/resume')
def runs_resume(run_id:str):
    return durable.resume_run(run_id)


@app.post('/api/runs/{run_id}/cancel')
def runs_cancel(run_id:str):
    return durable.cancel_run(run_id)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@app.exception_handler(APIError)
async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail), "details": None}},
    )


class CaseCreateRequest(BaseModel):
    title: str | None = None
    model_id: str = MODEL_ID
    task_id: str = "TASK-S1-001"
    zone_id: str = "ZONE-S1-L05-EDGE"
    as_of: str = DEMO_CLOCK
    evidence_ids: list[str] = Field(default_factory=lambda: ["EV-001"])
    bim_guids: list[str] | None = None
    assumptions: list[str] | None = None
    actor: str | None = None
    request_text: str = Field(default='', max_length=1500)
    actor_id: str = Field(default='demo-user', min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    inspection_context: InspectionContext | None = None


class ObservationRequest(BaseModel):
    observation: SiteObservation
    source: str = 'simulated'
    note: str = Field(min_length=1, max_length=800)
    expected_case_version: int = Field(ge=1)


class ScopeRequest(ScopeAnnotation):
    expected_case_version: int=Field(ge=1)


class TaskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1500)
    actor_id: str = Field(default='demo-user', min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    expected_case_version: int = Field(ge=1)


class ReviewRequest(BaseModel):
    decision: str
    reviewer: str = "演示安全员"
    comment: str = ""
    reviewed_at: str | None = None
    control_version: int | None = None
    expected_case_version: int | None = None
    new_controls: list[dict[str, Any]] | None = None


class ImplementationRequest(BaseModel):
    owner: str = "演示机电班组"
    implemented_at: str | None = None
    comment: str = ""
    expected_case_version: int | None = None


class EvidenceRequest(BaseModel):
    evidence_ids: list[str]
    actor: str = "演示安全员"


class VerifyRequest(BaseModel):
    after_evidence_ids: list[str]
    reviewer: str = "演示安全员"
    reviewer_confirmed: bool = False
    manual_checks_confirmed: bool = False
    as_of: str | None = None
    expected_case_version: int | None = None


class ReopenRequest(BaseModel):
    reason: str
    evidence_ids: list[str]
    actor: str = "演示安全员"


@app.put('/api/cases/{case_id}/scope')
def cases_scope(case_id:str,payload:ScopeRequest):
    return save_scope(case_id,payload.model_dump())


@app.put('/api/cases/{case_id}/activity-plan')
def cases_activity_plan(case_id:str,payload:ActivityPlanRequest):
    return save_activity_plan(case_id,payload.model_dump())


@app.post('/api/cases/{case_id}/site-notes',status_code=201)
def cases_site_note(case_id:str,payload:SiteNoteRequest):
    return add_site_note(case_id,payload.model_dump())


@app.post('/api/cases/{case_id}/site-notes/{note_id}/extract')
def cases_text_extract(case_id:str,note_id:str):
    return extract_site_note(case_id,note_id)


@app.post('/api/cases/{case_id}/site-notes/resolve')
def cases_text_resolve(case_id:str,payload:TextResolutionRequest):
    return resolve_text_conflict(case_id,payload.model_dump())


@app.get("/api/health")
def health() -> dict[str, Any]:
    db_ok = True
    db_error = None
    try:
        conn = connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = str(exc)
    try:
        import ifcopenshell  # noqa: F401

        ifc_available = True
        ifc_version = getattr(ifcopenshell, "version", "unknown")
    except Exception:
        ifc_available = False
        ifc_version = None
    return {
        "ok": db_ok,
        "mode": runtime_mode(),
        "demo_mode": DEMO_MODE,
        "live_config_complete": live_model_configured(),
        'vision_config_complete': vision_model_configured(),
        'models':{'coordinator':MODEL_NAME if live_model_configured() else None,
                  'vision':VISION_MODEL if vision_model_configured() else None},
        "db": {"ok": db_ok, "error": db_error},
        "ifcopenshell": {"available": ifc_available, "version": ifc_version},
        "model_cache": mesh.cache_status(),
        "demo_clock": DEMO_CLOCK,
        "version": "2.0.0",
        'agent_runtime':durable.runtime_status(),
        "data_root": str(DATA_ROOT),
        "package_root": str(PACKAGE_ROOT),
        "ports": {"frontend_dev": 5173, "backend": int(os.getenv("PORT", "8000"))},
    }


@app.get("/api/models")
def models() -> dict[str, Any]:
    conn = connect()
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM models").fetchall()]
        return {"models": rows}
    finally:
        conn.close()


@app.get("/api/models/{model_id}/storeys")
def storeys(model_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        get_model(conn, model_id)
        rows = [dict(row) for row in conn.execute("SELECT * FROM storeys WHERE model_id=?", (model_id,))]
        return {"rows": rows, "total": len(rows)}
    finally:
        conn.close()


@app.get("/api/models/{model_id}/elements")
def elements(
    model_id: str,
    storey_guid: str | None = None,
    ifc_class: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    conn = connect()
    try:
        get_model(conn, model_id)
        clauses = ["model_id=?"]
        params: list[Any] = [model_id]
        if storey_guid:
            clauses.append("storey_guid=?")
            params.append(storey_guid)
        if ifc_class:
            clauses.append("ifc_class=?")
            params.append(ifc_class)
        if q:
            clauses.append("(name LIKE ? OR guid LIKE ? OR ifc_class LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)
        total = conn.execute(f"SELECT COUNT(*) AS n FROM elements WHERE {where}", params).fetchone()["n"]
        rows = [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM elements WHERE {where} ORDER BY ifc_class, name LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
        ]
        scope_note = None
        if storey_guid and storey_guid != "1Vhy2b2Mj9FRewx9CZZoux":
            scope_note = (
                "首版只为 05 层建立了 1,247 个构件的查询索引，并预提取 35 个预览网格。"
                "其他楼层显示 0 不代表模型没有构件；原始 IFC 仍保留，可按 GUID 按需提取几何。"
            )
        return {
            "rows": rows,
            "total": total,
            "limit": limit,
            "offset": offset,
            "loaded_scope": {
                "storey_guid": storey_guid or "all-indexed",
                "indexed_storey_guid": "1Vhy2b2Mj9FRewx9CZZoux",
                "indexed_elements": 1247,
                "preview_meshes": 35,
                "note": scope_note,
            },
        }
    finally:
        conn.close()


@app.get('/api/inspection-context')
def selected_inspection_context(guid: str):
    from .bim_context import inspection_options
    return inspection_options(guid)


@app.get("/api/models/{model_id}/elements/{guid}")
def element_detail(model_id: str, guid: str) -> dict[str, Any]:
    conn = connect()
    try:
        element = get_element(conn, model_id, guid)
        payload = mesh.target_payload()
        preview = next((item for item in payload["meshes"] if item["guid"] == guid), None)
        element["geometry_available"] = preview is not None
        cached = mesh.cached_mesh(guid)
        element['geometry_available'] = cached is not None
        element["bbox_m"] = cached.get('bbox_m') if cached else None
        return {"element": element}
    finally:
        conn.close()


@app.get("/api/models/{model_id}/elements/{guid}/mesh")
def element_mesh(model_id: str, guid: str) -> dict[str, Any]:
    conn = connect()
    try:
        get_model(conn, model_id)
        get_element(conn, model_id, guid)
    finally:
        conn.close()
    return {"mesh": mesh.mesh_for_guid(guid)}


@app.get("/api/models/{model_id}/mesh")
def model_mesh(model_id: str, scope: str = "target") -> dict[str, Any]:
    if scope != "target":
        raise APIError(422, "scope_unsupported", "首版只支持 scope=target；其他对象使用 /elements/{guid}/mesh")
    conn = connect()
    try:
        get_model(conn, model_id)
    finally:
        conn.close()
    return mesh.target_payload()


@app.get("/api/tasks")
def tasks(zone_id: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    return {"rows": task_list(zone_id, as_of)}


@app.get("/api/rules")
def rules(
    q: str = "",
    as_of: str = DEMO_CLOCK,
    include_retired: bool = False,
    top_k: int = Query(3, ge=1, le=20),
) -> dict[str, Any]:
    return rules_list(q, include_retired, top_k, as_of)


@app.get("/api/rules/{rule_id}")
def rule_detail(rule_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM rules WHERE rule_id=?", (rule_id,)).fetchone()
        if not row:
            raise APIError(404, "rule_not_found", f"条款不存在：{rule_id}")
        return {"rule": dict(row)}
    finally:
        conn.close()


@app.get("/api/evidence")
def evidence_list(
    stage: str | None = None,
    zone_id: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    conn = connect()
    try:
        scope,params=access.scoped_sql()
        clauses = [scope]
        if stage:
            clauses.append("stage=?")
            params.append(stage)
        if zone_id:
            clauses.append("zone_id=?")
            params.append(zone_id)
        if q:
            clauses.append("(evidence_id LIKE ? OR label LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])
        rows = [
            dict(row)
            for row in conn.execute(
                f"SELECT * FROM evidence WHERE {' AND '.join(clauses)} ORDER BY evidence_id",
                params,
            ).fetchall()
        ]
        for row in rows:
            row["observation"] = loads(row.pop("observation_json"), {})
            row['perception'] = loads(row.pop('perception_json','{}'), {})
            row["bim_guids"] = loads(row.pop("bim_guids_json"), [])
            row["image_url"] = f"/api/files/evidence/{row['evidence_id']}"
        return {"rows": rows, "total": len(rows)}
    finally:
        conn.close()


@app.get("/api/evidence/{evidence_id}")
def evidence_detail(evidence_id: str) -> dict[str, Any]:
    conn = connect()
    try:
        item = get_evidence(conn, evidence_id)
        item["image_url"] = f"/api/files/evidence/{evidence_id}"
        return {"evidence": item, 'zone':get_zone(conn,item['zone_id'])['data']}
    finally:
        conn.close()


@app.get("/api/files/evidence/{evidence_id}")
def evidence_file(evidence_id: str) -> FileResponse:
    conn = connect()
    try:
        item = get_evidence(conn, evidence_id)
    finally:
        conn.close()
    raw = item.get("file_path")
    if not raw:
        raise APIError(404, "file_not_found", "该证据没有文件")
    path = Path(raw)
    if not path.is_absolute():
        path = resolve_data_path(raw)
    else:
        path = path.resolve()
        allowed = [DATA_ROOT.resolve(), UPLOAD_DIR.resolve()]
        if not any(_is_relative_to(path, root) for root in allowed):
            raise APIError(403, "file_forbidden", "证据路径不在允许范围内")
    if not path.exists():
        raise APIError(404, "file_not_found", "证据文件不存在")
    return FileResponse(path, filename=path.name)


@app.get("/api/files/rules/{rule_id}")
def rule_file(rule_id: str) -> FileResponse:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM rules WHERE rule_id=?", (rule_id,)).fetchone()
        if not row:
            raise APIError(404, "rule_not_found", f"条款不存在：{rule_id}")
        source = row["source_path"]
    finally:
        conn.close()
    path = resolve_data_path(source)
    if not path.exists():
        raise APIError(404, "file_not_found", f"规范原文不存在：{source}")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


def localized(payload: Any, lang: str | None) -> Any:
    """按展示语言投影响应文案；失败时回退原文，绝不影响业务结果。"""
    try:
        return translate_payload(payload, lang)
    except Exception:
        return payload


@app.get("/api/summary")
def summary(x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    return localized(dashboard_summary(), x_display_lang)


@app.get("/api/cases")
def cases(status: str | None = None, limit: int = Query(100, ge=1, le=300),
          x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    return localized({"rows": list_cases(status, limit)}, x_display_lang)


@app.post("/api/cases", status_code=201)
def cases_create(payload: CaseCreateRequest) -> dict[str, Any]:
    return create_case(payload.model_dump())


@app.get("/api/cases/{case_id}")
def cases_detail(case_id: str,
                 x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    return localized(case_bundle(case_id), x_display_lang)


@app.post("/api/cases/{case_id}/analyze", status_code=202)
def cases_analyze(case_id: str, background: BackgroundTasks) -> dict[str, Any]:
    bundle, run_id = agent_start(case_id)
    background.add_task(durable.dispatch, run_id)
    return {"case": bundle["case"], "run_id": run_id, "status": "queued"}


@app.post('/api/cases/{case_id}/ask', status_code=202)
def cases_ask(case_id: str, payload: TaskRequest, background: BackgroundTasks) -> dict[str, Any]:
    if not DEMO_MODE and not live_model_configured():
        raise APIError(503, 'live_model_config_incomplete', '请先补齐真实模型配置并重启，当前任务尚未变更。')
    record_task_request(case_id,payload.message,payload.actor_id,payload.expected_case_version)
    return cases_analyze(case_id,background)


@app.get('/api/cases/{case_id}/messages')
def case_messages(case_id: str, actor_id: str = Query('demo-user', min_length=1, max_length=80),
                  x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    from .coordinator import messages_for_case
    case_bundle(case_id)
    return localized({'rows':messages_for_case(case_id,actor_id,12),'scope':'local_demo_session'}, x_display_lang)


def agent_start(case_id: str):
    from .services import start_analysis

    return start_analysis(case_id)


@app.get("/api/runs/{run_id}")
def runs_detail(run_id: str,
                x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    return localized({"run": get_run(run_id)}, x_display_lang)


@app.get('/api/runs/{run_id}/stream')
async def run_stream(run_id:str,request:Request):
    from .run_stream import events
    get_run(run_id)
    return StreamingResponse(events(run_id,request),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@app.get("/api/cases/{case_id}/runs")
def case_runs(case_id: str,
              x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    case_bundle(case_id)
    return localized({"rows": list_runs(case_id)}, x_display_lang)


@app.get("/api/agent/runs")
def agent_runs(limit: int = Query(20, ge=1, le=100),
               x_display_lang: str | None = Header(default=None, alias="X-Display-Lang")) -> dict[str, Any]:
    return localized({"rows": list_runs(None, limit)}, x_display_lang)


@app.get("/api/agent/architecture")
def agent_architecture() -> dict[str, Any]:
    return agent.architecture()


@app.post("/api/cases/{case_id}/review")
def cases_review(case_id: str, payload: ReviewRequest) -> dict[str, Any]:
    return review_case(case_id, payload.model_dump())


@app.post("/api/cases/{case_id}/implementation")
def cases_implementation(case_id: str, payload: ImplementationRequest) -> dict[str, Any]:
    return implement_case(case_id, payload.model_dump())


@app.post("/api/cases/{case_id}/evidence")
def cases_evidence(case_id: str, payload: EvidenceRequest) -> dict[str, Any]:
    return add_evidence(case_id, payload.evidence_ids, payload.actor)


@app.post("/api/cases/{case_id}/evidence/upload")
async def cases_evidence_upload(
    case_id: str,
    file: Annotated[UploadFile, File()],
    captured_at: Annotated[str, Form()] = DEMO_CLOCK,
    stage: Annotated[str, Form()] = "after",
    note: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXT:
        raise APIError(422, "file_type", "只支持 PNG/JPG/PDF")
    if file.content_type not in ALLOWED_UPLOAD_MIME:
        raise APIError(422, "file_mime", f"不支持的文件类型：{file.content_type}")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    head = b""
    try:
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                if len(head) < 8:
                    head += chunk[: 8 - len(head)]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise APIError(422, "file_too_large", "文件超过 20MB 上限")
                handle.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise APIError(422, "empty_file", "文件为空")
    magic_ok = (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or head.startswith(b"%PDF-")
    )
    if not magic_ok:
        target.unlink(missing_ok=True)
        raise APIError(422, "file_signature", "文件内容与 PNG/JPG/PDF 签名不符")
    return add_uploaded_evidence(case_id, file.filename or target.name, target, captured_at, stage, note)


@app.post("/api/cases/{case_id}/verify")
def cases_verify(case_id: str, payload: VerifyRequest) -> dict[str, Any]:
    return verify_case(case_id, payload.model_dump())


@app.post('/api/cases/{case_id}/evidence/{evidence_id}/inspect')
def inspect_case_image(case_id: str, evidence_id: str):
    from .vision import inspect_image
    return {'perception':inspect_image(case_id,evidence_id)}


@app.post('/api/cases/{case_id}/evidence/{evidence_id}/observation')
def confirm_case_observation(case_id: str, evidence_id: str, payload: ObservationRequest):
    from .vision import confirm_observation
    return confirm_observation(case_id,evidence_id,payload.observation,payload.source,
                               payload.note,payload.expected_case_version)


@app.post("/api/cases/{case_id}/reopen")
def cases_reopen(case_id: str, payload: ReopenRequest) -> dict[str, Any]:
    return reopen_case(case_id, payload.model_dump())


@app.get("/api/cases/{case_id}/export")
def cases_export(case_id: str, format: str = Query("json", pattern="^(json|md|docx)$"),
                 lang: str = Query("zh", pattern="^(zh|en)$")) -> Response:
    content, filename, media_type = export_case(case_id, format, lang)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/demo/reset")
def demo_reset() -> dict[str, Any]:
    for folder in (UPLOAD_DIR,):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    reset_db()
    return {"ok": True, "message": "已重置 runtime 演示数据库与上传件；原始资料未改动。", "summary": dashboard_summary()}


@app.get("/api/demo/acceptance/latest")
def acceptance_latest() -> dict[str, Any]:
    return acceptance_summary()


@app.post("/api/demo/acceptance/run-all")
def acceptance_run_all() -> dict[str, Any]:
    results = run_all_acceptance()
    return {"results": results, "summary": acceptance_summary()}


@app.post("/api/demo/acceptance/{test_id}")
def acceptance_run(test_id: str) -> dict[str, Any]:
    result = run_acceptance(test_id)
    return {"result": result, "summary": acceptance_summary()}


@app.get("/api/tools/unit-check")
def tools_unit_check(value: float, from_unit: str = Query("mm", alias="from"), world_z_m: float = 17.3) -> dict[str, Any]:
    return unit_check(value, from_unit, world_z_m)


@app.get("/api/files/plan")
def plan_file() -> FileResponse:
    path = PACKAGE_ROOT / "00_执行计划与自检" / "执行计划.docx"
    if not path.exists():
        path = PACKAGE_ROOT / "00_执行计划与自检" / "执行计划.md"
    if not path.exists():
        raise APIError(404, "file_not_found", "执行计划尚未生成")
    return FileResponse(path, filename=path.name)


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise APIError(404, "not_found", "接口不存在")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:

    @app.get("/", include_in_schema=False)
    def root_without_build():
        return HTMLResponse(
            "<h1>BIM 施工安全协同平台 API</h1>"
            "<p>前端尚未构建。请运行 <code>cd frontend && npm run build</code>，"
            "或开发模式访问 <code>http://127.0.0.1:5173</code>。</p>"
            "<p><a href='/api/docs'>API 文档</a></p>"
        )
