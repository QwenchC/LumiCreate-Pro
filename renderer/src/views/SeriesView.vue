<template>
  <div class="series-view">
    <!-- Header -->
    <div class="series-header">
      <button class="btn btn-ghost btn-sm" @click="goHome">← 返回</button>
      <span class="series-emoji">{{ series.emoji || '📚' }}</span>
      <input class="series-name-input" v-model="series.name" @change="saveSeriesName"
             placeholder="系列名称" />
      <span class="series-badge">系列连载</span>
      <span class="flex-spacer"></span>
      <button class="btn btn-primary btn-sm" @click="openNewProject">＋ 新建本系列项目</button>
    </div>

    <p class="series-note">
      💡 本系列下所有项目【共用角色管理（含立绘）】；在任意一集的「角色管理」里改角色/加立绘，
      其余各集立即同步。新建项目时可从下方文案章节勾选导入。
    </p>

    <div class="series-body">
      <!-- 左：文案章节管理 -->
      <section class="series-col chapters-col">
        <div class="col-head">
          <h3>📖 文案章节管理</h3>
          <button class="btn btn-secondary btn-xs" @click="addChapter">＋ 新增章节</button>
        </div>
        <div v-if="!chapters.length" class="empty-hint">还没有章节。点「＋ 新增章节」开始整理连载文案。</div>
        <div v-for="(ch, i) in chapters" :key="ch.id" class="chapter-card"
             :class="{ active: editingId === ch.id }">
          <div class="chapter-head" @click="toggleEdit(ch)">
            <span class="chapter-idx">{{ i + 1 }}</span>
            <input class="chapter-title" v-model="ch.title" @click.stop
                   @change="saveChapter(ch)" placeholder="章节标题" />
            <span v-if="ch.used_by && ch.used_by.length" class="chapter-used"
                  :title="'已用于：' + ch.used_by.map(u => epLabel(u)).join('、')">
              已用于 {{ ch.used_by.map(u => epLabel(u)).join('、') }}
            </span>
            <span class="chapter-len text-muted">{{ (ch.content || '').length }} 字</span>
            <button class="btn btn-ghost btn-xs" @click.stop="delChapter(ch)" title="删除章节">✕</button>
            <span class="chapter-arrow">{{ editingId === ch.id ? '▲' : '▼' }}</span>
          </div>
          <textarea v-if="editingId === ch.id" class="chapter-content" v-model="ch.content"
                    @change="saveChapter(ch)" rows="10"
                    placeholder="粘贴/编辑该章节的文案内容…"></textarea>
        </div>
      </section>

      <!-- 右：本系列项目 -->
      <section class="series-col projects-col">
        <div class="col-head">
          <h3>🎦 本系列项目</h3>
          <button class="btn btn-secondary btn-xs" @click="sortAsc = !sortAsc"
                  :title="sortAsc ? '当前正序（第1集在上），点击切换逆序' : '当前逆序（最新集在上），点击切换正序'">
            {{ sortAsc ? '↑ 正序' : '↓ 逆序' }}
          </button>
        </div>
        <div v-if="!episodes.length" class="empty-hint">还没有项目。点右上「＋ 新建本系列项目」创建第一集。</div>
        <div v-for="e in displayedEpisodes" :key="e.no" class="proj-card"
             :class="{ 'proj-blank': e.blank, 'proj-clickable': !e.blank }"
             @click="openEpisode(e)">
          <span class="ep-no">第{{ e.no }}集</span>
          <template v-if="!e.blank">
            <span class="proj-name truncate">：{{ e.project_name }}</span>
            <span class="proj-time text-muted">{{ fmtTime(e.updated_at) }}</span>
            <button class="btn btn-ghost btn-xs ep-del" @click.stop="askDeleteEpisode(e)"
                    title="删除此集">✕</button>
          </template>
          <template v-else>
            <span class="proj-name proj-blank-label">：（空白集 · 占位）</span>
            <button class="btn btn-ghost btn-xs ep-del" @click.stop="removeBlank(e)"
                    title="删除空白集（后续集 -1）">✕</button>
          </template>
        </div>
      </section>
    </div>

    <!-- 新建本系列项目对话框 -->
    <div v-if="newDialog.show" class="overlay" @click.self="!newDialog.creating && (newDialog.show = false)">
      <div class="dialog card" style="width:560px;max-width:calc(100vw - 40px)">
        <h3 class="dialog-title">＋ 新建本系列项目</h3>
        <div class="form-group">
          <label>项目名称（集数名）</label>
          <input class="input" v-model="newDialog.name" placeholder="如：第 1 集" />
        </div>
        <div class="form-group">
          <label>导入文案章节（可多选）</label>
          <div v-if="!chapters.length" class="text-muted" style="font-size:12px">暂无章节，可创建后再补</div>
          <div v-for="ch in chapters" :key="ch.id" class="chapter-pick"
               :class="{ picked: newDialog.picked.includes(ch.id) }"
               @click="togglePick(ch.id)">
            <input type="checkbox" :checked="newDialog.picked.includes(ch.id)" @click.prevent />
            <span class="cp-title truncate">{{ ch.title || '(未命名章节)' }}</span>
            <span class="cp-len text-muted">{{ (ch.content || '').length }}字</span>
            <span v-if="ch.used_by && ch.used_by.length" class="cp-used"
                  title="已被其它集用过，避免重复选用">
              ⚠ 已用于 {{ ch.used_by.map(u => epLabel(u)).join('、') }}
            </span>
          </div>
          <p class="field-hint">勾选的章节会按顺序拼接导入到该项目「文案创建」。已用于其它项目的章节标黄提示，避免误选。</p>
        </div>
        <div v-if="newDialog.error" class="error-banner">⚠ {{ newDialog.error }}</div>
        <div class="dialog-actions">
          <button class="btn btn-ghost" :disabled="newDialog.creating" @click="newDialog.show = false">取消</button>
          <button class="btn btn-primary" :disabled="newDialog.creating || !newDialog.name.trim()"
                  @click="createSeriesProject">
            {{ newDialog.creating ? '创建中…' : '创建并打开' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 删除中间集：策略二选一对话框 -->
    <div v-if="delDialog.show" class="overlay" @click.self="!delDialog.busy && (delDialog.show = false)">
      <div class="dialog card" style="width:480px;max-width:calc(100vw - 40px)">
        <h3 class="dialog-title">删除「第{{ delDialog.no }}集：{{ delDialog.name }}」</h3>
        <p class="text-muted" style="font-size:13px;line-height:1.6;margin-bottom:12px">
          这是<strong>中间集</strong>。删除后，后续各集的集号如何处理？
        </p>
        <div class="del-choices">
          <button class="del-choice" :disabled="delDialog.busy" @click="confirmDeleteEpisode('shift')">
            <b>① 删除并顺移</b>
            <span>后续各集集号 -1，保持连续编号（第{{ delDialog.no + 1 }}集 → 第{{ delDialog.no }}集 …）</span>
          </button>
          <button class="del-choice" :disabled="delDialog.busy" @click="confirmDeleteEpisode('blank')">
            <b>② 保留空白集</b>
            <span>第{{ delDialog.no }}集留空占位，后续集号不变（适合之后重录补回此集）</span>
          </button>
        </div>
        <div v-if="delDialog.error" class="error-banner">⚠ {{ delDialog.error }}</div>
        <div class="dialog-actions">
          <button class="btn btn-ghost" :disabled="delDialog.busy" @click="delDialog.show = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useTabsStore } from '../stores/tabs'
import { useProjectStore } from '../stores/projects'

const API = 'http://127.0.0.1:18520/api'
const route = useRoute()
const router = useRouter()
const tabsStore = useTabsStore()
const projectStore = useProjectStore()

const series   = reactive({ id: '', name: '', emoji: '📚' })
const chapters = ref([])
const episodes = ref([])          // 完整集序列（含空白集），来自后端 series/projects
const maxNo    = ref(0)
const sortAsc  = ref(true)        // true=正序(第1集在上)，false=逆序
const editingId = ref(null)
const newDialog = reactive({ show: false, name: '', picked: [], creating: false, error: '' })
const delDialog = reactive({ show: false, no: 0, name: '', projectId: '', busy: false, error: '' })

const displayedEpisodes = computed(() =>
  sortAsc.value ? episodes.value : [...episodes.value].reverse())

function epLabel(u) {
  return u && u.episode_no ? `第${u.episode_no}集：${u.project_name}` : (u?.project_name || '')
}

const sid = () => route.params.id

async function load() {
  // 系列元数据：仅当确实 404（系列不存在）才回首页；瞬时错误（后端重启/5xx/网络）
  // 保留当前页，避免把用户误踢出存在的系列。
  let s
  try {
    s = await axios.get(`${API}/series/${sid()}`)
  } catch (e) {
    if (e?.response?.status === 404) { router.replace('/'); return }
    console.warn('加载系列失败（保留当前页，稍后重试）:', e?.message || e)
    return
  }
  series.id = s.data.id; series.name = s.data.name; series.emoji = s.data.emoji
  try {
    const ch = await axios.get(`${API}/series/${sid()}/chapters`)
    chapters.value = ch.data.chapters || []
  } catch (e) { console.warn('加载章节失败:', e?.message || e) }
  try {
    const pr = await axios.get(`${API}/series/${sid()}/projects`)
    episodes.value = pr.data.episodes || []
    maxNo.value = pr.data.max_no || 0
  } catch (e) { console.warn('加载系列项目失败:', e?.message || e) }
}

async function saveSeriesName() {
  try { await axios.put(`${API}/series/${sid()}`, { name: series.name }) } catch {}
}

function toggleEdit(ch) { editingId.value = editingId.value === ch.id ? null : ch.id }

async function addChapter() {
  const { data } = await axios.post(`${API}/series/${sid()}/chapters`,
    { title: `第 ${chapters.value.length + 1} 章`, content: '' })
  await reloadChapters()
  editingId.value = data.id
}
async function saveChapter(ch) {
  try { await axios.put(`${API}/series/${sid()}/chapters/${ch.id}`,
    { title: ch.title || '', content: ch.content || '' }) } catch {}
}
async function delChapter(ch) {
  if (!confirm(`删除章节「${ch.title || '未命名'}」？`)) return
  await axios.delete(`${API}/series/${sid()}/chapters/${ch.id}`)
  await reloadChapters()
}
async function reloadChapters() {
  const { data } = await axios.get(`${API}/series/${sid()}/chapters`)
  chapters.value = data.chapters || []
}

function openNewProject() {
  newDialog.name = `第 ${maxNo.value + 1} 集`
  newDialog.picked = []
  newDialog.error = ''
  newDialog.show = true
}
function togglePick(cid) {
  const i = newDialog.picked.indexOf(cid)
  if (i >= 0) newDialog.picked.splice(i, 1); else newDialog.picked.push(cid)
}
async function createSeriesProject() {
  if (!newDialog.name.trim()) return
  newDialog.creating = true; newDialog.error = ''
  try {
    const { data } = await axios.post(`${API}/projects`, {
      name: newDialog.name.trim(), series_id: sid(),
      chapter_ids: newDialog.picked, folder_id: 'default',
    })
    newDialog.show = false
    await load()            // 刷新本系列项目列表 + 章节 used_by 标注
    try { await projectStore.fetchProjects() } catch {}  // 让主页项目列表也即时包含新集
    tabsStore.openTab(data.id, data.name)
  } catch (e) {
    newDialog.error = e?.response?.data?.detail || e.message || '创建失败'
  } finally {
    newDialog.creating = false
  }
}

function openEpisode(e) {
  if (e.blank || !e.project_id) return
  tabsStore.openTab(e.project_id, e.project_name)
}

function askDeleteEpisode(e) {
  if (e.blank) return
  // 最后一集（最大集号）：直接删，无空缺，不需要选择策略
  if (e.no >= maxNo.value) {
    if (!confirm(`删除「第${e.no}集：${e.project_name}」？此操作不可撤销。`)) return
    doDeleteEpisode(e.project_id, 'blank').then(ok => {
      if (!ok) alert('删除失败，请重试（后端或网络错误）')
    })
    return
  }
  // 中间集：弹窗二选一
  delDialog.no = e.no; delDialog.name = e.project_name
  delDialog.projectId = e.project_id; delDialog.error = ''; delDialog.busy = false
  delDialog.show = true
}

async function confirmDeleteEpisode(strategy) {
  delDialog.busy = true; delDialog.error = ''
  const ok = await doDeleteEpisode(delDialog.projectId, strategy)
  delDialog.busy = false
  if (ok) delDialog.show = false
  else delDialog.error = '删除失败，请重试'
}

async function doDeleteEpisode(projectId, strategy) {
  try {
    await axios.post(`${API}/series/${sid()}/delete-episode`,
      { project_id: projectId, strategy })
    // 该集若已在标签打开，关掉
    try { tabsStore.closeTab(projectId) } catch {}
    await load()
    try { await projectStore.fetchProjects() } catch {}
    return true
  } catch (e) {
    console.warn('删除剧集失败:', e?.response?.data?.detail || e?.message || e)
    return false
  }
}

async function removeBlank(e) {
  if (!confirm(`删除空白「第${e.no}集」占位？后续各集集号将 -1。`)) return
  try {
    await axios.post(`${API}/series/${sid()}/delete-blank`, { episode_no: e.no })
    await load()
    try { await projectStore.fetchProjects() } catch {}
  } catch (err) {
    alert('删除空白集失败: ' + (err?.response?.data?.detail || err?.message || err))
  }
}

function goHome() { router.push('/') }
function fmtTime(t) { try { return t ? new Date(t).toLocaleString() : '' } catch { return '' } }

watch(() => route.params.id, load)
onMounted(load)
</script>

<style scoped>
.series-view { padding: 16px 20px; max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; height: 100%; box-sizing: border-box; }
.series-header { display: flex; align-items: center; gap: 10px; }
.series-emoji { font-size: 22px; }
.series-name-input { font-size: 18px; font-weight: 700; background: transparent; border: 1px solid transparent; color: var(--text, #eee); padding: 4px 8px; border-radius: 6px; }
.series-name-input:hover, .series-name-input:focus { border-color: var(--border, #444); outline: none; }
.series-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: rgba(178,102,255,.15); color: #b794f4; }
.flex-spacer { flex: 1; }
.series-note { font-size: 12px; line-height: 1.6; color: var(--text-muted, #aaa); background: rgba(102,178,255,.08); border: 1px solid rgba(102,178,255,.25); border-radius: 6px; padding: 8px 12px; margin: 10px 0; }
.series-body { display: flex; gap: 16px; flex: 1; min-height: 0; }
.series-col { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow-y: auto; }
.chapters-col { flex: 1.4; }
.col-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; position: sticky; top: 0; }
.col-head h3 { margin: 0; font-size: 14px; }
.empty-hint { font-size: 12px; color: var(--text-muted, #999); padding: 12px; }
.chapter-card { border: 1px solid var(--border, #333); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.chapter-card.active { border-color: var(--accent, #66b2ff); }
.chapter-head { display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: pointer; }
.chapter-idx { font-weight: 700; color: var(--accent, #66b2ff); min-width: 18px; }
.chapter-title { flex: 1; min-width: 0; background: transparent; border: 1px solid transparent; color: var(--text, #eee); padding: 3px 6px; border-radius: 4px; font-size: 13px; }
.chapter-title:hover, .chapter-title:focus { border-color: var(--border, #444); outline: none; }
.chapter-used { font-size: 10px; color: #5bbf7b; white-space: nowrap; }
.chapter-len { font-size: 11px; }
.chapter-arrow { font-size: 10px; color: var(--text-muted, #999); }
.chapter-content { width: 100%; box-sizing: border-box; border: none; border-top: 1px solid var(--border, #333); background: var(--bg-input, #1a1a1a); color: var(--text, #eee); padding: 8px 10px; font-size: 13px; line-height: 1.6; resize: vertical; }
.proj-card { display: flex; align-items: center; gap: 4px; padding: 9px 10px; border: 1px solid var(--border, #333); border-radius: 8px; margin-bottom: 6px; }
.proj-card.proj-clickable { cursor: pointer; }
.proj-card.proj-clickable:hover { border-color: var(--accent, #66b2ff); }
.proj-card.proj-blank { border-style: dashed; opacity: 0.7; }
.ep-no { font-size: 12px; font-weight: 700; color: var(--accent, #66b2ff); flex-shrink: 0; }
.proj-card.proj-blank .ep-no { color: var(--text-muted, #999); }
.proj-name { flex: 1; min-width: 0; font-size: 13px; }
.proj-blank-label { color: var(--text-muted, #999); font-style: italic; }
.proj-time { font-size: 11px; flex-shrink: 0; }
.ep-del { flex-shrink: 0; opacity: 0; }
.proj-card:hover .ep-del { opacity: 0.7; }
.ep-del:hover { opacity: 1 !important; color: var(--danger, #e5534b); }

/* 删除剧集策略对话框 */
.del-choices { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
.del-choice { display: flex; flex-direction: column; gap: 3px; text-align: left; padding: 10px 12px; border: 1px solid var(--border, #333); border-radius: 8px; background: var(--bg-input, #1a1a1a); color: var(--text, #eee); cursor: pointer; }
.del-choice:hover:not(:disabled) { border-color: var(--accent, #66b2ff); background: rgba(102,178,255,.08); }
.del-choice:disabled { opacity: 0.5; cursor: default; }
.del-choice b { font-size: 13px; }
.del-choice span { font-size: 11px; color: var(--text-muted, #999); }
.chapter-pick { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--border, #333); border-radius: 6px; margin-bottom: 5px; cursor: pointer; }
.chapter-pick.picked { border-color: var(--accent, #66b2ff); background: rgba(102,178,255,.08); }
.cp-title { flex: 1; min-width: 0; font-size: 13px; }
.cp-len { font-size: 11px; }
.cp-used { font-size: 10px; color: #d8a24a; white-space: nowrap; }
.field-hint { font-size: 11px; color: var(--text-muted, #999); margin-top: 4px; }
</style>
