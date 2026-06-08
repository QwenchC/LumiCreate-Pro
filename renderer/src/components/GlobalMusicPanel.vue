<template>
  <div class="gm-overlay" @click.self="$emit('close')">
    <div class="gm-panel card">
      <div class="gm-header">
        <h3>🎵 全局音乐库</h3>
        <span class="text-muted" style="font-size:11px;margin-left:8px">
          所有项目共享 · ACE-Step v1.5 生成 · 可作背景音乐
        </span>
        <button class="btn btn-ghost btn-xs" style="margin-left:auto"
                @click="$emit('close')">✕</button>
      </div>
      <div class="gm-body">
        <MusicGenerator scope="global" />
      </div>
    </div>
  </div>
</template>

<script setup>
import MusicGenerator from './MusicGenerator.vue'
defineEmits(['close'])
</script>

<style scoped>
.gm-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.gm-panel {
  width: 1100px; max-width: calc(100vw - 40px); height: 760px; max-height: calc(100vh - 40px);
  display: flex; flex-direction: column;
  background: var(--color-surface, var(--bg-panel));
  border-radius: 8px;
  padding: 0; overflow: hidden;
}
.gm-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border, var(--border));
  background: var(--color-surface-2, var(--bg-input));
}
.gm-header h3 { margin: 0; font-size: 15px; }
.gm-body { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
</style>
