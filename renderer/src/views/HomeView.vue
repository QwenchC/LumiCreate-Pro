<template>
  <div class="home-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <span class="sidebar-logo">✦ LumiCreate</span>
      </div>
      <nav class="sidebar-nav">
        <button class="nav-item active">
          <span class="nav-icon">📁</span> 我的项目
        </button>
      </nav>
      <div class="sidebar-footer">
        <button class="btn btn-ghost btn-sm" @click="$router.push('/settings')">
          ⚙ 引擎设置
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content">
      <!-- Toolbar -->
      <div class="toolbar">
        <h2 class="toolbar-title">我的项目</h2>
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
        </div>
      </div>
    </main>

    <!-- Create project dialog -->
    <Teleport to="body">
      <div v-if="showCreateDialog" class="overlay" @click.self="showCreateDialog = false">
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
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!newName.trim()" @click="createProject">创建</button>
            <button class="btn btn-ghost" @click="showCreateDialog = false">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete confirm -->
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/projects'

const router = useRouter()
const store = useProjectStore()

const STEPS = { manuscript: '文案', scenes: '分镜', images: '图片', audio: '音频', video: '视频' }

const searchQuery = ref('')
const showCreateDialog = ref(false)
const newName = ref('')
const newDesc = ref('')
const activeMenu = ref(null)
const deleteTarget = ref(null)

const filteredProjects = computed(() =>
  store.projects.filter(p =>
    p.name.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
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
  router.push(`/project/${proj.id}`)
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
  const proj = await store.createProject(newName.value.trim(), newDesc.value.trim())
  showCreateDialog.value = false
  newName.value = ''
  newDesc.value = ''
  router.push(`/project/${proj.id}`)
}

function refresh() { store.fetchProjects() }

// Close context menu on outside click
function onDocClick() { activeMenu.value = null }
onMounted(() => {
  store.fetchProjects()
  document.addEventListener('click', onDocClick)
  window.electronAPI?.onMenuNewProject(() => { showCreateDialog.value = true })
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
}
.sidebar-header { padding: 16px; border-bottom: 1px solid var(--color-border); }
.sidebar-logo { font-size: 16px; font-weight: 700; color: var(--color-accent); }
.sidebar-nav { flex: 1; padding: 12px 8px; }
.nav-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 9px 12px; border-radius: var(--radius);
  background: transparent; border: none; color: var(--color-text-muted);
  cursor: pointer; font-size: 13px; transition: background var(--transition);
}
.nav-item.active, .nav-item:hover { background: var(--color-surface-2); color: var(--color-text); }
.nav-icon { font-size: 16px; }
.sidebar-footer { padding: 12px; border-top: 1px solid var(--color-border); }

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
.project-progress-labels { display: flex; gap: 4px; }
.progress-label { flex: 1; font-size: 10px; text-align: center; }

/* Context menu */
.project-menu-trigger { position: relative; }
.context-menu {
  position: absolute; right: 0; top: 100%; z-index: 100;
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: var(--radius); min-width: 100px; overflow: hidden;
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
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 9999;
}
.dialog { max-width: 420px; width: 90%; }
.dialog-title { font-size: 16px; margin-bottom: 16px; }
.dialog-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--color-text-muted); }
.required { color: var(--color-error); }
.textarea { resize: vertical; min-height: 72px; }
</style>
