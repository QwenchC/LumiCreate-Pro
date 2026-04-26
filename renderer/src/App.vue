<template>
  <div class="app-shell">
    <TitleBar />
    <div class="app-body">
      <RouterView />
    </div>
    <UnsavedDialog v-if="showUnsaved" @save="handleSave" @discard="handleDiscard" @cancel="showUnsaved = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import TitleBar from './components/TitleBar.vue'
import UnsavedDialog from './components/UnsavedDialog.vue'

const router = useRouter()
const showUnsaved = ref(false)
let pendingAction = null

function handleSave() {
  window.dispatchEvent(new CustomEvent('lumi:save-project'))
  showUnsaved.value = false
  if (pendingAction) { pendingAction(); pendingAction = null }
}
function handleDiscard() {
  showUnsaved.value = false
  if (pendingAction) { pendingAction(); pendingAction = null }
}
function onBeforeClose() {
  if (window.__lumiUnsaved === true) {
    showUnsaved.value = true
    pendingAction = () => window.electronAPI?.windowCloseConfirmed()
  } else {
    window.electronAPI?.windowCloseConfirmed()
  }
}

onMounted(() => {
  window.electronAPI?.onBeforeClose(onBeforeClose)
  window.electronAPI?.onMenuOpenSettings(() => router.push('/settings'))
  window.electronAPI?.onMenuNewProject(() => router.push('/'))
})
onUnmounted(() => {
  ['app:before-close','menu:open-settings','menu:new-project'].forEach(
    ch => window.electronAPI?.removeAllListeners(ch)
  )
})
</script>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
.app-body {
  flex: 1;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}
</style>

