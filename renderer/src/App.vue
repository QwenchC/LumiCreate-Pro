<template>
  <div class="app-shell">
    <TitleBar @close-tab="requestCloseTab" @go-home="goHome" />
    <div class="app-body">
      <!-- Home / Settings use RouterView; v-show keeps it mounted so ProjectViews stay alive -->
      <RouterView v-show="!tabsStore.activeId" />

      <!-- Multi-project tabs area: created once first tab opens, never destroyed while tabs exist -->
      <div v-if="tabsStore.tabs.length" v-show="!!tabsStore.activeId" class="tabs-area">
        <!-- Each open project is always mounted but shown/hidden with v-show -->
        <div
          v-for="tab in tabsStore.tabs"
          :key="tab.id"
          v-show="tab.id === tabsStore.activeId"
          class="tab-panel-wrap"
        >
          <ProjectView
            :project-id="tab.id"
            @close-tab="requestCloseTab(tab.id)"
            @go-home="goHome"
          />
        </div>
      </div>
    </div>

    <UnsavedDialog
      v-if="closeConfirm.show"
      :message="`项目「${closeConfirm.tabName}」有未保存的更改，是否保存？`"
      @save="handleCloseDialogSave"
      @discard="handleCloseDialogDiscard"
      @cancel="closeConfirm.show = false"
    />

    <!-- E1: 后端日志浮窗（全局），右键 / ✕ 隐藏后可在标题栏点 📋 重开 -->
    <LogPanel v-if="logPanelEnabled" @hide="logPanelEnabled = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import TitleBar from './components/TitleBar.vue'
import UnsavedDialog from './components/UnsavedDialog.vue'
import ProjectView from './views/ProjectView.vue'
import LogPanel from './components/LogPanel.vue'
import { useTabsStore } from './stores/tabs'

// E1: 全局开关。默认开。可通过 localStorage.lumi-log-panel='off' 隐藏
const logPanelEnabled = ref(localStorage.getItem('lumi-log-panel') !== 'off')

function _onLogPanelToggle() {
  logPanelEnabled.value = !logPanelEnabled.value
  localStorage.setItem('lumi-log-panel', logPanelEnabled.value ? 'on' : 'off')
}
window.addEventListener('lumi:toggle-log-panel', _onLogPanelToggle)

const router = useRouter()
const tabsStore = useTabsStore()

// ── App-level window close ────────────────────────────────────────────────────
const showAppUnsaved = ref(false)

function onBeforeClose() {
  const dirty = tabsStore.tabs.some(t => t.isDirty)
  if (dirty) {
    showAppUnsaved.value = true
  } else {
    window.electronAPI?.windowCloseConfirmed()
  }
}

// ── Close-tab confirmation dialog ─────────────────────────────────────────────
const closeConfirm = ref({ show: false, tabId: null, tabName: '' })

function requestCloseTab(tabId) {
  const tab = tabsStore.tabs.find(t => t.id === tabId)
  if (!tab) return
  if (tab.isDirty) {
    closeConfirm.value = { show: true, tabId, tabName: tab.name }
  } else {
    tabsStore.closeTab(tabId)
    if (!tabsStore.activeId) router.push('/')
  }
}

function handleCloseDialogSave() {
  // Dispatch save to the active project's tab
  window.dispatchEvent(new CustomEvent('lumi:save-project', { detail: { projectId: closeConfirm.value.tabId } }))
  setTimeout(() => {
    tabsStore.closeTab(closeConfirm.value.tabId)
    closeConfirm.value.show = false
    if (!tabsStore.activeId) router.push('/')
  }, 400)
}

function handleCloseDialogDiscard() {
  tabsStore.closeTab(closeConfirm.value.tabId)
  closeConfirm.value.show = false
  if (!tabsStore.activeId) router.push('/')
}

function goHome() {
  // Deactivate project tabs → router view shows
  tabsStore.activeId = null
  router.push('/')
}

onMounted(() => {
  window.electronAPI?.onBeforeClose(onBeforeClose)
  window.electronAPI?.onMenuOpenSettings(() => { tabsStore.activeId = null; router.push('/settings') })
  window.electronAPI?.onMenuNewProject(() => { tabsStore.activeId = null; router.push('/') })
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
  display: flex;
  flex-direction: column;
}
.tabs-area {
  flex: 1;
  overflow: hidden;
  position: relative;
}
.tab-panel-wrap {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
</style>

