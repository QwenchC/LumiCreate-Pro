<template>
  <div class="th-overlay" @click.self="$emit('close')">
    <div class="th-panel card">
      <div class="th-header">
        <h3>📊 任务历史</h3>
        <button class="btn btn-ghost btn-xs" @click="$emit('close')">✕</button>
      </div>

      <!-- 本月统计卡片 -->
      <div v-if="stats" class="th-stats">
        <div class="th-stat-card">
          <div class="th-stat-num">{{ stats.total_tasks }}</div>
          <div class="th-stat-label">本月任务</div>
        </div>
        <div class="th-stat-card">
          <div class="th-stat-num">{{ formatDuration(stats.total_duration_ms) }}</div>
          <div class="th-stat-label">累计耗时</div>
        </div>
        <div class="th-stat-card" :class="{ bad: stats.total_errors }">
          <div class="th-stat-num">{{ stats.total_errors }}</div>
          <div class="th-stat-label">失败子项</div>
        </div>
      </div>

      <!-- 按类型计数 -->
      <div v-if="stats && Object.keys(stats.by_type).length" class="th-section">
        <div class="th-section-title">按类型</div>
        <div class="th-pills">
          <span v-for="(n, k) in stats.by_type" :key="k" class="th-pill">
            {{ TYPE_LABEL[k] || k }} · {{ n }}
          </span>
        </div>
      </div>

      <!-- 项目排行 -->
      <div v-if="stats && Object.keys(stats.by_project).length" class="th-section">
        <div class="th-section-title">项目排行</div>
        <div class="th-pills">
          <span v-for="(n, name) in stats.by_project" :key="name" class="th-pill">
            {{ name }} · {{ n }}
          </span>
        </div>
      </div>

      <!-- 过滤器 -->
      <div class="th-filter">
        <select v-model="filterType" class="input select-compact" style="width:140px">
          <option value="">全部类型</option>
          <option v-for="(label, k) in TYPE_LABEL" :key="k" :value="k">{{ label }}</option>
        </select>
        <input v-model="filterProject" class="input" placeholder="按项目 ID 过滤" style="flex:1" />
        <button class="btn btn-ghost btn-sm" @click="loadAll">↻ 刷新</button>
        <button class="btn btn-ghost btn-sm danger" @click="confirmClear">🗑 清空</button>
      </div>

      <!-- 记录表 -->
      <div class="th-records">
        <div v-if="!records.length" class="text-muted" style="padding:24px;text-align:center">
          {{ loading ? '加载中…' : '暂无记录' }}
        </div>
        <table v-else class="th-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>项目</th>
              <th>规模 / 失败</th>
              <th>耗时</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in records" :key="r.id" :class="r.status">
              <td>{{ formatTime(r.ended_at) }}</td>
              <td><span class="th-type-pill">{{ TYPE_LABEL[r.type] || r.type }}</span></td>
              <td class="truncate" :title="r.project_id">{{ r.project_name || r.project_id }}</td>
              <td>{{ r.items }} <span v-if="r.errors" class="th-bad">/ {{ r.errors }} ✗</span></td>
              <td>{{ formatDuration(r.duration_ms) }}</td>
              <td class="truncate" :title="r.note">{{ r.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'

defineEmits(['close'])

const API = 'http://127.0.0.1:18520/api'

const TYPE_LABEL = {
  images:   '🖼 图片',
  audio:    '🎙 音频',
  video:    '🎬 视频',
  merge:    '🎯 合并',
  subtitle: '💬 字幕',
  prompts:  '🖌 提示词',
}

const loading = ref(false)
const records = ref([])
const stats   = ref(null)
const filterType    = ref('')
const filterProject = ref('')

async function loadStats() {
  try {
    const r = await fetch(`${API}/task-history/stats`)
    if (r.ok) stats.value = await r.json()
  } catch {}
}

async function loadRecords() {
  loading.value = true
  try {
    const url = new URL(`${API}/task-history`)
    url.searchParams.set('limit', '500')
    if (filterType.value)    url.searchParams.set('type',       filterType.value)
    if (filterProject.value) url.searchParams.set('project_id', filterProject.value)
    const r = await fetch(url)
    if (r.ok) {
      const d = await r.json()
      records.value = d.records || []
    }
  } catch {}
  loading.value = false
}

async function loadAll() {
  await Promise.all([loadStats(), loadRecords()])
}

async function confirmClear() {
  if (!confirm('清空所有任务历史？此操作不可撤销。')) return
  try {
    await fetch(`${API}/task-history`, { method: 'DELETE' })
    await loadAll()
  } catch (e) { alert('清空失败: ' + e.message) }
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}
function formatDuration(ms) {
  if (!ms || ms < 1000) return (ms || 0) + ' ms'
  const s = Math.round(ms / 1000)
  if (s < 60) return s + 's'
  const m = Math.floor(s / 60), sec = s % 60
  if (m < 60) return `${m}m${sec}s`
  const h = Math.floor(m / 60), min = m % 60
  return `${h}h${min}m`
}

watch([filterType, filterProject], loadRecords)
onMounted(loadAll)
</script>

<style scoped>
.th-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 1000;
  display: flex; align-items: center; justify-content: center;
}
.th-panel {
  width: 900px; max-width: calc(100vw - 40px); max-height: calc(100vh - 40px);
  display: flex; flex-direction: column;
  background: var(--color-surface); border-radius: 8px;
  padding: 16px 20px;
}
.th-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.th-header h3 { margin: 0; font-size: 16px; }

.th-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 10px; }
.th-stat-card {
  background: var(--color-surface-2); border-radius: 6px;
  padding: 10px 14px; text-align: center;
}
.th-stat-card.bad { background: rgba(220,60,60,.10); }
.th-stat-num   { font-size: 22px; font-weight: 600; }
.th-stat-label { font-size: 11px; color: var(--color-text-muted); margin-top: 2px; }

.th-section { margin: 10px 0; }
.th-section-title { font-size: 11px; color: var(--color-text-muted); margin-bottom: 4px; }
.th-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.th-pill  {
  background: var(--color-surface-2); padding: 3px 8px;
  border-radius: 10px; font-size: 11px;
}

.th-filter { display: flex; gap: 8px; margin: 10px 0; }
.th-filter .danger:hover { color: var(--color-error); }

.th-records { flex: 1; overflow: auto; border: 1px solid var(--color-border); border-radius: 4px; }
.th-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.th-table th, .th-table td {
  padding: 5px 8px; border-bottom: 1px solid var(--color-border);
  text-align: left; vertical-align: middle;
}
.th-table th { background: var(--color-surface-2); position: sticky; top: 0; font-size: 11px; color: var(--color-text-muted); }
.th-table tr.error { background: rgba(220,60,60,.06); }
.th-table tr.partial { background: rgba(255,200,60,.05); }
.th-type-pill {
  background: var(--color-surface-2); padding: 2px 6px;
  border-radius: 4px; font-size: 11px;
}
.th-bad { color: #f66; font-weight: 600; }
.truncate { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
