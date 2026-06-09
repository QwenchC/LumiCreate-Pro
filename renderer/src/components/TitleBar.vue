<template>
  <div class="titlebar-wrap">
    <div class="titlebar">
      <div class="titlebar-drag">
        <img src="/icon.png" class="titlebar-icon" alt="" />
        <span class="titlebar-title">{{ $t('app.title') }}</span>
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
        <!-- E1: 日志浮窗开关（隐藏后可重开） -->
        <button class="ctrl-btn log-toggle" @click="toggleLogPanel"
                :title="logPanelOn ? '隐藏后端日志浮窗' : '显示后端日志浮窗'">
          📋
        </button>
        <!-- v1.4.9: 提示词插件 —— 全局可用，按类目浏览 + 撰写 + 复制 -->
        <button class="ctrl-btn prompts-toggle" @click="promptsOpen = true"
                title="打开提示词插件（按类目浏览 / 新增 / 撰写 / 复制）">
          💡
        </button>
        <!-- C2: ComfyUI 健康指示灯 -->
        <button
          class="comfy-pill"
          :class="comfyStatus"
          :title="comfyTitle"
          @click="checkComfy(true)"
        >
          <span class="comfy-dot" />
          <span class="comfy-text">ComfyUI</span>
        </button>
        <button class="ctrl-btn theme-btn" @click="toggleTheme" :title="isDark ? '切换到浅色模式' : '切换到深色模式'">
          {{ isDark ? '☀' : '🌙' }}
        </button>
        <button class="ctrl-btn" @click="minimize" title="最小化">─</button>
        <button class="ctrl-btn" @click="maximize" title="最大化/还原">□</button>
        <button class="ctrl-btn close-btn" @click="close" title="关闭">✕</button>
      </div>
    </div>

    <!-- v1.4.9: 提示词插件弹窗 -->
    <PromptsPlugin v-if="promptsOpen" @close="promptsOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTabsStore } from '../stores/tabs'
import PromptsPlugin from './PromptsPlugin.vue'

defineEmits(['close-tab', 'go-home'])

const tabsStore = useTabsStore()
const isDark = ref(true)

// v1.4.9: 提示词插件弹窗开关
const promptsOpen = ref(false)

// E1: 日志浮窗开关 toggle
const logPanelOn = ref(localStorage.getItem('lumi-log-panel') !== 'off')
function toggleLogPanel() {
  logPanelOn.value = !logPanelOn.value
  window.dispatchEvent(new CustomEvent('lumi:toggle-log-panel'))
}

// C2: ComfyUI 健康指示灯
const comfyStatus = ref('unknown')   // 'ok' | 'down' | 'unknown' | 'unset'
const comfyMessage = ref('')
const comfyLastCheck = ref(0)
let   _comfyTimer = null

const comfyTitle = computed(() => {
  const sec = comfyLastCheck.value
        ? Math.round((Date.now() - comfyLastCheck.value) / 1000)
        : null
  const when = sec != null ? ` · ${sec}s 前检测` : ''
  if (comfyStatus.value === 'ok')      return `ComfyUI 在线${when}：${comfyMessage.value}（点击立即重检）`
  if (comfyStatus.value === 'down')    return `ComfyUI 不可用${when}：${comfyMessage.value}（点击立即重检）`
  if (comfyStatus.value === 'unset')   return `ComfyUI 地址未配置（点击去设置）`
  return `ComfyUI 状态未知（点击立即检测）`
})

async function checkComfy(force = false) {
  try {
    const r = await fetch('http://127.0.0.1:18520/api/image-engine/test')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const d = await r.json()
    if (d.success) {
      comfyStatus.value = 'ok'
      comfyMessage.value = d.message || '连接正常'
    } else {
      // 后端 200 + success:false 通常代表"已配置但连不上"
      comfyStatus.value = 'down'
      comfyMessage.value = d.message || '未知错误'
    }
  } catch (e) {
    comfyStatus.value = 'down'
    comfyMessage.value = e.message
  }
  comfyLastCheck.value = Date.now()
}

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
  // C2: 启动时立即检查，之后每 60s 一次
  checkComfy()
  _comfyTimer = setInterval(checkComfy, 60_000)
})
onUnmounted(() => {
  if (_comfyTimer) clearInterval(_comfyTimer)
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

.titlebar-controls { display: flex; -webkit-app-region: no-drag; flex-shrink: 0; align-items: center; }

/* C2: ComfyUI 健康指示灯 */
.comfy-pill {
  display: flex; align-items: center; gap: 5px;
  background: transparent; border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  padding: 2px 8px; margin-right: 6px; height: 22px;
  border-radius: 10px; cursor: pointer;
  font-size: 11px; line-height: 1;
  -webkit-app-region: no-drag;
  transition: background var(--transition), border-color var(--transition);
}
.comfy-pill:hover { background: var(--color-surface-2); }
.comfy-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--color-text-muted);
}
.comfy-pill.ok    .comfy-dot { background: #4caf50; box-shadow: 0 0 4px rgba(76,175,80,.7); }
.comfy-pill.ok    { border-color: rgba(76,175,80,.4); color: var(--color-text); }
.comfy-pill.down  .comfy-dot { background: #e53935; }
.comfy-pill.down  { border-color: rgba(229,57,53,.5); color: #f88; }
.comfy-pill.unset .comfy-dot { background: #888; }
.log-toggle { width: 32px; font-size: 13px; }
.log-toggle:hover { background: var(--color-border); }
.prompts-toggle { width: 32px; font-size: 13px; margin-right: 4px; }
.prompts-toggle:hover { background: var(--color-border); }
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
