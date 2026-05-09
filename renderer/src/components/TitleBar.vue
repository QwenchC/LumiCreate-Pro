<template>
  <div class="titlebar">
    <div class="titlebar-drag">
      <img src="/icon.png" class="titlebar-icon" alt="" />
      <span class="titlebar-title">LumiCreate-Pro</span>
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
</template>

<script setup>
import { ref, onMounted } from 'vue'

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
.titlebar {
  height: var(--titlebar-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  -webkit-app-region: drag;
  flex-shrink: 0;
  padding: 0 0 0 12px;
}
.titlebar-drag { display: flex; align-items: center; gap: 8px; pointer-events: none; }
.titlebar-icon { width: 16px; height: 16px; }
.titlebar-title { font-size: 13px; font-weight: 600; color: var(--color-text); }
.titlebar-controls { display: flex; -webkit-app-region: no-drag; }
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
