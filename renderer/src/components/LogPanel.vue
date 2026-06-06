<template>
  <!-- 折叠状态：极小圆形按钮，几乎不占空间；只有点开才展开为面板 -->
  <button
    v-if="!open"
    class="log-fab"
    :class="{ 'has-error': errorCount > 0 }"
    :title="`后端日志 · ${lines.length} 行${errorCount ? ` · ${errorCount} 个错误` : ''}（点击展开 / 右键关闭）`"
    @click="open = true"
    @contextmenu.prevent="hide"
  >
    <span class="log-fab-icon">📋</span>
    <span v-if="errorCount" class="log-fab-badge">{{ Math.min(errorCount, 99) }}</span>
  </button>

  <!-- 展开状态：完整面板 -->
  <div v-else class="log-panel">
    <div class="log-header">
      <span class="log-title" @click="open = false" title="点击折叠">📋 后端日志</span>
      <span class="log-stats">
        {{ lines.length }} 行
        <span v-if="errorCount" class="log-err-count">· {{ errorCount }} ✗</span>
      </span>
      <button class="log-btn" @click="clear" title="清空日志">🗑</button>
      <button class="log-btn" @click="toggleAutoScroll"
              :title="autoScroll ? '关闭自动滚动' : '开启自动滚动'">
        {{ autoScroll ? '⤓' : '⤒' }}
      </button>
      <button class="log-btn" @click="open = false" title="折叠为小按钮">▾</button>
      <button class="log-btn close" @click="hide" title="完全隐藏（可在标题栏点 📋 重开）">✕</button>
    </div>
    <div class="log-body" ref="bodyRef">
      <div v-for="line in lines" :key="line.id"
           class="log-line" :class="line.level">
        <span class="log-time">{{ formatTs(line.ts) }}</span>
        <span class="log-text">{{ line.text }}</span>
      </div>
      <div v-if="!lines.length" class="log-empty">
        （还没有日志…后端任何 print/stderr 都会显示在这里）
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

const emit = defineEmits(['hide'])

const API = 'http://127.0.0.1:18520/api'

const open       = ref(false)
const lines      = ref([])         // [{id, ts, level, text}]
const autoScroll = ref(true)
const MAX_LINES  = 500
const bodyRef    = ref(null)
let   _es = null
let   _lastId = 0

function hide() {
  localStorage.setItem('lumi-log-panel', 'off')
  emit('hide')
}

const errorCount = computed(() => lines.value.filter(l => l.level === 'error').length)

function formatTs(ts) {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('zh-CN', { hour12: false }) + '.' +
         String(d.getMilliseconds()).padStart(3, '0')
}

function pushLine(evt) {
  if (!evt || evt.id <= _lastId) return
  _lastId = evt.id
  lines.value.push(evt)
  if (lines.value.length > MAX_LINES) {
    lines.value.splice(0, lines.value.length - MAX_LINES)
  }
  if (open.value && autoScroll.value) {
    nextTick(() => {
      const el = bodyRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
}

function clear() {
  lines.value = []
  fetch(`${API}/logs/clear`, { method: 'DELETE' }).catch(() => {})
}

function toggleAutoScroll() {
  autoScroll.value = !autoScroll.value
}

function connect() {
  try {
    _es = new EventSource(`${API}/logs/stream`)
    _es.onmessage = (e) => {
      try { pushLine(JSON.parse(e.data)) } catch {}
    }
    _es.onerror = () => {
      // 5 秒后重连（后端重启 / 网络抖动）
      _es?.close()
      setTimeout(connect, 5000)
    }
  } catch {
    setTimeout(connect, 5000)
  }
}

onMounted(connect)
onUnmounted(() => { _es?.close() })

defineExpose({ open })
</script>

<style scoped>
/* 折叠状态：右下角小圆按钮（28×28），半透明，鼠标 hover 才变实 */
.log-fab {
  position: fixed; right: 10px; bottom: 10px;
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  box-shadow: 0 2px 8px rgba(0,0,0,.25);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  z-index: 900; opacity: .35;
  transition: opacity var(--transition), transform var(--transition);
  padding: 0;
}
.log-fab:hover { opacity: 1; transform: scale(1.1); }
.log-fab.has-error {
  opacity: .85;
  border-color: rgba(220,60,60,.6);
}
.log-fab-icon { font-size: 14px; line-height: 1; }
.log-fab-badge {
  position: absolute; top: -4px; right: -4px;
  background: #e53935; color: #fff;
  border-radius: 8px; font-size: 9px;
  padding: 1px 4px; min-width: 14px; text-align: center;
  font-weight: 700;
}

/* 展开状态：完整面板 */
.log-panel {
  position: fixed; right: 12px; bottom: 12px; width: 520px;
  max-width: calc(100vw - 24px);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px; box-shadow: 0 4px 24px rgba(0,0,0,.35);
  z-index: 900; overflow: hidden;
  display: flex; flex-direction: column;
}
.log-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; cursor: pointer; user-select: none;
  background: var(--color-surface-2);
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
}
.log-title  { font-weight: 600; }
.log-stats  { color: var(--color-text-muted); flex: 1; font-size: 11px; }
.log-err-count { color: #f66; font-weight: 600; }
.log-btn {
  background: transparent; border: none; cursor: pointer;
  color: var(--color-text); font-size: 13px; padding: 0 4px;
  opacity: .65;
}
.log-btn:hover { opacity: 1; }
.log-btn.close:hover { color: var(--color-error); }
.log-title { cursor: pointer; }
.log-body {
  max-height: 280px; overflow: auto; padding: 6px 10px;
  font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.5;
  background: rgba(0,0,0,.25);
}
.log-line   { display: flex; gap: 6px; padding: 1px 0; word-break: break-all; }
.log-line.error { color: #f88; }
.log-line.info  { color: var(--color-text); }
.log-time   { color: var(--color-text-muted); flex-shrink: 0; font-size: 10px; }
.log-text   { flex: 1; }
.log-empty  { color: var(--color-text-muted); font-size: 12px; padding: 8px; text-align: center; }
</style>
