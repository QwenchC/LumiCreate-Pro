<template>
  <Teleport to="body">
    <div class="sfx-overlay" @click.self="$emit('close')">
      <div class="sfx-modal">
        <div class="sfx-header">
          <h3>🔊 音效编辑 — 时间轴</h3>
          <button class="btn btn-ghost btn-xs" @click="$emit('close')">✕</button>
        </div>

        <div class="sfx-body">
          <!-- 左：分镜列表 -->
          <div class="sfx-scenes">
            <div class="sfx-section-title">分镜（{{ scenes.length }}）</div>
            <ul class="sfx-scene-list">
              <li v-for="(s, i) in scenes" :key="s.id"
                  :class="{ active: i === activeIndex }"
                  @click="activeIndex = i">
                <span class="sfx-scene-idx">{{ i + 1 }}.</span>
                <span class="sfx-scene-title">{{ s.title || s.id }}</span>
                <span v-if="(timeline[s.id] || []).length" class="sfx-badge">
                  {{ (timeline[s.id] || []).length }}
                </span>
              </li>
            </ul>
          </div>

          <!-- 中：当前分镜时间轴 -->
          <div class="sfx-timeline">
            <div class="sfx-section-title">
              当前分镜 — {{ activeScene?.title || activeScene?.id || '请选择' }}
            </div>
            <div v-if="!activeScene" class="sfx-empty">左边选一个分镜开始编辑</div>
            <template v-else>
              <div v-if="(timeline[activeScene.id] || []).length === 0" class="sfx-empty">
                还没加音效。右边选一个 SFX 加进来。
              </div>
              <table v-else class="sfx-table">
                <thead>
                  <tr>
                    <th>时间点 (ms)</th>
                    <th>SFX</th>
                    <th>音量 (dB)</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(ov, j) in timeline[activeScene.id]" :key="j">
                    <td>
                      <input type="number" min="0" step="100"
                             v-model.number="ov.offset_ms" class="input input-xs" />
                    </td>
                    <td class="sfx-sfx-name" :title="sfxLabel(ov.sfx_id)">
                      {{ sfxLabel(ov.sfx_id) }}
                    </td>
                    <td>
                      <input type="number" min="-40" max="20" step="1"
                             v-model.number="ov.volume_db" class="input input-xs" />
                    </td>
                    <td>
                      <button class="btn btn-ghost btn-xs" @click="removeOverlay(j)">✕</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>

          <!-- 右：SFX 库 -->
          <div class="sfx-library">
            <div class="sfx-section-title">
              SFX 库（{{ library.length }}）
              <button class="btn btn-secondary btn-xs sfx-upload-btn"
                      @click="pickFile" :disabled="uploading">
                {{ uploading ? '上传中…' : '＋ 上传' }}
              </button>
              <input ref="fileInput" type="file" hidden
                     accept=".mp3,.m4a,.wav,.aac,.ogg,.flac"
                     @change="onFile" />
            </div>
            <div v-if="library.length === 0" class="sfx-empty">
              SFX 库还是空的，点上面 ＋ 上传你的音效文件。
            </div>
            <ul v-else class="sfx-library-list">
              <li v-for="clip in library" :key="clip.id">
                <div class="sfx-lib-row">
                  <span class="sfx-lib-name" :title="clip.name">{{ clip.name }}</span>
                  <span class="sfx-lib-meta">
                    {{ clip.duration_ms ? (clip.duration_ms / 1000).toFixed(1) + 's' : '?' }}
                  </span>
                  <button class="btn btn-ghost btn-xs" :title="'试听'"
                          @click="playSfx(clip)">▶</button>
                  <button class="btn btn-secondary btn-xs"
                          :disabled="!activeScene"
                          @click="addOverlay(clip)">+ 加入</button>
                  <button class="btn btn-ghost btn-xs" @click="deleteSfx(clip)">✕</button>
                </div>
              </li>
            </ul>
            <audio ref="auditionEl" style="display:none" />
          </div>
        </div>

        <div class="sfx-footer">
          <span class="text-muted sfx-hint">
            ℹ 改完按保存。SFX 会在下次跑「图片放映」时烧进分镜 mp4。
          </span>
          <button class="btn btn-ghost" @click="$emit('close')">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : '💾 保存时间轴' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  projectId: { type: String, required: true },
  scenes:    { type: Array,  required: true },
})
const emit = defineEmits(['close', 'saved'])

const API = 'http://localhost:18520/api'

// 时间轴：{ scene_id: [{sfx_id, offset_ms, volume_db}] }
const timeline = ref({})
const library  = ref([])
const activeIndex = ref(scenes_initial_index())
const saving   = ref(false)
const uploading = ref(false)
const fileInput = ref(null)
const auditionEl = ref(null)

const activeScene = computed(() => props.scenes[activeIndex.value] || null)

function scenes_initial_index() {
  return props.scenes.length > 0 ? 0 : -1
}

function sfxLabel(id) {
  const c = library.value.find(x => x.id === id)
  return c ? c.name : `(已删除 #${id})`
}

async function loadAll() {
  const [tl, lib] = await Promise.all([
    axios.get(`${API}/sfx/timeline/${props.projectId}`),
    axios.get(`${API}/sfx/list`),
  ])
  // 后端返回 {timeline: {...}}；保证每镜次数组就绪
  timeline.value = tl.data?.timeline || {}
  library.value  = lib.data?.items || []
}

function ensureSceneList(sid) {
  if (!Array.isArray(timeline.value[sid])) timeline.value[sid] = []
  return timeline.value[sid]
}

function addOverlay(clip) {
  if (!activeScene.value) return
  const arr = ensureSceneList(activeScene.value.id)
  arr.push({ sfx_id: clip.id, offset_ms: 0, volume_db: -6 })
}

function removeOverlay(j) {
  if (!activeScene.value) return
  const arr = timeline.value[activeScene.value.id]
  if (arr) arr.splice(j, 1)
}

function pickFile() {
  fileInput.value?.click()
}

async function onFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''   // 允许重选同一文件
  if (!f) return
  uploading.value = true
  try {
    const buf = await f.arrayBuffer()
    // ArrayBuffer → base64
    let bin = ''
    const u8 = new Uint8Array(buf)
    const CHUNK = 0x8000
    for (let i = 0; i < u8.length; i += CHUNK) {
      bin += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK))
    }
    const b64 = btoa(bin)
    const namePart = f.name.replace(/\.[^.]+$/, '')
    await axios.post(`${API}/sfx/upload`, {
      filename: f.name,
      name:     namePart,
      category: 'uncategorized',
      data:     b64,
    })
    // 刷新库
    const lib = await axios.get(`${API}/sfx/list`)
    library.value = lib.data?.items || []
  } catch (err) {
    alert('上传失败：' + (err?.response?.data?.detail || err.message))
  } finally {
    uploading.value = false
  }
}

function playSfx(clip) {
  const a = auditionEl.value
  if (!a) return
  a.src = `${API}/sfx/file/${clip.id}`
  a.play().catch(() => {})
}

async function deleteSfx(clip) {
  if (!confirm(`删除 SFX「${clip.name}」？已用到此 SFX 的时间轴条目会失效。`)) return
  try {
    await axios.delete(`${API}/sfx/clip/${clip.id}`)
    library.value = library.value.filter(x => x.id !== clip.id)
  } catch (err) {
    alert('删除失败：' + (err?.response?.data?.detail || err.message))
  }
}

async function save() {
  saving.value = true
  try {
    // 净化：去掉空数组键，过滤无效 sfx_id
    const clean = {}
    for (const [sid, arr] of Object.entries(timeline.value)) {
      if (!Array.isArray(arr) || arr.length === 0) continue
      const valid = arr.filter(o => Number.isInteger(o.sfx_id))
      if (valid.length) clean[sid] = valid
    }
    await axios.put(`${API}/sfx/timeline/${props.projectId}`, { timeline: clean })
    emit('saved')
    emit('close')
  } catch (err) {
    alert('保存失败：' + (err?.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
/* 用项目 design tokens：var(--bg-panel) / --text / --border / --bg-input / --accent
   之前用 --color-background / --color-border 是错的 token → light 主题下
   fallback #1e1e1e 配上深色文本 = 字背景同色看不清。 */
.sfx-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
}
.sfx-modal {
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  /* 改成确切的 width + max-height + flex 列布局，
     让 body 在 max-height 内伸缩，避免内部 grid 把外壳撑爆 */
  width: min(1100px, 96vw);
  max-height: min(86vh, 760px);
  display: flex; flex-direction: column; gap: 10px;
  min-height: 0;
}
.sfx-header {
  display: flex; align-items: center; justify-content: space-between;
  flex: 0 0 auto;
}
.sfx-header h3 { margin: 0; font-size: 15px; color: var(--text); }

/* 关键修复：body flex:1 + min-height:0 → grid 三栏在外壳剩余空间内伸缩，
   每栏内部 overflow:auto 滚动，再也不会撑出窗口边界 */
.sfx-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr) 280px;
  gap: 10px;
}
.sfx-scenes, .sfx-timeline, .sfx-library {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  overflow: auto;
  min-height: 0;
  min-width: 0;
}
.sfx-section-title {
  font-size: 12px; font-weight: 600;
  color: var(--text);
  margin-bottom: 6px; padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 6px;
  position: sticky; top: -8px; background: var(--bg-input);
  z-index: 1;
}
.sfx-section-title > .sfx-upload-btn { margin-left: auto; }

.sfx-scene-list, .sfx-library-list {
  list-style: none; padding: 0; margin: 0;
}
.sfx-scene-list li {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; cursor: pointer; border-radius: 4px;
  color: var(--text); font-size: 13px;
}
.sfx-scene-list li:hover { background: var(--bg-panel); }
.sfx-scene-list li.active {
  background: var(--accent);
  color: #fff;
}
.sfx-scene-list li.active .sfx-scene-idx { color: rgba(255, 255, 255, 0.75); }
.sfx-scene-idx { color: var(--text-muted); min-width: 22px; font-size: 12px; }
.sfx-scene-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sfx-badge {
  background: var(--accent);
  color: #fff; font-size: 10px;
  padding: 1px 6px; border-radius: 8px; line-height: 1.4;
}
.sfx-scene-list li.active .sfx-badge {
  background: #fff; color: var(--accent);
}

.sfx-table { width: 100%; border-collapse: collapse; color: var(--text); }
.sfx-table th, .sfx-table td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  text-align: left; font-size: 12px;
}
.sfx-table th {
  color: var(--text-muted); font-weight: 500;
  position: sticky; top: 22px; background: var(--bg-input);
}
.sfx-table input.input-xs {
  width: 70px; padding: 2px 6px; font-size: 12px;
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
}
.sfx-table .sfx-sfx-name {
  max-width: 180px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}

.sfx-lib-row {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 2px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
.sfx-lib-row:last-child { border-bottom: none; }
.sfx-lib-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 12px;
}
.sfx-lib-meta {
  color: var(--text-muted); font-size: 11px;
  flex: 0 0 auto;
}

.sfx-empty {
  color: var(--text-muted);
  text-align: center; padding: 24px 8px; font-size: 12px;
}
.sfx-footer {
  display: flex; align-items: center; gap: 8px;
  flex: 0 0 auto;
  padding-top: 8px; border-top: 1px solid var(--border);
}
.sfx-hint {
  font-size: 11px; flex: 1; color: var(--text-muted);
}
</style>
