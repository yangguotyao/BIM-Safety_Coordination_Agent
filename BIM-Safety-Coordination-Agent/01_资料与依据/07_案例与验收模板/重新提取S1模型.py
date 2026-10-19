from pathlib import Path
import sys,json,collections,csv,time,hashlib
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'_工作文件/工具依赖'))
import ifcopenshell,ifcopenshell.util.element as el,ifcopenshell.util.unit as unit,ifcopenshell.geom,ifcopenshell.util.placement as placement
p=root/'03_数据集/S1/bSDD_references_example.ifc'
t=time.time();m=ifcopenshell.open(str(p));print('OPENED',m.schema,'seconds',round(time.time()-t,1),flush=True)
classes=['IfcBuilding','IfcBuildingStorey','IfcElement','IfcSlab','IfcWall','IfcColumn','IfcOpeningElement','IfcTask','IfcWorkSchedule','IfcRelAssignsToProcess']
counts={x:len(m.by_type(x)) for x in classes};print('COUNTS',counts,flush=True)
scale=unit.calculate_unit_scale(m);storeys=m.by_type('IfcBuildingStorey');floors=[]
for s in storeys:
 els=el.get_decomposition(s);a=[x for x in els if x.is_a('IfcElement')]
 floors.append({'guid':s.GlobalId,'name':s.Name,'elevation_attribute_m':(s.Elevation or 0)*scale,'placement_z_m':float(placement.get_local_placement(s.ObjectPlacement)[2,3])*scale,'elements':len(a),'slabs':sum(x.is_a('IfcSlab') for x in a)})
print('FLOORS',floors,flush=True)
candidates=[]
for op in m.by_type('IfcOpeningElement'):
 for v in op.VoidsElements or []:
  host=v.RelatingBuildingElement
  if host.is_a('IfcSlab'):
   st=el.get_container(host)
   candidates.append((op,host,st))
print('SLAB_OPENINGS',len(candidates),flush=True)
settings=ifcopenshell.geom.settings();settings.set(settings.USE_WORLD_COORDS,True)
def geom(x):
 s=ifcopenshell.geom.create_shape(settings,x);vs=s.geometry.verts;fs=s.geometry.faces
 pts=[list(vs[i:i+3]) for i in range(0,len(vs),3)]
 return {'guid':x.GlobalId,'ifc_class':x.is_a(),'name':x.Name or '', 'vertices':pts,'triangles':[list(fs[i:i+3]) for i in range(0,len(fs),3)],'bbox_m':{'min':[min(v[i] for v in pts) for i in range(3)],'max':[max(v[i] for v in pts) for i in range(3)]}}
chosen=None
ranked=sorted(candidates,key=lambda q: (0 if q[2] and 2<((q[2].Elevation or 0)*scale)<25 else 1, q[0].GlobalId))
for op,h,st in ranked[:40]:
 try:
  g=geom(op);b=g['bbox_m'];dims=[b['max'][i]-b['min'][i] for i in range(3)]
  if min(dims[0],dims[1])>.15 and max(dims[0],dims[1])<12:
   chosen=(op,h,st,g);break
 except Exception:pass
if chosen:
 op,host,st,g=chosen;target={'kind':'actual_ifc_slab_opening','guid':op.GlobalId,'host_guid':host.GlobalId,'storey_guid':st.GlobalId if st else None,'storey_name':st.Name if st else None,'bbox_m':g['bbox_m']};meshes=[g]
else:
 f=next((x for x in floors if (x['name'] or '').startswith('05 ') and x['slabs']), next(x for x in floors if x['slabs']))
 st=m.by_guid(f['guid']); slab_geoms=[]
 for x in el.get_decomposition(st):
  if x.is_a('IfcSlab'):
   try:
    q=geom(x);b=q['bbox_m'];slab_geoms.append(((b['max'][0]-b['min'][0])*(b['max'][1]-b['min'][1]),x,q))
   except Exception:pass
 _,host,g=max(slab_geoms,key=lambda x:x[0]);target={'kind':'slab_edge_for_simulated_inspection','guid':host.GlobalId,'host_guid':host.GlobalId,'storey_guid':st.GlobalId,'storey_name':st.Name,'bbox_m':g['bbox_m']};meshes=[g]
st=m.by_guid(target['storey_guid']) if target['storey_guid'] else None
context=[x for x in el.get_decomposition(st) if x.is_a('IfcElement')] if st else [host]
if chosen:context.append(op)
# 保留选定楼层真实构件索引 不将未算的几何写成零
rows=[]
for x in sorted(set(context),key=lambda x:x.GlobalId):
 rows.append({'model_id':'S1-bSDD-example','model_version':hashlib.sha256(p.read_bytes()).hexdigest()[:12] if False else '4075c44a6e47','guid':x.GlobalId,'ifc_class':x.is_a(),'name':x.Name or '', 'storey_guid':st.GlobalId if st else '', 'storey_name':st.Name if st else ''})
out=root/'03_数据集/S1/解析结果';out.mkdir(exist_ok=True)
with (out/'选定楼层构件索引.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
# 按真实世界包围盒筛选附近构件 只生成静态预览数据 不代替主模型
bb=target['bbox_m'];center=[(bb['min'][i]+bb['max'][i])/2 for i in range(3)]
errors=[]
near=[x for x in context if x.is_a() in ['IfcSlab','IfcWall','IfcWallStandardCase','IfcColumn','IfcBeam'] and x.GlobalId not in {z['guid'] for z in meshes}]
for x in near[:160]:
 try:
  q=geom(x);b=q['bbox_m'];c=[(b['min'][i]+b['max'][i])/2 for i in range(3)]
  if sum((c[i]-center[i])**2 for i in range(2))<25**2:meshes.append(q)
  if len(meshes)>=35:break
 except Exception as e:errors.append({'guid':x.GlobalId,'error':str(e)[:200]})
summary={'schema':m.schema,'ifcopenshell_version':ifcopenshell.version,'source_file':str(p.relative_to(root)),'source_sha256':'4075c44a6e4769b10a0f3ef2c925847899c76444ea33b81d3caffa85f321f9f2','length_unit_to_m':scale,'counts':counts,'storeys':floors,'actual_slab_opening_count':len(candidates),'selected_target':target,'selected_storey_index_count':len(rows),'preview_mesh_count':len(meshes),'geometry_errors':errors,'data_limits':['本 IFC 无显式 IfcOpeningElement 实体，不等于几何无洞口','无 IfcTask 或 IfcWorkSchedule，进度为独立模拟数据','全部楼层 Elevation 属性为零，实际标高需使用放置变换及几何坐标','板边防护和人员暴露需要现场或标注证据，单凭设计模型不能确认隐患'],'validation_scope':'文件可打开、实体及关系可查询、选定对象几何可计算；不是全模型规范或几何有效性认证'}
(out/'模型检查结果.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(out/'区域几何预览.json').write_text(json.dumps({'coordinate_system':'IFC world coordinates in meters','target':target,'meshes':meshes},ensure_ascii=False))
print('RESULT',json.dumps(summary,ensure_ascii=False),flush=True)
