<template>
  <div class="pe-wrap">
    <div class="pe-label">{{ label }}</div>
    <div class="pe-swatches">
      <div v-for="(hex, i) in modelValue" :key="i" class="pe-swatch">
        <input type="color" :value="normalize(hex)"
               @input="updateAt(i, $event.target.value)" class="pe-color" />
        <span class="pe-hex">{{ hex }}</span>
        <button class="pe-del" @click="removeAt(i)" title="移除">✕</button>
      </div>
      <button class="pe-add" @click="add" :disabled="modelValue.length >= max"
              :title="modelValue.length >= max ? `最多 ${max} 个` : '添加颜色'">＋</button>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  max:        { type: Number, default: 16 },
  label:      { type: String, default: '配色' },
})
const emit = defineEmits(['update:modelValue'])

// Ideogram 要求大写 #RRGGBB
function toUpperHex(v) {
  let s = (v || '').trim()
  if (!s.startsWith('#')) s = '#' + s
  // #fff → #FFFFFF
  if (/^#[0-9a-fA-F]{3}$/.test(s)) {
    s = '#' + s.slice(1).split('').map(c => c + c).join('')
  }
  return s.toUpperCase()
}
function normalize(hex) {
  const s = toUpperHex(hex)
  return /^#[0-9A-F]{6}$/.test(s) ? s : '#000000'
}
function add() {
  if (props.modelValue.length >= props.max) return
  emit('update:modelValue', [...props.modelValue, '#FFFFFF'])
}
function updateAt(i, val) {
  const next = [...props.modelValue]
  next[i] = toUpperHex(val)
  emit('update:modelValue', next)
}
function removeAt(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.pe-wrap { display: flex; flex-direction: column; gap: 4px; }
.pe-label { font-size: 11px; color: var(--color-text-muted, #aaa); }
.pe-swatches { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.pe-swatch {
  display: flex; align-items: center; gap: 3px;
  border: 1px solid var(--color-border, #333); border-radius: 3px;
  padding: 1px 3px;
}
.pe-color { width: 22px; height: 20px; border: none; background: none; padding: 0; cursor: pointer; }
.pe-hex { font-size: 10px; font-family: monospace; color: var(--color-text-muted); }
.pe-del { background: none; border: none; color: #888; cursor: pointer; font-size: 10px; padding: 0 1px; }
.pe-del:hover { color: var(--color-error, #f66); }
.pe-add {
  width: 26px; height: 24px; border: 1px dashed var(--color-border, #555);
  border-radius: 3px; background: none; color: var(--color-text-muted);
  cursor: pointer; font-size: 14px;
}
.pe-add:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
