<template>
  <div class="rp-overlay" @click.self="$emit('close')">
    <div class="rp-modal">
      <div class="rp-header">
        <h3>选择参考图</h3>
        <span class="text-muted" style="font-size:12px">来源：角色立绘 / 元素库 / 本地上传</span>
        <button class="btn btn-ghost btn-xs" @click="$emit('close')" style="margin-left:auto">✕</button>
      </div>

      <div class="rp-tabs">
        <button class="rp-tab" :class="{ active: tab === 'portraits' }" @click="tab = 'portraits'">
          🎭 角色立绘
        </button>
        <button class="rp-tab" :class="{ active: tab === 'elements' }" @click="tab = 'elements'">
          📦 元素库
        </button>
        <button class="rp-tab" :class="{ active: tab === 'upload' }" @click="tab = 'upload'">
          ⬆ 本地上传
        </button>
      </div>

      <div class="rp-body">
        <!-- ── Portraits ────────────────────────────────────────────────── -->
        <div v-if="tab === 'portraits'" class="rp-portraits">
          <div v-if="!portraits.length" class="rp-empty">
            尚无角色立绘 — 请在「角色管理」生成立绘
          </div>
          <div v-else class="rp-grid">
            <div v-for="p in portraits" :key="p.char_name + ':' + p.filename"
                 class="rp-card"
                 :class="{ primary: p.is_primary }"
                 @click="pickPortrait(p)">
              <img :src="p.url" :alt="p.char_name" />
              <div class="rp-card-name">{{ p.char_name }}</div>
              <div class="rp-card-meta text-muted">
                {{ p.filename }}{{ p.is_primary ? ' · 主图' : '' }}
              </div>
            </div>
          </div>
        </div>

        <!-- ── Elements ─────────────────────────────────────────────────── -->
        <div v-else-if="tab === 'elements'" class="rp-elements">
          <div class="rp-elem-scope-tabs">
            <button class="rp-sub-tab"
                    :class="{ active: elemScope === 'global' }"
                    @click="elemScope = 'global'">🌐 全局</button>
            <button class="rp-sub-tab"
                    :class="{ active: elemScope === 'project' }"
                    @click="elemScope = 'project'">📁 项目</button>
          </div>
          <div class="rp-elem-body">
            <ElementsBrowser
              :key="elemScopeKey"
              :scope="elemScopeKey"
              :selection-mode="true"
              :max-select="1"
              @picked="onElementPicked"
            />
          </div>
        </div>

        <!-- ── Upload ───────────────────────────────────────────────────── -->
        <div v-else-if="tab === 'upload'" class="rp-upload">
          <div class="rp-upload-zone"
               :class="{ dragging: dragging }"
               @click="fileInput?.click()"
               @dragover.prevent="dragging = true"
               @dragleave.prevent="dragging = false"
               @drop.prevent="onDrop">
            <div class="rp-upload-icon">📁</div>
            <div class="rp-upload-text">
              点击或拖入图片以上传<br />
              <span class="text-muted" style="font-size:12px">
                文件将自动保存到{{ scopeLabel }} → local 文件夹
              </span>
            </div>
            <input ref="fileInput" type="file" accept="image/*"
                   style="display:none" @change="onFilePicked" />
          </div>
          <div v-if="uploadProgress" class="rp-upload-progress">{{ uploadProgress }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ElementsBrowser from './ElementsBrowser.vue'

const API = 'http://127.0.0.1:18520/api'

const props = defineProps({
  projectId: { type: String, required: true },
  // 默认元素库 scope：'global' 或 'project'
  defaultElemScope: { type: String, default: 'global' },
})
const emit = defineEmits(['picked', 'close'])

const tab = ref('portraits')

// ── Portraits ────────────────────────────────────────────────────────────────
const portraits = ref([])
function portraitFileUrl(charName, filename) {
  return `${API}/projects/${encodeURIComponent(props.projectId)}` +
         `/characters/${encodeURIComponent(charName)}/portraits/file/${encodeURIComponent(filename)}`
}
async function loadPortraits() {
  try {
    // 1) 拿角色列表（characters.json 的原始内容里没有 url 字段）
    const r = await fetch(`${API}/projects/${props.projectId}/characters`)
    if (!r.ok) return
    const data = await r.json()
    const chars = data.characters || []

    // 2) 并行查每个角色的 portraits 子端点（含 url + exists_on_disk）
    const lists = await Promise.all(chars.map(async c => {
      if (!c.name) return []
      try {
        const pr = await fetch(`${API}/projects/${props.projectId}` +
                                `/characters/${encodeURIComponent(c.name)}/portraits`)
        if (!pr.ok) return []
        const pd = await pr.json()
        return (pd.portraits || [])
          .filter(p => p.exists_on_disk !== false && p.filename)
          .map(p => ({
            char_name: c.name,
            filename: p.filename,
            is_primary: !!p.is_primary,
            url: portraitFileUrl(c.name, p.filename),
          }))
      } catch { return [] }
    }))

    const out = lists.flat()
    // 主图排在前
    out.sort((a, b) => Number(b.is_primary) - Number(a.is_primary))
    portraits.value = out
  } catch (e) { console.warn('loadPortraits failed', e) }
}

function pickPortrait(p) {
  emit('picked', {
    kind: 'portrait',
    project_id: props.projectId,
    char_name: p.char_name,
    filename: p.filename,
    // 显示用字段（前端缩略图）
    _preview_url: p.url,
    _label: `${p.char_name} · ${p.filename}`,
  })
}

// ── Elements ─────────────────────────────────────────────────────────────────
const elemScope = ref(props.defaultElemScope || 'global')
const elemScopeKey = computed(() =>
  elemScope.value === 'global' ? 'global' : `project:${props.projectId}`
)

function onElementPicked(items) {
  if (!items?.length) return
  const it = items[0]
  emit('picked', {
    kind: 'element',
    scope: it.scope,
    element_id: it.id,
    _preview_url: it.url,
    _label: it.name,
  })
}

// ── Upload ───────────────────────────────────────────────────────────────────
const fileInput = ref(null)
const dragging = ref(false)
const uploadProgress = ref('')
const uploadScope = ref('project')   // 默认上传到项目 local 文件夹

const scopeLabel = computed(() =>
  uploadScope.value === 'global' ? '全局元素库' : '项目元素'
)

async function onFilePicked(e) {
  const f = e.target.files?.[0]
  if (f) await uploadFile(f)
  e.target.value = ''
}
async function onDrop(e) {
  dragging.value = false
  const f = e.dataTransfer.files?.[0]
  if (f) await uploadFile(f)
}

async function uploadFile(file) {
  uploadProgress.value = '上传中…'
  try {
    const scope = uploadScope.value === 'global' ? 'global' : `project:${props.projectId}`
    const base = uploadScope.value === 'global'
      ? `${API}/elements`
      : `${API}/projects/${props.projectId}/elements`
    // 1) 找/建 local 文件夹
    const rFolders = await fetch(`${base}/folders`)
    const fdata = rFolders.ok ? await rFolders.json() : { folders: [] }
    let localFolder = (fdata.folders || []).find(
      f => f.parent_id === null && f.name === 'local'
    )
    if (!localFolder) {
      const r = await fetch(`${base}/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'local', parent_id: null }),
      })
      if (!r.ok) throw new Error('create local folder failed: ' + r.status)
      localFolder = await r.json()
    }
    // 2) 把图片转 base64 上传（后端 elements upload 用 JSON+base64）
    const dataB64 = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const s = String(reader.result || '')
        resolve(s.replace(/^data:[^;]+;base64,/, ''))
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
    const r = await fetch(`${base}/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder_id: localFolder.id,
        name: file.name,
        filename: file.name,
        mime: file.type || 'image/png',
        source: 'upload',
        data: dataB64,
      }),
    })
    if (!r.ok) throw new Error('upload failed: ' + r.status)
    const el = await r.json()
    uploadProgress.value = '完成 ✓'
    // 直接选中刚上传的元素
    emit('picked', {
      kind: 'element',
      scope,
      element_id: el.id,
      _preview_url: `${base}/file/${el.id}`,
      _label: el.name,
    })
  } catch (e) {
    console.error(e)
    uploadProgress.value = '失败：' + (e.message || e)
  }
}

onMounted(() => {
  loadPortraits()
})
</script>

<style scoped>
.rp-overlay {
  position: fixed; inset: 0; z-index: 10001;
  background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center;
}
.rp-modal {
  width: min(900px, 92vw); height: min(620px, 88vh);
  background: var(--bg-panel, #1e1e1e);
  border: 1px solid var(--border, #333); border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
}
.rp-header {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--border, #333);
}
.rp-header h3 { margin: 0; font-size: 15px; }

.rp-tabs {
  display: flex; gap: 4px; padding: 4px 8px;
  border-bottom: 1px solid var(--border, #333);
}
.rp-tab {
  padding: 6px 14px; border-radius: 6px 6px 0 0;
  background: transparent; border: none;
  color: var(--text-muted, #999); cursor: pointer;
  font-size: 13px;
}
.rp-tab.active {
  background: var(--bg-input, #2a2a2a);
  color: var(--text, #ddd); font-weight: 600;
}

.rp-body { flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; }

.rp-portraits { flex: 1; overflow: auto; padding: 14px; }
.rp-grid {
  /* 立绘是 1080×1920 竖幅；卡片宽 120 → 高约 213 */
  display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}
.rp-card {
  border: 1px solid var(--border, #333); border-radius: 6px;
  background: var(--bg-input, #2a2a2a); cursor: pointer;
  transition: border-color .15s, transform .15s;
  display: flex; flex-direction: column;
}
.rp-card:hover { border-color: var(--accent, #63b3ed); transform: translateY(-1px); }
.rp-card.primary { border-color: var(--accent, #63b3ed); }
/* 9:16 竖幅；object-position 顶部对齐让人物头部一定可见 */
.rp-card img {
  width: 100%; aspect-ratio: 9/16;
  object-fit: cover; object-position: center top;
  border-radius: 6px 6px 0 0;
}
.rp-card-name { padding: 6px 8px 0; font-size: 12px; font-weight: 600; }
.rp-card-meta { padding: 0 8px 6px; font-size: 10px; }

.rp-elements { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.rp-elem-scope-tabs { display: flex; gap: 2px; padding: 6px 10px; border-bottom: 1px solid var(--border, #333); }
.rp-sub-tab {
  padding: 4px 10px; border-radius: 4px;
  background: transparent; border: 1px solid transparent;
  color: var(--text-muted, #999); cursor: pointer; font-size: 12px;
}
.rp-sub-tab.active {
  background: var(--bg-input, #2a2a2a); color: var(--text, #ddd);
  border-color: var(--border, #333);
}
.rp-elem-body { flex: 1; min-height: 0; }

.rp-upload { flex: 1; overflow: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.rp-upload-zone {
  border: 2px dashed var(--border, #444); border-radius: 10px;
  padding: 60px 20px; text-align: center; cursor: pointer;
  transition: border-color .15s, background .15s;
}
.rp-upload-zone:hover, .rp-upload-zone.dragging {
  border-color: var(--accent, #63b3ed);
  background: rgba(99,179,237,.08);
}
.rp-upload-icon { font-size: 48px; margin-bottom: 12px; }
.rp-upload-text { font-size: 14px; line-height: 1.6; }
.rp-upload-progress { font-size: 12px; color: var(--text-muted, #999); text-align: center; }

.rp-empty { padding: 40px 20px; text-align: center; color: var(--text-muted, #999); font-size: 13px; }
</style>
