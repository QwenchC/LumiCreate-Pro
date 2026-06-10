<template>
  <Teleport to="body">
    <div class="eg-overlay" @click.self="$emit('close')">
      <div class="eg-modal">
        <div class="eg-header">
          <h3>✨ 生成图片到元素库</h3>
          <span class="text-muted eg-hint">
            复用当前图片引擎与工作流（含 Ideogram）→ 生成结果自动存入
            {{ scopeLabel }} 当前文件夹
          </span>
          <button class="btn btn-ghost btn-xs" @click="$emit('close')">✕</button>
        </div>

        <div class="eg-body">
          <!-- 左：表单 -->
          <div class="eg-form">
            <label class="eg-field">
              工作流 / 模型
              <select v-model="workflow" class="eg-inp" :disabled="busy">
                <option v-if="!workflows.length" value="">（无可用工作流）</option>
                <option v-for="w in workflows" :key="w" :value="w">{{ w }}</option>
              </select>
            </label>

            <div class="eg-field">
              <div class="eg-prompt-head">
                <span>提示词{{ isIdeogram ? '（Ideogram：纯 JSON caption）' : '' }}</span>
                <button v-if="isIdeogram" class="btn btn-ghost btn-xs"
                        @click="builderOpen = true" :disabled="busy">🧩 构建器</button>
              </div>
              <textarea v-model="prompt" class="eg-inp" rows="4"
                        :placeholder="isIdeogram ? '用 🧩 构建器生成结构化 JSON，或粘贴 caption JSON' : '描述要生成的图片素材…'"></textarea>
            </div>

            <label v-if="!isIdeogram" class="eg-field">
              负面提示词（可选）
              <input v-model="negative" class="eg-inp" placeholder="lowres, blurry…" :disabled="busy" />
            </label>

            <div class="eg-row">
              <label class="eg-field-sm">宽<input type="number" v-model.number="width" class="eg-inp" min="64" step="8" :disabled="busy" /></label>
              <label class="eg-field-sm">高<input type="number" v-model.number="height" class="eg-inp" min="64" step="8" :disabled="busy" /></label>
              <label class="eg-field-sm">数量<input type="number" v-model.number="count" class="eg-inp" min="1" max="8" :disabled="busy" /></label>
              <label class="eg-field-sm">种子<input type="number" v-model.number="seed" class="eg-inp" placeholder="-1 随机" :disabled="busy" /></label>
            </div>

            <div class="eg-actions">
              <button class="btn btn-primary" :disabled="busy || !workflow || !prompt.trim()"
                      @click="run">
                {{ busy ? `生成中… ${doneCount}/${count}` : '✨ 生成并入库' }}
              </button>
              <span v-if="errorMsg" class="eg-error">⚠ {{ errorMsg }}</span>
            </div>
          </div>

          <!-- 右：结果 -->
          <div class="eg-results">
            <div class="eg-results-title">本次生成（{{ saved.length }} 张已入库）</div>
            <div v-if="!results.length" class="eg-results-empty text-muted">
              生成的图片会显示在这里，并自动保存到元素库
            </div>
            <div v-else class="eg-results-grid">
              <div v-for="(r, i) in results" :key="i" class="eg-result-card">
                <img v-if="r.src" :src="r.src" class="eg-result-thumb" />
                <div v-else class="eg-result-thumb eg-result-pending">
                  {{ r.error ? '✕' : '…' }}
                </div>
                <div class="eg-result-state" :class="{ ok: r.saved, err: r.error }">
                  {{ r.error ? '失败' : (r.saved ? '✓ 已入库' : (r.src ? '保存中…' : (r.progress || '排队…'))) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>

  <Ideogram4PromptBuilder v-if="builderOpen"
                          :initial-json="prompt"
                          :initial-w="width"
                          :initial-h="height"
                          @apply="onBuilderApply"
                          @close="builderOpen = false" />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import Ideogram4PromptBuilder from './Ideogram4PromptBuilder.vue'

const props = defineProps({
  // 当前 scope 的 elements API 根（如 .../api/elements 或 .../api/projects/{pid}/elements）
  uploadBase: { type: String, required: true },
  folderId:   { type: [Number, null], default: null },
  scopeLabel: { type: String, default: '元素库' },
})
const emit = defineEmits(['saved', 'close'])

const API = 'http://127.0.0.1:18520/api'

const workflows = ref([])
const workflow  = ref('')
const prompt    = ref('')
const negative  = ref('')
const width     = ref(1024)
const height    = ref(1024)
const count     = ref(1)
const seed      = ref(-1)

const busy      = ref(false)
const doneCount = ref(0)
const errorMsg  = ref('')
const results   = ref([])     // [{src, saved, error, progress}]
const builderOpen = ref(false)

const isIdeogram = computed(() => workflow.value === 'image_ideogram4_t2i')
const saved = computed(() => results.value.filter(r => r.saved))

onMounted(async () => {
  try {
    const [wfRes, setRes] = await Promise.all([
      axios.get(`${API}/image-engine/workflows`),
      axios.get(`${API}/settings`).catch(() => ({ data: {} })),
    ])
    workflows.value = wfRes.data || []
    const img = setRes.data?.image_engine || {}
    if (img.image_width)  width.value  = img.image_width
    if (img.image_height) height.value = img.image_height
    // 默认选中：设置里的 default_workflow（若在列表里），否则第一个
    if (img.default_workflow && workflows.value.includes(img.default_workflow)) {
      workflow.value = img.default_workflow
    } else if (workflows.value.length) {
      workflow.value = workflows.value[0]
    }
  } catch (e) {
    errorMsg.value = '加载工作流失败：' + (e?.response?.data?.detail || e.message)
  }
})

function onBuilderApply(jsonStr) {
  prompt.value = jsonStr
}

async function run() {
  if (busy.value) return
  busy.value = true
  errorMsg.value = ''
  doneCount.value = 0
  results.value = Array.from({ length: count.value }, () => ({
    src: '', saved: false, error: '', progress: '',
  }))
  for (let i = 0; i < count.value; i++) {
    await generateOne(i)
    doneCount.value = i + 1
  }
  busy.value = false
}

async function generateOne(idx) {
  const slot = results.value[idx]
  try {
    const reqSeed = (seed.value !== undefined && seed.value >= 0)
      ? seed.value + idx          // 多张时按序错开，避免完全重复
      : null
    const resp = await fetch(`${API}/image-engine/generate-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name:   workflow.value,
        positive_prompt: prompt.value,
        negative_prompt: isIdeogram.value ? '' : negative.value,
        width: width.value, height: height.value,
        seed: reqSeed,
      }),
    })
    if (!resp.ok) {
      let d = 'HTTP ' + resp.status
      try { d = (await resp.json()).detail || d } catch {}
      throw new Error(d)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let b64 = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        let evt
        try { evt = JSON.parse(raw) } catch { continue }
        if (evt.event === 'progress') {
          slot.progress = evt.message || (evt.percent != null ? evt.percent + '%' : '生成中…')
        } else if (evt.event === 'completed') {
          b64 = (evt.images || [])[0]?.data || ''
        } else if (evt.event === 'error') {
          throw new Error(evt.message || '生成失败')
        }
      }
    }
    if (!b64) throw new Error('未返回图片数据')
    slot.src = 'data:image/png;base64,' + b64
    // 入库
    await saveElement(b64)
    slot.saved = true
    emit('saved')
  } catch (e) {
    slot.error = e.message || String(e)
    if (!errorMsg.value) errorMsg.value = slot.error
  }
}

async function saveElement(b64) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const name = `gen_${stamp}_${Math.random().toString(36).slice(2, 6)}`
  await fetch(`${props.uploadBase}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_id: props.folderId,
      name,
      filename: name + '.png',
      mime: 'image/png',
      data: b64,
      source: 't2i',
      source_meta: { workflow: workflow.value, prompt: prompt.value, seed: seed.value },
      width: width.value, height: height.value,
    }),
  })
}
</script>

<style scoped>
.eg-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
}
.eg-modal {
  background: var(--color-surface, #1e1e1e);
  color: var(--color-text, #eee);
  border: 1px solid var(--color-border, #333);
  border-radius: 10px;
  width: min(960px, 96vw); max-height: 92vh;
  display: flex; flex-direction: column; gap: 10px;
  padding: 14px 16px;
}
.eg-header { display: flex; align-items: center; gap: 10px; }
.eg-header h3 { margin: 0; font-size: 15px; }
.eg-hint { font-size: 11px; flex: 1; }

.eg-body { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 14px; min-height: 0; }
.eg-form { display: flex; flex-direction: column; gap: 10px; }
.eg-field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--color-text-muted, #aaa); }
.eg-prompt-head { display: flex; align-items: center; justify-content: space-between; }
.eg-row { display: flex; gap: 8px; }
.eg-field-sm { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--color-text-muted, #aaa); flex: 1; }
.eg-inp {
  background: var(--color-bg, #111); color: var(--color-text);
  border: 1px solid var(--color-border); border-radius: 4px;
  padding: 5px 7px; font-size: 12px; font-family: inherit; width: 100%;
}
textarea.eg-inp { resize: vertical; }
.eg-actions { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.eg-error { font-size: 11px; color: var(--color-error, #f66); }

.eg-results { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.eg-results-title { font-size: 12px; font-weight: 600; border-bottom: 1px solid var(--color-border); padding-bottom: 4px; }
.eg-results-empty { font-size: 12px; padding: 20px; text-align: center; }
.eg-results-grid {
  display: grid; gap: 8px; overflow: auto;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
}
.eg-result-card { display: flex; flex-direction: column; gap: 3px; }
.eg-result-thumb {
  width: 100%; aspect-ratio: 1; object-fit: cover;
  border-radius: 5px; background: rgba(0,0,0,0.2);
  display: flex; align-items: center; justify-content: center;
}
.eg-result-pending { color: #888; font-size: 20px; }
.eg-result-state { font-size: 10px; color: var(--color-text-muted, #999); text-align: center; }
.eg-result-state.ok { color: #6c6; }
.eg-result-state.err { color: var(--color-error, #f66); }
</style>
