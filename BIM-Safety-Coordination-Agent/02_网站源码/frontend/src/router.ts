import { createRouter, createWebHistory } from 'vue-router'
import { onLocaleChange, t } from './i18n'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/overview',
      name: 'dashboard',
      component: () => import('./views/DashboardView.vue'),
      meta: { titleKey: 'route.dashboard' },
    },
    {
      path: '/inspection',
      name: 'inspection',
      component: () => import('./views/StartInspectionView.vue'),
      meta: { titleKey: 'route.inspection' },
    },
    {
      path: '/',
      alias: '/bim',
      name: 'bim',
      component: () => import('./views/BimView.vue'),
      meta: { titleKey: 'route.bim' },
    },
    {
      path: '/cases',
      name: 'cases',
      component: () => import('./views/CasesView.vue'),
      meta: { titleKey: 'route.cases' },
    },
    {
      path: '/cases/:id',
      name: 'case-detail',
      component: () => import('./views/CaseDetailView.vue'),
      meta: { titleKey: 'route.caseDetail' },
    },
    {
      path: '/agent',
      name: 'agent',
      component: () => import('./views/AgentView.vue'),
      meta: { titleKey: 'route.agent' },
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('./views/KnowledgeView.vue'),
      meta: { titleKey: 'route.knowledge' },
    },
    {
      path: '/evidence',
      name: 'evidence',
      component: () => import('./views/EvidenceView.vue'),
      meta: { titleKey: 'route.evidence' },
    },
    {
      path: '/acceptance',
      name: 'acceptance',
      component: () => import('./views/AcceptanceView.vue'),
      meta: { titleKey: 'route.acceptance' },
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('./views/AboutView.vue'),
      meta: { titleKey: 'route.about' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

function applyTitle(to: { meta: Record<string | number | symbol, unknown> }) {
  const key = (to.meta.titleKey as string) || 'route.default'
  document.title = `${t(key)} · ${t('route.default')}`
}

router.afterEach(applyTitle)
onLocaleChange(() => applyTitle(router.currentRoute.value))

export default router
