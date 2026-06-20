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
                  :title="'已用于：' + ch.used_by.map(u => u.project_name).join('、')">
              已用于 {{ ch.used_by.map(u => u.project_name).join('、') }}
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

      <!-- 右：本系列项目（集数） -->
      <section class="series-col projects-col">
        <div class="col-head"><h3>🎦 本系列项目（集数）</h3></div>
        <div v-if="!projects.length" class="empty-hint">还没有项目。点右上「＋ 新建本系列项目」创建第一集。</div>
        <div v-for="p in projects" :key="p.id" class="proj-card" @click="openProject(p)">
          <span class="sidebar-project-icon">🎦</span>
          <span class="proj-name truncate">{{ p.name }}</span>
          <span class="proj-time text-muted">{{ fmtTime(p.updated_at) }}</span>
        </div>
      </section>
    </div>

    <!-- 新建本系列项目对话框 -->
    <div v-if="newDialog.show" class="overlay" @click.self="newDialog.show = false">
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
                  title="已被其它项目用过，避免重复选用">
              ⚠ 已用于 {{ ch.used_by.map(u => u.project_name).join('、') }}
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useTabsStore } from '../stores/tabs'

const API = 'http://127.0.0.1:18520/api'
const route = useRoute()
const router = useRouter()
const tabsStore = useTabsStore()

const series   = reactive({ id: '', name: '', emoji: '📚' })
const chapters = ref([])
const projects = ref([])
const editingId = ref(null)
const newDialog = reactive({ show: false, name: '', picked: [], creating: false, error: '' })

const sid = () => route.params.id

async function load() {
  try {
    const [s, ch, pr] = await Promise.all([
      axios.get(`${API}/series/${sid()}`),
      axios.get(`${API}/series/${sid()}/chapters`).catch(() => ({ data: { chapters: [] } })),
      axios.get(`${API}/series/${sid()}/projects`).catch(() => ({ data: { projects: [] } })),
    ])
    series.id = s.data.id; series.name = s.data.name; series.emoji = s.data.emoji
    chapters.value = ch.data.chapters || []
    projects.value = pr.data.projects || []
  } catch (e) {
    // 系列不存在 → 回首页
    router.replace('/')
  }
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
  newDialog.name = `第 ${projects.value.length + 1} 集`
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
    tabsStore.openTab(data.id, data.name)
  } catch (e) {
    newDialog.error = e?.response?.data?.detail || e.message || '创建失败'
  } finally {
    newDialog.creating = false
  }
}

function openProject(p) { tabsStore.openTab(p.id, p.name) }
function goHome() { router.push('/') }
function fmtTime(t) { try { return new Date(t).toLocaleString() } catch { return '' } }

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
.proj-card { display: flex; align-items: center; gap: 8px; padding: 9px 10px; border: 1px solid var(--border, #333); border-radius: 8px; margin-bottom: 6px; cursor: pointer; }
.proj-card:hover { border-color: var(--accent, #66b2ff); }
.proj-name { flex: 1; min-width: 0; font-size: 13px; }
.proj-time { font-size: 11px; }
.chapter-pick { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--border, #333); border-radius: 6px; margin-bottom: 5px; cursor: pointer; }
.chapter-pick.picked { border-color: var(--accent, #66b2ff); background: rgba(102,178,255,.08); }
.cp-title { flex: 1; min-width: 0; font-size: 13px; }
.cp-len { font-size: 11px; }
.cp-used { font-size: 10px; color: #d8a24a; white-space: nowrap; }
.field-hint { font-size: 11px; color: var(--text-muted, #999); margin-top: 4px; }
</style>
