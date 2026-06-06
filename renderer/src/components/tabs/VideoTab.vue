<template>
  <div class="tab-panel video-tab">

    <!-- ── Toolbar ── -->
    <div class="video-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">视频生成</h3>
        <span class="text-muted" style="font-size:13px" v-if="scenes.length">
          {{ readyCount }} / {{ scenes.length }} 个分镜就绪
        </span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopGeneration">⏹ 停止</button>
        <template v-else>
          <button
            class="btn btn-success btn-sm"
            :disabled="!allVideosReady || merging"
            :title="!allVideosReady ? '所有分镜视频生成完毕后才能合并' : '合并所有分镜视频（可设过渡 + BGM）'"
            @click="openMergeOptions"
          >{{ merging ? '合并中…' : '🎬 合并视频…' }}</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!selectedWorkflow || !readyCount"
            @click="resumeGeneration"
            :title="!readyCount ? '需要首帧图片、末帧图片和合并音频' : '仅生成尚未完成的视频分镜'"
          >⏯ 继续生成</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!scenes.length || generatingAllVideoPrompts"
            title="为所有分镜用 LLM 自动生成视频提示词"
            @click="generateAllPrompts"
          >
            {{ generatingAllVideoPrompts
              ? `提示词 ${videoPromptProgress}/${scenes.length}…`
              : '✦ 全部生成提示词' }}
          </button>
          <button
            v-if="generatingAllVideoPrompts"
            class="btn btn-danger btn-sm"
            @click="_videoPromptAbort?.abort(); generatingAllVideoPrompts = false; generatingVideoPromptId = null"
          >⏹ 中断提示词</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!selectedWorkflow || !readyCount"
            @click="startGeneration"
            :title="!readyCount ? '需要首帧图片、末帧图片和合并音频' : ''"
          >▶ 开始生成</button>
        </template>
      </div>
    </div>

    <!-- D1/D3: 合并设置弹窗 -->
    <Teleport to="body">
      <div v-if="mergeOptionsOpen" class="overlay" @click.self="mergeOptionsOpen = false">
        <div class="dialog card" style="width:520px;max-width:calc(100vw - 40px)">
          <h3 class="dialog-title">🎬 合并设置</h3>

          <div class="form-group">
            <label>🎚 镜间过渡</label>
            <div class="form-row">
              <select v-model="mergeTransition" class="input select" style="flex:1">
                <option value="cut">硬切（cut，无过渡 · 最快，与原版相同）</option>
                <option value="fade">渐黑（fade）</option>
                <option value="fadeblack">黑色淡入（fadeblack）</option>
                <option value="dissolve">交叉溶解（dissolve）</option>
                <option value="wipeleft">擦除-向左（wipeleft）</option>
                <option value="wiperight">擦除-向右（wiperight）</option>
                <option value="slideleft">滑动-向左（slideleft）</option>
                <option value="slideright">滑动-向右（slideright）</option>
                <option value="circleopen">圆形展开（circleopen）</option>
                <option value="circleclose">圆形闭合（circleclose）</option>
              </select>
              <input type="number" min="50" max="2000" step="50"
                     v-model.number="mergeTransitionMs" class="input"
                     :disabled="mergeTransition === 'cut'"
                     style="width:90px" title="过渡时长 (ms)" />
              <span class="text-muted" style="font-size:12px;align-self:center">ms</span>
            </div>
            <p class="form-hint">
              非 cut 时整片需要重新编码，会比硬切慢；推荐 200–500ms。
            </p>
          </div>

          <div class="form-group">
            <label>🎵 背景音乐 (BGM)</label>
            <div class="bgm-row">
              <span v-if="bgmInfo.exists" class="bgm-pill">
                ✓ {{ bgmInfo.filename }} · {{ (bgmInfo.size / 1024).toFixed(0) }} KB
              </span>
              <span v-else class="text-muted" style="font-size:12px">未上传</span>
              <button class="btn btn-secondary btn-xs" :disabled="bgmUploading" @click="pickBgmFile">
                {{ bgmUploading ? '上传中…' : (bgmInfo.exists ? '🔁 替换' : '⬆ 上传 BGM') }}
              </button>
              <button v-if="bgmInfo.exists" class="btn btn-ghost btn-xs" @click="deleteBgm">✕ 删除</button>
            </div>
            <div v-if="bgmInfo.exists" class="form-row" style="margin-top:6px;align-items:center">
              <label style="font-size:12px;min-width:64px">音量 dB</label>
              <input type="range" min="-40" max="0" step="1" v-model.number="mergeBgmVolDb" style="flex:1" />
              <span style="font-size:12px;min-width:42px;text-align:right">{{ mergeBgmVolDb }} dB</span>
            </div>
            <div v-if="bgmInfo.exists" class="form-row" style="margin-top:6px">
              <input type="number" min="0" max="5000" step="100"
                     v-model.number="mergeBgmFadeIn" class="input" style="flex:1"
                     placeholder="淡入 ms" title="BGM 淡入时长" />
              <input type="number" min="0" max="5000" step="100"
                     v-model.number="mergeBgmFadeOut" class="input" style="flex:1"
                     placeholder="淡出 ms" title="BGM 淡出时长" />
            </div>
            <p class="form-hint" v-if="bgmInfo.exists">
              BGM 会循环播放到视频结束。音量 -20 dB 通常作为人声背景音；-10 dB 接近人声前景。
            </p>
          </div>

          <div class="dialog-actions">
            <button class="btn btn-ghost" @click="mergeOptionsOpen = false">取消</button>
            <button class="btn btn-primary" :disabled="merging" @click="confirmMerge">
              {{ merging ? '合并中…' : '🎬 开始合并' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- C1: 工作流节点映射编辑器 -->
    <Teleport to="body">
      <div v-if="workflowMetaOpen" class="overlay" @click.self="workflowMetaOpen = false">
        <div class="dialog card" style="width:560px;max-width:calc(100vw - 40px)">
          <h3 class="dialog-title">⚙ 节点映射 · {{ selectedWorkflow }}</h3>
          <p class="text-muted" style="font-size:12px;margin-bottom:10px">
            填写该工作流里下列字段对应的 ComfyUI 节点 ID（LiteGraph 整数）。
            没改过工作流就保持默认即可——这些值就是 <code>flfa2i-lumicreate</code> 的原生节点 ID。
            遇到自定义工作流注入失败时，在 ComfyUI 右上角 Properties 里看节点 ID 填进来。
          </p>
          <div class="meta-grid">
            <template v-for="f in META_FIELDS" :key="f.key">
              <div class="meta-label" :title="f.desc">{{ f.label }}</div>
              <input type="number" class="input meta-input"
                     v-model.number="workflowMetaForm.node_map[f.key].node_id"
                     :placeholder="`默认 ${f.defaultId}`" />
              <input type="number" class="input meta-input meta-widget"
                     v-model.number="workflowMetaForm.node_map[f.key].widget"
                     placeholder="widget" title="widgets_values 下标，默认 0" />
            </template>
          </div>
          <div class="form-group" style="margin-top:8px">
            <label>备注</label>
            <textarea v-model="workflowMetaForm.notes" class="input textarea" rows="2"
                      placeholder="（可选）记录这个工作流的版本/来源等"></textarea>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-ghost" @click="workflowMetaOpen = false">取消</button>
            <button class="btn btn-warning btn-sm" @click="resetWorkflowMeta">↺ 恢复默认</button>
            <button class="btn btn-primary" :disabled="workflowMetaSaving" @click="saveWorkflowMeta">
              {{ workflowMetaSaving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- A1: 上次失败镜次提示 + 一键重试 -->
    <div v-if="lastErrorCount && !running" class="last-errors-banner">
      <span>⚠ 上次失败：{{ lastErrorCount }} 个视频分镜</span>
      <button class="btn btn-warning btn-xs" :disabled="!selectedWorkflow" @click="retryFailedBatch">↻ 只重试失败镜</button>
      <button class="btn btn-ghost btn-xs" @click="dismissLastErrors">✕ 忽略</button>
      <details class="last-errors-detail">
        <summary class="text-muted" style="font-size:11px;cursor:pointer">查看详情</summary>
        <ul>
          <li v-for="(msg, k) in lastErrors" :key="k"><code>{{ k }}</code>: {{ msg }}</li>
        </ul>
      </details>
    </div>

    <!-- ── Config ── -->
    <div class="video-config card" v-if="!running">
      <div class="config-row">
        <div class="config-group">
          <label class="cfg-label">工作流</label>
          <select class="input select-compact" v-model="selectedWorkflow">
            <option value="">— 选择工作流 —</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
          </select>
          <button class="btn btn-ghost btn-xs"
                  :disabled="!selectedWorkflow"
                  title="编辑该工作流的节点 ID 映射；自定义工作流改了节点后必须在此更新，否则首末帧/音频/分辨率注入会落到错节点"
                  @click="openWorkflowMeta">⚙ 节点映射</button>
        </div>
        <div class="config-group">
          <label class="cfg-label">分辨率（宽×高）</label>
          <select class="input select-compact" v-model="resolution">
            <option value="720x1280">720×1280（竖屏 HD）</option>
            <option value="1280x720">1280×720（横屏 HD）</option>
            <option value="576x1024">576×1024（竖屏 中）</option>
            <option value="1024x576">1024×576（横屏 中）</option>
            <option value="544x960">544×960（竖屏 小）</option>
            <option value="960x544">960×544（横屏 小）</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">帧率</label>
          <select class="input select-compact" v-model.number="fps" style="width:90px">
            <option :value="24">24fps</option>
            <option :value="25">25fps</option>
            <option :value="30">30fps</option>
          </select>
        </div>
      </div>
      <p class="config-hint">
        ⚠ 视频分辨率限制在 1280px 以内（本地算力有限），每边自动对齐至 32px 倍数
      </p>
    </div>

    <!-- ── Loading / Empty ── -->
    <div v-if="loadingScenes" class="empty-state"><div class="spinner" /><p class="text-muted">加载中…</p></div>
    <div v-else-if="!scenes.length" class="empty-state">
      <div class="empty-icon">🎞</div><p>请先完成「分镜设计」</p>
    </div>

    <!-- ── Overall progress ── -->
    <div v-if="(running || genFinished) && scenes.length" class="progress-wrap card">
      <div class="progress-label">
        <span>整体进度</span><span>{{ completedCount }} / {{ scenes.length }}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" :style="{ width: overallPct + '%' }" /></div>
    </div>

    <!-- ── Scene list ── -->
    <div class="scene-video-list" v-if="scenes.length">
      <div v-for="scene in scenesWithData" :key="scene.id" class="scene-video-card card">

        <!-- Header -->
        <div class="svcard-header">
          <span class="scene-num">{{ String(scene.index).padStart(2,'0') }}</span>
          <div class="svcard-desc">{{ sceneFullText(scene) }}</div>
          <span class="svcard-status" :class="sceneStatusClass(scene.id)">
            {{ sceneStatusLabel(scene.id) }}
          </span>
          <!-- Per-scene regen button -->
          <button
            class="btn btn-ghost btn-xs"
            :disabled="running || !sceneReady(scene)"
            @click="generateOne(scene)"
            title="单独生成此分镜"
          >↺</button>
        </div>

        <!-- Readiness indicators -->
        <div class="asset-checks">
          <span class="asset-tag" :class="scene.hasStart ? 'ok' : 'miss'">
            {{ scene.hasStart ? '✓' : '✗' }} 首帧
          </span>
          <span class="asset-tag" :class="scene.hasEnd ? 'ok' : 'miss'">
            {{ scene.hasEnd ? '✓' : '✗' }} 末帧
          </span>
          <span class="asset-tag" :class="scene.hasAudio ? 'ok' : 'miss'">
            {{ scene.hasAudio ? '✓' : '✗' }} 合并音频
            <template v-if="scene.hasAudio"> ({{ formatMs(scene.audioDurationMs) }})</template>
          </span>
        </div>

        <!-- Prompt section -->
        <div class="prompt-section">
          <div class="prompt-header">
            <span class="prompt-label">
              视频提示词
              <span v-if="scenePrompts[scene.id]" class="prompt-set-badge">已设置</span>
            </span>
            <div class="prompt-actions">
              <button
                class="btn btn-ghost btn-xs"
                @click="editPrompt(scene)"
                title="手动编辑视频提示词"
              >✎ 编辑</button>
              <button class="btn btn-ghost btn-xs"
                :disabled="!!generatingVideoPromptId"
                @click="generatePrompt(scene)"
                :title="generatingVideoPromptId === scene.id ? 'LLM 生成中…' : '用 LLM 生成视频提示词'"
              >
                {{ generatingVideoPromptId === scene.id ? '⏳ 生成中…' : '✦ 生成' }}
              </button>
              <button
                v-if="scenePrompts[scene.id]"
                class="btn btn-ghost btn-xs"
                @click="togglePrompt(scene.id)"
              >{{ promptVisible[scene.id] ? '收起' : '展开' }}</button>
            </div>
          </div>
          <div v-if="promptVisible[scene.id]" class="prompt-editor-wrap">
            <textarea
              class="prompt-textarea"
              :value="scenePrompts[scene.id]"
              @input="onPromptInput(scene.id, $event.target.value)"
              placeholder="输入视频生成提示词，或点击「生成」自动填写…"
              rows="3"
            />
          </div>
        </div>

        <!-- Per-scene progress bar -->
        <div class="scene-mini-bar-wrap" v-if="sceneState[scene.id] === 'active'">
          <div class="scene-mini-bar">
            <div class="scene-mini-fill" :style="{ width: sceneProgressPct(scene.id) + '%' }" />
          </div>
          <span class="text-muted" style="font-size:11px">{{ sceneProgressPct(scene.id) }}%</span>
        </div>

        <!-- Video result -->
        <div v-if="sceneVideos[scene.id]" class="video-result">
          <video
            :src="'data:video/mp4;base64,' + sceneVideos[scene.id]"
            controls
            class="video-player"
          />
        </div>

      </div>
    </div>

    <!-- ── Error banner ── -->
    <div v-if="genError" class="error-banner">
      ⚠ {{ genError }}
      <button class="btn btn-ghost btn-xs" @click="genError = ''">关闭</button>
    </div>

    <!-- ── Merge result dialog ── -->
    <div v-if="mergeResult" class="merge-dialog-overlay" @click.self="mergeResult = null">
      <div class="merge-dialog card">
        <h4 class="merge-dialog-title">🎬 合并完成</h4>
        <p class="merge-dialog-path">{{ mergeResult.output_path }}</p>
        <div class="merge-dialog-actions">
          <button class="btn btn-primary" @click="openMergedVideo">▶ 打开视频</button>
          <button class="btn btn-secondary" @click="showMergedInFolder">📂 打开所在目录</button>
          <button class="btn btn-ghost" @click="mergeResult = null">关闭</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import { useTabsStore } from '../../stores/tabs'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

// ── state ──────────────────────────────────────────────────────────────────────
const scenes          = ref([])

// C1: 工作流节点映射编辑器
const META_FIELDS = [
  { key: 'first_frame_image', label: '首帧图片节点',   desc: 'LoadImage FIRST FRAME',  defaultId: 45  },
  { key: 'last_frame_image',  label: '末帧图片节点',   desc: 'LoadImage LAST FRAME',   defaultId: 47  },
  { key: 'audio',             label: '音频节点',       desc: 'LoadAudio',              defaultId: 232 },
  { key: 'width',             label: '宽度节点',       desc: 'INTConstant WIDTH',      defaultId: 166 },
  { key: 'height',            label: '高度节点',       desc: 'INTConstant HEIGHT',     defaultId: 167 },
  { key: 'duration_secs',     label: '时长节点（秒）', desc: 'INTConstant LENGTH',     defaultId: 169 },
  { key: 'fps',               label: '帧率节点',       desc: 'PrimitiveFloat FPS',     defaultId: 164 },
  { key: 'positive_prompt',   label: '正向提示词节点', desc: 'CLIPTextEncode pos',     defaultId: 16  },
]
const workflowMetaOpen   = ref(false)
const workflowMetaForm   = ref({ node_map: {}, notes: '', type: 'video', version: 1 })
const workflowMetaSaving = ref(false)

function _emptyMetaForm() {
  const nm = {}
  for (const f of META_FIELDS) nm[f.key] = { node_id: f.defaultId, widget: 0 }
  return { node_map: nm, notes: '', type: 'video', version: 1 }
}

async function openWorkflowMeta() {
  if (!selectedWorkflow.value) return
  workflowMetaForm.value = _emptyMetaForm()
  try {
    const r = await fetch(`${API}/image-engine/workflow-meta/${encodeURIComponent(selectedWorkflow.value)}?type=video`)
    if (r.ok) {
      const d = await r.json()
      const nm = workflowMetaForm.value.node_map
      for (const f of META_FIELDS) {
        const v = d.node_map?.[f.key]
        if (v && typeof v === 'object') {
          nm[f.key] = { node_id: v.node_id ?? f.defaultId, widget: v.widget ?? 0 }
        }
      }
      workflowMetaForm.value.notes = d.notes || ''
    }
  } catch {}
  workflowMetaOpen.value = true
}

function resetWorkflowMeta() {
  if (!confirm('恢复为内置默认节点映射？已填的值会被覆盖。')) return
  workflowMetaForm.value = _emptyMetaForm()
}

async function saveWorkflowMeta() {
  workflowMetaSaving.value = true
  try {
    const r = await fetch(`${API}/image-engine/workflow-meta/${encodeURIComponent(selectedWorkflow.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(workflowMetaForm.value),
    })
    if (!r.ok) throw new Error(await r.text())
    workflowMetaOpen.value = false
  } catch (e) {
    alert('保存节点映射失败: ' + e.message)
  } finally {
    workflowMetaSaving.value = false
  }
}

// A1: 上次批量失败的视频镜次
const lastErrors      = ref({})
const lastErrorCount  = computed(() => Object.keys(lastErrors.value || {}).length)

async function reloadLastErrors() {
  if (!props.projectId) return
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/last-run-errors`)
    if (!r.ok) return
    const d = await r.json()
    lastErrors.value = (d.stage === 'video' ? d.errors : null) || {}
  } catch { lastErrors.value = {} }
}

async function dismissLastErrors() {
  lastErrors.value = {}
  try { await fetch(`${API}/projects/${props.projectId}/last-run-errors`, { method: 'DELETE' }) } catch {}
}

async function retryFailedBatch() {
  if (!Object.keys(lastErrors.value).length) return
  if (!selectedWorkflow.value) return
  const failedSceneIds = new Set(Object.keys(lastErrors.value))
  // 失败镜过滤后调用 _runGeneration（已有函数）批量重做
  const failedScenes = scenes.value.filter(
    s => failedSceneIds.has(String(s.id)) && sceneReady(s)
  )
  if (!failedScenes.length) return
  running.value = true; genFinished.value = false; stopFlag.value = false; genError.value = ''
  try {
    await _runGeneration(failedScenes)
  } finally {
    running.value = false
    genFinished.value = true
    await reloadLastErrors()
  }
}
const imagesData      = ref({})   // slot key → base64 PNG
const imagesSelected  = ref({})   // "{scene_id}:start"|":end" → slot_index
const audioData       = ref({})   // "__stitched__{sceneId}" → {data, duration_ms}
const loadingScenes   = ref(false)
const workflows       = ref([])
const selectedWorkflow = ref('')
const resolution      = ref('720x1280')
const fps             = ref(25)
const running         = ref(false)
const genFinished     = ref(false)
const stopFlag        = ref(false)
const genError        = ref('')
const sceneState      = ref({})   // id → pending|active|done|error
const sceneProgress   = ref({})   // id → {value, max}
const sceneVideos     = ref({})   // id → base64 mp4
const mergeResult     = ref(null) // { output_path, output_dir } once merged
const merging         = ref(false)
const scenePrompts    = ref({})   // scene_id → prompt string
const promptVisible   = ref({})   // scene_id → bool (expanded)
let _promptSaveTimer  = null
// manuscript + characters for LLM video prompt
const manuscript             = ref('')
const allCharacters          = ref([])   // [{name, role, appearance, traits}]
// per-scene LLM generating state
const generatingVideoPromptId   = ref(null)   // scene.id being generated
const generatingAllVideoPrompts = ref(false)
const videoPromptProgress       = ref(0)

// ── derived ────────────────────────────────────────────────────────────────────
const scenesWithData = computed(() =>
  scenes.value.map(s => {
    const startKey = `${s.id}:start`
    const endKey   = `${s.id}:end`
    const startSlot = imagesSelected.value[startKey] ?? 0
    const endSlot   = imagesSelected.value[endKey]   ?? 0
    const startImg  = imagesData.value[`${startKey}:${startSlot}`] || null
    const endImg    = imagesData.value[`${endKey}:${endSlot}`]     || null
    const stitchKey = `__stitched__${s.id}`
    const stitched  = audioData.value[stitchKey] || null
    return {
      ...s,
      hasStart:      !!startImg,
      hasEnd:        !!endImg,
      hasAudio:      !!stitched,
      startImageB64: startImg || '',
      endImageB64:   endImg   || '',
      audioB64:      stitched?.data || '',
      audioDurationMs: stitched?.duration_ms || 0,
    }
  })
)

const readyCount = computed(() =>
  scenesWithData.value.filter(s => s.hasStart && s.hasEnd && s.hasAudio).length
)

const completedCount = computed(() =>
  Object.values(sceneState.value).filter(v => v === 'done' || v === 'error').length
)

const overallPct = computed(() =>
  scenes.value.length ? Math.round(completedCount.value / scenes.value.length * 100) : 0
)

const allVideosReady = computed(() =>
  scenes.value.length > 0 &&
  scenes.value.every(s => !!sceneVideos.value[s.id])
)

function sceneReady(s) { return s.hasStart && s.hasEnd && s.hasAudio }

function sceneFullText(scene) {
  if (!scene) return '（无描述）'
  const desc = scene.description || ''
  const firstDialogue = (scene.dialogues || [])[0]?.text || ''
  if (firstDialogue && (desc.endsWith('…') || desc.length < firstDialogue.length)) {
    return firstDialogue
  }
  return desc || '（无描述）'
}
function sceneStatusClass(id) { return sceneState.value[id] || 'pending' }
function sceneStatusLabel(id) {
  return ({ pending: '', active: '生成中…', done: '✓ 完成', error: '✗ 错误' })[sceneState.value[id]] || ''
}
function sceneProgressPct(id) {
  const p = sceneProgress.value[id]
  return p?.max ? Math.round(p.value / p.max * 100) : 0
}
function formatMs(ms) { return ms ? `${(ms/1000).toFixed(1)}s` : '' }

// ── load ───────────────────────────────────────────────────────────────────────
async function loadData() {
  if (!props.projectId) return
  loadingScenes.value = true
  try {
    const [scenesRes, imgRes, audRes, settingsRes, wfRes, vidRes, promptsRes] = await Promise.all([
      axios.get(`${API}/projects/${props.projectId}/scenes`),
      axios.get(`${API}/projects/${props.projectId}/images`).catch(() => ({ data: { slots: [], selected: {} } })),
      axios.get(`${API}/projects/${props.projectId}/audio`).catch(() => ({ data: {} })),
      axios.get(`${API}/settings`).catch(() => ({ data: {} })),
      axios.get(`${API}/video-engine/workflows`).catch(() => ({ data: [] })),
      axios.get(`${API}/projects/${props.projectId}/videos`).catch(() => ({ data: {} })),
      axios.get(`${API}/projects/${props.projectId}/video-prompts`).catch(() => ({ data: {} })),
    ])

    scenes.value = scenesRes.data?.scenes || []

    // Build images lookup: "{sceneId}:start:{slotIndex}" → URL or data URL
    const imgLookup = {}
    for (const slot of (imgRes.data?.slots || [])) {
      const key = `${slot.scene_id}:${slot.frame_type}:${slot.slot_index}`
      if (slot.url)  imgLookup[key] = 'http://localhost:18520' + slot.url
      else if (slot.data) imgLookup[key] = 'data:image/png;base64,' + slot.data
    }
    imagesData.value    = imgLookup
    imagesSelected.value = imgRes.data?.selected || {}

    // Audio stitched data
    // Also map reading-mode MS TTS clips (__ms_reading__{id}) into the same
    // __stitched__{id} key so scenesWithData picks them up transparently.
    const aud = audRes.data || {}
    const stitched = {}
    for (const [k, v] of Object.entries(aud)) {
      if (k.startsWith('__stitched__')) {
        stitched[k] = v
      } else if (k.startsWith('__ms_reading__')) {
        const sceneId = k.slice('__ms_reading__'.length)
        // Only apply if no stitched entry already exists for this scene
        if (!stitched[`__stitched__${sceneId}`]) {
          stitched[`__stitched__${sceneId}`] = v
        }
      }
    }
    audioData.value = stitched

    // Settings
    const vCfg = settingsRes.data?.video_engine || {}
    resolution.value = vCfg.resolution || '720x1280'
    fps.value        = vCfg.fps ?? 25
    if (vCfg.default_workflow) selectedWorkflow.value = vCfg.default_workflow
    workflows.value  = wfRes.data || []

    // Saved videos
    sceneVideos.value = vidRes.data || {}

    // Saved video prompts
    scenePrompts.value = promptsRes.data || {}

    // Load manuscript + characters for LLM prompt generation
    try {
      const msRes = await axios.get(`${API}/projects/${props.projectId}/manuscript`)
      manuscript.value = msRes.data?.content || ''
    } catch {}
    try {
      const chRes = await axios.get(`${API}/projects/${props.projectId}/characters`)
      allCharacters.value = chRes.data?.characters || []
    } catch {}

  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
  await reloadLastErrors()   // A1
  await reloadBgm()           // D1
}

onMounted(loadData)
onUnmounted(() => { clearTimeout(_promptSaveTimer); _savePrompts() })

// When this project's tab becomes active again (after being in the background),
// refresh the saved video list so any videos that finished while hidden show up.
const tabsStore = useTabsStore()
watch(() => tabsStore.activeId, async (newId) => {
  if (newId !== props.projectId) return
  if (running.value || !scenes.value.length) return
  try {
    const { data } = await axios.get(`${API}/projects/${props.projectId}/videos`)
    sceneVideos.value = data || {}
  } catch {}
})

// ── generation ─────────────────────────────────────────────────────────────────
let currentReader = null

async function startGeneration() {
  if (!selectedWorkflow.value) return

  const existingCount = scenes.value.filter(s => !!sceneVideos.value[s.id]).length
  if (existingCount > 0) {
    const ok = confirm(
      `检测到已有 ${existingCount} 个分镜视频。\n` +
      `点击“确定”将覆盖重生成；点击“取消”后请使用“继续生成”仅补生成未完成分镜。`
    )
    if (!ok) return
  }

  running.value     = true
  genFinished.value = false
  stopFlag.value    = false
  genError.value    = ''

  const states = {}
  for (const s of scenes.value) states[s.id] = 'pending'
  sceneState.value    = states
  sceneProgress.value = {}

  const readyScenes = scenesWithData.value.filter(sceneReady)
  await _runGeneration(readyScenes)
}

async function resumeGeneration() {
  if (!selectedWorkflow.value) return
  running.value     = true
  genFinished.value = false
  stopFlag.value    = false
  genError.value    = ''

  const states = { ...sceneState.value }
  for (const s of scenes.value) {
    if (sceneVideos.value[s.id]) {
      states[s.id] = 'done'
    } else if (!states[s.id]) {
      states[s.id] = 'pending'
    }
  }
  sceneState.value = states

  const readyScenes = scenesWithData.value.filter(s => sceneReady(s) && !sceneVideos.value[s.id])
  if (!readyScenes.length) {
    running.value = false
    genFinished.value = true
    return
  }
  await _runGeneration(readyScenes)
}

async function generateOne(scene) {
  if (running.value || !sceneReady(scene)) return
  running.value = true
  stopFlag.value = false
  sceneState.value = { ...sceneState.value, [scene.id]: 'pending' }
  await _runGeneration([scene])
}

function _buildPromptFallback(scene) {
  // Mechanical fallback used only when LLM is unavailable
  const base = scene.start_frame_prompt || scene.description || ''
  const dialogues = (scene.dialogues || []).filter(d => d.character && d.character !== '旁白' && d.text)
  if (!dialogues.length) return base
  const dlgParts = dialogues.map(d => `${d.character} says: "${d.text}"`)
  return base ? `${base}. ${dlgParts.join(', ')}.` : dlgParts.join(', ') + '.'
}

// Call LLM to generate a video prompt for one scene (streaming SSE), returns final text
async function _fetchVideoPromptLLM(scene, abortSignal) {
  const sceneChars = (scene._scene_characters || [])
  const chars = sceneChars.length
    ? allCharacters.value.filter(c => sceneChars.includes(c.name))
    : allCharacters.value

  const res = await fetch(`${API}/text-engine/generate-video-prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: abortSignal,
    body: JSON.stringify({
      description:        scene.description,
      dialogues:          scene.dialogues || [],
      characters:         chars,
      start_frame_prompt: scene.start_frame_prompt || '',
      end_frame_prompt:   scene.end_frame_prompt   || '',
      manuscript:         manuscript.value,
      scene_index:        scene.index,
      total_scenes:       scenes.value.length,
    }),
  })
  if (!res.ok) throw new Error(await res.text())

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = ''

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
      try {
        const obj = JSON.parse(raw)
        if (obj.error) throw new Error(obj.error)
        if (obj.text) result += obj.text
      } catch (e) {
        if (raw.includes('"error"')) throw e
      }
    }
  }
  return result.trim()
}

async function generatePrompt(scene) {
  if (generatingVideoPromptId.value) return
  generatingVideoPromptId.value = scene.id
  try {
    const text = await _fetchVideoPromptLLM(scene, null)
    scenePrompts.value  = { ...scenePrompts.value,  [scene.id]: text || _buildPromptFallback(scene) }
    promptVisible.value = { ...promptVisible.value, [scene.id]: true }
    _scheduleSavePrompts()
  } catch (e) {
    if (e.name !== 'AbortError') {
      // Fallback to mechanical prompt on error
      scenePrompts.value  = { ...scenePrompts.value,  [scene.id]: _buildPromptFallback(scene) }
      promptVisible.value = { ...promptVisible.value, [scene.id]: true }
      _scheduleSavePrompts()
    }
  } finally {
    generatingVideoPromptId.value = null
  }
}

function editPrompt(scene) {
  // If no prompt exists yet, prefill with a mechanical draft as editable baseline.
  if (!scenePrompts.value[scene.id]) {
    const draft = _buildPromptFallback(scene)
    scenePrompts.value = { ...scenePrompts.value, [scene.id]: draft }
    _scheduleSavePrompts()
  }
  promptVisible.value = { ...promptVisible.value, [scene.id]: true }
}

let _videoPromptAbort = null

const _PROMPT_PARALLEL = 3   // concurrent LLM prompt requests

async function generateAllPrompts() {
  if (generatingAllVideoPrompts.value) return
  generatingAllVideoPrompts.value = true
  videoPromptProgress.value = 0
  _videoPromptAbort = new AbortController()

  const allScenes = scenesWithData.value
  for (let i = 0; i < allScenes.length; i += _PROMPT_PARALLEL) {
    if (_videoPromptAbort?.signal.aborted) break
    const batch = allScenes.slice(i, i + _PROMPT_PARALLEL)
    await Promise.allSettled(batch.map(async s => {
      if (_videoPromptAbort?.signal.aborted) return
      try {
        const text = await _fetchVideoPromptLLM(s, _videoPromptAbort.signal)
        scenePrompts.value  = { ...scenePrompts.value,  [s.id]: text || _buildPromptFallback(s) }
        promptVisible.value = { ...promptVisible.value, [s.id]: true }
      } catch (e) {
        if (e.name === 'AbortError') return
        scenePrompts.value  = { ...scenePrompts.value,  [s.id]: _buildPromptFallback(s) }
        promptVisible.value = { ...promptVisible.value, [s.id]: true }
      } finally {
        videoPromptProgress.value++
        _scheduleSavePrompts()
      }
    }))
  }

  generatingVideoPromptId.value   = null
  generatingAllVideoPrompts.value = false
  _videoPromptAbort = null
}

function togglePrompt(sceneId) {
  promptVisible.value = { ...promptVisible.value, [sceneId]: !promptVisible.value[sceneId] }
}

function onPromptInput(sceneId, value) {
  scenePrompts.value = { ...scenePrompts.value, [sceneId]: value }
  _scheduleSavePrompts()
}

function _scheduleSavePrompts() {
  clearTimeout(_promptSaveTimer)
  _promptSaveTimer = setTimeout(_savePrompts, 800)
}

async function _savePrompts() {
  if (!props.projectId) return
  try {
    await axios.put(`${API}/projects/${props.projectId}/video-prompts`, scenePrompts.value)
  } catch (e) {
    console.warn('提示词保存失败:', e)
  }
}

// Resolve an image src (URL string or data-URL) to a raw base64 string.
// Uses FileReader for efficient binary→base64 conversion without string size limits.
function _srcToB64(src) {
  if (!src) return Promise.resolve('')
  if (src.startsWith('data:')) return Promise.resolve(src.replace(/^data:image\/\w+;base64,/, ''))
  return fetch(src)
    .then(r => r.ok ? r.blob() : Promise.reject(new Error('fetch ' + r.status)))
    .then(blob => new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload  = () => resolve(reader.result.replace(/^data:[^;]+;base64,/, ''))
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(blob)
    }))
    .catch(() => '')
}

// Send one scene at a time to avoid "Invalid string length" from huge JSON payloads.
async function _runGeneration(sceneList) {
  try {
    for (const s of sceneList) {
      if (stopFlag.value) break

      // Resolve images for this single scene only
      const [startB64, endB64] = await Promise.all([
        _srcToB64(s.startImageB64),
        _srcToB64(s.endImageB64),
      ])

      const payload = {
        workflow_name: selectedWorkflow.value,
        resolution:    resolution.value,
        fps:           fps.value,
        project_id:    props.projectId,    // A1
        scenes: [{
          scene_id:        String(s.id),
          scene_index:     s.index,
          start_image_b64: startB64,
          end_image_b64:   endB64,
          audio_b64:       s.audioB64,
          duration_ms:     s.audioDurationMs || 4000,
          positive_prompt: scenePrompts.value[s.id] ?? _buildPromptFallback(s),
        }],
      }

      let response
      try {
        response = await fetch(`${API}/video-engine/generate-stream`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(payload),
        })
      } catch (fetchErr) {
        handleEvent({ event: 'scene_error', scene_id: String(s.id), message: fetchErr.message })
        continue
      }

      if (!response.ok) {
        let detail = 'HTTP ' + response.status
        try { const j = await response.json(); detail = j.detail || detail } catch {}
        handleEvent({ event: 'scene_error', scene_id: String(s.id), message: detail })
        continue
      }

      currentReader = response.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        if (stopFlag.value) { currentReader.cancel(); break }
        const { done, value } = await currentReader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n'); buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') break
          try { handleEvent(JSON.parse(raw)) } catch {}
        }
      }
      currentReader = null
    }
    if (!stopFlag.value) genFinished.value = true
  } catch (e) {
    if (!stopFlag.value) genError.value = `生成失败: ${e.message}`
  } finally {
    running.value = false
    currentReader = null
    emit('dirty')
    await reloadLastErrors()   // A1: 刷新失败横幅
  }
}

function handleEvent(evt) {
  const { event, scene_id } = evt
  if (event === 'scene_start') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'active' }
  } else if (event === 'progress') {
    sceneProgress.value = { ...sceneProgress.value, [scene_id]: { value: evt.value, max: evt.max } }
  } else if (event === 'scene_done') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'done' }
    if (evt.video) {
      sceneVideos.value = { ...sceneVideos.value, [scene_id]: evt.video }
      // A3: 单镜增量保存（避免一次 PUT 30+ 个 mp4 base64）
      _saveOneVideo(scene_id, evt.video)
    }
  } else if (event === 'scene_retrying') {
    // VRAM offload detected — backend is freeing memory and retrying; keep scene active
    sceneProgress.value = { ...sceneProgress.value, [scene_id]: { value: 0, max: 100, retrying: true } }
    console.info(`分镜 ${scene_id}: ${evt.message}`)
  } else if (event === 'scene_error') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'error' }
    genError.value = `分镜 ${scene_id} 失败: ${evt.message}`
  } else if (event === 'batch_done') {
    genFinished.value = true
  }
}

function stopGeneration() {
  stopFlag.value = true
  currentReader?.cancel()
  running.value = false
}

async function _saveVideos() {
  if (!props.projectId) return
  try {
    const slots = Object.entries(sceneVideos.value).map(([scene_id, data]) => ({ scene_id, data }))
    await axios.put(`${API}/projects/${props.projectId}/videos`, slots)
  } catch (e) {
    // Non-critical — just log, don't surface to user
    console.warn('视频保存失败:', e)
  }
}

// A3: 单镜增量保存（每镜完成立刻落盘，不再每次重新 PUT 全量）
async function _saveOneVideo(scene_id, b64) {
  if (!props.projectId || !b64) return
  try {
    await axios.put(`${API}/projects/${props.projectId}/videos/slot`, { scene_id: String(scene_id), data: b64 })
  } catch (e) {
    console.warn('单镜视频保存失败:', e)
  }
}

async function mergeVideos() {
  if (!allVideosReady.value || merging.value) return
  merging.value = true
  genError.value = ''
  try {
    const scene_order = scenes.value.map(s => String(s.id))
    const { data } = await axios.post(`${API}/video-engine/merge-project-video`, {
      project_id: props.projectId,
      scene_order,
      // D3: 镜间过渡
      transition: mergeTransition.value,
      transition_duration_ms: mergeTransitionMs.value,
      // D1: BGM 混音；-100 表示不启用 BGM
      bgm_volume_db:   bgmInfo.value.exists ? mergeBgmVolDb.value : -100,
      bgm_fade_in_ms:  mergeBgmFadeIn.value,
      bgm_fade_out_ms: mergeBgmFadeOut.value,
    })
    mergeResult.value = data
  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '合并失败'
  } finally {
    merging.value = false
  }
}

// ── D1/D3: 合并设置 ──────────────────────────────────────────────────────
const mergeOptionsOpen = ref(false)
function openMergeOptions() {
  if (!allVideosReady.value) return
  reloadBgm()
  mergeOptionsOpen.value = true
}
async function confirmMerge() {
  mergeOptionsOpen.value = false
  await mergeVideos()
}

// ── D1: BGM 上传/查询/删除 ─────────────────────────────────────────────────
const bgmInfo        = ref({ exists: false, filename: '', size: 0 })
const bgmUploading   = ref(false)
const mergeBgmVolDb  = ref(-18)
const mergeBgmFadeIn = ref(1000)
const mergeBgmFadeOut = ref(1500)
const mergeTransition   = ref('cut')
const mergeTransitionMs = ref(300)

async function reloadBgm() {
  if (!props.projectId) return
  try {
    const r = await fetch(`${API}/video-engine/bgm/${props.projectId}`)
    if (r.ok) bgmInfo.value = await r.json()
  } catch {}
}

function pickBgmFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.mp3,.m4a,.wav,.aac,.ogg,.flac,audio/*'
  input.onchange = async () => {
    const f = input.files?.[0]
    if (!f) return
    bgmUploading.value = true
    try {
      const arrayBuf = await f.arrayBuffer()
      // base64 编码大文件分块
      const u8 = new Uint8Array(arrayBuf)
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < u8.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK))
      }
      const b64 = btoa(bin)
      const r = await fetch(`${API}/video-engine/bgm/${props.projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: f.name, data: b64 }),
      })
      if (!r.ok) throw new Error(await r.text())
      await reloadBgm()
    } catch (e) {
      alert('BGM 上传失败: ' + e.message)
    } finally {
      bgmUploading.value = false
    }
  }
  input.click()
}

async function deleteBgm() {
  if (!confirm('删除当前 BGM？')) return
  try {
    await fetch(`${API}/video-engine/bgm/${props.projectId}`, { method: 'DELETE' })
    await reloadBgm()
  } catch (e) { alert('删除失败: ' + e.message) }
}

async function openMergedVideo() {
  if (!mergeResult.value) return
  await window.electronAPI?.openPath(mergeResult.value.output_path)
  mergeResult.value = null
}

async function showMergedInFolder() {
  if (!mergeResult.value) return
  await window.electronAPI?.showItemInFolder(mergeResult.value.output_path)
  mergeResult.value = null
}
</script>

<style scoped>
.video-tab { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.last-errors-banner {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:6px 16px; background:rgba(220,60,60,.08);
  border-bottom:1px solid rgba(220,60,60,.4); font-size:12px; flex-shrink:0;
}
.last-errors-banner .last-errors-detail { width:100%; }
.last-errors-banner ul { margin:4px 0 0 18px; padding:0; font-size:11px; line-height:1.5; }
.last-errors-banner code { background:rgba(255,255,255,.08); padding:1px 4px; border-radius:3px; }
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 110px 80px;
  gap: 6px 10px; align-items: center; font-size: 13px;
}
.meta-input { padding: 4px 6px; font-size: 12px; }
.meta-widget { width: 80px; }
.meta-label  { color: var(--color-text); }
.bgm-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.bgm-pill { background:rgba(60,180,90,.15); border:1px solid rgba(60,180,90,.5); padding:3px 8px; border-radius:4px; font-size:12px; }
.video-toolbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px 8px; flex-shrink:0;
}
.toolbar-left  { display:flex; align-items:center; gap:12px; }
.toolbar-right { display:flex; align-items:center; gap:8px; }
.toolbar-title { margin:0; font-size:15px; font-weight:600; }

.video-config  { flex-shrink:0; margin:0 16px 8px; padding:12px; }
.config-row    { display:flex; flex-wrap:wrap; gap:12px; }
.config-group  { display:flex; align-items:center; gap:6px; }
.cfg-label     { font-size:12px; color:var(--text-muted); white-space:nowrap; }
.select-compact { font-size:12px; }
.config-hint   { margin:8px 0 0; font-size:11px; color:var(--text-muted); }

.progress-wrap { flex-shrink:0; margin:0 16px 8px; padding:10px 12px; }
.progress-label { display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px; }
.progress-track { height:6px; border-radius:4px; background:var(--bg-tertiary); overflow:hidden; }
.progress-fill  { height:100%; background:var(--accent); transition:width .3s; }

.scene-video-list {
  flex:1; overflow-y:auto; padding:0 16px 16px; display:flex; flex-direction:column; gap:10px;
}
.scene-video-card { padding:12px; display:flex; flex-direction:column; gap:8px; }

.svcard-header { display:flex; align-items:flex-start; gap:8px; }
.svcard-desc {
  flex:1; min-width:0; font-size:13px; font-weight:500;
  white-space:pre-wrap; word-break:break-all; cursor:default;
}
.svcard-status { font-size:12px; font-weight:600; }
.svcard-status.active { color:var(--accent); }
.svcard-status.done   { color:var(--color-success,#4caf50); }
.svcard-status.error  { color:var(--color-error,#f44336); }

.scene-num { font-size:11px; font-weight:700; background:var(--accent); color:#fff; border-radius:4px; padding:1px 6px; }

.asset-checks { display:flex; gap:6px; flex-wrap:wrap; }
.asset-tag { font-size:11px; padding:2px 7px; border-radius:10px; border:1px solid; font-weight:500; }
.asset-tag.ok   { border-color:var(--color-success,#4caf50); color:var(--color-success,#4caf50); }
.asset-tag.miss { border-color:var(--color-warning,#ff9800); color:var(--color-warning,#ff9800); }

.scene-mini-bar-wrap { display:flex; align-items:center; gap:8px; }
.scene-mini-bar { flex:1; height:4px; border-radius:2px; background:var(--bg-tertiary); overflow:hidden; }
.scene-mini-fill{ height:100%; background:var(--accent); transition:width .2s; }

.video-result { border-top:1px dashed var(--border-color); padding-top:8px; }
.video-player { width:100%; max-height:320px; border-radius:6px; background:#000; }

.empty-state {
  flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; opacity:.7;
}
.empty-icon { font-size:40px; }
.spinner { width:24px; height:24px; border:2px solid var(--border-color); border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.error-banner {
  flex-shrink:0; margin:0 16px 8px; padding:8px 12px; border-radius:6px;
  background:color-mix(in srgb, var(--color-error,#f44336) 12%, transparent);
  border:1px solid var(--color-error,#f44336);
  font-size:13px; display:flex; align-items:center; gap:8px;
}

.merge-dialog-overlay {
  position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:200;
  display:flex; align-items:center; justify-content:center;
}
.merge-dialog {
  min-width:360px; max-width:520px; padding:20px 24px; display:flex; flex-direction:column; gap:14px;
}
.merge-dialog-title { margin:0; font-size:16px; font-weight:700; }
.merge-dialog-path {
  font-size:12px; color:var(--text-muted); word-break:break-all;
  background:var(--bg-tertiary); padding:6px 10px; border-radius:4px;
}
.merge-dialog-actions { display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }

/* ── Prompt section ── */
.prompt-section {
  border-top: 1px dashed var(--border-color);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-label {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.prompt-set-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
}
.prompt-actions { display: flex; gap: 4px; }
.prompt-editor-wrap { display: flex; flex-direction: column; gap: 4px; }
.prompt-textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font-size: 12px;
  line-height: 1.5;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  min-height: 64px;
}
.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
}
</style>
