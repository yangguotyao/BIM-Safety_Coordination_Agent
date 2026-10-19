<script setup lang="ts">
import { t } from '../i18n'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Box, Check, Loader2, Upload } from 'lucide-vue-next'
import CaseProgress from '../components/CaseProgress.vue'
import ScopeEditor from '../components/ScopeEditor.vue'
import { api } from '../api'
import { actorId, errorMessage, refreshSummary, toast } from '../store'
import type { CaseBundle, Evidence,ScopeAnnotation } from '../types'
const route = useRoute(), router = useRouter()
const guid = typeof route.query.guid === 'string' ? route.query.guid : '0FOHK4aT910wgskSbVHn0U'
const options = ref<any>(null), rows = ref<Evidence[]>([])
const loading = ref(true), busy = ref(false), error = ref('')
const mode = ref(guid === '0FOHK4aT910wgskSbVHn0U' ? 'preset' : 'upload')
const selectedId = ref('EV-001'), title = ref(t('05 层楼板 · 安全检查'))
const request = ref(t('全面检查所选L05楼板区域的临边防护和人员暴露风险，结合现场证据与规范依据提出控制措施。'))
const asOf = ref('2026-10-16T09:00:00+08:00')
const file = ref<File | null>(null), preview = ref('')
const scope = reactive({ guid, edge_index:0, boundary_confirmed:false, exposure_distance_m:.6,
  worker_point_m:null as number[]|null,worker_point_source:'simulated' as ScopeAnnotation['worker_point_source'],
  activity:t('05层楼板区域机电材料转运'), planned_start:'2026-10-16T08:00:00+08:00',
  planned_end:'2026-10-16T12:00:00+08:00', owner:'演示机电班组' })
const selected = computed(() => rows.value.find(item => item.evidence_id === selectedId.value))
const annotation=computed<ScopeAnnotation>({get:()=>scope,set:value=>Object.assign(scope,value)})
const scenarios = [
  {id:'EV-001',title:t('临边防护缺失'),note:t('预置完整整改流程')},
  {id:'EV-003',title:t('栏杆高度不足'),note:t('预置高度检查')},
  {id:'EV-004',title:t('现场信息缺失'),note:t('预置待补证分支')},
  {id:'EV-007',title:t('防护正常样例'),note:t('预置无需整改分支')},
]
onMounted(async () => {
  try {
    options.value = await api.get(`/inspection-context?guid=${encodeURIComponent(guid)}`)
    if (!options.value.preset_available) mode.value = 'upload'
    rows.value = (await api.get<{rows:Evidence[]}>('/evidence?stage=before')).rows
  } catch (cause) { error.value = errorMessage(cause) }
  finally { loading.value = false }
})
function chooseFile(event:Event) {
  const picked = (event.target as HTMLInputElement).files?.[0] || null
  if (picked && picked.size > 20 * 1024 * 1024) { toast(t('文件不能超过20MB'),'warning'); return }
  if (preview.value) URL.revokeObjectURL(preview.value)
  file.value = picked
  preview.value = picked?.type.startsWith('image/') ? URL.createObjectURL(picked) : ''
}
onBeforeUnmount(() => { if (preview.value) URL.revokeObjectURL(preview.value) })
async function start() {
  if (busy.value || !options.value || !request.value.trim()) return
  busy.value = true
  let createdId = ''
  try {
    const created = await api.post<CaseBundle>('/cases', {
      title:title.value, request_text:request.value, actor_id:actorId, model_id:'S1-bSDD-example',
      task_id:'TASK-S1-001', zone_id:'ZONE-S1-L05-EDGE', bim_guids:[guid], as_of:asOf.value,
      evidence_ids:mode.value==='preset' ? [selectedId.value] : [],
      inspection_context:mode.value==='upload' ? scope : undefined,
    })
    createdId = created.case.case_id
    if (mode.value==='upload' && file.value) {
      const data = new FormData()
      data.append('file',file.value); data.append('captured_at',asOf.value)
      data.append('stage','before'); data.append('note',file.value.name)
      await api.postForm(`/cases/${createdId}/evidence/upload`,data)
    }
    await api.post(`/cases/${createdId}/analyze`)
    await refreshSummary()
    toast(mode.value==='upload' ? t('已发起分析；图像观察候选生成后请人工确认。') : t('检查已发起。'),'success')
    router.push(`/cases/${createdId}`)
  } catch (cause) {
    toast(errorMessage(cause),'error',8000)
    if (createdId) router.push(`/cases/${createdId}`)
  } finally { busy.value = false }
}
</script>

<template>
  <div class="page inspection-page">
    <header class="page-head"><div><h1>{{ t('发起安全检查') }}</h1></div><router-link class="btn" to="/cases">{{ t('检查记录') }}</router-link></header>
    <CaseProgress />
    <div v-if="loading" class="card setup-section"><Loader2 class="spin" :size="18" /> {{ t('正在读取选中构件的实际几何与可选边线…') }}</div>
    <div v-else-if="error" class="card setup-section"><p class="error-text">{{ error }}</p><router-link class="btn" to="/">{{ t('返回 BIM 选择楼板') }}</router-link></div>
    <div v-else class="setup-grid">
      <form @submit.prevent="start">
        <section class="card setup-section"><div class="setup-head"><span>01</span><h2>{{ t('确认检查对象与活动') }}</h2></div>
          <div class="scope-box"><Box :size="25" /><div><strong>{{ options.element.storey_name }} · {{ options.element.ifc_class }}</strong><p>{{ options.element.name }}</p><small class="mono">{{ guid }}</small></div><router-link :to="{path:'/',query:{guid}}">{{ t('查看 BIM') }}</router-link></div>
          <div class="mode-choice"><button v-if="options.preset_available" type="button" class="btn" :class="{'btn-primary':mode==='preset'}" @click="mode='preset'">{{ t('预置案例') }}</button><button type="button" class="btn" :class="{'btn-primary':mode==='upload'}" @click="mode='upload'">{{ t('上传新现场证据') }}</button></div>
          <div class="field"><label for="check-title">{{ t('检查名称') }}</label><input id="check-title" v-model="title" class="input" required /></div>
          <div class="field"><label for="check-time">{{ t('检查时刻') }}</label><input id="check-time" v-model="asOf" class="input" required /></div>
          <template v-if="mode==='upload'">
            <div class="field"><label for="activity">{{ t('施工活动') }}</label><input id="activity" v-model="scope.activity" class="input" required /></div>
            <div class="form-row"><div class="field"><label for="planned-start">{{ t('计划开始') }}</label><input id="planned-start" v-model="scope.planned_start" class="input" required /></div><div class="field"><label for="planned-end">{{ t('计划结束') }}</label><input id="planned-end" v-model="scope.planned_end" class="input" required /></div></div>
            <div class="field"><label for="owner">{{ t('实施责任主体') }}</label><input id="owner" v-model="scope.owner" class="input" required /></div>
            <ScopeEditor :guid="guid" v-model="annotation" />
            <label class="scope-confirm"><input v-model="scope.boundary_confirmed" type="checkbox" required /> {{ t('确认所选边线与模拟人员点') }}</label>
          </template>
        </section>
        <section class="card setup-section"><div class="setup-head"><span>02</span><h2>{{ mode==='preset' ? '选择预置现场证据' : '上传检查时证据' }}</h2></div>
          <div v-if="mode==='preset'" class="scenario-grid"><button v-for="item in scenarios" :key="item.id" type="button" class="scenario" :class="{active:selectedId===item.id}" @click="selectedId=item.id"><Check v-if="selectedId===item.id" :size="16" /><strong>{{ item.title }}</strong></button></div>
          <template v-else><label class="upload-area"><Upload :size="23" /><strong>选择现场图片或标注图</strong><input type="file" accept=".png,.jpg,.jpeg,.pdf" aria-label="上传检查时现场证据" required @change="chooseFile" /></label></template>
        </section>
        <section class="card setup-section"><div class="setup-head"><span>03</span><h2>描述检查任务</h2></div><div class="field"><label for="inspection-request">检查任务描述</label><textarea id="inspection-request" v-model="request" class="textarea" rows="4" required /></div></section>
        <button class="btn btn-primary start-button" :disabled="busy || (mode==='upload' && (!file || !scope.boundary_confirmed))"><Loader2 v-if="busy" :size="17" class="spin" />{{ busy ? '正在建立检查并提交分析…' : '开始检查' }}<ArrowRight :size="16" /></button>
      </form>
      <aside class="card evidence-preview"><h2>本次关联资料</h2><img v-if="mode==='preset' && selected" :src="selected.image_url" :alt="selected.label" /><img v-else-if="preview" :src="preview" alt="本次上传的证据预览" /><div v-else class="empty-preview"><Upload :size="32" /><p>{{ file?.name || '尚未选择文件' }}</p></div><strong>{{ mode==='preset' ? selected?.label : file?.name || '新现场证据' }}</strong></aside>
    </div>
  </div>
</template>

<style scoped>
.setup-grid{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(260px,1fr);gap:22px;margin-top:22px;align-items:start}.setup-section{padding:24px;margin-bottom:18px}.setup-head{display:flex;gap:12px;align-items:center;margin-bottom:20px}.setup-head>span{color:var(--blue);background:#e9f1ff;padding:7px;border-radius:9px;font-size:12px}.setup-head h2,.evidence-preview h2{font-size:17px}.scope-box{display:flex;align-items:center;gap:12px;padding:15px;background:var(--panel-2);border-radius:10px}.scope-box>div{min-width:0;flex:1}.scope-box p{font-size:12px;line-height:1.6;color:var(--muted);margin:5px 0}.scope-box small{font-size:11px;overflow-wrap:anywhere}.scope-box>a{font-size:12px;white-space:nowrap}.mode-choice{display:flex;gap:9px;margin:18px 0;flex-wrap:wrap}.field{margin-top:14px}.form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.form-row .field{min-width:0}.scope-confirm{display:flex;align-items:flex-start;gap:9px;margin-top:18px;font-size:12px;line-height:1.8;color:var(--muted)}.scope-confirm input{margin-top:5px}.scenario-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.scenario{position:relative;text-align:left;border:1px solid var(--line);background:var(--panel-2);border-radius:10px;padding:17px;color:var(--text)}.scenario.active{border-color:var(--blue);background:#edf4ff}.scenario strong{display:block;font-size:15px;line-height:1.5;padding-right:20px}.scenario svg{position:absolute;right:10px;top:12px;color:var(--blue)}.upload-area{display:grid;gap:13px;justify-items:center;border:1px dashed #9cb4d0;border-radius:12px;padding:26px 12px;background:var(--panel-2);font-size:13px}.upload-area input{max-width:100%;font-size:12px}.setup-section>.small{line-height:1.8;margin-top:14px}.evidence-preview{padding:22px;position:sticky;top:90px}.evidence-preview img{width:100%;max-height:310px;object-fit:contain;border:1px solid var(--line);border-radius:9px;margin:18px 0}.evidence-preview>strong{display:block;font-size:14px;overflow-wrap:anywhere}.empty-preview{display:grid;gap:14px;justify-items:center;padding:50px 15px;background:var(--panel-2);margin:18px 0;border-radius:10px;color:var(--muted);font-size:12px}.start-button{width:100%;height:47px;margin-bottom:20px}.error-text{color:var(--red);margin-bottom:16px}@media(max-width:1050px){.setup-grid{grid-template-columns:1fr}.evidence-preview{position:static}}@media(max-width:600px){.setup-section{padding:18px}.form-row,.scenario-grid{grid-template-columns:1fr}.scope-box{flex-wrap:wrap}}
</style>
