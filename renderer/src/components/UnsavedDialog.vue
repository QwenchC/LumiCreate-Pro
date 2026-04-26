<template>
  <Teleport to="body">
    <div class="overlay">
      <div class="dialog card">
        <h3 class="dialog-title">⚠ 有未保存的更改</h3>
        <p class="dialog-body">项目已修改但尚未保存，是否保存当前更改？</p>
        <div class="dialog-actions">
          <button class="btn btn-primary" @click="$emit('save')">保存</button>
          <button class="btn btn-secondary" @click="$emit('discard')">不保存</button>
          <button class="btn btn-ghost" @click="$emit('cancel')">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineEmits(['save', 'discard', 'cancel'])
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
.dialog { max-width: 380px; width: 90%; }
.dialog-title { font-size: 16px; margin-bottom: 10px; }
.dialog-body { color: var(--color-text-muted); margin-bottom: 20px; line-height: 1.6; }
.dialog-actions { display: flex; gap: 10px; justify-content: flex-end; }
</style>
