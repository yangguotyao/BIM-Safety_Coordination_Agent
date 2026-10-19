<script setup lang="ts">
import { computed,nextTick,ref,watch } from 'vue'
import { Crosshair,RotateCcw,Loader2 } from 'lucide-vue-next'
import BimViewer from './BimViewer.vue'
import { api } from '../api'
import { errorMessage } from '../store'
import type { MeshPayload,MeshData,ScopeAnnotation } from '../types'
const props=withDefaults(defineProps<{guid:string;modelValue:ScopeAnnotation;readonly?:boolean}>(),{readonly:false})
const emit=defineEmits<{'update:modelValue':[value:ScopeAnnotation]}>()
const options=ref<any>(null),meshes=ref<MeshData[]>([]),error=ref(''),loading=ref(false),placing=ref(false)
const viewer=ref<InstanceType<typeof BimViewer>|null>(null)
let sequence=0
const edges=computed<number[][][]>(()=>options.value?.edge_options || [])
const current=computed(()=>props.modelValue.guid===props.guid ? props.modelValue : {guid:props.guid,edge_index:0,worker_point_m:null,worker_point_source:'simulated',boundary_confirmed:false} as ScopeAnnotation)
const defaultPoint=(index:number)=>{
  const [a,b]=edges.value[index] || []
  if (!a || !b) return null
  const length=Math.hypot(b[0]-a[0],b[1]-a[1])
  return [(a[0]+b[0])/2-(b[1]-a[1])/length*.6,(a[1]+b[1])/2+(b[0]-a[0])/length*.6,(a[2]+b[2])/2].map(v=>Math.round(v*1000)/1000)
}
const point=computed(()=>current.value.worker_point_m || defaultPoint(current.value.edge_index))
const distance=computed(()=>{
  const [a,b]=edges.value[current.value.edge_index] || [],p=point.value
  if (!a || !b || !p) return '—'
  const dx=b[0]-a[0],dy=b[1]-a[1]
  const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
  return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy).toFixed(3)
})
function update(values:Partial<ScopeAnnotation>) {
  if (!props.readonly) emit('update:modelValue',{...current.value,guid:props.guid,...values})
}
function selectEdge(index:number) { update({edge_index:index,worker_point_m:defaultPoint(index),boundary_confirmed:false}) }
function movePoint(value:number[]) { update({worker_point_m:value,boundary_confirmed:false}) }
function coordinate(axis:number,event:Event) {
  const value=Number((event.target as HTMLInputElement).value)
  if (!point.value || !Number.isFinite(value)) return
  const next=point.value.slice();next[axis]=value;movePoint(next)
}
watch(()=>props.guid,async guid=>{
  const request=++sequence;options.value=null;meshes.value=[];placing.value=false;error.value='';loading.value=true
  try {
    const [context,payload]=await Promise.all([api.get<any>(`/inspection-context?guid=${encodeURIComponent(guid)}`),api.get<MeshPayload>('/models/S1-bSDD-example/mesh?scope=target')])
    let all=payload.meshes
    if (!all.some(mesh=>mesh.guid===guid)) {
      const value=await api.get<{mesh:MeshData}>(`/models/S1-bSDD-example/elements/${encodeURIComponent(guid)}/mesh`)
      all=[...all,value.mesh]
    }
    if (request!==sequence) return
    options.value=context;meshes.value=all
    if (current.value.worker_point_m==null) update({edge_index:0,worker_point_m:defaultPoint(0)})
    await nextTick();viewer.value?.focusGuid(guid)
  } catch(cause) { if(request===sequence) error.value=errorMessage(cause) }
  finally { if(request===sequence) loading.value=false }
},{immediate:true})
</script>

<template>
  <div class="scope-editor">
    <div class="scope-tools"><label>检查边线<select class="select" aria-label="三维检查边线" :value="current.edge_index" :disabled="readonly || loading" @change="selectEdge(Number(($event.target as HTMLSelectElement).value))"><option v-for="(edge,index) in edges" :key="index" :value="index">边线 {{ index+1 }} · {{ Math.hypot(...edge[0].map((v,i)=>edge[1][i]-v)).toFixed(2) }} m</option></select></label><button type="button" class="btn" :class="{'btn-primary':placing}" :disabled="readonly || loading" @click="placing=!placing"><Crosshair :size="16" />{{ placing ? '正在标注人员点' : '标注人员点' }}</button><button type="button" class="btn btn-icon" aria-label="重置标注视角" @click="viewer?.resetView()"><RotateCcw :size="15" /></button><strong class="distance-reading">{{ distance }} <small>m · 距边线</small></strong></div>
    <div v-if="error" class="scope-error">{{ error }}</div>
    <div class="scope-canvas"><BimViewer ref="viewer" :meshes="meshes" :target-guid="guid" :selected-guid="guid" :edge-segments="edges" :selected-edge-index="current.edge_index" :evidence-point="point" evidence-label="检查人员点" :point-placement="placing && !readonly" @select-edge="selectEdge" @place-point="movePoint" /><span v-if="loading" class="scope-loading"><Loader2 class="spin" :size="18" />加载检查几何</span></div>
    <div class="point-fields"><label v-for="(axis,index) in ['X','Y','Z']" :key="axis">{{ axis }}（m）<input class="input" type="number" step="any" :aria-label="`标注人员 ${axis}`" :value="point?.[index]?.toFixed(3)" :disabled="readonly || loading" @change="coordinate(index,$event)" /></label><label>点位来源<select class="select" aria-label="人员点来源" :value="current.worker_point_source" :disabled="readonly" @change="update({worker_point_source:($event.target as HTMLSelectElement).value as ScopeAnnotation['worker_point_source']})"><option value="simulated">模拟标注</option><option value="human_observed">现场人工标注</option></select></label></div>
  </div>
</template>
<style scoped>
.scope-editor{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin-top:18px}.scope-tools{display:flex;gap:10px;align-items:flex-end;padding:14px;flex-wrap:wrap}.scope-tools>label{min-width:160px;flex:1;font-size:13px;display:grid;gap:5px}.distance-reading{font-size:22px;color:var(--blue);padding:7px 3px;white-space:nowrap}.distance-reading small{font-size:12px;font-weight:400;color:var(--muted)}.scope-canvas{height:480px;position:relative}.point-fields{display:grid;grid-template-columns:repeat(3,1fr) 1.3fr;gap:12px;padding:16px;border-top:1px solid var(--line)}.point-fields label{display:grid;gap:6px;min-width:0;font-size:13px;color:var(--text-soft)}.scope-error{padding:14px;color:var(--red)}.scope-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;background:#f5f8fbe8;color:var(--muted)}@media(max-width:600px){.point-fields{grid-template-columns:repeat(2,1fr)}.distance-reading{margin-left:auto}.scope-tools .btn{font-size:12px}}
</style>
