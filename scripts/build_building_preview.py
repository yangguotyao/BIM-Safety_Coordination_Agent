"""Export the local S1 IFC's represented elements as a batched, metre-scale GLB."""
from __future__ import annotations

from array import array
from collections import Counter
import json
from pathlib import Path
import struct
import time

import ifcopenshell
import ifcopenshell.geom

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'BIM-Safety-Coordination-Agent'
SOURCE = PACKAGE / '01_资料与依据/03_数据集/S1/bSDD_references_example.ifc'
OUTPUT = PACKAGE / '02_网站源码/frontend/public/bim'


def build():
    started = time.monotonic()
    model = ifcopenshell.open(str(SOURCE))
    elements = [e for e in model.by_type('IfcElement') if e.Representation and not e.is_a('IfcFeatureElement')]
    containment = {}
    floors = {}
    for relation in model.by_type('IfcRelContainedInSpatialStructure'):
        parent = relation.RelatingStructure
        if parent.is_a('IfcBuildingStorey'):
            floors[parent.GlobalId] = {'guid': parent.GlobalId, 'name': parent.Name, 'elevation_m': parent.Elevation}
            for element in relation.RelatedElements:
                containment[element.GlobalId] = parent.GlobalId
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    settings.set(settings.WELD_VERTICES, True)
    settings.set('mesher-linear-deflection', .05)
    iterator = ifcopenshell.geom.iterator(settings, model, 2, include=elements)
    groups = {}
    guids = set()
    minimum, maximum = [float('inf')]*3, [float('-inf')]*3
    print(f'IFC opened; {len(elements)} represented elements to export.', flush=True)
    if not iterator.initialize():
        raise RuntimeError('IFC geometry iterator did not initialize')
    while True:
        shape = iterator.get()
        vertices, indices = shape.geometry.verts, shape.geometry.faces
        if vertices and indices:
            element = model.by_guid(shape.guid)
            key = (containment.get(shape.guid, ''), element.is_a())
            group = groups.setdefault(key, {'vertices': array('d'), 'indices': array('I'), 'count': 0})
            offset = len(group['vertices'])//3
            group['vertices'].extend(vertices)
            group['indices'].extend(i+offset for i in indices)
            group['count'] += 1
            guids.add(shape.guid)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], min(vertices[axis::3]))
                maximum[axis] = max(maximum[axis], max(vertices[axis::3]))
            if len(guids)%1000 == 0:
                print(f'{len(guids)} elements exported in {time.monotonic()-started:.1f}s', flush=True)
        if not iterator.next():
            break
    origin = [(a+b)/2 for a,b in zip(minimum,maximum)]
    gltf = {'asset': {'version':'2.0','generator':'S1 IFC overview export'},
            'scene':0, 'scenes':[{'nodes':[]}], 'nodes':[], 'meshes':[],
            'accessors':[], 'bufferViews':[], 'materials':[], 'buffers':[]}
    binary = bytearray()
    materials = {}
    palette = {'IfcSlab':[.64,.72,.78,1], 'IfcWall':[.80,.83,.85,1],
               'IfcWallStandardCase':[.80,.83,.85,1], 'IfcWindow':[.29,.49,.62,1],
               'IfcDoor':[.40,.53,.62,1], 'IfcPlate':[.49,.63,.70,1],
               'IfcMember':[.37,.49,.57,1], 'IfcCovering':[.77,.80,.81,1]}

    def attribute(data, kind, component, count, low=None, high=None):
        while len(binary)%4:
            binary.append(0)
        view = len(gltf['bufferViews'])
        gltf['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data)})
        binary.extend(data)
        item = {'bufferView':view,'componentType':component,'count':count,'type':kind}
        if low is not None:
            item.update(min=low,max=high)
        gltf['accessors'].append(item)
        return len(gltf['accessors'])-1

    for (floor,kind), group in sorted(groups.items()):
        if kind not in materials:
            materials[kind] = len(gltf['materials'])
            gltf['materials'].append({'name':kind, 'doubleSided':True,
                'pbrMetallicRoughness':{'baseColorFactor':palette.get(kind,[.62,.68,.72,1]),
                                      'metallicFactor':.08,'roughnessFactor':.78}})
        vertices = group['vertices']
        positions = array('f')
        for i in range(0,len(vertices),3):
            positions.extend((vertices[i]-origin[0],vertices[i+2]-origin[2],-(vertices[i+1]-origin[1])))
        low = [min(positions[i::3]) for i in range(3)]
        high = [max(positions[i::3]) for i in range(3)]
        pos = attribute(positions.tobytes(),'VEC3',5126,len(positions)//3,low,high)
        small_indices = len(positions)//3 <= 65536
        index_data = array('H',group['indices']) if small_indices else group['indices']
        idx = attribute(index_data.tobytes(),'SCALAR',5123 if small_indices else 5125,len(index_data))
        gltf['meshes'].append({'primitives':[{'attributes':{'POSITION':pos},'indices':idx,'material':materials[kind]}]})
        gltf['nodes'].append({'name':f'{floors.get(floor,{}).get("name","Building")} / {kind}',
            'mesh':len(gltf['meshes'])-1,'extras':{'storeyGuid':floor,'ifcClass':kind,'elementCount':group['count']}})
        gltf['scenes'][0]['nodes'].append(len(gltf['nodes'])-1)
    gltf['buffers'].append({'byteLength':len(binary)})
    document = json.dumps(gltf,separators=(',',':')).encode('utf-8')
    document += b' '*((-len(document))%4)
    binary += b'\0'*((-len(binary))%4)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    destination = OUTPUT/'s1-building.glb'
    destination.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(document)+len(binary))+
        struct.pack('<I4s',len(document),b'JSON')+document+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
    metadata = {'model_id':'S1-bSDD-example','model_version':'4075c44a6e47','units':'m',
        'source':'bSDD_references_example.ifc','represented_elements':len(elements),
        'exported_elements':len(guids),'batches':len(groups),
        'triangles':sum(len(g['indices'])//3 for g in groups.values()),
        'bbox_m':{'min':minimum,'max':maximum},'origin_ifc':origin,
        'storeys':sorted(floors.values(),key=lambda f:f['elevation_m'] or 0),
        'classes':dict(Counter({k:sum(g['count'] for (_,c),g in groups.items() if c==k) for _,k in groups})),
        'bytes':destination.stat().st_size,'elapsed_seconds':round(time.monotonic()-started,1)}
    (OUTPUT/'s1-building.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=True),flush=True)


if __name__ == '__main__':
    build()
