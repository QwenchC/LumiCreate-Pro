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

          <!-- v1.6.2: 系列连载（后端实体，点击进专属页：章节文案 + 共享角色） -->
          <div class="series-section">
            <div class="series-section-title">
              📚 系列连载
              <span class="series-section-hint">共用角色/立绘</span>
            </div>
            <div
              v-for="s in seriesList"
              :key="s.id"
              class="folder-item series-item"
              :title="s.name + '（系列连载 · 点击进入）'"
              @click="openSeries(s)"
            >
              <span class="folder-emoji">{{ s.emoji || '📚' }}</span>
              <span class="folder-name truncate">{{ s.name }}</span>
              <span class="series-tag">连载</span>
              <div class="folder-actions" @click.stop>
                <button class="folder-action-btn danger" title="删除系列（需先清空其项目）"
                        @click.stop="confirmDeleteSeries(s)">✕</button>
              </div>
            </div>
            <div v-if="!seriesList.length" class="sidebar-project-empty">还没有连载系列</div>
          </div>
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
            <div v-if="seriesList.length" class="collapsed-divider"></div>
            <div
              v-for="s in seriesList"
              :key="s.id"
              class="folder-icon-pill series-pill"
              :title="s.name + '（系列连载）'"
              @click="openSeries(s)"
            >{{ s.emoji || '📚' }}</div>
          </div>
        </template>
      </nav>
      <button v-if="!sidebarCollapsed" class="add-folder-btn" @click="openCreateFolderDialog">
        + 新建文件夹 / 系列连载
      </button>

      <!-- B3: 模板区 -->
      <div v-if="!sidebarCollapsed && templates.length" class="templates-section">
        <div class="templates-title">📦 项目模板</div>
        <div v-for="t in templates" :key="t.id" class="template-pill">
          <span class="template-name truncate" :title="t.description || t.name">{{ t.name }}</span>
          <button class="template-btn" title="用此模板新建项目" @click="newFromTemplate(t)">＋</button>
          <button class="template-btn danger" title="删除模板" @click="confirmDeleteTemplate(t)">✕</button>
        </div>
      </div>
      <div class="sidebar-footer" :class="{ collapsed: sidebarCollapsed }">
        <button class="sidebar-footer-btn" title="全局元素库"
                @click="globalElementsOpen = true">
          <span class="sidebar-footer-icon">📦</span>
          <span v-if="!sidebarCollapsed" class="sidebar-footer-label">元素库</span>
        </button>
        <button class="sidebar-footer-btn" title="音乐库"
                @click="globalMusicOpen = true">
          <span class="sidebar-footer-icon">🎵</span>
          <span v-if="!sidebarCollapsed" class="sidebar-footer-label">音乐库</span>
        </button>
        <button class="sidebar-footer-btn" title="任务历史"
                @click="taskHistoryOpen = true">
          <span class="sidebar-footer-icon">📊</span>
          <span v-if="!sidebarCollapsed" class="sidebar-footer-label">任务历史</span>
        </button>
        <button class="sidebar-footer-btn" title="引擎设置"
                @click="$router.push('/settings')">
          <span class="sidebar-footer-icon">⚙</span>
          <span v-if="!sidebarCollapsed" class="sidebar-footer-label">设置</span>
        </button>
      </div>
    </aside>

    <!-- E2: 任务历史弹层 -->
    <TaskHistoryPanel v-if="taskHistoryOpen" @close="taskHistoryOpen = false" />

    <!-- 轮 3: 全局元素库弹层 -->
    <GlobalElementsPanel v-if="globalElementsOpen" @close="globalElementsOpen = false" />

    <!-- v1.4.2: 全局音乐库弹层 -->
    <GlobalMusicPanel v-if="globalMusicOpen" @close="globalMusicOpen = false" />

    <!-- Main content -->
    <main class="main-content">
      <!-- Toolbar -->
      <div class="toolbar">
        <h2 class="toolbar-title">
          {{ currentFolder.emoji }} {{ currentFolder.name }}
          <span v-if="searchQuery" class="text-muted" style="font-size:13px;font-weight:normal;margin-left:8px">
            · 全局搜索 "{{ searchQuery }}" · {{ filteredProjects.length }} 个结果
          </span>
        </h2>
        <div class="toolbar-actions">
          <input ref="searchInputEl" v-model="searchQuery" class="input search-input" placeholder="搜索项目 (Ctrl+F)" />
          <select v-model="sortMode" class="input select-compact" style="width:120px" title="排序方式">
            <option value="updated_desc">最近更新</option>
            <option value="created_desc">最新创建</option>
            <option value="name">按名字</option>
          </select>
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
            <select v-model="copyFromProjectId" class="input" :disabled="!!fromTemplateId">
              <option value="">不复制，从空白开始</option>
              <option v-for="p in store.projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <p v-if="copyFromProjectId" class="field-hint" style="margin-top:4px;font-size:11px;color:var(--color-text-muted);opacity:0.7">将从该项目复制角色列表与文案配置（世界观、角色设定等），不复制文案内容和分镜。</p>
          </div>
          <div class="form-group">
            <label>📦 从模板新建（可选，二选一）</label>
            <select v-model="fromTemplateId" class="input" :disabled="!!copyFromProjectId">
              <option value="">不使用模板</option>
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}{{ t.description ? '（' + t.description + '）' : '' }}</option>
            </select>
            <p v-if="fromTemplateId" class="field-hint" style="margin-top:4px;font-size:11px;color:var(--color-text-muted);opacity:0.7">将拷贝模板的对白模式 + 角色卡（含 voice / appearance）；引擎设置仍使用全局值。</p>
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
          <div v-if="showFolderDialog === 'create'" class="form-group">
            <label>类型</label>
            <div class="ftype-picker">
              <button class="ftype-btn" :class="{ selected: folderType === 'normal' }"
                      @click="folderType = 'normal'">
                📁 普通文件夹
                <span class="ftype-desc">仅用于归类项目</span>
              </button>
              <button class="ftype-btn" :class="{ selected: folderType === 'series' }"
                      @click="folderType = 'series'; folderEmoji = (folderEmoji==='📁' ? '📚' : folderEmoji)">
                📚 系列连载
                <span class="ftype-desc">各集共用角色/立绘 + 章节文案</span>
              </button>
            </div>
          </div>
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
            <label>{{ folderType === 'series' && showFolderDialog === 'create' ? '系列名称' : '文件夹名称' }} <span class="required">*</span></label>
            <input v-model="folderName" class="input"
                   :placeholder="folderType === 'series' && showFolderDialog === 'create' ? '例：我的连载剧 第一季' : '例：短视频项目'"
                   @keyup.enter="submitFolderDialog" />
            <p v-if="folderType === 'series' && showFolderDialog === 'create'" class="field-hint"
               style="margin-top:6px;font-size:11px;color:var(--color-text-muted);opacity:0.8">
              创建后将进入「系列专属页」：在那里管理章节文案、新建各集项目；同系列各集自动共用角色与立绘。
            </p>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!folderName.trim() || creatingSeries" @click="submitFolderDialog">
              {{ creatingSeries ? '创建中…' : (showFolderDialog === 'create' ? '创建' : '保存') }}
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
import TaskHistoryPanel from '../components/TaskHistoryPanel.vue'
import GlobalElementsPanel from '../components/GlobalElementsPanel.vue'
import GlobalMusicPanel from '../components/GlobalMusicPanel.vue'

const router = useRouter()
const store = useProjectStore()
const tabsStore = useTabsStore()
void router    // 模板里通过 $router 访问，避免编译器把 router 视为未用

// E2: 任务历史弹层
const taskHistoryOpen = ref(false)
// 轮 3: 全局元素库
const globalElementsOpen = ref(false)
// v1.4.2: 全局音乐库
const globalMusicOpen = ref(false)

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
const folderType = ref('normal')   // v1.6.2: 'normal' | 'series'
const creatingSeries = ref(false)
const renameFolderTarget = ref(null)

function openCreateFolderDialog() {
  folderName.value = ''
  folderEmoji.value = '📁'
  folderType.value = 'normal'
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
  folderType.value = 'normal'
  renameFolderTarget.value = null
}

async function submitFolderDialog() {
  if (!folderName.value.trim()) return
  // v1.6.2: 系列连载 → 创建后端系列实体，进入专属页
  if (showFolderDialog.value === 'create' && folderType.value === 'series') {
    if (creatingSeries.value) return
    creatingSeries.value = true
    try {
      const r = await fetch('http://127.0.0.1:18520/api/series', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: folderName.value.trim(), emoji: folderEmoji.value || '📚' }),
      })
      if (!r.ok) throw new Error(await r.text())
      const s = await r.json()
      await loadSeries()
      closeFolderDialog()
      router.push(`/series/${s.id}`)
    } catch (e) {
      alert('创建系列失败: ' + (e?.message || e))
    } finally {
      creatingSeries.value = false
    }
    return
  }
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

// ── v1.6.2: 系列连载 ──────────────────────────────────────────────────────────────

const seriesList = ref([])

async function loadSeries() {
  try {
    const r = await fetch('http://127.0.0.1:18520/api/series')
    if (r.ok) seriesList.value = await r.json()
  } catch {}
}

function openSeries(s) {
  router.push(`/series/${s.id}`)
}

async function confirmDeleteSeries(s) {
  if (!confirm(`删除系列「${s.name}」？\n（仅当该系列下没有项目时可删除；共享角色池也会一并清除）`)) return
  try {
    const r = await fetch(`http://127.0.0.1:18520/api/series/${s.id}`, { method: 'DELETE' })
    if (r.status === 409) { alert('该系列下仍有项目，请先删除/移出这些项目再删除系列。'); return }
    if (!r.ok && r.status !== 204) throw new Error(await r.text())
    await loadSeries()
  } catch (e) {
    alert('删除系列失败: ' + (e?.message || e))
  }
}

// ── Project state ──────────────────────────────────────────────────────────────

const searchQuery = ref('')
const searchInputEl = ref(null)
const showCreateDialog = ref(false)
const newName = ref('')
const newDesc = ref('')
const copyFromProjectId = ref('')
const fromTemplateId    = ref('')
const templates         = ref([])

async function reloadTemplates() {
  try {
    const r = await fetch('http://127.0.0.1:18520/api/templates')
    if (r.ok) templates.value = await r.json()
  } catch {}
}

async function newFromTemplate(t) {
  fromTemplateId.value = t.id
  copyFromProjectId.value = ''
  newName.value = t.name + ' - 新建'
  showCreateDialog.value = true
}

async function confirmDeleteTemplate(t) {
  if (!confirm(`删除模板「${t.name}」？项目本身不受影响。`)) return
  try {
    await fetch(`http://127.0.0.1:18520/api/templates/${t.id}`, { method: 'DELETE' })
    await reloadTemplates()
  } catch (e) { alert('删除模板失败: ' + e.message) }
}
const activeMenu = ref(null)
const deleteTarget = ref(null)
const projectsDir = ref('')
const moveTarget = ref(null)
const renameTarget = ref(null)
const renameName = ref('')

const sortMode = ref('updated_desc')   // updated_desc | name | created_desc

const filteredProjects = computed(() => {
  const q = (searchQuery.value || '').trim().toLowerCase()
  let list = store.projects.filter(p => {
    const fId = p.folder_id || 'default'
    // 搜索非空时跨文件夹搜（点击侧栏文件夹仍想缩小范围 → 留个开关：仍按文件夹过滤）
    if (!q && fId !== activeFolder.value) return false
    if (q) {
      const name = (p.name || '').toLowerCase()
      const desc = (p.description || '').toLowerCase()
      if (!name.includes(q) && !desc.includes(q)) return false
    }
    return true
  })
  // 排序
  list = [...list]
  switch (sortMode.value) {
    case 'name':
      list.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'zh-CN'))
      break
    case 'created_desc':
      list.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      break
    default:
      list.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
  }
  return list
})

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
  } else if (fromTemplateId.value) {
    // B3: 应用模板（POST templates/{id}/apply）
    try {
      await fetch(`http://127.0.0.1:18520/api/templates/${fromTemplateId.value}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: proj.id }),
      })
    } catch {}
  }
  showCreateDialog.value = false
  newName.value = ''
  newDesc.value = ''
  copyFromProjectId.value = ''
  fromTemplateId.value = ''
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

// B5: 主屏快捷键
//   Ctrl+F   → 聚焦搜索框
//   Ctrl+N   → 新建项目
//   Esc      → 清空搜索 / 关闭对话框
function onHomeKey(e) {
  const tag = (e.target?.tagName || '').toLowerCase()
  const inField = tag === 'input' || tag === 'textarea' || e.target?.isContentEditable
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
    e.preventDefault()
    searchInputEl.value?.focus?.()
    searchInputEl.value?.select?.()
  } else if ((e.ctrlKey || e.metaKey) && e.key === 'n' && !inField) {
    e.preventDefault()
    showCreateDialog.value = true
  } else if (e.key === 'Escape' && !inField) {
    if (showCreateDialog.value) showCreateDialog.value = false
    else if (searchQuery.value) searchQuery.value = ''
  }
}

onMounted(async () => {
  loadFolders()
  await store.fetchProjects()
  syncFoldersFromProjects()
  await reloadTemplates()
  await loadSeries()
  document.addEventListener('click', onDocClick)
  window.addEventListener('keydown', onHomeKey)
  window.electronAPI?.onMenuNewProject(() => { showCreateDialog.value = true })
  try {
    const res = await fetch('http://127.0.0.1:18520/api/settings')
    const cfg = await res.json()
    projectsDir.value = cfg.projects_dir || ''
  } catch {}
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('keydown', onHomeKey)
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
/* v1.4.2: 侧边栏底部按钮 — 2×2 紧凑布局，展开时显示图标 + 短文字，收起时仅图标 */
.sidebar-footer {
  padding: 8px;
  border-top: 1px solid var(--color-border);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}
.sidebar-footer.collapsed {
  grid-template-columns: 1fr;
  padding: 6px 4px;
}
.sidebar-footer-btn {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 6px 8px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  transition: background var(--transition), color var(--transition), border-color var(--transition);
  min-width: 0;
  white-space: nowrap;
}
.sidebar-footer-btn:hover {
  background: var(--color-surface-2);
  color: var(--color-text);
  border-color: var(--color-border);
}
.sidebar-footer-icon { font-size: 15px; line-height: 1; flex-shrink: 0; }
.sidebar-footer-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-footer.collapsed .sidebar-footer-btn { padding: 6px 0; }

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

/* v1.6.2: 系列连载区 */
.series-section { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--color-border); }
.series-section-title {
  font-size: 11px; color: var(--color-text-muted); padding: 2px 10px 6px;
  display: flex; align-items: baseline; gap: 6px;
  text-transform: none; letter-spacing: 0.3px;
}
.series-section-hint { font-size: 10px; opacity: 0.6; }
.series-item .folder-emoji { font-size: 15px; }
.series-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 9px; flex-shrink: 0;
  background: rgba(178,102,255,.15); color: #b794f4;
}
.series-item:hover .series-tag { background: rgba(178,102,255,.25); }
.series-pill { box-shadow: inset 2px 0 0 #b794f4; }
.collapsed-divider { width: 24px; height: 1px; background: var(--color-border); margin: 6px 0; }

/* v1.6.2: 文件夹类型选择 */
.ftype-picker { display: flex; gap: 8px; }
.ftype-btn {
  flex: 1; display: flex; flex-direction: column; gap: 3px;
  padding: 10px 8px; border-radius: var(--radius);
  border: 2px solid var(--color-border); background: var(--color-surface-2);
  cursor: pointer; font-size: 13px; color: var(--color-text); text-align: left;
  transition: border-color var(--transition), background var(--transition);
}
.ftype-btn:hover { border-color: var(--color-accent); }
.ftype-btn.selected { border-color: var(--color-accent); background: var(--color-surface); }
.ftype-desc { font-size: 10px; color: var(--color-text-muted); }

/* Add folder button */
.add-folder-btn {
  display: flex; align-items: center; gap: 6px;
  width: calc(100% - 16px); margin: 0 8px 8px;
  padding: 8px 10px; flex-shrink: 0;
  background: transparent; border: 1px dashed var(--color-border);
  border-radius: var(--radius); color: var(--color-text-muted);
  cursor: pointer; font-size: 12px; text-align: left;
  transition: border-color var(--transition), color var(--transition);
}
.add-folder-btn:hover { border-color: var(--color-accent); color: var(--color-accent); }

/* B3: 模板区 */
.templates-section { padding: 8px 12px 12px; border-top: 1px solid var(--color-border); margin-top: 4px; }
.templates-title { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.template-pill {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 6px; border-radius: 4px; font-size: 12px;
  background: var(--color-surface-2);
  margin-bottom: 4px;
}
.template-pill:hover { background: var(--color-border); }
.template-name { flex: 1; min-width: 0; }
.template-btn {
  background: none; border: none; cursor: pointer; opacity: .5;
  color: var(--color-text); font-size: 13px; padding: 0 4px;
}
.template-btn:hover { opacity: 1; }
.template-btn.danger:hover { color: var(--color-error); }

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
  flex: 1;
  /* v1.4.9 修复：原本 padding: 20px 让滚动条紧贴窗口右边，拖动时
   * 容易蹭到 Electron 的 resize 命中区（Win 默认 ~6-8px）触发缩放。
   * 拆开成 上 / 右 / 下 / 左 —— 右内边距 12 + 右外边距 10 = 卡片右侧
   * 仍是 22px 视觉留白（原 20），滚动条则被推离窗口边 10px。 */
  padding: 20px 12px 20px 20px;
  margin-right: 10px;
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
