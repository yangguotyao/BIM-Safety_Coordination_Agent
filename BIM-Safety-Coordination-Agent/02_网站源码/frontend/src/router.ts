import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/overview',
      name: 'dashboard',
      component: () => import('./views/DashboardView.vue'),
      meta: { title: '业务总览', eyebrow: '安全协同工作台' },
    },
    {
      path: '/inspection',
      name: 'inspection',
      component: () => import('./views/StartInspectionView.vue'),
      meta: { title: '发起安全检查', eyebrow: '安全协同工作台' },
    },
    {
      path: '/',
      alias: '/bim',
      name: 'bim',
      component: () => import('./views/BimView.vue'),
      meta: { title: 'BIM 工作台', eyebrow: 'BIM WORKSPACE' },
    },
    {
      path: '/cases',
      name: 'cases',
      component: () => import('./views/CasesView.vue'),
      meta: { title: '检查记录', eyebrow: '安全协同工作台' },
    },
    {
      path: '/cases/:id',
      name: 'case-detail',
      component: () => import('./views/CaseDetailView.vue'),
      meta: { title: '检查工作台', eyebrow: '安全检查' },
    },
    {
      path: '/agent',
      name: 'agent',
      component: () => import('./views/AgentView.vue'),
      meta: { title: 'Agent 工作流', eyebrow: 'AGENT TRACE' },
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('./views/KnowledgeView.vue'),
      meta: { title: '规范知识库', eyebrow: 'KNOWLEDGE BASE' },
    },
    {
      path: '/evidence',
      name: 'evidence',
      component: () => import('./views/EvidenceView.vue'),
      meta: { title: '证据库', eyebrow: 'EVIDENCE' },
    },
    {
      path: '/acceptance',
      name: 'acceptance',
      component: () => import('./views/AcceptanceView.vue'),
      meta: { title: '验收实验室', eyebrow: 'ACCEPTANCE LAB' },
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('./views/AboutView.vue'),
      meta: { title: '方案与边界', eyebrow: 'METHOD & BOUNDARY' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.afterEach((to) => {
  const title = (to.meta.title as string) || 'BIM 施工安全协同平台'
  document.title = `${title} · BIM 施工安全协同平台`
})

export default router
