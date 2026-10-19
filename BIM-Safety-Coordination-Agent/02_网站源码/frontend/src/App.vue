<script setup lang="ts">
import AppShell from './components/AppShell.vue'
import AccessGate from './components/AccessGate.vue'
import {accessState} from './api'
</script>

<template>
  <AccessGate />
  <AppShell v-if="!accessState.required">
    <router-view v-slot="{ Component }">
      <transition name="page" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </AppShell>
</template>
