<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps<{ title?: string; detail?: string }>()
</script>

<template>
  <div class="empty">
    <Inbox :size="26" />
    <strong>{{ title || '暂无数据' }}</strong>
    <span v-if="detail" class="small">{{ detail }}</span>
    <slot />
  </div>
</template>
