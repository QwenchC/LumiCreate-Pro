<template>
  <div class="home-layout">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-header">
        <span v-if="!sidebarCollapsed" class="sidebar-logo">✦ LumiCreate</span>
        <button class="sidebar-toggle" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="sidebarCollapsed = !sidebarCollapsed">
          {{ sidebarCollapsed ? '▶' : '◀' }}
        </button>
      </div>
      <nav class="sidebar-nav">
        <!-- Expanded -->
        <template v-if="!sidebarCollapsed">
          <div class="folders-section">
            <div v-for="folder in folders" :key="folder.id">
              <!-- Folder header row -->
              <div
                class="folder-item"
                :class="{ active: activeFolder === folder.id && !expandedFolders.has(folder.id) }"
                @click="toggleFolderExpand(folder.id)"
              >
                <span class="folder-expand-arrow" :class="{ open: expandedFolders.has(folder.id) }">&#9654;</span>
                <span class="folder-emoji">{{ folder.emoji }}</span>
                <span class="folder-name truncate">{{ folder.name }}</span>
                <span class="folder-count text-muted">{{ projectsInFolder(folder.id).length }}</span>
                <div class="folder-actions" @click.stop>
                  <button class="folder-action-btn" title="重命名" @click.stop="startRenameFolder(folder)">✏</button>
                  <button
                    v-if="folder.id !== 'default'"
                    class="folder-action-btn danger"
                    title="删除文件夹"
                    @click.stop="confirmDeleteFolder(folder)"
                  >✕</button>
                </div>
              </div>
              <!-- Project sub-list when expanded -->
              <div v-if="expandedFolders.has(folder.id)" class="folder-projects">
                <div
                  v-for="proj in projectsInFolder(folder.id)"
                  :key="proj.id"
                  class="sidebar-project-item"
                  :class="{ 'has-video': proj.has_final_video }"
                  :title="proj.name"
                  @click="openProject(proj)"
                >
                  <span class="sidebar-project-icon">🎦</span>
                  <span class="sidebar-project-name truncate">{{ proj.name }}</span>
                </div>
                <div v-if="projectsInFolder(folder.id).length === 0" class="sidebar-project-empty">暂无项目</div>
              </div>
            </div>
          </div>
          <button class="add-folder-btn" @click="openCreateFolderDialog">
            + 新建文件夹
          </button>
        </template>
        <!-- Collapsed: emoji icons only -->
        <template v-else>
          <div class="folders-section folders-section--collapsed">
            <div
              v-for="folder in folders"
              :key="folder.id"
              class="folder-icon-pill"
              :class="{ active: activeFolder === folder.id }"
              :title="folder.name"
              @click="activeFolder = folder.id"
            >{{ folder.emoji }}</div>
          </div>
        </template>
      </nav>
      <div class="sidebar-footer">
        <button v-if="!sidebarCollapsed" class="btn btn-ghost btn-sm" @click="$router.push('/settings')">
          ⚙ 引擎设置
        </button>
        <button v-else class="sidebar-settings-icon" title="引擎设置" @click="$router.push('/settings')">⚙</button>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content">
      <!-- Toolbar -->
      <div class="toolbar">
        <h2 class="toolbar-title">{{ currentFolder.emoji }} {{ currentFolder.name }}</h2>
        <div class="toolbar-actions">
          <input v-model="searchQuery" class="input search-input" placeholder="搜索项目..." />
          <button class="btn btn-primary" @click="showCreateDialog = true">
            + 新建项目
          </button>
          <button class="btn btn-secondary" @click="refresh">
            🔄 刷新
          </button>
        </div>
      </div>

      <!-- Project grid -->
      <div v-if="store.loading" class="empty-state">
        <div class="spinner" />
        <p>加载中...</p>
      </div>
      <div v-else-if="filteredProjects.length === 0" class="empty-state">
        <div class="empty-icon">📂</div>
        <p>暂无项目，点击「新建项目」开始创作</p>
        <button class="btn btn-primary" @click="showCreateDialog = true">新建项目</button>
      </div>
      <div v-else class="project-grid">
        <div
          v-for="proj in filteredProjects"
          :key="proj.id"
          class="project-card card"
          @click="openProject(proj)"
        >
          <div class="project-card-header">
            <span class="project-icon">🎬</span>
            <div class="project-menu-trigger" @click.stop>
              <button class="btn btn-ghost btn-sm" @click.stop="toggleMenu(proj.id)">⋯</button>
              <div v-if="activeMenu === proj.id" class="context-menu">
                <div class="ctx-item" @click.stop="openProject(proj)">打开</div>
                <div class="ctx-item" @click.stop="startRenameProject(proj)">重命名</div>
                <div class="ctx-item" @click.stop="startMoveProject(proj)">移至文件夹</div>
                <div class="ctx-item danger" @click.stop="confirmDelete(proj)">删除</div>
              </div>
            </div>
          </div>
          <h3 class="project-name truncate">{{ proj.name }}</h3>
          <p class="project-desc truncate text-muted">{{ proj.description || '暂无描述' }}</p>
          <div class="project-meta">
            <span class="text-muted">更新: {{ formatDate(proj.updated_at) }}</span>
          </div>
          <div class="project-progress">
            <div
              v-for="(step, key) in STEPS"
              :key="key"
              class="progress-step"
              :class="{ done: (proj.progress?.[key] ?? 0) === 100, active: isActive(proj.progress, key) }"
              :title="`${step}: ${proj.progress?.[key] ?? 0}%`"
            />
          </div>
          <div class="project-progress-labels">
            <span v-for="(step, key) in STEPS" :key="key" class="progress-label text-muted">{{ step }}</span>
          </div>
          <div class="project-card-actions" @click.stop>
            <button
              class="card-action-btn"
              :class="{ 'card-action-btn--active': proj.has_final_video }"
              :disabled="!proj.has_final_video"
              :title="proj.has_final_video ? '播放合成视频' : '视频尚未合成'"
              @click.stop="playVideo(proj)"
            >▶ 播放</button>
            <button
              class="card-action-btn"
              title="在文件夹中显示"
              @click.stop="openFolder(proj)"
            >📂 目录</button>
          </div>
        </div>
      </div>
    </main>

    <!-- Create project dialog -->
    <Teleport to="body">
      <div v-if="showCreateDialog" class="overlay" @click.self="showCreateDialog = false; copyFromProjectId = ''">
        <div class="dialog card">
          <h3 class="dialog-title">新建项目</h3>
          <div class="form-group">
            <label>项目名称 <span class="required">*</span></label>
            <input v-model="newName" class="input" placeholder="例：我的漫剧第一话" @keyup.enter="createProject" autofocus />
          </div>
          <div class="form-group">
            <label>项目描述</label>
            <textarea v-model="newDesc" class="input textarea" placeholder="简短描述项目内容（可选）" rows="3" />
          </div>
          <div class="form-group">
            <label>复制配置（可选）</label>
            <select v-model="copyFromProjectId" class="input">
              <option value="">不复制，从空白开始</option>
              <option v-for="p in store.projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <p v-if="copyFromProjectId" class="field-hint" style="margin-top:4px;font-size:11px;color:var(--color-text-muted);opacity:0.7">将从该项目复制角色列表与文案配置（世界观、角色设定等），不复制文案内容和分镜。</p>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!newName.trim()" @click="createProject">创建</button>
            <button class="btn btn-ghost" @click="showCreateDialog = false">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete project confirm -->
    <Teleport to="body">
      <div v-if="deleteTarget" class="overlay">
        <div class="dialog card">
          <h3 class="dialog-title">⚠ 删除确认</h3>
          <p class="text-muted" style="margin-bottom:16px">
            确定要删除项目「<b>{{ deleteTarget.name }}</b>」吗？此操作不可撤销。
          </p>
          <div class="dialog-actions">
            <button class="btn btn-danger" @click="doDelete">删除</button>
            <button class="btn btn-ghost" @click="deleteTarget = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Folder create/rename dialog -->
    <Teleport to="body">
      <div v-if="showFolderDialog" class="overlay" @click.self="closeFolderDialog">
        <div class="dialog card">
          <h3 class="dialog-title">{{ showFolderDialog === 'create' ? '新建文件夹' : '重命名文件夹' }}</h3>
          <div class="form-group">
            <label>图标</label>
            <div class="emoji-picker">
              <button
                v-for="e in EMOJI_OPTIONS"
                :key="e"
                class="emoji-btn"
                :class="{ selected: folderEmoji === e }"
                @click="folderEmoji = e"
              >{{ e }}</button>
            </div>
          </div>
          <div class="form-group">
            <label>文件夹名称 <span class="required">*</span></label>
            <input v-model="folderName" class="input" placeholder="例：短视频项目" @keyup.enter="submitFolderDialog" />
          </div>
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!folderName.trim()" @click="submitFolderDialog">
              {{ showFolderDialog === 'create' ? '创建' : '保存' }}
            </button>
            <button class="btn btn-ghost" @click="closeFolderDialog">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete folder confirm -->
    <Teleport to="body">
      <div v-if="deleteFolderTarget" class="overlay">
        <div class="dialog card">
          <h3 class="dialog-title">⚠ 删除文件夹</h3>
          <p class="text-muted" style="margin-bottom:16px">
            确定要删除文件夹「<b>{{ deleteFolderTarget.emoji }} {{ deleteFolderTarget.name }}</b>」吗？
            <br /><br />文件夹中的所有项目将自动转移到「我的项目」中。
          </p>
          <div class="dialog-actions">
            <button class="btn btn-danger" @click="doDeleteFolder">删除文件夹</button>
            <button class="btn btn-ghost" @click="deleteFolderTarget = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Rename project dialog -->
    <Teleport to="body">
      <div v-if="renameTarget" class="overlay" @click.self="renameTarget = null">
        <div class="dialog card">
          <h3 class="dialog-title">重命名项目</h3>
          <div class="form-group">
            <label>项目名称 <span class="required">*</span></label>
            <input v-model="renameName" class="input" placeholder="输入新名称" @keyup.enter="doRenameProject" autofocus />
          </div>
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!renameName.trim()" @click="doRenameProject">保存</button>
            <button class="btn btn-ghost" @click="renameTarget = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Move project to folder dialog -->
    <Teleport to="body">
      <div v-if="moveTarget" class="overlay" @click.self="moveTarget = null">
        <div class="dialog card">
          <h3 class="dialog-title">移至文件夹</h3>
          <p class="text-muted" style="margin-bottom:12px">为「<b>{{ moveTarget.name }}</b>」选择目标文件夹</p>
          <div class="folder-list">
            <div
              v-for="folder in folders"
              :key="folder.id"
              class="folder-list-item"
              :class="{ current: (moveTarget.folder_id || 'default') === folder.id }"
              @click="doMoveProject(folder.id)"
            >
              <span class="folder-list-emoji">{{ folder.emoji }}</span>
              <span class="folder-list-name">{{ folder.name }}</span>
              <span v-if="(moveTarget.folder_id || 'default') === folder.id" class="current-tag">当前</span>
            </div>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-ghost" @click="moveTarget = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/projects'
import { useTabsStore } from '../stores/tabs'

const router = useRouter()
const store = useProjectStore()
const tabsStore = useTabsStore()

const STEPS = { manuscript: '文案', scenes: '分镜', images: '图片', audio: '音频', video: '视频' }

const EMOJI_OPTIONS = [
  '📁','📂','🗂','📋','📌','📎','🎬','🎞','🎨','🎭',
  '🎵','🎪','🌟','⭐','🔥','💫','🎯','🚀','🌈','💡',
  '📚','🎮','🏆','💎','🌸','🍀','🎀','✨','🎙','🖼',
  '🎲','🧩','🏅','🎗','🌙','🍁',
]

// ── Folder state ───────────────────────────────────────────────────────────────

const DEFAULT_FOLDER = { id: 'default', name: '我的项目', emoji: '📁' }
const folders = ref([{ ...DEFAULT_FOLDER }])
const activeFolder = ref('default')
const expandedFolders = ref(new Set(['default']))
const sidebarCollapsed = ref(false)

function loadFolders() {
  try {
    const saved = localStorage.getItem('lumi-folders')
    if (saved) {
      const parsed = JSON.parse(saved)
      const rest = parsed.filter(f => f.id !== 'default')
      const def = parsed.find(f => f.id === 'default') || DEFAULT_FOLDER
      folders.value = [def, ...rest]
    }
  } catch {}
  try {
    const exp = localStorage.getItem('lumi-expanded-folders')
    if (exp) expandedFolders.value = new Set(JSON.parse(exp))
  } catch {}
  sidebarCollapsed.value = localStorage.getItem('lumi-sidebar-collapsed') === 'true'
}

// Called after projects are loaded — ensure all folder_ids referenced by projects exist in sidebar
function syncFoldersFromProjects() {
  const knownIds = new Set(folders.value.map(f => f.id))
  const missing = store.projects
    .map(p => p.folder_id || 'default')
    .filter(id => id !== 'default' && !knownIds.has(id))
  const uniqueMissing = [...new Set(missing)]
  if (uniqueMissing.length > 0) {
    for (const id of uniqueMissing) {
      folders.value.push({ id, name: id.replace(/^folder_\d+_?/, '') || id, emoji: '📁' })
    }
    saveFolders()
  }
}

function saveFolders() {
  localStorage.setItem('lumi-folders', JSON.stringify(folders.value))
  localStorage.setItem('lumi-sidebar-collapsed', String(sidebarCollapsed.value))
  localStorage.setItem('lumi-expanded-folders', JSON.stringify([...expandedFolders.value]))
}

const currentFolder = computed(() =>
  folders.value.find(f => f.id === activeFolder.value) || DEFAULT_FOLDER
)

// ── Folder dialog ──────────────────────────────────────────────────────────────

const showFolderDialog = ref(null) // 'create' | 'rename'
const folderName = ref('')
const folderEmoji = ref('📁')
const renameFolderTarget = ref(null)

function openCreateFolderDialog() {
  folderName.value = ''
  folderEmoji.value = '📁'
  renameFolderTarget.value = null
  showFolderDialog.value = 'create'
}

function startRenameFolder(folder) {
  renameFolderTarget.value = folder
  folderName.value = folder.name
  folderEmoji.value = folder.emoji
  showFolderDialog.value = 'rename'
}

function closeFolderDialog() {
  showFolderDialog.value = null
  folderName.value = ''
  folderEmoji.value = '📁'
  renameFolderTarget.value = null
}

function submitFolderDialog() {
  if (!folderName.value.trim()) return
  if (showFolderDialog.value === 'create') {
    const newFolder = {
      id: `folder_${Date.now()}`,
      name: folderName.value.trim(),
      emoji: folderEmoji.value,
    }
    folders.value.push(newFolder)
    activeFolder.value = newFolder.id
    expandedFolders.value.add(newFolder.id)
  } else {
    const idx = folders.value.findIndex(f => f.id === renameFolderTarget.value.id)
    if (idx !== -1) {
      folders.value[idx] = {
        ...folders.value[idx],
        name: folderName.value.trim(),
        emoji: folderEmoji.value,
      }
    }
  }
  saveFolders()
  closeFolderDialog()
}

function toggleFolderExpand(folderId) {
  if (expandedFolders.value.has(folderId)) {
    expandedFolders.value.delete(folderId)
  } else {
    expandedFolders.value.add(folderId)
  }
  activeFolder.value = folderId
  localStorage.setItem('lumi-expanded-folders', JSON.stringify([...expandedFolders.value]))
}

function projectsInFolder(folderId) {
  return store.projects.filter(p => (p.folder_id || 'default') === folderId)
}

// ── Delete folder ──────────────────────────────────────────────────────────────

const deleteFolderTarget = ref(null)

function confirmDeleteFolder(folder) {
  deleteFolderTarget.value = folder
}

async function doDeleteFolder() {
  const folderId = deleteFolderTarget.value.id
  const affected = store.projects.filter(p => (p.folder_id || 'default') === folderId)
  await Promise.all(affected.map(p => store.moveProject(p.id, 'default')))
  folders.value = folders.value.filter(f => f.id !== folderId)
  saveFolders()
  if (activeFolder.value === folderId) activeFolder.value = 'default'
  deleteFolderTarget.value = null
}

// ── Project state ──────────────────────────────────────────────────────────────

const searchQuery = ref('')
const showCreateDialog = ref(false)
const newName = ref('')
const newDesc = ref('')
const copyFromProjectId = ref('')
const activeMenu = ref(null)
const deleteTarget = ref(null)
const projectsDir = ref('')
const moveTarget = ref(null)
const renameTarget = ref(null)
const renameName = ref('')

const filteredProjects = computed(() =>
  store.projects.filter(p => {
    const fId = p.folder_id || 'default'
    if (fId !== activeFolder.value) return false
    return p.name.toLowerCase().includes(searchQuery.value.toLowerCase())
  })
)

function formatDate(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function isActive(progress, key) {
  const keys = Object.keys(STEPS)
  const idx = keys.indexOf(key)
  const val = progress?.[key] ?? 0
  return val > 0 && val < 100 || (idx > 0 && (progress?.[keys[idx - 1]] ?? 0) === 100 && val === 0)
}

function openProject(proj) {
  activeMenu.value = null
  tabsStore.openTab(proj.id, proj.name)
}

function playVideo(proj) {
  if (!proj.has_final_video || !projectsDir.value) return
  const base = projectsDir.value.replace(/[\\/]+$/, '')
  window.electronAPI?.openPath(`${base}/${proj.id}/video/final_video.mp4`)
}

function openFolder(proj) {
  if (!projectsDir.value) return
  const base = projectsDir.value.replace(/[\\/]+$/, '')
  window.electronAPI?.showItemInFolder(`${base}/${proj.id}`)
}

function toggleMenu(id) {
  activeMenu.value = activeMenu.value === id ? null : id
}

function confirmDelete(proj) {
  activeMenu.value = null
  deleteTarget.value = proj
}

async function doDelete() {
  await store.deleteProject(deleteTarget.value.id)
  deleteTarget.value = null
}

async function createProject() {
  if (!newName.value.trim()) return
  const proj = await store.createProject(newName.value.trim(), newDesc.value.trim(), activeFolder.value)
  if (copyFromProjectId.value) {
    try {
      await fetch(`http://127.0.0.1:18520/api/projects/${proj.id}/copy-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_project_id: copyFromProjectId.value }),
      })
    } catch {}
  }
  showCreateDialog.value = false
  newName.value = ''
  newDesc.value = ''
  copyFromProjectId.value = ''
  tabsStore.openTab(proj.id, proj.name)
}

function startRenameProject(proj) {
  activeMenu.value = null
  renameTarget.value = proj
  renameName.value = proj.name
}

async function doRenameProject() {
  if (!renameName.value.trim() || !renameTarget.value) return
  await store.renameProject(renameTarget.value.id, renameName.value.trim())
  renameTarget.value = null
}

function startMoveProject(proj) {
  activeMenu.value = null
  moveTarget.value = proj
}

async function doMoveProject(folderId) {
  if ((moveTarget.value.folder_id || 'default') !== folderId) {
    await store.moveProject(moveTarget.value.id, folderId)
  }
  moveTarget.value = null
}

function refresh() { store.fetchProjects() }

watch(sidebarCollapsed, val => {
  localStorage.setItem('lumi-sidebar-collapsed', String(val))
})

function onDocClick() { activeMenu.value = null }

onMounted(async () => {
  loadFolders()
  await store.fetchProjects()
  syncFoldersFromProjects()
  document.addEventListener('click', onDocClick)
  window.electronAPI?.onMenuNewProject(() => { showCreateDialog.value = true })
  try {
    const res = await fetch('http://127.0.0.1:18520/api/settings')
    const cfg = await res.json()
    projectsDir.value = cfg.projects_dir || ''
  } catch {}
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  window.electronAPI?.removeAllListeners('menu:new-project')
})
</script>

<style scoped>
.home-layout { display: flex; height: 100%; overflow: hidden; }

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex; flex-direction: column; flex-shrink: 0;
  transition: width 0.2s ease;
}
.sidebar.collapsed { width: 52px; }
.sidebar-header {
  padding: 12px 8px;
  border-bottom: 1px solid var(--color-border);
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
  min-height: 49px;
}
.sidebar-logo { font-size: 14px; font-weight: 700; color: var(--color-accent); white-space: nowrap; overflow: hidden; }
.sidebar-toggle {
  flex-shrink: 0; width: 24px; height: 24px; border-radius: 6px; border: none;
  background: transparent; cursor: pointer; font-size: 11px;
  color: var(--color-text-muted); display: flex; align-items: center; justify-content: center;
  transition: background var(--transition), color var(--transition);
}
.sidebar-toggle:hover { background: var(--color-surface-2); color: var(--color-text); }
.sidebar.collapsed .sidebar-header { justify-content: center; }
.sidebar-nav { flex: 1; padding: 8px; display: flex; flex-direction: column; overflow-y: auto; }
.sidebar-footer { padding: 12px; border-top: 1px solid var(--color-border); display: flex; justify-content: center; }
.sidebar-settings-icon {
  width: 32px; height: 32px; border-radius: var(--radius); border: none;
  background: transparent; cursor: pointer; font-size: 16px;
  color: var(--color-text-muted); display: flex; align-items: center; justify-content: center;
  transition: background var(--transition), color var(--transition);
}
.sidebar-settings-icon:hover { background: var(--color-surface-2); color: var(--color-text); }

/* Collapsed folder icons */
.folders-section--collapsed { display: flex; flex-direction: column; align-items: center; gap: 4px; padding-top: 4px; }
.folder-icon-pill {
  width: 36px; height: 36px; border-radius: var(--radius);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; cursor: pointer;
  transition: background var(--transition);
}
.folder-icon-pill:hover { background: var(--color-surface-2); }
.folder-icon-pill.active { background: var(--color-surface-2); box-shadow: inset 2px 0 0 var(--color-accent); }

/* Folder list */
.folders-section { flex: 1; }
.folder-item {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 10px; border-radius: var(--radius);
  cursor: pointer; font-size: 13px; color: var(--color-text-muted);
  transition: background var(--transition), color var(--transition);
  position: relative;
  user-select: none;
}
.folder-item:hover, .folder-item.active {
  background: var(--color-surface-2); color: var(--color-text);
}
.folder-expand-arrow {
  font-size: 9px; flex-shrink: 0; color: var(--color-text-muted);
  transition: transform 0.15s ease;
  display: inline-block;
}
.folder-expand-arrow.open { transform: rotate(90deg); }
.folder-emoji { font-size: 15px; flex-shrink: 0; }
.folder-count { font-size: 11px; flex-shrink: 0; }
.folder-name { flex: 1; min-width: 0; }

/* Project sub-list */
.folder-projects {
  padding: 2px 0 4px 28px;
  display: flex; flex-direction: column; gap: 1px;
}
.sidebar-project-item {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 8px; border-radius: var(--radius);
  cursor: pointer; font-size: 12px; color: var(--color-text-muted);
  transition: background var(--transition), color var(--transition);
}
.sidebar-project-item:hover { background: var(--color-surface-2); color: var(--color-text); }
.sidebar-project-icon { font-size: 13px; flex-shrink: 0; }
.sidebar-project-name { flex: 1; min-width: 0; }
.sidebar-project-empty { font-size: 11px; color: var(--color-text-muted); padding: 4px 8px; font-style: italic; }

/* Folder action buttons (hidden until hover) */
.folder-actions {
  display: flex; gap: 2px; opacity: 0;
  transition: opacity var(--transition);
  flex-shrink: 0;
}
.folder-item:hover .folder-actions { opacity: 1; }
.folder-action-btn {
  width: 22px; height: 22px; border-radius: 4px; border: none;
  background: transparent; cursor: pointer; font-size: 11px;
  color: var(--color-text-muted); display: flex; align-items: center; justify-content: center;
  transition: background var(--transition), color var(--transition);
}
.folder-action-btn:hover { background: var(--color-border); color: var(--color-text); }
.folder-action-btn.danger:hover { background: var(--color-error); color: #fff; }

/* Add folder button */
.add-folder-btn {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 8px 10px; margin-top: 4px;
  background: transparent; border: 1px dashed var(--color-border);
  border-radius: var(--radius); color: var(--color-text-muted);
  cursor: pointer; font-size: 12px; text-align: left;
  transition: border-color var(--transition), color var(--transition);
}
.add-folder-btn:hover { border-color: var(--color-accent); color: var(--color-accent); }

/* Main */
.main-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid var(--color-border); flex-shrink: 0;
}
.toolbar-title { font-size: 18px; font-weight: 700; }
.toolbar-actions { display: flex; gap: 10px; align-items: center; }
.search-input { width: 220px; }

/* Grid */
.project-grid {
  flex: 1; padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
  overflow-y: auto;
  align-content: start;
}
.project-card {
  cursor: pointer; transition: border-color var(--transition), transform var(--transition);
  position: relative;
}
.project-card:hover { border-color: var(--color-accent); transform: translateY(-2px); }
.project-card-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.project-icon { font-size: 28px; }
.project-name { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.project-desc { font-size: 12px; margin-bottom: 10px; }
.project-meta { font-size: 11px; margin-bottom: 10px; }
.project-progress { display: flex; gap: 4px; margin-bottom: 4px; }
.progress-step {
  flex: 1; height: 4px; border-radius: 2px; background: var(--color-border);
  transition: background var(--transition);
}
.progress-step.done { background: var(--color-success); }
.progress-step.active { background: var(--color-accent); }
.project-progress-labels { display: flex; gap: 4px; margin-bottom: 10px; }
.progress-label { flex: 1; font-size: 10px; text-align: center; }

/* Card action buttons */
.project-card-actions {
  display: flex; gap: 6px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px; margin-top: 2px;
}
.card-action-btn {
  flex: 1; padding: 5px 0; font-size: 12px; font-weight: 500;
  border-radius: var(--radius); border: 1px solid var(--color-border);
  background: transparent; color: var(--color-text-muted);
  cursor: pointer; transition: background var(--transition), color var(--transition), border-color var(--transition);
}
.card-action-btn:disabled { opacity: 0.38; cursor: not-allowed; }
.card-action-btn:not(:disabled):hover { background: var(--color-surface-2); color: var(--color-text); }
.card-action-btn--active { border-color: var(--color-accent); color: var(--color-accent); }
.card-action-btn--active:not(:disabled):hover { background: var(--color-accent); color: #fff; }

/* Context menu */
.project-menu-trigger { position: relative; }
.context-menu {
  position: absolute; right: 0; top: 100%; z-index: 100;
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: var(--radius); min-width: 120px; overflow: hidden;
}
.ctx-item { padding: 8px 14px; cursor: pointer; font-size: 13px; }
.ctx-item:hover { background: var(--color-border); }
.ctx-item.danger { color: var(--color-error); }

/* Empty state */
.empty-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px;
  color: var(--color-text-muted);
}
.empty-icon { font-size: 56px; }

/* Spinner */
.spinner {
  width: 32px; height: 32px; border-radius: 50%;
  border: 3px solid var(--color-border); border-top-color: var(--color-accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Dialogs */
/* Dialogs — base styles are in global.css */
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--color-text-muted); }
.required { color: var(--color-error); }
.textarea { resize: vertical; min-height: 72px; }

/* Emoji picker */
.emoji-picker {
  display: flex; flex-wrap: wrap; gap: 4px;
  padding: 8px; background: var(--color-surface-2);
  border-radius: var(--radius); border: 1px solid var(--color-border);
}
.emoji-btn {
  width: 34px; height: 34px; border-radius: 6px; border: 2px solid transparent;
  background: transparent; cursor: pointer; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  transition: background var(--transition), border-color var(--transition);
}
.emoji-btn:hover { background: var(--color-border); }
.emoji-btn.selected { border-color: var(--color-accent); background: var(--color-surface); }

/* Move to folder list */
.folder-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 4px; }
.folder-list-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: var(--radius);
  border: 1px solid var(--color-border); cursor: pointer;
  transition: background var(--transition), border-color var(--transition);
}
.folder-list-item:hover { background: var(--color-surface-2); border-color: var(--color-accent); }
.folder-list-item.current { background: var(--color-surface-2); opacity: 0.6; cursor: default; }
.folder-list-emoji { font-size: 18px; }
.folder-list-name { flex: 1; font-size: 14px; }
.current-tag {
  font-size: 11px; padding: 2px 6px;
  background: var(--color-accent); color: #fff; border-radius: 10px;
}
</style>
