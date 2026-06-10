<template>
  <div class="eb-shell">
    <!-- 顶部工具栏 -->
    <div class="eb-toolbar">
      <!-- v1.5.0: scope 切换（全局库 ↔ 本项目库共通），仅在项目上下文显示 -->
      <div v-if="scopeChoices.length > 1" class="eb-scope-switch">
        <button v-for="sc in scopeChoices" :key="sc.value"
                class="eb-scope-chip"
                :class="{ active: activeScope === sc.value }"
                @click="switchScope(sc.value)">{{ sc.label }}</button>
      </div>
      <div class="eb-breadcrumb">
        <span class="eb-crumb" @click="setFolder(null)">
          📦 {{ activeScope === 'global' ? '全局元素库' : '项目元素' }}
        </span>
        <template v-for="(c, idx) in breadcrumb" :key="c.id">
          <span class="eb-sep">/</span>
          <span class="eb-crumb"
                @click="setFolder(c.id)"
                :class="{ active: idx === breadcrumb.length - 1 }">
            {{ c.name }}
          </span>
        </template>
      </div>
      <div class="eb-actions">
        <button class="btn btn-ghost btn-xs" @click="loadAll" title="刷新">↻</button>
        <button class="btn btn-secondary btn-xs" @click="promptNewFolder">📁＋ 新建文件夹</button>
        <button class="btn btn-primary btn-xs" @click="genOpen = true" title="用图片引擎生成素材并入库">✨ 生成图片</button>
        <button class="btn btn-primary btn-xs" @click="triggerUpload">⬆ 上传图片</button>
        <input ref="fileInput" type="file" accept="image/*" multiple
               style="display:none" @change="onFilePicked" />
      </div>
    </div>

    <div class="eb-body">
      <!-- 左侧文件夹树 -->
      <aside class="eb-tree">
        <div class="eb-tree-row eb-tree-root"
             :class="{ active: currentFolderId === null }"
             @click="setFolder(null)"
             @dragover.prevent @drop="onDropToFolder(null, $event)">
          <span class="eb-tree-arrow">📦</span>
          <span class="eb-tree-name">根目录</span>
          <span class="eb-tree-count text-muted">{{ rootElementCount }}</span>
        </div>
        <TreeNode v-for="root in tree" :key="root.id"
                  :node="root"
                  :current-id="currentFolderId"
                  :elements-by-folder="elementsByFolder"
                  @select="setFolder"
                  @rename="promptRename"
                  @delete="confirmDeleteFolder"
                  @drop-element="moveElementToFolder" />
      </aside>

      <!-- 右侧网格 -->
      <main class="eb-grid-wrap"
            @dragover.prevent
            @drop="onDropToFolder(currentFolderId, $event)">
        <div v-if="loading" class="eb-empty">加载中…</div>
        <div v-else-if="!items.length" class="eb-empty">
          <div style="font-size:32px;margin-bottom:6px">🗂</div>
          <div>当前文件夹为空</div>
          <div class="text-muted" style="margin-top:6px;font-size:12px">
            拖入图片直接上传，或点上方"⬆ 上传图片"
          </div>
        </div>
        <div v-else class="eb-grid">
          <div v-for="el in items" :key="el.id"
               class="eb-card"
               :class="{ selected: selectedIds.has(el.id) }"
               draggable="true"
               @dragstart="onElementDragStart(el, $event)"
               @click="onCardClick(el)">
            <img :src="elementUrl(el.id)" class="eb-thumb" :alt="el.name"
                 @error="onThumbError" />
            <div class="eb-card-name truncate" :title="el.name">{{ el.name }}</div>
            <div class="eb-card-meta text-muted">
              {{ el.width || '?' }}×{{ el.height || '?' }} · {{ formatBytes(el.bytes) }}
            </div>
            <div class="eb-card-actions" @click.stop>
              <button v-if="otherScope" class="eb-mini"
                      :title="`复制到${otherScopeLabel}`" @click="copyElementToOther(el)">⇄</button>
              <button class="eb-mini" title="重命名" @click="promptRenameElement(el)">✎</button>
              <button class="eb-mini" title="删除" @click="confirmDeleteElement(el)">🗑</button>
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 状态/选择模式提示 -->
    <div v-if="selectionMode && selectedIds.size" class="eb-selection-bar">
      已选 {{ selectedIds.size }} / {{ maxSelect || '∞' }} —
      <button class="btn btn-primary btn-xs" @click="confirmSelection">✓ 确定</button>
      <button class="btn btn-ghost btn-xs" @click="selectedIds.clear()">清除</button>
    </div>

    <!-- v1.5.0: 生成图片入库 -->
    <ElementGenerateDialog v-if="genOpen"
                           :upload-base="apiBase"
                           :folder-id="currentFolderId"
                           :scope-label="activeScope === 'global' ? '全局元素库' : '项目元素库'"
                           @saved="loadItems"
                           @close="genOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import TreeNode from './ElementsTreeNode.vue'
import ElementGenerateDialog from './ElementGenerateDialog.vue'

const props = defineProps({
  scope: { type: String, required: true },   // "global" | "project:<pid>"
  // 选择模式：用户点击元素返回选中列表（轮 5 参考图 picker 用）
  selectionMode: { type: Boolean, default: false },
  maxSelect: { type: Number, default: 0 },  // 0 = 不限
})
const emit = defineEmits(['picked', 'close'])

const API = 'http://127.0.0.1:18520'

// v1.5.0: 当前激活 scope（可在"本项目库"和"全局库"间切换，使两库共通）
const activeScope      = ref(props.scope)
const folders          = ref([])  // 平铺的 folders
const items            = ref([])  // 当前文件夹的元素
const currentFolderId  = ref(null)
const loading          = ref(false)
const selectedIds      = ref(new Set())
const fileInput        = ref(null)
const genOpen          = ref(false)   // 生成图片弹窗

// ── scope 切换 ────────────────────────────────────────────────────────────────


function _scopeApiBase(scope) {
  if (scope === 'global') return `${API}/api/elements`
  if (scope.startsWith('project:')) {
    const pid = scope.slice('project:'.length)
    return `${API}/api/projects/${encodeURIComponent(pid)}/elements`
  }
  return `${API}/api/elements`
}

// 可切换的 scope 列表：项目上下文 → [本项目, 全局]；纯全局面板 → 仅全局
const scopeChoices = computed(() => {
  if (props.scope.startsWith('project:')) {
    return [{ label: '本项目', value: props.scope }, { label: '全局库', value: 'global' }]
  }
  return [{ label: '全局库', value: 'global' }]
})
// "另一个库"（跨库复制目标）：在两个 scope 间取非当前那个
const otherScope = computed(() => {
  const other = scopeChoices.value.find(s => s.value !== activeScope.value)
  return other ? other.value : null
})
const otherScopeLabel = computed(() =>
  otherScope.value === 'global' ? '全局库' : '本项目')

function switchScope(scope) {
  if (scope === activeScope.value) return
  activeScope.value = scope
  currentFolderId.value = null
  selectedIds.value = new Set()
  loadAll()
}

// ── 路径辅助 ──────────────────────────────────────────────────────────────────


const apiBase = computed(() => _scopeApiBase(activeScope.value))

function elementUrl(id) {
  return `${apiBase.value}/file/${id}`
}

// 平铺转树
const tree = computed(() => {
  const byParent = new Map()
  for (const f of folders.value) {
    const p = f.parent_id ?? '_root_'
    if (!byParent.has(p)) byParent.set(p, [])
    byParent.get(p).push(f)
  }
  function buildChildren(parentKey) {
    return (byParent.get(parentKey) || []).map(f => ({
      ...f,
      children: buildChildren(f.id),
    }))
  }
  return buildChildren('_root_')
})

const elementsByFolder = ref({})  // 这是个缓存，仅 listing 当前文件夹时不会全有；只用作显示数字

const rootElementCount = computed(() => {
  // 不真实查每个文件夹只显示当前根计数（避免 N+1 网络请求）；
  // 实际计数前端可以做"懒加载文件夹时再查"
  return currentFolderId.value === null ? items.value.length : '-'
})

const breadcrumb = computed(() => {
  if (currentFolderId.value === null) return []
  const out = []
  let cur = folders.value.find(f => f.id === currentFolderId.value)
  while (cur) {
    out.unshift(cur)
    cur = cur.parent_id ? folders.value.find(f => f.id === cur.parent_id) : null
  }
  return out
})

// ── 数据加载 ──────────────────────────────────────────────────────────────────


async function loadFolders() {
  try {
    const r = await fetch(`${apiBase.value}/folders`)
    if (r.ok) folders.value = (await r.json()).folders || []
  } catch {}
}

async function loadItems() {
  loading.value = true
  try {
    const url = new URL(`${apiBase.value}/`)
    if (currentFolderId.value !== null) {
      url.searchParams.set('folder_id', String(currentFolderId.value))
    }
    const r = await fetch(url)
    if (r.ok) items.value = (await r.json()).elements || []
  } catch (e) {
    console.warn('load elements failed', e)
  }
  loading.value = false
}

async function loadAll() {
  await Promise.all([loadFolders(), loadItems()])
}

function setFolder(id) {
  currentFolderId.value = id
  loadItems()
}

// props.scope 变化（如切换项目）→ 重置激活 scope 并重载
watch(() => props.scope, (s) => {
  activeScope.value = s
  currentFolderId.value = null
  loadAll()
}, { immediate: false })

onMounted(loadAll)

// ── Folder CRUD ───────────────────────────────────────────────────────────────


async function promptNewFolder() {
  const name = prompt('新文件夹名（不能含 / \\）：')
  if (!name) return
  try {
    const r = await fetch(`${apiBase.value}/folders`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, parent_id: currentFolderId.value }),
    })
    if (!r.ok) throw new Error(await r.text())
    await loadFolders()
  } catch (e) {
    alert('创建失败: ' + e.message)
  }
}

async function promptRename(folder) {
  const name = prompt('新名字：', folder.name)
  if (!name || name === folder.name) return
  try {
    const r = await fetch(`${apiBase.value}/folders/${folder.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!r.ok) throw new Error(await r.text())
    await loadFolders()
  } catch (e) { alert('重命名失败: ' + e.message) }
}

async function confirmDeleteFolder(folder) {
  if (!confirm(`删除文件夹「${folder.name}」及其全部子文件夹和元素？此操作不可撤销。`)) return
  try {
    await fetch(`${apiBase.value}/folders/${folder.id}`, { method: 'DELETE' })
    if (currentFolderId.value === folder.id) currentFolderId.value = null
    await loadAll()
  } catch (e) { alert('删除失败: ' + e.message) }
}

// ── 元素 CRUD ─────────────────────────────────────────────────────────────────


async function promptRenameElement(el) {
  const name = prompt('新名字：', el.name)
  if (!name || name === el.name) return
  try {
    await fetch(`${apiBase.value}/${el.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    await loadItems()
  } catch (e) { alert('重命名失败: ' + e.message) }
}

async function confirmDeleteElement(el) {
  if (!confirm(`删除元素「${el.name}」？`)) return
  try {
    await fetch(`${apiBase.value}/${el.id}`, { method: 'DELETE' })
    await loadItems()
  } catch (e) { alert('删除失败: ' + e.message) }
}

async function moveElementToFolder(elementId, targetFolderId) {
  try {
    await fetch(`${apiBase.value}/${elementId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_id: targetFolderId }),
    })
    await loadItems()
  } catch (e) { alert('移动失败: ' + e.message) }
}

// ── 上传 ──────────────────────────────────────────────────────────────────────


function triggerUpload() {
  fileInput.value?.click()
}

async function onFilePicked(ev) {
  const files = Array.from(ev.target.files || [])
  for (const f of files) await uploadOne(f)
  ev.target.value = ''
  await loadItems()
}

async function onDropToFolder(folderId, ev) {
  const files = Array.from(ev.dataTransfer?.files || [])
  if (files.length) {
    for (const f of files) await uploadOne(f, folderId)
    await loadItems()
    return
  }
  // 拖的是已存在的 element
  const elId = ev.dataTransfer?.getData('text/x-element-id')
  if (elId) {
    await moveElementToFolder(Number(elId), folderId)
  }
}

async function uploadOne(file, folderIdOverride) {
  const buf = await file.arrayBuffer()
  const u8 = new Uint8Array(buf)
  let bin = ''
  const C = 0x8000
  for (let i = 0; i < u8.length; i += C) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + C))
  }
  const data = btoa(bin)
  try {
    await fetch(`${apiBase.value}/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder_id: folderIdOverride === undefined ? currentFolderId.value : folderIdOverride,
        name: file.name.replace(/\.[^.]+$/, ''),
        filename: file.name,
        mime: file.type || 'image/png',
        data,
      }),
    })
  } catch (e) {
    alert(`上传 ${file.name} 失败: ${e.message}`)
  }
}

// ── 选择模式 ──────────────────────────────────────────────────────────────────


function onCardClick(el) {
  if (!props.selectionMode) return
  if (selectedIds.value.has(el.id)) {
    selectedIds.value.delete(el.id)
  } else {
    if (props.maxSelect && selectedIds.value.size >= props.maxSelect) {
      // 单选模式自动替换；多选 max 时拒绝
      if (props.maxSelect === 1) selectedIds.value.clear()
      else return
    }
    selectedIds.value.add(el.id)
  }
  // 触发响应式更新
  selectedIds.value = new Set(selectedIds.value)
}

function confirmSelection() {
  const sel = items.value.filter(el => selectedIds.value.has(el.id)).map(el => ({
    id: el.id,
    name: el.name,
    url: elementUrl(el.id),
    file_path: el.file_path,
    scope: activeScope.value,
  }))
  emit('picked', sel)
}

// v1.5.0: 跨库复制 —— 把当前元素复制到"另一个库"（全局 ↔ 本项目）
async function copyElementToOther(el) {
  if (!otherScope.value) return
  try {
    const r = await fetch(`${apiBase.value}/${el.id}/copy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_scope: otherScope.value, target_folder_id: null }),
    })
    if (!r.ok) throw new Error(await r.text())
    alert(`已复制「${el.name}」到${otherScopeLabel.value}`)
  } catch (e) {
    alert('复制失败: ' + e.message)
  }
}

// ── 拖拽 ──────────────────────────────────────────────────────────────────────


function onElementDragStart(el, ev) {
  ev.dataTransfer.setData('text/x-element-id', String(el.id))
  ev.dataTransfer.effectAllowed = 'move'
}

function onThumbError(ev) {
  ev.target.style.background = 'rgba(255,0,0,.1)'
}

function formatBytes(n) {
  if (!n) return '0 B'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

defineExpose({ loadAll })
</script>

<style scoped>
.eb-shell { display:flex; flex-direction:column; height:100%; min-height:0; }

.eb-toolbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:8px 12px; border-bottom:1px solid var(--color-border);
  background:var(--color-surface);
  flex-shrink:0;
}
.eb-scope-switch {
  display:flex; gap:2px; margin-right:8px;
  background:var(--color-bg, rgba(0,0,0,.2)); border-radius:6px; padding:2px;
}
.eb-scope-chip {
  border:none; background:transparent; cursor:pointer;
  color:var(--color-text-muted); font-size:11px; padding:3px 10px; border-radius:4px;
}
.eb-scope-chip.active { background:var(--color-accent, #4af); color:#fff; }

.eb-breadcrumb { display:flex; gap:4px; align-items:center; font-size:12px; }
.eb-crumb { cursor:pointer; color:var(--color-text-muted); padding:2px 4px; border-radius:3px; }
.eb-crumb:hover { background:var(--color-surface-2); }
.eb-crumb.active { color:var(--color-text); font-weight:600; }
.eb-sep { color:var(--color-text-muted); opacity:.5; }
.eb-actions { display:flex; gap:6px; }

.eb-body { flex:1; display:flex; min-height:0; overflow:hidden; }

.eb-tree {
  width:220px; flex-shrink:0; overflow:auto;
  border-right:1px solid var(--color-border);
  background:var(--color-surface);
  padding:6px 4px;
}
.eb-tree-row {
  display:flex; align-items:center; gap:4px;
  padding:4px 8px; border-radius:4px;
  font-size:12px; cursor:pointer; user-select:none;
}
.eb-tree-row:hover { background:var(--color-surface-2); }
.eb-tree-row.active { background:var(--color-accent-soft, rgba(80,140,220,.15)); color:var(--color-text); }
.eb-tree-arrow { width:14px; text-align:center; }
.eb-tree-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.eb-tree-count { font-size:10px; opacity:.6; }

.eb-grid-wrap {
  flex:1; overflow:auto; padding:12px;
  background:var(--color-bg-secondary, rgba(0,0,0,.05));
}
.eb-grid {
  display:grid; gap:10px;
  grid-template-columns:repeat(auto-fill, minmax(140px, 1fr));
}
.eb-card {
  background:var(--color-surface);
  border:1px solid var(--color-border);
  border-radius:6px; padding:6px; cursor:pointer;
  position:relative;
  transition:transform .1s, box-shadow .1s;
}
.eb-card:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.15); }
.eb-card.selected {
  border-color:var(--color-accent);
  box-shadow:0 0 0 2px var(--color-accent);
}
.eb-thumb {
  width:100%; aspect-ratio:1; object-fit:cover;
  border-radius:4px; background:rgba(0,0,0,.15);
  display:block;
}
.eb-card-name { font-size:12px; margin-top:4px; }
.eb-card-meta { font-size:10px; }
.eb-card-actions {
  position:absolute; top:8px; right:8px;
  display:flex; gap:4px; opacity:0; transition:opacity .1s;
}
.eb-card:hover .eb-card-actions { opacity:1; }
.eb-mini {
  background:rgba(0,0,0,.55); color:#fff;
  border:none; cursor:pointer;
  width:24px; height:24px; border-radius:50%;
  font-size:12px; display:flex; align-items:center; justify-content:center;
}
.eb-mini:hover { background:rgba(220,60,60,.85); }

.eb-empty {
  display:flex; flex-direction:column; align-items:center;
  justify-content:center; height:100%; color:var(--color-text-muted);
  font-size:13px;
}

.eb-selection-bar {
  flex-shrink:0; padding:6px 12px;
  display:flex; align-items:center; gap:8px;
  background:var(--color-accent-soft, rgba(80,140,220,.15));
  border-top:1px solid var(--color-border);
  font-size:12px;
}
</style>
