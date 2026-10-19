<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-vue-next'
import { dismissToast, store } from '../store'

const icon = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}
</script>

<template>
  <div class="toasts">
    <transition-group name="toast">
      <div v-for="item in store.toasts" :key="item.id" class="toast" :class="`toast-${item.kind}`">
        <component :is="icon[item.kind]" :size="16" />
        <span>{{ item.message }}</span>
        <button class="toast-x" @click="dismissToast(item.id)"><X :size="13" /></button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(420px, calc(100vw - 40px));
}
.toast {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 12px;
  border-radius: 9px;
  border: 1px solid var(--line-strong);
  background: var(--panel);
  box-shadow: 0 14px 40px rgba(0, 0, 0, 0.4);
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.55;
  backdrop-filter: blur(12px);
}
.toast svg {
  flex: none;
  margin-top: 1px;
}
.toast-success svg { color: var(--green); }
.toast-error svg { color: var(--red); }
.toast-warning svg { color: var(--amber); }
.toast-info svg { color: var(--cyan); }
.toast-x {
  margin-left: auto;
  border: none;
  background: transparent;
  color: var(--dim);
  display: grid;
  place-items: center;
  padding: 2px;
}
.toast-x:hover { color: var(--text); }
.toast-enter-active,
.toast-leave-active { transition: 180ms ease; }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
