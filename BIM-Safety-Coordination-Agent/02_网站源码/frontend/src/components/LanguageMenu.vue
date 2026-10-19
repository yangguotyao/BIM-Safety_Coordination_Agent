<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, Languages } from 'lucide-vue-next'
import { localeState, setLocale, type Locale } from '../i18n'

withDefaults(defineProps<{
  variant?: 'light' | 'dark'
  placement?: 'down' | 'up'
  compact?: boolean
}>(), {
  variant: 'light',
  placement: 'down',
  compact: false,
})

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const options: { value: Locale; label: string }[] = [
  { value: 'zh', label: '简体中文' },
  { value: 'en', label: 'English' },
]

function choose(next: Locale) {
  setLocale(next)
  open.value = false
}

function onPointerDown(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('mousedown', onPointerDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onPointerDown))
</script>

<template>
  <div ref="root" class="lang-menu" :class="[variant, placement]">
    <button
      type="button"
      class="lang-trigger"
      :aria-expanded="open"
      aria-haspopup="listbox"
      aria-label="Language"
      @click="open = !open"
    >
      <Languages :size="15" />
      <span v-if="!compact">Language</span>
    </button>
    <div v-if="open" class="lang-list" role="listbox">
      <button
        v-for="item in options"
        :key="item.value"
        type="button"
        class="lang-item"
        :class="{ active: localeState.locale === item.value }"
        role="option"
        :aria-selected="localeState.locale === item.value"
        @click="choose(item.value)"
      >
        <span>{{ item.label }}</span>
        <Check v-if="localeState.locale === item.value" :size="14" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.lang-menu { position: relative; display: inline-block; }
.lang-trigger {
  display: flex; align-items: center; gap: 8px; width: 100%;
  padding: 8px 10px; border-radius: 9px; border: 1px solid transparent;
  background: none; cursor: pointer; font-size: 13px; line-height: 1;
  transition: background .15s, color .15s, border-color .15s;
}
.lang-list {
  position: absolute; z-index: 60; min-width: 148px; padding: 6px;
  border-radius: 11px; display: grid; gap: 2px;
}
.lang-menu.down .lang-list { top: calc(100% + 6px); left: 0; }
.lang-menu.up .lang-list { bottom: calc(100% + 6px); left: 0; }
/* 登录页在右上角，下拉列表改为右对齐，避免超出视口 */
.lang-menu.light.down .lang-list { left: auto; right: 0; }
.lang-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 8px 10px; border: 0; border-radius: 8px; background: none;
  cursor: pointer; font-size: 13px; text-align: left; white-space: nowrap;
  transition: background .12s, color .12s;
}
.lang-item.active { font-weight: 600; }

/* 浅色（登录页） */
.lang-menu.light .lang-trigger { color: #46618a; border-color: #d3e0ee; background: #fff; }
.lang-menu.light .lang-trigger:hover { color: #1d4ed8; border-color: #b8cfe8; background: #f4f9ff; }
.lang-menu.light .lang-list { background: #fff; border: 1px solid #dbe6f2; box-shadow: 0 12px 28px #17335a1f; }
.lang-menu.light .lang-item { color: #35506f; }
.lang-menu.light .lang-item:hover { background: #eef5fd; }
.lang-menu.light .lang-item.active { color: #1d4ed8; }

/* 深色（侧栏） */
.lang-menu.dark .lang-trigger { color: #b1c4d9; }
.lang-menu.dark .lang-trigger:hover { color: #fff; background: #ffffff0d; }
.lang-menu.dark .lang-list { background: #152c46; border: 1px solid #ffffff1a; box-shadow: 0 14px 30px #0006; }
.lang-menu.dark .lang-item { color: #c3d5e8; }
.lang-menu.dark .lang-item:hover { background: #ffffff12; color: #fff; }
.lang-menu.dark .lang-item.active { color: #85dcff; }
</style>
