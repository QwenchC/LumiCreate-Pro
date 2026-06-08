<template>
  <div class="sd-panel card">
    <div class="sd-header" @click="expanded = !expanded">
      <span class="sd-arrow">{{ expanded ? '▼' : '▶' }}</span>
      <h4>🎨 SD 高级参数 <span class="text-muted">(Stable Diffusion 工作流专用)</span></h4>
      <button v-if="expanded" class="btn btn-ghost btn-xs" @click.stop="refreshModelInfo"
              :disabled="loading" title="刷新可用模型列表">
        {{ loading ? '⏳' : '↻' }}
      </button>
    </div>

    <div v-if="expanded" class="sd-body">
      <!-- ── Checkpoint ── -->
      <div class="sd-row">
        <label class="sd-label">Checkpoint</label>
        <select v-model="local.checkpoint" class="input sd-input">
          <option value="">(用工作流默认)</option>
          <option v-for="c in modelInfo.checkpoints" :key="c" :value="c">{{ c }}</option>
        </select>
        <span v-if="modelInfo.error" class="sd-warn">⚠ {{ modelInfo.error }}</span>
      </div>

      <!-- ── LoRA chain ── -->
      <div class="sd-row">
        <label class="sd-label">LoRA 链</label>
        <div class="sd-lora-list">
          <div v-for="(l, i) in local.loras" :key="i" class="sd-lora-row">
            <select v-model="l.name" class="input sd-lora-name">
              <option value="">— None —</option>
              <option v-for="lo in modelInfo.loras" :key="lo" :value="lo">{{ lo }}</option>
            </select>
            <input type="number" min="-2" max="2" step="0.05"
                   v-model.number="l.strength" class="input sd-lora-strength"
                   title="LoRA 强度 (0 = 禁用，可负，常用 0.4 ~ 1.0)" />
            <button class="btn btn-ghost btn-xs"
                    @click="local.loras.splice(i, 1)" title="移除此 LoRA">✕</button>
          </div>
          <button class="btn btn-ghost btn-xs sd-add-lora"
                  :disabled="local.loras.length >= 7"
                  @click="local.loras.push({ name: '', strength: 0.8 })">
            ＋ 添加 LoRA <span class="text-muted">({{ local.loras.length }}/7)</span>
          </button>
        </div>
      </div>

      <!-- ── Negative prompt (顶层 prop 输入框，便于跨场景共用) ── -->
      <div class="sd-row">
        <label class="sd-label">负面提示词</label>
        <textarea v-model="local.negative_prompt" class="input sd-textarea" rows="3"
                  placeholder="worst quality, low quality, bad anatomy, ..."></textarea>
      </div>

      <!-- ── KSampler params ── -->
      <div class="sd-row sd-grid">
        <div class="sd-field">
          <label>步数 (steps)</label>
          <input type="number" min="1" max="100" step="1"
                 v-model.number="local.steps" class="input sd-num" />
        </div>
        <div class="sd-field">
          <label>CFG</label>
          <input type="number" min="0" max="30" step="0.1"
                 v-model.number="local.cfg" class="input sd-num" />
        </div>
        <div class="sd-field">
          <label>采样器</label>
          <select v-model="local.sampler_name" class="input sd-num">
            <option value="">(默认)</option>
            <option v-for="s in modelInfo.samplers" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div class="sd-field">
          <label>调度器</label>
          <select v-model="local.scheduler" class="input sd-num">
            <option value="">(默认)</option>
            <option v-for="s in modelInfo.schedulers" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </div>

      <p class="sd-hint">
        ⚙ 这些参数 + 顶部工具栏的"画风 / 每帧张数 / 分辨率"会一起作用；
        位面 ckpt 改了影响所有 LoRA 适配性，建议从已验证组合开始调
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'

const API = 'http://127.0.0.1:18520/api'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  // negative_prompt 跟 sd_params 分开存（属于每镜的提示词体系），从外部传入 + emit
  negativePrompt: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'update:negativePrompt'])

const expanded = ref(true)
const loading  = ref(false)
const modelInfo = reactive({
  checkpoints: [], loras: [], samplers: [], schedulers: [], error: '',
})

const local = reactive({
  checkpoint:      props.modelValue?.checkpoint      ?? '',
  loras:           Array.isArray(props.modelValue?.loras) ? [...props.modelValue.loras] : [],
  steps:           props.modelValue?.steps           ?? 0,
  cfg:             props.modelValue?.cfg             ?? 0,
  sampler_name:    props.modelValue?.sampler_name    ?? '',
  scheduler:       props.modelValue?.scheduler       ?? '',
  negative_prompt: props.negativePrompt ?? '',
})

// 双向同步：local → emit
watch(() => ({
  checkpoint:    local.checkpoint,
  loras:         local.loras,
  steps:         local.steps,
  cfg:           local.cfg,
  sampler_name:  local.sampler_name,
  scheduler:     local.scheduler,
}), v => emit('update:modelValue', { ...v }), { deep: true })
watch(() => local.negative_prompt,
      v => emit('update:negativePrompt', v))

// 父组件更新 → local
watch(() => props.modelValue, v => {
  if (!v) return
  if (local.checkpoint !== v.checkpoint)    local.checkpoint = v.checkpoint ?? ''
  if (JSON.stringify(local.loras) !== JSON.stringify(v.loras)) {
    local.loras = Array.isArray(v.loras) ? [...v.loras] : []
  }
  for (const k of ['steps','cfg','sampler_name','scheduler']) {
    if (local[k] !== v[k]) local[k] = v[k]
  }
}, { deep: true })

async function refreshModelInfo() {
  loading.value = true
  modelInfo.error = ''
  try {
    const r = await fetch(`${API}/image-engine/model-info`)
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    modelInfo.checkpoints = d.checkpoints || []
    modelInfo.loras       = d.loras       || []
    modelInfo.samplers    = d.samplers    || []
    modelInfo.schedulers  = d.schedulers  || []
    if (d.error) modelInfo.error = d.error
  } catch (e) {
    modelInfo.error = e.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(refreshModelInfo)
</script>

<style scoped>
.sd-panel { display: flex; flex-direction: column; gap: 10px;
            background: var(--bg-panel); border: 1px solid var(--border);
            border-radius: 6px; margin: 10px 16px; padding: 0; overflow: hidden; }
.sd-header { display: flex; align-items: center; gap: 8px; padding: 10px 14px;
             background: var(--bg-input); cursor: pointer; user-select: none;
             border-bottom: 1px solid var(--border); }
.sd-header h4 { margin: 0; font-size: 14px; flex: 1; }
.sd-arrow { font-size: 10px; color: var(--text-muted); }
.sd-body { padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; }
.sd-row { display: flex; flex-direction: column; gap: 4px; }
.sd-row.sd-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; }
.sd-label { font-size: 12px; color: var(--text-muted); }
.sd-input { font-size: 13px; }
.sd-textarea { font-size: 12px; font-family: monospace; resize: vertical; }
.sd-field label { font-size: 11px; color: var(--text-muted); display: block; margin-bottom: 4px; }
.sd-num { width: 100%; height: 28px; font-size: 12px; }

.sd-lora-list { display: flex; flex-direction: column; gap: 6px; }
.sd-lora-row { display: grid; grid-template-columns: 1fr 90px 28px; gap: 8px;
               align-items: center; }
.sd-lora-name { font-size: 12px; }
.sd-lora-strength { height: 28px; font-size: 12px; text-align: right; padding: 0 6px; }
.sd-add-lora { align-self: flex-start; }

.sd-warn { color: var(--danger, #fc8181); font-size: 11px; margin-top: 4px; }
.sd-hint { font-size: 11px; color: var(--text-muted); margin: 0; }
</style>
