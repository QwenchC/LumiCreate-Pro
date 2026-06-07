<template>
  <div class="ge-overlay" @click.self="$emit('close')">
    <div class="ge-panel card">
      <div class="ge-header">
        <h3>📦 全局元素库</h3>
        <span class="text-muted" style="font-size:11px;margin-left:8px">
          所有项目共享 · 漫剧元素 / 角色立绘参考 / 通用素材
        </span>
        <button class="btn btn-ghost btn-xs" style="margin-left:auto"
                @click="$emit('close')">✕</button>
      </div>
      <div class="ge-body">
        <ElementsBrowser scope="global" />
      </div>
    </div>
  </div>
</template>

<script setup>
import ElementsBrowser from './ElementsBrowser.vue'
defineEmits(['close'])
</script>

<style scoped>
.ge-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.ge-panel {
  width: 1100px; max-width: calc(100vw - 40px); height: 720px; max-height: calc(100vh - 40px);
  display: flex; flex-direction: column;
  background: var(--color-surface); border-radius: 8px;
  padding: 0; overflow: hidden;
}
.ge-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-2);
}
.ge-header h3 { margin: 0; font-size: 15px; }
.ge-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
</style>
