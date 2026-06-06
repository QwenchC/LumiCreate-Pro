<template>
  <div class="titlebar-wrap">
    <div class="titlebar">
      <div class="titlebar-drag">
        <img src="/icon.png" class="titlebar-icon" alt="" />
        <span class="titlebar-title">LumiCreate-Pro</span>
      </div>
      <!-- Project tabs in the title bar -->
      <div class="project-tabs" v-if="tabsStore.tabs.length">
        <!-- Home button at the leftmost position -->
        <button class="proj-tab home-tab" @click="$emit('go-home')" title="返回项目列表">
          🏠
        </button>
        <button
          v-for="tab in tabsStore.tabs"
          :key="tab.id"
          class="proj-tab"
          :class="{ active: tab.id === tabsStore.activeId }"
          @click="tabsStore.activateTab(tab.id)"
        >
          <span class="proj-tab-name">{{ tab.name }}</span>
          <span v-if="tab.isDirty" class="proj-tab-dot" title="未保存">●</span>
          <span
            class="proj-tab-close"
            @click.stop="$emit('close-tab', tab.id)"
            title="关闭"
          >✕</span>
        </button>
      </div>
      <div class="titlebar-controls">
        <button class="ctrl-btn theme-btn" @click="toggleTheme" :title="isDark ? '切换到浅色模式' : '切换到深色模式'">
          {{ isDark ? '☀' : '🌙' }}
        </button>
        <button class="ctrl-btn" @click="minimize" title="最小化">─</button>
        <button class="ctrl-btn" @click="maximize" title="最大化/还原">□</button>
        <button class="ctrl-btn close-btn" @click="close" title="关闭">✕</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useTabsStore } from '../stores/tabs'

defineEmits(['close-tab', 'go-home'])

const tabsStore = useTabsStore()
const isDark = ref(true)

function applyTheme(dark) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
  isDark.value = dark
  localStorage.setItem('lumi-theme', dark ? 'dark' : 'light')
}

function toggleTheme() {
  applyTheme(!isDark.value)
}

onMounted(() => {
  const saved = localStorage.getItem('lumi-theme')
  applyTheme(saved !== 'light')
})

function minimize() { window.electronAPI?.windowMinimize() }
function maximize() { window.electronAPI?.windowMaximize() }
function close()    { window.electronAPI?.windowClose() }
</script>

<style scoped>
.titlebar-wrap { flex-shrink: 0; }
.titlebar {
  height: var(--titlebar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  -webkit-app-region: drag;
  padding: 0 0 0 12px;
}
.titlebar-drag { display: flex; align-items: center; gap: 8px; pointer-events: none; flex-shrink: 0; }
.titlebar-icon { width: 16px; height: 16px; }
.titlebar-title { font-size: 13px; font-weight: 600; color: var(--color-text); white-space: nowrap; }

/* Project tabs strip
 * NOTE: 容器本身保持 drag（继承自 .titlebar），只有 .proj-tab / 关闭按钮等子元素 no-drag。
 * padding-right 留一段空白拖动带，避免 tabs 占满后整条中间无处可按。 */
.project-tabs {
  flex: 1; min-width: 0;
  display: flex; align-items: stretch;
  overflow-x: auto; overflow-y: hidden;
  scrollbar-width: none;
  margin: 0 8px;
  padding-right: 80px;
  gap: 2px;
}
.project-tabs::-webkit-scrollbar { display: none; }
.proj-tab {
  display: flex; align-items: center; gap: 5px;
  padding: 0 10px;
  height: var(--titlebar-height);
  background: transparent;
  border: none; border-bottom: 2px solid transparent;
  color: var(--color-text-muted);
  cursor: pointer; font-size: 12px; white-space: nowrap;
  flex-shrink: 0;
  transition: background var(--transition), color var(--transition), border-color var(--transition);
  -webkit-app-region: no-drag;
}
.proj-tab:hover { background: var(--color-surface-2); color: var(--color-text); }
.proj-tab.active {
  color: var(--color-text);
  border-bottom-color: var(--color-accent);
  background: var(--color-surface-2);
}
.proj-tab-name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.proj-tab-dot  { color: var(--color-warning); font-size: 8px; }
.proj-tab-close {
  font-size: 10px; opacity: 0.4; padding: 2px 2px; border-radius: 3px;
  transition: opacity var(--transition), background var(--transition);
}
.proj-tab:hover .proj-tab-close { opacity: 0.8; }
.proj-tab-close:hover { opacity: 1 !important; background: var(--color-error); color: #fff; }
.home-tab { font-size: 14px; opacity: 0.7; }
.home-tab:hover { opacity: 1; }

.titlebar-controls { display: flex; -webkit-app-region: no-drag; flex-shrink: 0; }
.ctrl-btn {
  width: 46px;
  height: var(--titlebar-height);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 13px;
  transition: background var(--transition);
}
.ctrl-btn:hover { background: var(--color-border); color: var(--color-text); }
.close-btn:hover { background: var(--color-error) !important; color: #fff; }
.theme-btn { font-size: 15px; }
</style>
