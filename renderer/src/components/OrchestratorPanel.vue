<template>
  <div class="orch-overlay" @click.self="onClose">
    <div class="orch-panel card">
      <div class="orch-header">
        <h3>🚀 一键全流程生成</h3>
        <button class="btn btn-ghost btn-xs" @click="onClose">✕</button>
      </div>

      <div v-if="!running && !finished" class="orch-config">
        <p class="form-hint">
          按下方阶段顺序串跑。已生成的内容会自动跳过（不会覆盖既有图片/音频）。
          视频与合并阶段需要在「视频生成」tab 手动触发（依赖图片 URL 拼装）。
        </p>

        <div class="form-group">
          <label>启用阶段</label>
          <div class="stage-checks">
            <label v-for="s in ALL_STAGES" :key="s.key" class="stage-check">
              <input type="checkbox" :value="s.key" v-model="selectedStages" />
              <span>{{ s.icon }} {{ s.label }}</span>
            </label>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group" style="flex:1">
            <label>图片工作流</label>
            <select v-model="imageWorkflow" class="input">
              <option value="">— 选择 —</option>
              <option v-for="wf in imageWorkflows" :key="wf" :value="wf">{{ wf }}</option>
            </select>
          </div>
          <div class="form-group" style="flex:1">
            <label>视频工作流（仅传递）</label>
            <select v-model="videoWorkflow" class="input">
              <option value="">— 选择 —</option>
              <option v-for="wf in videoWorkflows" :key="wf" :value="wf">{{ wf }}</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>🎬 分镜方式</label>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" :value="false" v-model="manualSplit" />
              <span><b>AI 有机分镜（推荐）</b><br>
                <span class="text-muted" style="font-size:11px">
                  按情节 / 视角 / 动作切分，宁多不少。需要 LLM 调用，耗时稍长但镜次质量高。
                </span>
              </span>
            </label>
            <label class="radio-item">
              <input type="radio" :value="true" v-model="manualSplit" />
              <span>机械式手动分镜<br>
                <span class="text-muted" style="font-size:11px">
                  按句切分 + 字符上限；快但忽略语义，适合纯朗读快速跑通。
                </span>
              </span>
            </label>
          </div>
          <div v-if="manualSplit" class="form-row" style="margin-top:6px">
            <div class="form-group" style="flex:1">
              <label style="font-size:12px">每镜最大字符数</label>
              <input type="number" min="20" max="112" v-model.number="maxCharsPerScene" class="input" />
            </div>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group" style="flex:1">
            <label>朗读语速</label>
            <select v-model="rate" class="input">
              <option value="-25%">慢</option>
              <option value="+0%">正常</option>
              <option value="+25%">快（默认）</option>
              <option value="+50%">很快</option>
            </select>
          </div>
          <div class="form-group" style="flex:1">
            <label>字幕字号（0 自适应）</label>
            <input type="number" min="0" max="60" v-model.number="subtitleFontSize" class="input" />
          </div>
        </div>

        <div class="orch-actions">
          <button class="btn btn-ghost btn-sm" @click="onClose">取消</button>
          <button class="btn btn-primary btn-sm" :disabled="!canStart" @click="start">▶ 开始</button>
        </div>
      </div>

      <div v-else class="orch-progress">
        <div class="orch-stages">
          <div v-for="s in ALL_STAGES" :key="s.key"
               class="orch-stage"
               :class="{
                 active:  stageStatus[s.key] === 'active',
                 done:    stageStatus[s.key] === 'done',
                 error:   stageStatus[s.key] === 'error',
                 skipped: stageStatus[s.key] === 'skipped',
               }">
            <span class="orch-stage-icon">{{ stageIcon(s.key) }}</span>
            <span class="orch-stage-label">{{ s.icon }} {{ s.label }}</span>
            <span class="orch-stage-detail">{{ stageDetail[s.key] || '' }}</span>
          </div>
        </div>

        <div class="orch-log">
          <div v-for="(line, i) in logTail" :key="i" class="orch-log-line" :class="line.type">
            <span class="orch-log-stage">[{{ line.stage }}]</span> {{ line.text }}
          </div>
        </div>

        <div class="orch-actions">
          <button v-if="running" class="btn btn-danger btn-sm" @click="stop">⏹ 停止</button>
          <button v-else class="btn btn-secondary btn-sm" @click="reset">重新配置</button>
          <button v-if="finished" class="btn btn-primary btn-sm" @click="onClose">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['close'])

const API = 'http://127.0.0.1:18520/api'

// 顺序与后端 DEFAULT_STAGES 保持一致：merge 必须在 subtitle 之前
const ALL_STAGES = [
  { key: 'scenes',   label: '分镜',     icon: '🎞' },
  { key: 'prompts',  label: '帧提示词', icon: '🖌' },
  { key: 'images',   label: '图片',     icon: '🖼' },
  { key: 'audio',    label: '音频',     icon: '🎙' },
  { key: 'video',    label: '视频',     icon: '🎬' },
  { key: 'merge',    label: '合并',     icon: '🎯' },
  { key: 'subtitle', label: '字幕',     icon: '💬' },
]

const selectedStages = ref(['scenes', 'prompts', 'images', 'audio', 'video', 'merge', 'subtitle'])
const imageWorkflow  = ref('')
const videoWorkflow  = ref('')
const manualSplit    = ref(false)       // 默认 AI 有机分镜
const maxCharsPerScene = ref(50)
const rate = ref('+25%')
const subtitleFontSize = ref(0)
// v1.4.1: 图片和视频用各自支持的子集，不混在同一个 list
const imageWorkflows = ref([])
const videoWorkflows = ref([])

const running  = ref(false)
const finished = ref(false)
const stageStatus = reactive({})   // {stage: 'pending'|'active'|'done'|'error'|'skipped'}
const stageDetail = reactive({})   // {stage: '<status text>'}
const logBuffer   = ref([])

const logTail = computed(() => logBuffer.value.slice(-100))

let _abort = null

const canStart = computed(() => selectedStages.value.length && (
  !selectedStages.value.includes('images') || imageWorkflow.value
))

function stageIcon(key) {
  switch (stageStatus[key]) {
    case 'done':    return '✓'
    case 'active':  return '◐'
    case 'error':   return '✗'
    case 'skipped': return '–'
    default:        return ' '
  }
}

async function loadWorkflows() {
  try {
    const [ri, rv] = await Promise.all([
      fetch(`${API}/image-engine/workflows`),
      fetch(`${API}/video-engine/workflows`),
    ])
    if (ri.ok) imageWorkflows.value = await ri.json()
    if (rv.ok) videoWorkflows.value = await rv.json()
  } catch {}
  // Pre-fill from settings if available
  try {
    const sr = await fetch(`${API}/settings`)
    if (sr.ok) {
      const s = await sr.json()
      imageWorkflow.value = s.image_engine?.default_workflow || imageWorkflow.value
      videoWorkflow.value = s.video_engine?.default_workflow || videoWorkflow.value
    }
  } catch {}
}

function reset() {
  running.value  = false
  finished.value = false
  for (const k of Object.keys(stageStatus)) {
    stageStatus[k] = ''
    stageDetail[k] = ''
  }
  logBuffer.value = []
}

function appendLog(stage, text, type = 'info') {
  logBuffer.value.push({ stage: stage || '?', text, type })
  // Cap to 500 lines to avoid runaway memory
  if (logBuffer.value.length > 500) logBuffer.value.splice(0, logBuffer.value.length - 500)
}

async function start() {
  reset()
  running.value = true
  for (const k of selectedStages.value) stageStatus[k] = 'pending'

  _abort = new AbortController()
  try {
    const resp = await fetch(`${API}/orchestrator/generate-all`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal:  _abort.signal,
      body: JSON.stringify({
        project_id:         props.projectId,
        stages:             selectedStages.value,
        image_workflow:     imageWorkflow.value,
        video_workflow:     videoWorkflow.value,
        subtitle_font_size: subtitleFontSize.value,
        manual_split:       manualSplit.value,
        max_chars_per_scene: maxCharsPerScene.value,
        rate:               rate.value,
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`)

    const reader  = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') continue
        try { handleEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') appendLog('?', `请求失败: ${e.message}`, 'error')
  } finally {
    running.value  = false
    finished.value = true
  }
}

function handleEvent(ev) {
  const { event, stage } = ev
  if (event === 'pipeline_start') {
    appendLog('pipeline', `开始执行 ${ev.stages?.join(' → ') || ''}`)
  } else if (event === 'stage_start') {
    stageStatus[stage] = 'active'
    if (ev.count) stageDetail[stage] = `共 ${ev.count} 项`
    appendLog(stage, ev.count ? `开始（${ev.count} 项）` : '开始')
  } else if (event === 'stage_done') {
    stageStatus[stage] = 'done'
    stageDetail[stage] = ev.count != null ? `完成 (${ev.count})` : '完成'
    appendLog(stage, '完成 ✓', 'success')
  } else if (event === 'stage_error') {
    stageStatus[stage] = 'error'
    stageDetail[stage] = '出错'
    appendLog(stage, `错误: ${ev.message}`, 'error')
  } else if (event === 'stage_skipped') {
    stageStatus[stage] = 'skipped'
    stageDetail[stage] = '已跳过'
    appendLog(stage, `跳过：${ev.message || ''}`, 'warn')
  } else if (event === 'pipeline_done') {
    appendLog('pipeline', '全部完成 🎉', 'success')
  } else if (event === 'pipeline_error') {
    appendLog('pipeline', `失败: ${ev.message}`, 'error')
  } else if (event === 'completed' || event === 'scene_done') {
    // 上游 image / audio / video / subtitle 阶段透传的成功事件
    appendLog(stage || '?', `完成 ${ev.scene_id || ev.frame_type || ''}`)
  } else if (event === 'scene_error' || event === 'audio_scene_error') {
    appendLog(stage || '?', `失败 ${ev.scene_id || ''}: ${ev.message || ''}`, 'error')
  } else if (event === 'subtitle_skip' || event === 'merge_skip' || event === 'video_skip') {
    appendLog(stage || '?', `跳过: ${ev.message || ''}`, 'warn')
  } else if (event === 'merge_done') {
    appendLog('merge', `输出 ${ev.output_path || ''}`, 'success')
  } else if (event === 'merge_error') {
    appendLog('merge', `失败: ${ev.message || ''}`, 'error')
  } else if (event === 'progress') {
    if (ev.value != null && ev.max != null) {
      stageDetail[stage] = `${ev.value}/${ev.max}`
    }
  }
}

function stop() {
  _abort?.abort()
  appendLog('pipeline', '用户中断', 'warn')
}

function onClose() {
  if (running.value) {
    if (!confirm('正在跑全流程，确认中断并关闭？')) return
    _abort?.abort()
  }
  emit('close')
}

onMounted(loadWorkflows)
onUnmounted(() => { _abort?.abort() })
</script>

<style scoped>
.orch-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.orch-panel {
  width: 720px; max-width: calc(100vw - 40px); max-height: calc(100vh - 40px);
  display: flex; flex-direction: column;
  background: var(--color-surface); border-radius: 8px;
  padding: 16px 20px;
}
.orch-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.orch-header h3 { margin: 0; font-size: 16px; }

.stage-checks { display: flex; flex-wrap: wrap; gap: 8px 14px; }
.stage-check  { display: flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer; }

.form-row { display: flex; gap: 12px; }

.orch-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }

.orch-progress { display: flex; flex-direction: column; gap: 10px; overflow: hidden; }
.orch-stages { display: flex; flex-direction: column; gap: 4px; }
.orch-stage {
  display: grid; grid-template-columns: 20px 120px 1fr; gap: 8px;
  padding: 4px 8px; border-radius: 4px; font-size: 13px;
  background: var(--color-surface-2);
}
.orch-stage.active  { background: rgba(80,140,220,.15); border-left: 3px solid var(--color-accent); }
.orch-stage.done    { background: rgba(60,180,90,.10); }
.orch-stage.error   { background: rgba(220,60,60,.10); border-left: 3px solid var(--color-error); }
.orch-stage.skipped { opacity: .55; }
.orch-stage-icon  { font-weight: 700; text-align: center; }
.orch-stage-detail { color: var(--color-text-muted); font-size: 11px; align-self: center; }

.orch-log {
  flex: 1; min-height: 200px; max-height: 320px; overflow: auto;
  background: rgba(0,0,0,.25); border-radius: 4px; padding: 8px;
  font-family: ui-monospace, monospace; font-size: 11px;
  border: 1px solid var(--color-border);
}
.orch-log-line { padding: 1px 0; }
.orch-log-line.success { color: #6cf; }
.orch-log-line.warn    { color: #fb3; }
.orch-log-line.error   { color: #f66; }
.orch-log-stage { color: var(--color-text-muted); margin-right: 4px; }
</style>
