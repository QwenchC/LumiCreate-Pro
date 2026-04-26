<template>
  <div class="tab-panel">
    <div class="tab-inner">

      <!-- ── Left: Config panel ── -->
      <aside class="config-panel card">
        <h4 class="config-title">💡 智能生成配置</h4>

        <div class="form-group">
          <label>篇幅</label>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" value="short" v-model="config.length" />
              短篇 (3–5 min)
            </label>
            <label class="radio-item">
              <input type="radio" value="medium" v-model="config.length" />
              中篇 (5–10 min)
            </label>
            <label class="radio-item">
              <input type="radio" value="long" v-model="config.length" />
              长篇 (10+ min)
            </label>
          </div>
        </div>

        <div class="form-group">
          <label>目标受众</label>
          <input v-model="config.audience" class="input" placeholder="例：青少年、都市白领" />
        </div>

        <div class="form-group">
          <label>故事风格</label>
          <select v-model="config.style" class="input select">
            <option value="">请选择</option>
            <option>热血</option>
            <option>恋爱</option>
            <option>悬疑</option>
            <option>搞笑</option>
            <option>奇幻</option>
            <option>日常</option>
            <option>科幻</option>
            <option>历史</option>
          </select>
        </div>

        <div class="form-group">
          <label>主题 / 核心灵感</label>
          <textarea
            v-model="config.theme"
            class="input textarea"
            placeholder="描述故事的核心主题、关键人物或灵感来源..."
            rows="4"
          />
        </div>

        <div class="config-actions">
          <button
            class="btn btn-primary w-full"
            :disabled="generating"
            @click="generate(false)"
          >
            {{ generating ? '生成中...' : '✨ 基于配置生成' }}
          </button>
          <button
            v-if="content"
            class="btn btn-secondary w-full"
            :disabled="generating"
            @click="generate(true)"
          >
            🔄 基于现有内容改写
          </button>
        </div>

        <!-- Status -->
        <div v-if="statusMsg" class="status-msg" :class="statusType">
          {{ statusMsg }}
        </div>
      </aside>

      <!-- ── Right: Editor ── -->
      <div class="editor-panel">
        <div class="editor-toolbar">
          <div class="toolbar-left">
            <span class="word-count">字数：{{ content.length }}</span>
            <span v-if="generating" class="gen-indicator">
              <span class="gen-dot" /> 生成中...
            </span>
            <span v-if="isDirty && !generating" class="dirty-indicator">● 未保存</span>
          </div>
          <div class="toolbar-right">
            <button
              v-if="generating"
              class="btn btn-danger btn-sm"
              @click="stopGenerate"
            >
              ■ 停止
            </button>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="!content || generating"
              @click="clearContent"
            >
              清空
            </button>
            <button
              class="btn btn-primary btn-sm"
              :disabled="!isDirty || saving"
              @click="save"
            >
              {{ saving ? '保存中...' : '💾 确认保存' }}
            </button>
          </div>
        </div>

        <div class="editor-wrap">
          <textarea
            ref="editorRef"
            v-model="content"
            class="editor-textarea"
            placeholder="在此输入文案内容，或使用左侧配置通过 LLM 自动生成..."
            :readonly="generating"
            @input="onInput"
          />
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({ projectId: String })
const emit = defineEmits(['dirty', 'saved'])

const API = 'http://127.0.0.1:18520/api'

// ── State ──────────────────────────────────────────────────────────────────────
const content  = ref('')
const isDirty  = ref(false)
const saving   = ref(false)
const generating = ref(false)
const statusMsg  = ref('')
const statusType = ref('') // 'ok' | 'err'
const editorRef  = ref(null)

const config = ref({
  length: 'medium',
  audience: '',
  style: '',
  theme: '',
})

let abortController = null

// ── Load from backend ──────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/manuscript`)
    if (res.ok) {
      const data = await res.json()
      content.value = data.content || ''
      if (data.config && Object.keys(data.config).length) {
        config.value = { ...config.value, ...data.config }
      }
    }
  } catch {}

  window.addEventListener('lumi:save-project', onGlobalSave)
})
onUnmounted(() => {
  window.removeEventListener('lumi:save-project', onGlobalSave)
  abortController?.abort()
})

// ── Generate ───────────────────────────────────────────────────────────────────
async function generate(useExisting = false) {
  generating.value = true
  statusMsg.value = ''
  abortController = new AbortController()

  if (!useExisting) content.value = ''

  try {
    const res = await fetch(`${API}/text-engine/generate-manuscript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config: config.value,
        existing_content: useExisting ? content.value : '',
      }),
      signal: abortController.signal,
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || res.statusText)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const obj = JSON.parse(raw)
          if (obj.error) throw new Error(obj.error)
          if (obj.text) {
            content.value += obj.text
            isDirty.value = true
            scrollToBottom()
          }
        } catch (e) {
          if (e.message !== 'undefined') console.warn('SSE parse error', e)
        }
      }
    }

    statusMsg.value = '✓ 生成完成，请检查内容后保存'
    statusType.value = 'ok'
    emit('dirty')
  } catch (e) {
    if (e.name === 'AbortError') {
      statusMsg.value = '已停止生成'
      statusType.value = ''
    } else {
      statusMsg.value = `生成失败: ${e.message}`
      statusType.value = 'err'
    }
  } finally {
    generating.value = false
    abortController = null
  }
}

function stopGenerate() {
  abortController?.abort()
}

function scrollToBottom() {
  nextTick(() => {
    if (editorRef.value) {
      editorRef.value.scrollTop = editorRef.value.scrollHeight
    }
  })
}

// ── Save ───────────────────────────────────────────────────────────────────────
async function save() {
  saving.value = true
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/manuscript`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content.value, config: config.value }),
    })
    if (!res.ok) throw new Error(await res.text())
    isDirty.value = false
    window.__lumiUnsaved = false
    statusMsg.value = '✓ 已保存'
    statusType.value = 'ok'
    emit('saved')
  } catch (e) {
    statusMsg.value = `保存失败: ${e.message}`
    statusType.value = 'err'
  } finally {
    saving.value = false
    setTimeout(() => { if (statusMsg.value.startsWith('✓')) statusMsg.value = '' }, 3000)
  }
}

function clearContent() {
  if (confirm('确定清空当前文案？')) {
    content.value = ''
    isDirty.value = true
    emit('dirty')
  }
}

function onInput() {
  isDirty.value = true
  window.__lumiUnsaved = true
  emit('dirty')
}

function onGlobalSave() {
  if (isDirty.value) save()
}
</script>

<style scoped>
.tab-panel { height: 100%; overflow: hidden; padding: 16px; }
.tab-inner  { display: flex; gap: 16px; height: 100%; }

/* ── Config panel ── */
.config-panel { width: 268px; flex-shrink: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 0; }
.config-title { font-size: 14px; font-weight: 700; margin-bottom: 16px; }
.form-group   { margin-bottom: 14px; }
.form-group label { display: block; font-size: 12px; color: var(--color-text-muted); margin-bottom: 5px; }
.radio-group  { display: flex; flex-direction: column; gap: 6px; }
.radio-item   { display: flex; align-items: center; gap: 7px; font-size: 13px; cursor: pointer; }
.radio-item input { accent-color: var(--color-accent); }
.select       { appearance: none; cursor: pointer; }
.textarea     { resize: vertical; min-height: 80px; font-family: inherit; }
.config-actions { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.w-full       { width: 100%; justify-content: center; }
.status-msg   { margin-top: 12px; font-size: 12px; padding: 8px 10px; border-radius: var(--radius); background: var(--color-surface-2); }
.status-msg.ok  { color: var(--color-success); }
.status-msg.err { color: var(--color-error); }

/* ── Editor panel ── */
.editor-panel   { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.editor-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius) var(--radius) 0 0;
  flex-shrink: 0;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 10px; }
.word-count     { font-size: 12px; color: var(--color-text-muted); }
.dirty-indicator { font-size: 12px; color: var(--color-warning); }
.gen-indicator  { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-accent); }
.gen-dot        { width: 7px; height: 7px; border-radius: 50%; background: var(--color-accent); animation: pulse 1s infinite; }
@keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }

.editor-wrap    { flex: 1; overflow: hidden; }
.editor-textarea {
  width: 100%; height: 100%;
  background: var(--color-surface); color: var(--color-text);
  border: 1px solid var(--color-border);
  border-top: none;
  border-radius: 0 0 var(--radius) var(--radius);
  padding: 16px 18px;
  font-size: 14px; line-height: 1.9;
  resize: none; outline: none; font-family: inherit;
  transition: border-color var(--transition);
}
.editor-textarea:focus { border-color: var(--color-accent); }
.editor-textarea[readonly] { opacity: 0.85; }
</style>

