<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { BookOpen, Box, ChevronLeft, ChevronRight, ClipboardList, FileText, FlaskConical, GitBranch, Images, LayoutDashboard, Menu, Plus, ShieldCheck, UserRound, Wifi, WifiOff } from 'lucide-vue-next'
import { bootstrap, store } from '../store'
import ToastHost from './ToastHost.vue'
import {api} from '../api'
async function signOut(){await api.post('/access/logout');window.location.reload()}
const route = useRoute()
const collapsed = ref(false)
const mobileOpen = ref(false)
const nav = [
  { label: '业务工作台', items: [
    { to: '/', label: 'BIM 工作台', icon: Box },
    { to: '/overview', label: '业务总览', icon: LayoutDashboard },
    { to: '/#home-task', label: '发起安全检查', icon: Plus },
    { to: '/cases', label: '检查记录', icon: ClipboardList },
  ] },
  { label: '项目资料', items: [
    { to: '/evidence', label: '现场证据', icon: Images },
    { to: '/knowledge', label: '规范依据', icon: BookOpen },
  ] },
]
const secondaryNav = [
  { to: '/agent', label: 'Agent 运行记录', icon: GitBranch },
  { to: '/acceptance', label: '测试与验收', icon: FlaskConical },
  { to: '/about', label: '方法与数据说明', icon: FileText },
]
const active = (path: string) => path==='/#home-task' ? route.path==='/' && route.hash==='#home-task' : path==='/' ? route.name==='bim' && !route.hash : route.path===path || route.path.startsWith(path+'/')
const online = computed(() => Boolean(store.health?.ok))
const modeLabel = computed(() => store.health?.mode === 'live' ? '模型已连接' : store.health?.mode === 'live_incomplete' ? '模型未配置' : '规则演示模式')
onMounted(bootstrap)
</script>

<template>
  <div class="shell" :class="{ collapsed, 'mobile-open': mobileOpen }">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark"><ShieldCheck :size="25" /></span><div v-show="!collapsed" class="brand-text"><strong>BIM 安全协同</strong></div><button class="collapse-btn" :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed"><ChevronRight v-if="collapsed" :size="15" /><ChevronLeft v-else :size="15" /></button></div>
      <div v-show="!collapsed" class="project-card"><span class="project-dot" /><div><small>当前项目</small><strong>S1 建设项目</strong></div></div>
      <nav class="nav" aria-label="主导航">
        <div v-for="group in nav" :key="group.label" class="nav-group"><p v-show="!collapsed" class="nav-label">{{ group.label }}</p><router-link v-for="item in group.items" :key="item.to" :to="item.to" class="nav-item" :class="{ active: active(item.to) }" :title="collapsed ? item.label : undefined" @click="mobileOpen = false"><component :is="item.icon" :size="18" /><span v-show="!collapsed">{{ item.label }}</span><ChevronRight v-if="!collapsed && active(item.to)" :size="13" class="nav-arrow" /></router-link></div>
        <details class="system-nav" :open="secondaryNav.some(item => active(item.to))"><summary :title="collapsed ? '运行与说明' : undefined">{{ collapsed ? '···' : '运行与说明' }}</summary><router-link v-for="item in secondaryNav" :key="item.to" :to="item.to" class="nav-item" :class="{ active: active(item.to) }" :title="item.label" @click="mobileOpen = false"><component :is="item.icon" :size="17" /><span v-show="!collapsed">{{ item.label }}</span></router-link></details>
      </nav>
      <div class="sidebar-foot"><div class="connection"><component :is="online ? Wifi : WifiOff" :size="14" /><span v-show="!collapsed">{{ online ? '服务已连接' : '正在连接服务' }}</span><i :class="{ online }" /></div><div v-show="!collapsed" class="workspace-user"><span><UserRound :size="18" /></span><div><strong>{{ store.access?.mode==='token' ? store.access.label : '演示安全员' }}</strong><button v-if="store.access?.mode==='token'" class="btn btn-sm" @click="signOut">退出</button></div></div></div>
    </aside>
    <button v-if="mobileOpen" class="nav-scrim" aria-label="关闭导航" @click="mobileOpen = false" />
    <div class="main">
      <header class="topbar"><div class="crumbs"><button class="mobile-menu" aria-label="展开导航" @click="mobileOpen = !mobileOpen"><Menu :size="21" /></button><span class="crumb-home">安全协同工作台</span><ChevronRight :size="13" class="dim" /><strong>{{ route.meta.title || '业务总览' }}</strong></div><div class="top-right"><span class="project-label">S1 示例项目</span><span class="badge" :class="store.health?.mode === 'live' ? 'tone-green' : 'tone-blue'">{{ modeLabel }}</span></div></header>
      <main class="content"><div v-if="store.bootError" class="boot-error card"><WifiOff :size="19" /><div><strong>暂时无法连接服务</strong><p>{{ store.bootError }}，请确认启动窗口仍在运行。</p></div><button class="btn btn-sm" @click="bootstrap">重新连接</button></div><slot /></main>
    </div><ToastHost />
  </div>
</template>

<style scoped>
.shell{min-height:100vh;display:flex}.sidebar{--text:#edf4ff;--muted:#9bb2cb;--dim:#8da7c4;--line:#ffffff15;--panel-solid:#152c46;position:fixed;inset:0 auto 0 0;width:272px;display:flex;flex-direction:column;padding:25px 18px 18px;background:radial-gradient(ellipse at 0 0,#245da936,transparent 45%),linear-gradient(180deg,#0b172a,#102740 70%,#0b1d32);border-right:1px solid #203953;color:var(--text);z-index:50;transition:width .2s,transform .2s}.main{flex:1;min-width:0;margin-left:272px;transition:margin-left .2s}.brand{display:flex;align-items:center;gap:11px;position:relative;padding:0 2px 25px}.brand-mark{width:42px;height:44px;display:grid;place-items:center;background:linear-gradient(140deg,#85dcff,#69a9ff);border-radius:13px;color:#102a43;flex-shrink:0;box-shadow:0 8px 20px #0002}.brand-text strong,.brand-text small{display:block;white-space:nowrap}.brand-text strong{font-size:20px;letter-spacing:.02em}.brand-text small{font-size:10px;margin-top:5px;color:#91adc9}.collapse-btn{position:absolute;right:-8px;top:11px;display:grid;place-items:center;width:19px;height:25px;border:0;background:none;color:#7b99b9}.project-card{display:flex;align-items:flex-start;gap:11px;padding:15px 12px;background:#6caddc10;border:1px solid #a8ccec20;border-radius:13px;margin-bottom:26px}.project-dot{width:7px;height:7px;background:#36d6be;border-radius:50%;margin-top:6px;box-shadow:0 0 0 4px #36d6be12}.project-card small,.project-card strong,.project-card div>span{display:block}.project-card small{font-size:11px;color:#8eabc5}.project-card strong{font-size:16px;margin:6px 0}.project-card div>span{font-size:11px;color:#9fb6ce}.nav{flex:1;overflow-y:auto}.nav-group{margin-bottom:27px}.nav-label{font-size:12px;color:#718da9;margin:0 12px 11px;letter-spacing:.08em}.nav-item{display:flex;align-items:center;gap:12px;min-height:49px;padding:11px 12px;margin:5px 0;border-radius:10px;color:#b1c4d9;font-size:16px;transition:.15s}.nav-item:hover{background:#ffffff08;color:white}.nav-item.active{background:linear-gradient(105deg,#2563eb,#1686bc);color:white;font-weight:650;box-shadow:0 7px 18px #0002}.nav-arrow{margin-left:auto}.system-nav{margin:4px 0 20px}.system-nav summary{cursor:pointer;color:#9eb6ce;font-size:14px;padding:10px 12px}.system-nav .nav-item{font-size:15px;min-height:44px}.sidebar-foot{border-top:1px solid #ffffff12;padding-top:14px}.connection{display:flex;align-items:center;gap:9px;color:#91abc6;font-size:11px;padding:0 6px 16px}.connection i{margin-left:auto;width:6px;height:6px;border-radius:50%;background:#b68350}.connection i.online{background:#3cc9a3}.workspace-user{display:flex;align-items:center;gap:11px;padding:13px 10px;border-radius:12px;background:#ffffff06;border:1px solid #ffffff0b}.workspace-user>span{display:grid;place-items:center;width:35px;height:35px;border-radius:10px;background:#244662;color:#97c8ee}.workspace-user strong,.workspace-user small{display:block}.workspace-user strong{font-size:12px}.workspace-user small{font-size:10px;color:#89a3be;margin-top:4px}.topbar{height:68px;position:sticky;top:0;z-index:30;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:0 34px;border-bottom:1px solid var(--line);background:#ffffffed;backdrop-filter:blur(12px)}.crumbs,.top-right{display:flex;align-items:center;gap:12px;font-size:15px}.crumb-home,.project-label{color:var(--muted);font-size:12px}.crumbs strong{font-weight:600}.content{min-width:0}.mobile-menu{display:none;background:none;border:0;padding:0;color:var(--text)}.boot-error{display:flex;gap:12px;align-items:center;margin:24px 34px 0;padding:16px;color:var(--red)}.boot-error strong{color:var(--text)}.boot-error p{font-size:12px;margin-top:5px;color:var(--muted)}.boot-error .btn{margin-left:auto}.collapsed .sidebar{width:78px;padding:25px 13px}.collapsed .main{margin-left:78px}.collapsed .collapse-btn{right:-8px;top:48px}.collapsed .brand{padding-bottom:26px}.collapsed .nav-item{justify-content:center;padding:13px}.collapsed .system-nav summary{text-align:center}.nav-scrim{display:none}
@media(max-width:1100px){.topbar{padding:0 24px}.project-label{display:none}}
@media(max-width:850px){.sidebar,.collapsed .sidebar{width:272px;padding:25px 18px;transform:translateX(-100%)}.main,.collapsed .main{margin-left:0}.mobile-open .sidebar{transform:translateX(0)}.mobile-menu{display:flex}.crumb-home{display:none}.topbar{height:60px;padding:0 18px}.collapse-btn{display:none}.nav-scrim{display:block;position:fixed;inset:0;border:0;background:#07172e80;z-index:40}.sidebar-foot{margin-top:auto}}
</style>
