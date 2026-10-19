<script setup lang="ts">
import { X } from 'lucide-vue-next'

defineProps<{
  open: boolean
  title: string
  subtitle?: string
  width?: string
}>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <teleport to="body">
    <transition name="modal">
      <div v-if="open" class="modal-mask" @click.self="emit('close')">
        <div class="modal card" :style="{ width: width || '620px' }" role="dialog" aria-modal="true">
          <div class="modal-head">
            <div>
              <div class="modal-title">{{ title }}</div>
              <div v-if="subtitle" class="modal-sub">{{ subtitle }}</div>
            </div>
            <button class="btn btn-ghost btn-icon btn-sm" @click="emit('close')"><X :size="16" /></button>
          </div>
          <div class="modal-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="modal-foot">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(2, 8, 16, 0.72);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 90;
  padding: 24px;
}
.modal {
  max-height: min(86vh, 900px);
  max-width: calc(100vw - 40px);
  display: flex;
  flex-direction: column;
  background: var(--panel);
}
.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--line);
}
.modal-title {
  font-size: 16px;
  font-weight: 600;
}
.modal-sub {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11.5px;
}
.modal-body {
  padding: 20px;
  overflow-y: auto;
}
.modal-foot {
  padding: 14px 20px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.18s ease;
}
.modal-enter-active .modal,
.modal-leave-active .modal {
  transition: transform 0.18s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal,
.modal-leave-to .modal {
  transform: translateY(8px) scale(0.985);
}
</style>
