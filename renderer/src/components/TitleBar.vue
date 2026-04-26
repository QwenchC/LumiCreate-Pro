<template>
  <div class="titlebar">
    <div class="titlebar-drag">
      <img src="/icon.png" class="titlebar-icon" alt="" />
      <span class="titlebar-title">LumiCreate-Local</span>
    </div>
    <div class="titlebar-controls">
      <button class="ctrl-btn" @click="minimize" title="最小化">─</button>
      <button class="ctrl-btn" @click="maximize" title="最大化/还原">□</button>
      <button class="ctrl-btn close-btn" @click="close" title="关闭">✕</button>
    </div>
  </div>
</template>

<script setup>
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
</style>
