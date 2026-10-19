<script setup lang="ts">
import {ref} from 'vue'
import {ShieldCheck,Loader2} from 'lucide-vue-next'
import {api,accessState} from '../api'
import {t} from '../i18n'
import LanguageMenu from './LanguageMenu.vue'
const token=ref(''),busy=ref(false),error=ref('')
async function signIn(){busy.value=true;error.value='';try{await api.signIn(token.value);token.value='';window.location.reload()}catch(cause){error.value=cause instanceof Error ? cause.message : t('gate.failed')}finally{busy.value=false}}
</script>
<template><main v-if="accessState.required" class="access-gate"><div class="gate-lang"><LanguageMenu variant="light" placement="down" /></div><form class="card access-form" @submit.prevent="signIn"><ShieldCheck :size="32"/><h1>{{ t('gate.title') }}</h1><label>{{ t('gate.token') }}<input v-model="token" class="input" type="password" autocomplete="off" required :aria-label="t('gate.token')" /></label><p v-if="error">{{ error }}</p><button class="btn btn-primary" :disabled="busy || !token"><Loader2 v-if="busy" :size="16" class="spin"/>{{ t('gate.enter') }}</button></form></main></template>
<style scoped>.access-gate{min-height:100vh;display:grid;place-items:center;background:#f0f5fa;padding:24px}.gate-lang{position:fixed;top:22px;right:26px;z-index:10}.access-form{padding:38px;width:min(420px,100%);display:grid;gap:23px}.access-form>svg{color:var(--blue)}.access-form h1{font-size:25px}.access-form label{display:grid;gap:10px;font-size:14px}.access-form p{font-size:13px;color:var(--red)}.access-form button{min-height:44px}@media(max-width:560px){.gate-lang{top:14px;right:14px}}</style>
