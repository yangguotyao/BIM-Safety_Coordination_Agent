<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
import { t } from '../i18n'
defineProps<{ title?: string; detail?: string }>()
</script>

<template>
  <div class="empty">
    <Inbox :size="26" />
    <strong>{{ title || t('common.noData') }}</strong>
    <span v-if="detail" class="small">{{ detail }}</span>
    <slot />
  </div>
</template>
