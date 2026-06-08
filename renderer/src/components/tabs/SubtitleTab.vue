<template>
  <div class="tab-panel subtitle-tab">

    <!-- ── Toolbar ── -->
    <div class="sub-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">字幕生成</h3>
        <span v-if="!hasFinalVideo" class="badge-warn">⚠ 需先合并视频</span>
        <span v-else-if="hasSrt" class="badge-ok">✓ 字幕已生成</span>
      </div>
      <div class="toolbar-right">
        <button
          class="btn btn-ghost btn-sm"
          :disabled="!hasFinalVideo"
          @click="refreshStatus"
          title="刷新状态"
        >⟳ 刷新</button>
        <button
          v-if="hasEmbedded"
          class="btn btn-secondary btn-sm"
          @click="openEmbedded"
        >📂 打开嵌字幕视频</button>
        <button
          v-if="hasEmbedded"
          class="btn btn-secondary btn-sm"
          @click="bgmMixerOpen = true"
          title="给 final_video_subbed.mp4 叠加背景音乐"
        >🎵 添加 BGM</button>
      </div>
    </div>

    <!-- v1.4.2: BGM 混音对话框 -->
    <BgmMixerDialog v-if="bgmMixerOpen"
                    :project-id="projectId"
                    source="final_video_subbed"
                    @close="bgmMixerOpen = false" />

    <!-- ── Not ready ── -->
    <div v-if="!hasFinalVideo" class="empty-state">
      <div class="empty-icon">🎬</div>
      <p>请先在「视频生成」中合并所有分镜，生成 final_video.mp4</p>
    </div>

    <!-- ── Main UI (only when final_video exists) ── -->
    <div v-else class="sub-body">

      <!-- Left column: script editor -->
      <div class="sub-col sub-col-script card">
        <div class="col-header">
          <span class="col-title">字幕脚本</span>
          <div class="col-actions">
            <button class="btn btn-ghost btn-xs" @click="loadFromScenes" title="从分镜自动导入台词">
              ⬇ 从分镜导入
            </button>
            <button class="btn btn-ghost btn-xs" @click="showPreprocess = true" title="粘贴原稿并自动断句">
              ✂ 断句工具
            </button>
          </div>
        </div>
        <div class="script-hint">每行一条字幕（空行忽略）</div>
        <textarea
          v-model="scriptText"
          class="input script-textarea"
          placeholder="在此粘贴字幕文本，每行一句…"
          spellcheck="false"
        />
        <div class="line-count">{{ scriptLines.length }} 行</div>
      </div>

      <!-- Right column: settings + actions -->
      <div class="sub-col sub-col-settings">

        <!-- Config card -->
        <div class="card config-card">
          <div class="config-title">生成设置</div>
          <div class="cfg-row">
            <label class="cfg-label">帧率（需与视频一致）</label>
            <select v-model.number="fps" class="input select-sm">
              <option :value="24">24fps（AI标准 23.976）</option>
              <option :value="25">25fps（PAL）</option>
              <option :value="30">30fps（29.97）</option>
            </select>
          </div>
          <div class="cfg-row">
            <label class="cfg-label">Whisper 模型</label>
            <select v-model="modelName" class="input select-sm">
              <option value="base">base（快，适合中文）</option>
              <option value="small">small（较慢，更准确）</option>
              <option value="medium">medium（慢）</option>
            </select>
          </div>
          <div class="cfg-row">
            <label class="cfg-label">整体偏移（秒，负=提前）</label>
            <input
              v-model.number="manualAdvance"
              type="number" step="0.05"
              class="input input-sm"
              style="width:90px"
            />
          </div>
        </div>

        <!-- Generate SRT -->
        <div class="card action-card">
          <button
            class="btn btn-primary btn-block"
            :disabled="generating || !scriptLines.length"
            @click="generateSrt"
          >
            {{ generating ? '生成中…' : '▶ 生成字幕（SRT）' }}
          </button>

          <!-- Step progress -->
          <div v-if="generating || genPct >= 0" class="step-progress">
            <div class="progress-track" style="margin-bottom:6px">
              <div
                class="progress-fill"
                :class="{ indeterminate: genPct < 0 }"
                :style="genPct >= 0 ? { width: genPct + '%' } : {}"
              />
            </div>
            <div class="step-list">
              <span
                v-for="s in GEN_STEPS" :key="s.key"
                class="step-chip"
                :class="stepClass(s.key)"
              >{{ s.label }}</span>
            </div>
          </div>

          <!-- Progress log -->
          <div v-if="genLog.length" class="gen-log">
            <div v-for="(msg, i) in genLog" :key="i" class="log-line" :class="msg.type">
              {{ msg.text }}
            </div>
          </div>

          <!-- SRT preview -->
          <template v-if="hasSrt && srtPreview">
            <div class="srt-label">字幕预览（前 10 条）</div>
            <pre class="srt-preview">{{ srtPreview }}</pre>
            <div class="srt-actions">
              <button class="btn btn-ghost btn-xs" @click="openSrtFolder">📂 打开 SRT 目录</button>
            </div>
          </template>
        </div>

        <!-- Embed subtitles -->
        <div class="card action-card" v-if="hasSrt">
          <div class="embed-title">嵌入字幕到视频</div>
          <p class="embed-hint">将 SRT 字幕烧录进 fixed_cfr.mp4，生成 final_video_subbed.mp4</p>

          <!-- Font config -->
          <div class="cfg-row" style="margin-bottom:6px">
            <label class="cfg-label">字幕字体</label>
            <select v-model="fontName" class="input select-sm">
              <option value="等线 Bold">等线 Bold（推荐）</option>
              <option value="等线">等线</option>
              <option value="微软雅黑 Bold">微软雅黑 Bold</option>
              <option value="微软雅黑">微软雅黑</option>
              <option value="黑体">黑体</option>
              <option value="宋体">宋体</option>
              <option value="仿宋">仿宋</option>
              <option value="楷体">楷体</option>
            </select>
          </div>
          <div class="cfg-row" style="margin-bottom:6px">
            <label class="cfg-label">字体大小</label>
            <input v-model.number="fontSize" type="number" min="10" max="60"
              class="input input-sm" style="width:70px" />
          </div>

          <!-- D2: 颜色与描边 -->
          <div class="cfg-row" style="margin-bottom:6px">
            <label class="cfg-label">文字颜色</label>
            <input v-model="primaryColour" type="color" class="input input-sm" style="width:70px;padding:0" />
            <label class="cfg-label" style="margin-left:12px">描边色</label>
            <input v-model="outlineColour" type="color" class="input input-sm" style="width:70px;padding:0" />
          </div>
          <div class="cfg-row" style="margin-bottom:6px">
            <label class="cfg-label">描边粗细</label>
            <input v-model.number="outlineWidth" type="number" min="0" max="6" step="0.5"
              class="input input-sm" style="width:70px" />
            <label class="cfg-label" style="margin-left:12px">阴影</label>
            <input v-model.number="shadowDepth" type="number" min="0" max="6" step="0.5"
              class="input input-sm" style="width:70px" />
          </div>
          <div class="cfg-row" style="margin-bottom:6px">
            <label class="cfg-label">位置</label>
            <select v-model="position" class="input select-sm" style="width:90px">
              <option value="bottom">底部</option>
              <option value="center">居中</option>
              <option value="top">顶部</option>
            </select>
            <label class="cfg-label" style="margin-left:12px">边距 V</label>
            <input v-model.number="marginV" type="number" min="0" max="500" step="5"
              class="input input-sm" style="width:70px" />
          </div>
          <div class="cfg-row" style="margin-bottom:10px">
            <label class="cfg-label">
              <input type="checkbox" v-model="bold" /> 粗体
            </label>
            <label class="cfg-label" style="margin-left:12px">
              <input type="checkbox" v-model="italic" /> 斜体
            </label>
            <button class="btn btn-ghost btn-xs" style="margin-left:auto" @click="resetStyle">↺ 重置样式</button>
          </div>

          <button
            class="btn btn-secondary btn-block"
            :disabled="embedding"
            @click="embedSubtitles"
          >
            {{ embedding ? '烧录中…' : '🔤 嵌入字幕' }}
          </button>

          <!-- Embed progress bar -->
          <div v-if="embedding || embedPct > 0" class="progress-wrap">
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: embedPct + '%' }" />
            </div>
            <span class="pct-label">{{ embedPct }}%</span>
          </div>

          <div v-if="embedLog.length" class="gen-log">
            <div v-for="(msg, i) in embedLog" :key="i" class="log-line" :class="msg.type">
              {{ msg.text }}
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- ── Preprocess dialog ── -->
    <Teleport to="body">
      <div v-if="showPreprocess" class="overlay" @click.self="showPreprocess = false">
        <div class="dialog card" style="width:540px">
          <div class="dialog-title">✂ 断句工具</div>
          <p style="font-size:13px;color:var(--color-text-muted);margin-bottom:8px">
            粘贴原稿（或台词），自动按 ，。？！：""…—— 断句，每句变为一行
          </p>
          <div style="display:flex;gap:6px;margin-bottom:8px">
            <button class="btn btn-ghost btn-xs" @click="loadManuscriptToPreprocess" :disabled="loadingManuscript">
              {{ loadingManuscript ? '加载中…' : '📋 从文案复制' }}
            </button>
          </div>
          <textarea
            v-model="rawManuscript"
            class="input script-textarea"
            style="height:200px"
            placeholder="粘贴原稿文字…"
          />
          <div class="dialog-actions">
            <button class="btn btn-ghost btn-sm" @click="showPreprocess = false">取消</button>
            <button class="btn btn-primary btn-sm" @click="applyPreprocess">应用到脚本</button>
          </div>
        </div>
      </div>
    </Teleport>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import BgmMixerDialog from '../BgmMixerDialog.vue'

// v1.4.2: BGM 混音对话框可见性
const bgmMixerOpen = ref(false)

const props = defineProps({ projectId: String })

const API = 'http://127.0.0.1:18520/api/subtitle-engine'

// ── Status ────────────────────────────────────────────────────────────────────
const hasFinalVideo = ref(false)
const hasSrt        = ref(false)
const hasEmbedded   = ref(false)
const embeddedPath  = ref('')

async function refreshStatus() {
  try {
    const { data } = await axios.get(`${API}/status/${props.projectId}`)
    hasFinalVideo.value = data.has_final_video
    hasSrt.value        = data.has_srt
    hasEmbedded.value   = data.has_embedded
    embeddedPath.value  = data.embedded_path || ''
    if (hasSrt.value) loadSrtPreview()
  } catch {}
}

// ── Script editor ─────────────────────────────────────────────────────────────
const scriptText = ref('')
const scriptLines = computed(() =>
  scriptText.value.split('\n').map(l => l.trim()).filter(l => l)
)

async function loadFromScenes() {
  try {
    const { data } = await axios.get(`${API}/script/${props.projectId}`)
    if (data.lines?.length) {
      scriptText.value = data.lines.join('\n')
    }
  } catch {}
}

// ── Preprocess dialog ─────────────────────────────────────────────────────────
const showPreprocess    = ref(false)
const rawManuscript     = ref('')
const loadingManuscript = ref(false)

async function loadManuscriptToPreprocess() {
  loadingManuscript.value = true
  try {
    const { data } = await axios.get(`http://127.0.0.1:18520/api/projects/${props.projectId}/manuscript`)
    if (data?.content?.trim()) {
      rawManuscript.value = data.content
    }
  } catch {}
  loadingManuscript.value = false
}

async function applyPreprocess() {
  if (!rawManuscript.value.trim()) return
  try {
    const { data } = await axios.post(`${API}/preprocess-text`, { text: rawManuscript.value })
    scriptText.value = data.text
    showPreprocess.value = false
    rawManuscript.value  = ''
  } catch {}
}

// ── Config ────────────────────────────────────────────────────────────────────
const fps           = ref(24)
const modelName     = ref('base')
const manualAdvance = ref(0.0)

// ── Font (embed) ──────────────────────────────────────────────────────────────
const fontName = ref('等线 Bold')
const fontSize = ref(18)
// D2: 扩展样式
const primaryColour = ref('#FFFFFF')
const outlineColour = ref('#000000')
const outlineWidth  = ref(2)
const shadowDepth   = ref(0)
const marginV       = ref(30)
const position      = ref('bottom')
const bold          = ref(true)
const italic        = ref(false)

function resetStyle() {
  primaryColour.value = '#FFFFFF'
  outlineColour.value = '#000000'
  outlineWidth.value  = 2
  shadowDepth.value   = 0
  marginV.value       = 30
  position.value      = 'bottom'
  bold.value          = true
  italic.value        = false
}

// ── Generate SRT ──────────────────────────────────────────────────────────────
const GEN_STEPS = [
  { key: 'normalize',     label: '帧率标准化' },
  { key: 'audio',         label: '提取音频' },
  { key: 'align',         label: '加载模型' },
  { key: 'align_running', label: 'Whisper 对齐' },
  { key: 'split',         label: '切分时间戳' },
  { key: 'write',         label: '写入 SRT' },
]

const generating   = ref(false)
const genLog       = ref([])
const genPct       = ref(-2)   // -2 = hidden, -1 = indeterminate, 0-100 = progress
const activeStep   = ref('')

function stepClass(key) {
  const done = GEN_STEPS.findIndex(s => s.key === key)
  const cur  = GEN_STEPS.findIndex(s => s.key === activeStep.value)
  if (key === activeStep.value) return 'step-active'
  if (cur > done) return 'step-done'
  return 'step-pending'
}

const srtPreview = ref('')
async function loadSrtPreview() {
  // Load first 10 lines of SRT for display — via status we know it exists
  // We can't read files directly, so we fetch the script and format a preview
  srtPreview.value = '（已生成，点击「打开 SRT 目录」查看文件）'
}

function addLog(text, type = 'info') {
  genLog.value.push({ text, type })
  if (genLog.value.length > 30) genLog.value.shift()
}

async function generateSrt() {
  if (generating.value || !scriptLines.value.length) return
  generating.value = true
  genLog.value = []
  genPct.value = 0
  activeStep.value = ''
  hasSrt.value = false
  srtPreview.value = ''

  try {
    const res = await fetch(`${API}/generate-srt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.projectId,
        lines: scriptLines.value,
        fps: fps.value,
        manual_advance: manualAdvance.value,
        model_name: modelName.value,
      }),
    })
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const raw = part.slice(6).trim()
        if (raw === '[DONE]') { generating.value = false; break }
        try {
          const evt = JSON.parse(raw)
          if (evt.step === 'error') {
            addLog('✗ ' + evt.message, 'error')
          } else if (evt.step === 'done') {
            addLog(`✓ ${evt.message}（${evt.count} 条）`, 'ok')
            genPct.value = 100
            activeStep.value = 'done'
            hasSrt.value = true
            srtPreview.value = '（已生成，点击「打开 SRT 目录」查看文件）'
          } else {
            activeStep.value = evt.step
            if (typeof evt.pct === 'number') genPct.value = evt.pct
            addLog(evt.message)
          }
        } catch {}
      }
    }
  } catch (e) {
    addLog('✗ ' + (e.message || '请求失败'), 'error')
  } finally {
    generating.value = false
  }
}

// ── Embed ─────────────────────────────────────────────────────────────────────
const embedding = ref(false)
const embedLog  = ref([])
const embedPct  = ref(0)

async function embedSubtitles() {
  if (embedding.value) return
  embedding.value = true
  embedLog.value  = []
  embedPct.value  = 0

  try {
    const res = await fetch(`${API}/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id:     props.projectId,
        font_name:      fontName.value,
        font_size:      fontSize.value,
        primary_colour: primaryColour.value,
        outline_colour: outlineColour.value,
        outline_width:  outlineWidth.value,
        shadow_depth:   shadowDepth.value,
        margin_v:       marginV.value,
        position:       position.value,
        bold:           bold.value,
        italic:         italic.value,
      }),
    })
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const raw = part.slice(6).trim()
        if (raw === '[DONE]') { embedding.value = false; break }
        try {
          const evt = JSON.parse(raw)
          if (evt.step === 'error') {
            embedLog.value.push({ text: '✗ ' + evt.message, type: 'error' })
          } else if (evt.step === 'done') {
            embedLog.value.push({ text: '✓ ' + evt.message, type: 'ok' })
            embedPct.value = 100
            embeddedPath.value = evt.output_path || ''
            hasEmbedded.value  = true
          } else if (evt.step === 'progress') {
            if (typeof evt.pct === 'number' && evt.pct >= 0) embedPct.value = evt.pct
          } else {
            embedLog.value.push({ text: evt.message, type: 'info' })
          }
        } catch {}
      }
    }
  } catch (e) {
    embedLog.value.push({ text: '✗ ' + (e.message || '请求失败'), type: 'error' })
  } finally {
    embedding.value = false
  }
}

// ── File actions ──────────────────────────────────────────────────────────────
async function openSrtFolder() {
  try {
    const { data } = await axios.get('http://127.0.0.1:18520/api/settings')
    const projectsDir = (data?.projects_dir || '').replace(/[\\/]+$/, '')
    await window.electronAPI?.showItemInFolder(
      `${projectsDir}\\${props.projectId}\\video\\subtitles.srt`
    )
  } catch {}
}

async function openEmbedded() {
  if (embeddedPath.value) {
    await window.electronAPI?.openPath(embeddedPath.value)
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  refreshStatus()
})
</script>

<style scoped>
.subtitle-tab { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.sub-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px 8px; flex-shrink: 0;
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; }
.toolbar-right { display: flex; gap: 8px; }
.toolbar-title { margin: 0; font-size: 15px; font-weight: 600; }
.badge-warn { background: var(--color-warning); color: #000; font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.badge-ok   { background: var(--color-success); color: #fff; font-size: 12px; padding: 2px 8px; border-radius: 10px; }

.sub-body {
  flex: 1; min-height: 0;
  display: flex; gap: 12px; padding: 0 16px 16px; overflow: hidden;
}
.sub-col { display: flex; flex-direction: column; min-height: 0; }
.sub-col-script   { flex: 0 0 420px; }
.sub-col-settings { flex: 1; overflow-y: auto; gap: 10px; display: flex; flex-direction: column; }

.col-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.col-title  { font-size: 13px; font-weight: 600; }
.col-actions { display: flex; gap: 4px; }
.script-hint { font-size: 11px; color: var(--color-text-muted); margin-bottom: 4px; }
.script-textarea { flex: 1; min-height: 0; resize: none; font-family: monospace; font-size: 13px; line-height: 1.6; }
.line-count { font-size: 11px; color: var(--color-text-muted); text-align: right; margin-top: 4px; }

.config-card { padding: 12px; flex-shrink: 0; }
.config-title { font-size: 13px; font-weight: 600; margin-bottom: 10px; }
.cfg-row  { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.cfg-label { font-size: 12px; color: var(--color-text-muted); }
.select-sm { font-size: 12px; }
.input-sm  { font-size: 12px; padding: 4px 8px; }

.action-card { padding: 12px; flex-shrink: 0; }
.btn-block { width: 100%; }
.embed-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.embed-hint  { font-size: 12px; color: var(--color-text-muted); margin-bottom: 8px; }

.gen-log { margin-top: 8px; max-height: 160px; overflow-y: auto; background: var(--color-surface); border-radius: var(--radius); padding: 8px; }
.log-line { font-size: 12px; font-family: monospace; line-height: 1.5; }
.log-line.error { color: var(--color-error); }
.log-line.ok    { color: var(--color-success); }

.srt-label   { font-size: 12px; font-weight: 600; margin: 10px 0 4px; }
.srt-preview { font-size: 11px; font-family: monospace; background: var(--color-surface); border-radius: var(--radius); padding: 8px; max-height: 120px; overflow-y: auto; white-space: pre-wrap; }
.srt-actions { margin-top: 6px; display: flex; gap: 6px; }

/* Progress bars */
.progress-track {
  height: 6px;
  background: var(--color-surface);
  border-radius: 3px;
  overflow: hidden;
  margin-top: 8px;
}
.progress-fill {
  height: 100%;
  background: var(--color-primary, #4f8ef7);
  border-radius: 3px;
  transition: width 0.4s ease;
}
.progress-fill.indeterminate {
  width: 40% !important;
  animation: indeterminate 1.4s ease-in-out infinite;
}
@keyframes indeterminate {
  0%   { transform: translateX(-120%); }
  100% { transform: translateX(350%); }
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.progress-wrap .progress-track { flex: 1; margin-top: 0; }
.pct-label { font-size: 11px; color: var(--color-text-muted); min-width: 32px; text-align: right; }

/* Step chips */
.step-progress { margin-top: 8px; }
.step-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.step-chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  border: 1px solid transparent;
}
.step-chip.step-pending { background: var(--color-surface); color: var(--color-text-muted); }
.step-chip.step-active  { background: var(--color-primary, #4f8ef7); color: #fff; border-color: var(--color-primary, #4f8ef7); }
.step-chip.step-done    { background: var(--color-success, #22c55e); color: #fff; }
</style>
