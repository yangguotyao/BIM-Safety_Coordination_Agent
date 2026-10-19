"""A selected IFC slab becomes an explicit, human-confirmed inspection scope."""
import math
import uuid
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from .config import MODEL_ID, PROJECT_ID, STOREY_GUID, TARGET_GUID
from .db import connect, dumps
from .errors import APIError
from .mesh import mesh_for_guid
from .tools import get_element, get_model, get_zone, parse_dt


class ScopeAnnotation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    guid: str
    edge_index: int = Field(default=0, ge=0)
    boundary_confirmed: bool = False
    exposure_distance_m: float = Field(default=.6, ge=0, le=20)
    worker_point_m: list[float] | None = Field(default=None,min_length=3,max_length=3)
    worker_point_source: Literal['simulated','human_observed'] = 'simulated'


class InspectionContext(ScopeAnnotation):
    activity: str = Field(min_length=1, max_length=200)
    planned_start: str
    planned_end: str
    owner: str = Field(min_length=1, max_length=80)


def top_edges(mesh):
    top = max(v[2] for v in mesh['vertices'])
    edges = {}
    for triangle in mesh['triangles']:
        vertices = [mesh['vertices'][i] for i in triangle]
        if any(abs(v[2] - top) > .005 for v in vertices):
            continue
        for a, b in zip(vertices, vertices[1:] + vertices[:1]):
            key = tuple(sorted((tuple(round(x, 4) for x in a), tuple(round(x, 4) for x in b))))
            edges[key] = edges.get(key, 0) + 1
    boundary = [list(map(list, pair)) for pair, count in edges.items()
                if count == 1 and math.dist(pair[0][:2], pair[1][:2]) > .1]
    return sorted(boundary, key=lambda pair: math.dist(pair[0], pair[1]), reverse=True)[:12]


def inspection_options(guid: str):
    conn = connect()
    try:
        element = get_element(conn, MODEL_ID, guid)
        model = get_model(conn, MODEL_ID)
        if element['ifc_class'] != 'IfcSlab' or element['storey_guid'] != STOREY_GUID:
            raise APIError(422, 'inspection_scope', '本版临边检查支持05层楼板，请先在模型中选择楼板。')
        existing = get_zone(conn, 'ZONE-S1-L05-EDGE') if guid == TARGET_GUID else None
    finally:
        conn.close()
    geometry = mesh_for_guid(guid)
    edges = top_edges(geometry)
    if existing:
        edges.insert(0, existing['data']['edge_segment_m'])
    if not edges:
        raise APIError(422, 'boundary_unknown', '没有可校核的上表面边线，不能自动创建临边检查区域。')
    return {'element': {**element, 'bbox_m':geometry['bbox_m']}, 'model_id':MODEL_ID,
            'model_version':model['version'], 'edge_options':edges,
            'preset_available':guid == TARGET_GUID,
            'note':'边线从IFC几何提取，仅是检查边界候选；临空性质和人员位置需人工确认。'}


def annotation_data(spec, options):
    if not spec.boundary_confirmed:
        raise APIError(422,'boundary_confirmation_required','请确认所选检查边线和人员点')
    if spec.edge_index >= len(options['edge_options']):
        raise APIError(422,'unknown_boundary','所选检查边线不存在')
    edge = options['edge_options'][spec.edge_index]
    a,b = edge
    length = math.dist(a[:2],b[:2])
    point = spec.worker_point_m or [(a[0]+b[0])/2-(b[1]-a[1])/length*spec.exposure_distance_m,
        (a[1]+b[1])/2+(b[0]-a[0])/length*spec.exposure_distance_m,(a[2]+b[2])/2]
    bbox = options['element']['bbox_m']
    if not all(math.isfinite(v) for v in point) or any(not bbox['min'][i]-20<=point[i]<=bbox['max'][i]+20 for i in range(3)):
        raise APIError(422,'point_out_of_scope','人员点必须位于所选构件周边20m范围内')
    from .tools import _point_segment_distance_2d
    distance,_,_ = _point_segment_distance_2d(*point[:2],*a[:2],*b[:2])
    return {'guid':spec.guid,'edge_index':spec.edge_index,'edge_segment_m':edge,'worker_point_m':point,
        'worker_point_source':spec.worker_point_source,
        'worker_point_provenance':'人工模拟标注' if spec.worker_point_source=='simulated' else '人工现场标注',
        'distance_to_edge_m':round(distance,3),'boundary_confirmed':True,'exposure_threshold_m':1.0,
        'target':{'guid':spec.guid,'bbox_m':bbox},'geometry_source':'selected_ifc_top_surface_boundary'}


def save_scope(case_id, payload):
    from .case_edits import editable_case,record_edit
    from .db import transaction
    from .services import case_bundle
    spec=ScopeAnnotation.model_validate({k:v for k,v in payload.items() if k!='expected_case_version'})
    with transaction() as conn:
        case=editable_case(conn,case_id,payload['expected_case_version'])
        if spec.guid not in case['bim_guids']:
            raise APIError(422,'scope_guid_mismatch','标注构件必须属于本案例')
        data=annotation_data(spec,inspection_options(spec.guid))
        conn.execute('UPDATE cases SET scope_json=? WHERE case_id=?',(dumps(data),case_id))
        record_edit(conn,case,'scope_updated',data)
    return case_bundle(case_id)


def prepare_context(value: dict, as_of: str):
    spec = InspectionContext.model_validate(value)
    if not spec.boundary_confirmed:
        raise APIError(422, 'boundary_confirmation_required', '请确认本次采用的检查边线和模拟人员位置。')
    options = inspection_options(spec.guid)
    start, end, check = map(parse_dt, (spec.planned_start, spec.planned_end, as_of))
    if not start or not end or not check or not start <= check <= end or start >= end:
        raise APIError(422, 'task_time_window', '检查时刻必须处于有效的施工活动时间窗内。')
    if spec.edge_index >= len(options['edge_options']):
        raise APIError(422, 'unknown_boundary', '所选检查边线不存在，请刷新模型上下文。')
    annotation = annotation_data(spec,options)
    suffix = uuid.uuid4().hex[:10].upper()
    zone_id, task_id = 'ZONE-SELECTED-' + suffix, 'TASK-SELECTED-' + suffix
    element = options['element']
    data = {**annotation,'zone_id':zone_id,
            'geometry_source':'selected_ifc_top_surface_boundary',
            'exposure_threshold_m':1.0, 'boundary_confirmed':True,
            'fall_reference_note':'坠落高度需另行测量或明确作为模拟观察录入。'}
    zone = {'zone_id':zone_id, 'model_id':MODEL_ID, 'storey_guid':element['storey_guid'],
            'storey_name':element['storey_name'], 'target_guid':spec.guid, 'data':data}
    task = {'task_id':task_id,'project_id':PROJECT_ID,'model_id':MODEL_ID,'zone_id':zone_id,
            'activity':spec.activity,'planned_start':spec.planned_start,'planned_end':spec.planned_end,
            'owner':spec.owner,'provenance':'human_authored_demo_schedule',
            'note':'用户编制的演示活动，关联实际选中IFC构件，非原项目实测进度。'}
    return zone, task


def store_context(conn, zone, task):
    conn.execute('INSERT INTO zones (zone_id,model_id,storey_guid,storey_name,target_guid,data_json) VALUES (?,?,?,?,?,?)',
                 (zone['zone_id'], MODEL_ID, zone['storey_guid'], zone['storey_name'],
                  zone['target_guid'], dumps(zone['data'])))
    # Explicit column names keep the insert compatible with existing databases.
    conn.execute('''INSERT INTO tasks (task_id,project_id,model_id,zone_id,activity,planned_start,planned_end,
                 owner,provenance,note,bim_guids_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                 tuple(task[key] for key in ['task_id','project_id','model_id','zone_id','activity',
                       'planned_start','planned_end','owner','provenance','note']) + (dumps([zone['target_guid']]),))
