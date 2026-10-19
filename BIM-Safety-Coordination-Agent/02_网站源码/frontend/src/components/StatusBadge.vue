<script setup lang="ts">
import { computed } from 'vue'
import { statusLabel, statusTone } from '../utils'

const props = defineProps<{ status: string; label?: string; dot?: boolean }>()
const tone = computed(() => statusTone(props.status))
</script>

<template>
  <span class="badge" :class="[`tone-${tone}`, { 'badge-dot': dot }]">{{ label || statusLabel(status) }}</span>
</template>
