<template>
  <div class="mg-shell">
    <!-- ── Generator panel ── -->
    <div class="mg-gen-panel card">
      <div class="mg-gen-header">
        <h3>🎵 音乐生成</h3>
        <span class="mg-scope-badge" :class="scope">
          {{ scope === 'project' ? '项目内：' + projectId : '全局' }}
        </span>
      </div>

      <div class="mg-row">
        <div class="mg-field" style="flex:2">
          <label>名字 <span class="text-muted">(可选)</span></label>
          <input v-model="form.name" class="input" placeholder="例：开场主题曲" />
        </div>
        <div class="mg-field" style="width:120px">
          <label>时长(秒)</label>
          <input v-model.number="form.duration_seconds" type="number"
                 min="10" max="240" step="1" class="input" />
        </div>
        <div class="mg-field" style="width:90px">
          <label>BPM</label>
          <input v-model.number="form.bpm" type="number"
                 min="40" max="240" step="1" class="input" />
        </div>
        <div class="mg-field" style="width:80px">
          <label>拍号</label>
          <select v-model="form.time_signature" class="input">
            <option value="3">3/4</option>
            <option value="4">4/4</option>
            <option value="6">6/8</option>
          </select>
        </div>
        <div class="mg-field" style="width:96px">
          <label>语言</label>
          <select v-model="form.language" class="input">
            <option value="zh">中文</option>
            <option value="en">English</option>
            <option value="ja">日本語</option>
            <option value="ko">한국어</option>
          </select>
        </div>
        <div class="mg-field" style="width:120px">
          <label>调式</label>
          <select v-model="form.key_scale" class="input">
            <option v-for="k in KEY_OPTIONS" :key="k" :value="k">{{ k }}</option>
          </select>
        </div>
      </div>

      <div class="mg-field">
        <div class="mg-field-header">
          <label>标签 (风格 / 流派 / 编曲描述，英文或中文皆可)</label>
          <button class="btn btn-ghost btn-xs" @click="aiAssistOpen = true"
                  :disabled="aiBusy" title="用 LLM 根据简介生成标签 + 歌词">
            {{ aiBusy ? '⏳' : '✨' }} AI 助写
          </button>
        </div>
        <textarea v-model="form.tags" class="input mg-textarea" rows="4"
                  placeholder="例：一首国风电子摇滚片头曲，急促的竹笛循环开场..."></textarea>
      </div>

      <div class="mg-field">
        <label>歌词 <span class="text-muted">(留空 = 纯器乐；用 [Intro] [Verse] [Chorus] 等段落标记效果更好)</span></label>
        <textarea v-model="form.lyrics" class="input mg-textarea" rows="8"
                  placeholder="[Verse 1]&#10;..."></textarea>
      </div>

      <div class="mg-actions">
        <div class="mg-seed-row">
          <label class="mg-seed-label">
            <input type="checkbox" v-model="fixSeed" />
            🔒 固定 seed
          </label>
          <input v-if="fixSeed" v-model.number="form.seed" type="number"
                 class="input mg-seed-input" placeholder="seed (留空 = 随机)" />
          <span v-else class="text-muted" style="font-size:12px">
            每次生成自动用新随机种子，避免重复出同一首
          </span>
        </div>
        <button v-if="running" class="btn btn-secondary"
                @click="cancelGenerate" title="中止 ComfyUI 任务的接收">
          ✕ 取消
        </button>
        <button class="btn btn-primary"
                :disabled="running || !canGenerate"
                @click="generate">
          {{ running ? '⏳ 生成中…' : '▶ 生成音乐' }}
        </button>
      </div>

      <div v-if="running || progressLabel" class="mg-progress-wrap">
        <div class="mg-progress-track">
          <div class="mg-progress-fill" :style="{ width: progressPct + '%' }" />
        </div>
        <div class="mg-progress-label">{{ progressLabel }}</div>
      </div>

      <div v-if="errorMsg" class="mg-error">⚠ {{ errorMsg }}</div>
    </div>

    <!-- ── Library ── -->
    <div class="mg-lib-panel card">
      <div class="mg-lib-header">
        <h3>📚 音乐库 ({{ tracks.length }})</h3>
        <button class="btn btn-ghost btn-xs" :disabled="cleaning" @click="cleanupDead"
                title="清理文件丢失或损坏的条目（小于 1KB 视为损坏）">
          {{ cleaning ? '⏳' : '🧹' }} 清理失效
        </button>
        <button class="btn btn-ghost btn-xs" :disabled="uploading" @click="triggerUpload"
                title="导入本地音频文件到音乐库">
          {{ uploading ? '⏳ 上传中…' : '⬆ 上传音频' }}
        </button>
        <button class="btn btn-ghost btn-xs" @click="loadTracks">↻ 刷新</button>
        <input ref="uploadInput" type="file"
               accept="audio/*,.mp3,.m4a,.wav,.aac,.ogg,.flac"
               style="display:none" @change="onUploadFile" />
      </div>

      <div v-if="!tracks.length" class="mg-empty">尚无音乐</div>
      <div v-else class="mg-track-list">
        <div v-for="t in tracks" :key="t.id" class="mg-track-row">
          <div class="mg-track-info">
            <div class="mg-track-name">{{ t.name }}</div>
            <div class="mg-track-meta text-muted">
              {{ formatSecs(t.duration_secs) }} · {{ t.bpm }} BPM · {{ t.language }} ·
              {{ t.key_scale }} · seed {{ t.seed }}
              <span v-if="t.project_id"> · 项目 {{ t.project_id }}</span>
            </div>
            <div v-if="t.tags" class="mg-track-tags text-muted truncate" :title="t.tags">
              {{ t.tags }}
            </div>
          </div>
          <audio :src="audioUrl(t.id)" controls preload="none" class="mg-audio" />
          <div class="mg-track-actions">
            <button v-if="scope === 'project' && projectId"
                    class="btn btn-ghost btn-xs" :disabled="bgmBusyId === t.id"
                    :title="'复制为本项目 BGM —— 下次合并视频自动使用'"
                    @click="setAsProjectBgm(t)">
              {{ bgmBusyId === t.id ? '⏳' : '📌 设为 BGM' }}
            </button>
            <button class="btn btn-ghost btn-xs" :title="'用这首的参数填回表单'"
                    @click="cloneParams(t)">↺ 参数</button>
            <button class="btn btn-ghost btn-xs" :title="'删除'"
                    @click="deleteTrack(t)">🗑</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── AI 助写对话框 ── -->
    <Teleport to="body">
      <div v-if="aiAssistOpen" class="mg-ai-overlay" @click.self="closeAiAssist">
        <div class="mg-ai-modal card">
          <div class="mg-ai-header">
            <h3>✨ AI 助写 — 自动生成标签 + 歌词</h3>
            <button class="btn btn-ghost btn-xs" @click="closeAiAssist">✕</button>
          </div>
          <div class="mg-ai-body">
            <div class="mg-field">
              <label>简介 (告诉 LLM 你想要什么样的歌)</label>
              <textarea v-model="aiForm.user_request" class="input mg-textarea" rows="4"
                        placeholder="例：一首武侠燃曲，开场低沉笛声，副歌爆发，唱一个隐世剑客重出江湖的故事..."></textarea>
              <span class="text-muted" style="font-size:11px">
                LLM 会根据你已填好的语言 / 时长 / BPM / 调式 自动配套
              </span>
            </div>
            <div class="mg-ai-meta">
              <span class="text-muted">语言：{{ aiLangLabel }}</span>
              <span class="text-muted">时长：{{ form.duration_seconds }}s</span>
              <span class="text-muted">{{ form.bpm }} BPM / {{ form.time_signature }}/4</span>
              <span class="text-muted">调：{{ form.key_scale }}</span>
              <label class="mg-ai-instrumental">
                <input type="checkbox" v-model="aiForm.instrumental" />
                纯器乐（不写歌词）
              </label>
            </div>
            <div v-if="aiError" class="mg-ai-error">⚠ {{ aiError }}</div>
            <div class="mg-ai-actions">
              <button class="btn btn-ghost" @click="closeAiAssist" :disabled="aiBusy">取消</button>
              <button class="btn btn-primary"
                      :disabled="aiBusy || !aiForm.user_request.trim()"
                      @click="runAiAssist">
                {{ aiBusy ? '⏳ 生成中…' : '▶ 让 AI 写' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

const API = 'http://127.0.0.1:18520/api'

const props = defineProps({
  // 'global' (主屏) | 'project' (项目内 tab)
  scope:     { type: String, default: 'global' },
  projectId: { type: String, default: '' },
})

// v1.6.2: 本地音频上传入库
const uploadInput = ref(null)
const uploading   = ref(false)
function triggerUpload() { uploadInput.value?.click() }
async function onUploadFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''                  // 清空，允许再次选同一文件
  if (!file) return
  uploading.value = true
  try {
    const b64 = await new Promise((res, rej) => {
      const r = new FileReader()
      r.onload  = () => res(String(r.result || '').split(',')[1] || '')
      r.onerror = () => rej(r.error || new Error('读取失败'))
      r.readAsDataURL(file)
    })
    const r = await fetch(`${API}/music/upload`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename: file.name,
        data: b64,
        name: file.name.replace(/\.[^.]+$/, ''),
        project_id: props.scope === 'project' ? props.projectId : '',
      }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { detail = (await r.json()).detail || detail } catch {}
      throw new Error(detail)
    }
    await loadTracks()
  } catch (err) {
    alert('上传失败：' + (err.message || err))
  } finally {
    uploading.value = false
  }
}

const KEY_OPTIONS = [
  'C major', 'C minor', 'C# major', 'C# minor',
  'D major', 'D minor', 'D# major', 'D# minor',
  'E major', 'E minor', 'F major', 'F minor',
  'F# major', 'F# minor', 'G major', 'G minor',
  'G# major', 'G# minor', 'A major', 'A minor',
  'A# major', 'A# minor', 'B major', 'B minor',
]

const form = reactive({
  name:             '',
  duration_seconds: 60,
  bpm:              120,
  time_signature:   '4',
  language:         'zh',
  key_scale:        'C major',
  tags:             '',
  lyrics:           '',
  seed:             null,
})
const fixSeed = ref(false)

const running       = ref(false)
const progressPct   = ref(0)
const progressLabel = ref('')
const errorMsg      = ref('')

const tracks = ref([])
const bgmBusyId = ref(null)    // 正在调 set-as-bgm 的 track id
const cleaning = ref(false)

// AI 助写
const aiAssistOpen = ref(false)
const aiBusy       = ref(false)
const aiError      = ref('')
const aiForm = reactive({
  user_request: '',
  instrumental: false,
})
const LANG_LABELS = { zh: '中文', en: 'English', ja: '日本語', ko: '한국어' }
const aiLangLabel = computed(() => LANG_LABELS[form.language] || form.language)

const canGenerate = computed(() => !!form.tags.trim())

let _reader = null
let _abortCtl = null

async function generate() {
  if (running.value) return
  errorMsg.value    = ''
  progressPct.value = 0
  progressLabel.value = '⏳ 提交到 ComfyUI…'
  running.value     = true

  const payload = {
    workflow_name:    'audio_ace_step_1_5_split_4b',
    duration_seconds: form.duration_seconds,
    bpm:              form.bpm,
    time_signature:   form.time_signature,
    language:         form.language,
    key_scale:        form.key_scale,
    tags:             form.tags,
    lyrics:           form.lyrics,
    name:             form.name,
    project_id:       props.scope === 'project' ? props.projectId : '',
    seed:             (fixSeed.value && form.seed) ? form.seed : null,
  }

  _abortCtl = new AbortController()
  try {
    const resp = await fetch(`${API}/music/generate-stream`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
      signal:  _abortCtl.signal,
    })
    if (!resp.ok) {
      let detail = 'HTTP ' + resp.status
      try { const j = await resp.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    _reader = resp.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await _reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          handleEvent(ev)
        } catch {}
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      errorMsg.value = '已取消'
    } else {
      errorMsg.value = e.message || String(e)
    }
  } finally {
    running.value = false
    _reader = null
    _abortCtl = null
    progressLabel.value = ''
    progressPct.value = 0
  }
}

function cancelGenerate() {
  // 取消 fetch + 关 SSE reader；后端 ComfyUI 那边任务仍然继续，但前端不再消费
  try { _abortCtl?.abort() } catch {}
  try { _reader?.cancel() } catch {}
}

async function setAsProjectBgm(t) {
  if (!props.projectId) return
  if (bgmBusyId.value) return
  bgmBusyId.value = t.id
  try {
    const r = await fetch(`${API}/music/track/${t.id}/set-as-bgm`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ project_id: props.projectId }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { const j = await r.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    const data = await r.json()
    alert(`✓ 已设为项目 BGM：${data.filename}\n下次合并视频时自动使用`)
  } catch (e) {
    alert('设为 BGM 失败：' + (e.message || e))
  } finally {
    bgmBusyId.value = null
  }
}

function handleEvent(ev) {
  if (ev.event === 'queued') {
    progressLabel.value = `🎼 ComfyUI 已接受（seed = ${ev.seed}）`
  } else if (ev.event === 'progress') {
    const v = Number(ev.value) || 0
    const m = Number(ev.max)   || 1
    progressPct.value = Math.min(100, Math.round(v / m * 100))
    progressLabel.value = `生成中 · ${v}/${m}`
  } else if (ev.event === 'completed') {
    progressLabel.value = '✓ 完成'
    progressPct.value   = 100
    loadTracks()
  } else if (ev.event === 'error') {
    errorMsg.value = ev.message || '生成失败'
  }
}

async function loadTracks() {
  try {
    const q = props.scope === 'project' && props.projectId
      ? `?project_id=${encodeURIComponent(props.projectId)}`
      : ''
    const r = await fetch(`${API}/music/tracks${q}`)
    if (r.ok) {
      const d = await r.json()
      tracks.value = d.tracks || []
    }
  } catch (e) { console.warn('load tracks failed', e) }
}

function audioUrl(id) { return `${API}/music/file/${id}` }

function formatSecs(s) {
  s = Number(s) || 0
  const m = Math.floor(s / 60)
  const r = s - m * 60
  return `${m}:${String(r).padStart(2, '0')}`
}

function cloneParams(t) {
  form.name             = t.name + ' (副本)'
  form.duration_seconds = t.duration_secs
  form.bpm              = t.bpm
  form.time_signature   = t.time_signature
  form.language         = t.language
  form.key_scale        = t.key_scale
  form.tags             = t.tags
  form.lyrics           = t.lyrics
  // seed 不复制 —— 重新生成时默认随机，免得用户复制完又出同一首
  fixSeed.value = false
  form.seed     = null
}

async function runAiAssist() {
  if (aiBusy.value || !aiForm.user_request.trim()) return
  aiBusy.value  = true
  aiError.value = ''
  try {
    const r = await fetch(`${API}/text-engine/generate-music-prompt`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        user_request:     aiForm.user_request.trim(),
        language:         form.language,
        duration_seconds: form.duration_seconds,
        bpm:              form.bpm,
        time_signature:   form.time_signature,
        key_scale:        form.key_scale,
        project_id:       props.scope === 'project' ? props.projectId : '',
        include_lyrics:   !aiForm.instrumental,
      }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { const j = await r.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    const data = await r.json()
    if (data.tags) form.tags = data.tags
    if (data.lyrics) form.lyrics = data.lyrics
    aiAssistOpen.value = false
  } catch (e) {
    aiError.value = e.message || String(e)
  } finally {
    aiBusy.value = false
  }
}

function closeAiAssist() {
  if (aiBusy.value) return
  aiAssistOpen.value = false
  aiError.value = ''
}

async function cleanupDead() {
  if (cleaning.value) return
  cleaning.value = true
  try {
    const r = await fetch(`${API}/music/cleanup`, { method: 'POST' })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    const d = await r.json()
    await loadTracks()
    if (d.deleted_count) {
      alert(`✓ 已清理 ${d.deleted_count} 个失效条目`)
    } else {
      alert('音乐库已经干净，没有失效条目')
    }
  } catch (e) {
    alert('清理失败: ' + (e.message || e))
  } finally {
    cleaning.value = false
  }
}

async function deleteTrack(t) {
  if (!confirm(`删除 "${t.name}"？此操作不可撤销。`)) return
  try {
    const r = await fetch(`${API}/music/track/${t.id}`, { method: 'DELETE' })
    if (r.ok) loadTracks()
  } catch (e) { alert('删除失败: ' + e.message) }
}

onMounted(loadTracks)
onUnmounted(() => { try { _reader?.cancel() } catch {} })
</script>

<style scoped>
.mg-shell { display: flex; flex-direction: column; gap: 16px; padding: 16px; overflow: auto; }

.mg-gen-panel, .mg-lib-panel {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 14px; display: flex; flex-direction: column; gap: 10px;
}
.mg-gen-header, .mg-lib-header {
  display: flex; align-items: center; gap: 12px;
}
.mg-gen-header h3, .mg-lib-header h3 { margin: 0; font-size: 15px; flex: 1; }
.mg-scope-badge {
  font-size: 11px; padding: 3px 8px; border-radius: 4px;
  background: rgba(99,179,237,.1); color: #63b3ed;
  border: 1px solid rgba(99,179,237,.3);
}
.mg-scope-badge.project { background: rgba(183,148,244,.1); color: #b794f4;
                          border-color: rgba(183,148,244,.3); }

.mg-row { display: flex; gap: 10px; flex-wrap: wrap; }
.mg-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.mg-field label { font-size: 12px; color: var(--text-muted); }
.mg-textarea { font-size: 13px; resize: vertical; min-height: 64px; }

.mg-actions {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  border-top: 1px solid var(--border); padding-top: 12px;
}
.mg-seed-row { display: flex; align-items: center; gap: 8px; flex: 1; }
.mg-seed-label { display: inline-flex; align-items: center; gap: 4px;
                  font-size: 12px; cursor: pointer; }
.mg-seed-input { width: 200px; height: 28px; font-size: 12px; }

.mg-progress-wrap { display: flex; flex-direction: column; gap: 4px; }
.mg-progress-track { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.mg-progress-fill  { height: 100%; background: var(--accent); transition: width .3s; }
.mg-progress-label { font-size: 12px; color: var(--text-muted); }

.mg-error { color: var(--danger, #fc8181); font-size: 13px;
             background: rgba(229,62,62,.08); padding: 8px 12px;
             border-radius: 4px; }

.mg-empty { padding: 24px; text-align: center; color: var(--text-muted); }

.mg-track-list { display: flex; flex-direction: column; gap: 8px; }
.mg-track-row {
  display: grid; grid-template-columns: 1fr 360px auto; gap: 12px;
  align-items: center; padding: 10px 12px;
  background: var(--bg-input); border-radius: 6px;
  border: 1px solid var(--border);
}
.mg-track-info { min-width: 0; }
.mg-track-name { font-size: 14px; font-weight: 600; }
.mg-track-meta { font-size: 11px; margin-top: 2px; }
.mg-track-tags { font-size: 11px; margin-top: 2px; max-width: 100%; }
.mg-audio { width: 100%; height: 32px; }
.mg-track-actions { display: flex; gap: 4px; }

.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* AI 助写 */
.mg-field-header { display: flex; align-items: center; gap: 8px; }
.mg-field-header label { flex: 1; }
.mg-ai-overlay {
  position: fixed; inset: 0; z-index: 10001;
  background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center;
}
.mg-ai-modal {
  width: min(640px, 94vw);
  background: var(--bg-panel, #1e1e1e);
  border: 1px solid var(--border, #333); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.mg-ai-header {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.mg-ai-header h3 { margin: 0; font-size: 15px; flex: 1; }
.mg-ai-body { padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }
.mg-ai-meta {
  display: flex; flex-wrap: wrap; gap: 12px;
  font-size: 12px;
  padding: 8px 10px; border-radius: 4px;
  background: var(--bg-input);
}
.mg-ai-instrumental {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 4px;
  cursor: pointer;
}
.mg-ai-actions { display: flex; gap: 8px; justify-content: flex-end; }
.mg-ai-error {
  color: var(--danger, #fc8181); font-size: 12px;
  background: rgba(229,62,62,.08); padding: 6px 10px; border-radius: 4px;
}
</style>
