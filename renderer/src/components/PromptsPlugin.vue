<template>
  <Teleport to="body">
    <div class="pp-overlay" @click.self="$emit('close')">
      <div class="pp-modal">
        <div class="pp-header">
          <h3>💡 提示词插件</h3>
          <span class="pp-hint text-muted">
            点击标签追加到下方撰写框，或自行输入；一键复制后回到需要的地方粘贴
          </span>
          <button class="btn btn-ghost btn-xs" @click="$emit('close')">✕</button>
        </div>

        <div class="pp-body">
          <!-- 左：类目 -->
          <div class="pp-categories">
            <div class="pp-section-title">类目（{{ categories.length }}）</div>
            <ul class="pp-cat-list">
              <li v-for="cat in categories" :key="cat"
                  :class="{ active: cat === activeCategory }"
                  @click="activeCategory = cat">
                {{ cat }}
              </li>
            </ul>
            <div class="pp-cat-actions">
              <button class="btn btn-ghost btn-xs" @click="resetBuiltins"
                      :disabled="resetting" :title="'重置内置标签（不影响自定义）'">
                ↺ 重置内置
              </button>
            </div>
          </div>

          <!-- 中：标签网格 + 搜索 -->
          <div class="pp-tags">
            <div class="pp-tags-toolbar">
              <input class="input pp-search"
                     v-model="search"
                     placeholder="🔍 搜索名称 / 内容 / 描述…" />
              <button class="btn btn-secondary btn-xs"
                      @click="showAddForm = !showAddForm">
                {{ showAddForm ? '✕ 取消' : '＋ 新增自定义' }}
              </button>
            </div>
            <!-- 新增表单 -->
            <div v-if="showAddForm" class="pp-add-form">
              <input class="input input-xs" placeholder="类目（如：自定义）"
                     v-model="newTag.category" />
              <input class="input input-xs" placeholder="显示名（中文短标签）"
                     v-model="newTag.name" />
              <input class="input input-xs" placeholder="提示词内容（实际复制的文本）"
                     v-model="newTag.content" />
              <input class="input input-xs" placeholder="描述（可选）"
                     v-model="newTag.description" />
              <button class="btn btn-primary btn-xs"
                      :disabled="!newTag.name || !newTag.content || saving"
                      @click="addTag">{{ saving ? '保存中…' : '✓ 保存' }}</button>
            </div>
            <div v-if="!filteredTags.length" class="pp-empty">
              该类目下还没有匹配的标签。
            </div>
            <div v-else class="pp-tag-grid">
              <div v-for="t in filteredTags" :key="t.id"
                   class="pp-tag-chip"
                   :class="{ 'pp-tag-custom': !t.is_builtin }"
                   :title="t.description || t.content"
                   @click="appendTag(t)">
                <span class="pp-tag-name">{{ t.name }}</span>
                <span class="pp-tag-content">{{ t.content }}</span>
                <button v-if="!t.is_builtin" class="pp-tag-del"
                        @click.stop="deleteTag(t)" title="删除自定义标签">✕</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 下：撰写区 + 复制 -->
        <div class="pp-composer">
          <div class="pp-section-title">
            撰写区 — {{ composer.length }} 字符
            <span class="pp-status text-muted">{{ copyStatus }}</span>
          </div>
          <textarea class="input pp-textarea"
                    v-model="composer"
                    placeholder="点击上方标签会追加到这里，也可以自行键入；编辑好后点「复制」"
                    rows="3"></textarea>
          <div class="pp-composer-actions">
            <button class="btn btn-ghost btn-sm" @click="composer = ''"
                    :disabled="!composer">🗑 清空</button>
            <span class="pp-sep">·</span>
            <span class="text-muted pp-tip">分隔符：</span>
            <label class="pp-radio">
              <input type="radio" v-model="separator" value=", " /> 逗号
            </label>
            <label class="pp-radio">
              <input type="radio" v-model="separator" value=" " /> 空格
            </label>
            <label class="pp-radio">
              <input type="radio" v-model="separator" value="\n" /> 换行
            </label>
            <button class="btn btn-primary btn-sm pp-copy-btn"
                    :disabled="!composer"
                    @click="copyToClipboard">
              📋 复制到剪贴板
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'

const emit = defineEmits(['close'])
const API = 'http://localhost:18520/api'

const categories     = ref([])
const tags           = ref([])
const activeCategory = ref('')
const search         = ref('')
const composer       = ref('')
const separator      = ref(', ')
const showAddForm    = ref(false)
const saving         = ref(false)
const resetting      = ref(false)
const copyStatus     = ref('')

const newTag = ref({
  category: '自定义', name: '', content: '', description: '',
})

async function loadCategories() {
  try {
    const r = await axios.get(`${API}/prompts/categories`)
    categories.value = r.data?.categories || []
    if (categories.value.length && !activeCategory.value) {
      activeCategory.value = categories.value[0]
    }
  } catch (e) {
    console.warn('[prompts] failed to load categories:', e)
  }
}

async function loadTags() {
  if (!activeCategory.value) {
    tags.value = []
    return
  }
  try {
    const r = await axios.get(
      `${API}/prompts/list?category=${encodeURIComponent(activeCategory.value)}`
    )
    tags.value = r.data?.tags || []
  } catch (e) {
    console.warn('[prompts] failed to load tags:', e)
    tags.value = []
  }
}

watch(activeCategory, loadTags)

const filteredTags = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return tags.value
  return tags.value.filter(t =>
    (t.name || '').toLowerCase().includes(q) ||
    (t.content || '').toLowerCase().includes(q) ||
    (t.description || '').toLowerCase().includes(q)
  )
})

function appendTag(t) {
  const piece = t.content || ''
  if (!piece) return
  const cur = composer.value
  if (!cur) {
    composer.value = piece
  } else {
    // 末尾已经是 sep / 空白则不再添 sep
    const trimEnd = cur.replace(/\s+$/, '')
    const sep = separator.value
    composer.value = (trimEnd.endsWith(sep.trim()) || sep.trim() === '')
      ? cur + (cur.endsWith(' ') ? '' : ' ') + piece
      : trimEnd + sep + piece
  }
}

async function copyToClipboard() {
  const txt = composer.value
  if (!txt) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(txt)
    } else {
      const ta = document.createElement('textarea')
      ta.value = txt; document.body.appendChild(ta)
      ta.select(); document.execCommand('copy')
      document.body.removeChild(ta)
    }
    copyStatus.value = '✓ 已复制 ' + txt.length + ' 字符'
    setTimeout(() => { copyStatus.value = '' }, 2200)
  } catch (e) {
    copyStatus.value = '复制失败：' + e.message
  }
}

async function addTag() {
  saving.value = true
  try {
    const r = await axios.post(`${API}/prompts/tag`, {
      category:    (newTag.value.category || '自定义').trim() || '自定义',
      name:        newTag.value.name.trim(),
      content:     newTag.value.content.trim(),
      description: (newTag.value.description || '').trim(),
    })
    // 添加成功 → 切到该 category，重载
    await loadCategories()
    activeCategory.value = r.data.category
    await loadTags()
    // 重置表单
    newTag.value = { category: r.data.category, name: '', content: '', description: '' }
    showAddForm.value = false
  } catch (e) {
    alert('保存失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function deleteTag(t) {
  if (t.is_builtin) return
  if (!confirm(`删除自定义标签「${t.name}」？`)) return
  try {
    await axios.delete(`${API}/prompts/tag/${t.id}`)
    await loadTags()
  } catch (e) {
    alert('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

async function resetBuiltins() {
  if (!confirm('重置内置标签库到出厂状态？\n（不影响你自己新增的自定义标签）')) return
  resetting.value = true
  try {
    await axios.post(`${API}/prompts/reset-builtins`)
    await loadCategories()
    await loadTags()
  } catch (e) {
    alert('重置失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    resetting.value = false
  }
}

onMounted(async () => {
  await loadCategories()
  await loadTags()
})
</script>

<style scoped>
.pp-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
}
.pp-modal {
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  width: min(1100px, 96vw);
  max-height: min(88vh, 800px);
  display: flex; flex-direction: column; gap: 10px;
  min-height: 0;
}
.pp-header {
  display: flex; align-items: center; gap: 12px;
  flex: 0 0 auto;
}
.pp-header h3 { margin: 0; font-size: 15px; color: var(--text); }
.pp-hint { font-size: 11px; flex: 1; }

/* body 左右两栏 */
.pp-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 10px;
}
.pp-categories, .pp-tags {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  overflow: auto;
  min-height: 0;
  min-width: 0;
  display: flex; flex-direction: column;
}
.pp-section-title {
  font-size: 12px; font-weight: 600; color: var(--text);
  margin-bottom: 6px; padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
}
.pp-cat-list {
  list-style: none; padding: 0; margin: 0;
  flex: 1;
}
.pp-cat-list li {
  padding: 6px 10px;
  cursor: pointer; border-radius: 4px;
  color: var(--text); font-size: 13px;
}
.pp-cat-list li:hover { background: var(--bg-panel); }
.pp-cat-list li.active {
  background: var(--accent);
  color: #fff;
}
.pp-cat-actions {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border);
}

/* 标签栏 toolbar + 网格 */
.pp-tags-toolbar {
  display: flex; gap: 6px; align-items: center;
  margin-bottom: 8px; flex: 0 0 auto;
}
.pp-search {
  flex: 1; padding: 4px 8px; font-size: 13px;
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.pp-add-form {
  display: grid;
  grid-template-columns: 1fr 1fr 2fr 2fr auto;
  gap: 5px;
  margin-bottom: 8px;
}
.pp-add-form .input {
  padding: 4px 7px; font-size: 12px;
  background: var(--bg-panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
}
.pp-tag-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
  overflow: auto;
  align-content: start;
}
.pp-tag-chip {
  position: relative;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 8px;
  cursor: pointer;
  transition: background var(--transition), border-color var(--transition);
  display: flex; flex-direction: column;
  min-width: 0;
}
.pp-tag-chip:hover {
  background: var(--accent);
  border-color: var(--accent);
}
.pp-tag-chip:hover .pp-tag-name,
.pp-tag-chip:hover .pp-tag-content { color: #fff; }
.pp-tag-custom {
  border-left: 3px solid var(--color-warning, #fbbf24);
}
.pp-tag-name {
  font-size: 12px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pp-tag-content {
  font-size: 10px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-top: 2px;
}
.pp-tag-del {
  position: absolute; top: 2px; right: 2px;
  width: 16px; height: 16px;
  background: transparent; border: none;
  color: var(--text-muted);
  cursor: pointer; font-size: 11px;
  opacity: 0; transition: opacity var(--transition);
  border-radius: 3px;
}
.pp-tag-chip:hover .pp-tag-del { opacity: 1; }
.pp-tag-del:hover { background: var(--color-error, #f87171); color: #fff; }
.pp-empty {
  color: var(--text-muted);
  text-align: center; padding: 24px; font-size: 12px;
}

/* 撰写区 */
.pp-composer {
  flex: 0 0 auto;
  display: flex; flex-direction: column; gap: 6px;
}
.pp-textarea {
  width: 100%;
  background: var(--bg-input);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 8px;
  font-family: inherit; font-size: 13px;
  resize: vertical;
  min-height: 60px;
}
.pp-composer-actions {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px;
}
.pp-sep { color: var(--text-muted); margin: 0 4px; }
.pp-tip { font-size: 11px; }
.pp-radio {
  display: flex; align-items: center; gap: 3px;
  font-size: 11px; color: var(--text); cursor: pointer;
}
.pp-radio input { margin: 0; }
.pp-copy-btn { margin-left: auto; }
.pp-status {
  font-size: 11px; margin-left: auto;
}
</style>
