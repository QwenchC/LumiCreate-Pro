<template>
  <div class="tab-panel characters-tab">

    <div class="char-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">角色管理</h3>
        <span class="text-muted" style="font-size:12px">角色外观描述将自动注入图片提示词，保持角色一致性</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-secondary btn-sm" @click="importFromManuscript" :disabled="syncing">
          {{ syncing ? '导入中...' : '↓ 从文案导入角色' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="addCharacter">＋ 添加角色</button>
        <button class="btn btn-primary btn-sm" :disabled="!isDirty || saving" @click="save">
          {{ saving ? '保存中...' : '💾 保存' }}
        </button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!characters.length" class="char-empty">
      <div class="empty-icon">🎭</div>
      <p>暂无角色</p>
      <p class="text-muted" style="font-size:12px">点击「从文案导入角色」可从文案配置中导入角色（仅新增，不覆盖已有角色），<br/>或手动点击「添加角色」创建。</p>
    </div>

    <!-- Character cards -->
    <div v-else class="char-list">
      <div v-for="(char, i) in characters" :key="i" class="char-card card">
        <div class="char-card-header">
          <div class="char-avatar">{{ char.name ? char.name[0] : '?' }}</div>
          <div class="char-basic">
            <input
              v-model="char.name"
              class="input char-name-input"
              placeholder="角色姓名"
              @input="markDirty"
            />
            <input
              v-model="char.role"
              class="input char-role-input"
              placeholder="角色定位（主角、反派…）"
              @input="markDirty"
            />
          </div>
          <div class="char-actions-inline">
            <button
              class="btn btn-ghost btn-xs"
              :disabled="!!char._finding"
              @click="lookupFromManuscript(i)"
              title="从文案配置/文案内容检索该角色"
            >{{ char._finding ? '检索中…' : '🔎 检索' }}</button>
            <button
              class="btn btn-ghost btn-xs"
              :disabled="!!char._profiling"
              @click="generateProfileFromManuscript(i)"
              title="基于文本引擎从文案生成角色描述"
            >{{ char._profiling ? '生成中…' : '✦ 生成描述' }}</button>
          </div>
          <button class="btn btn-ghost btn-sm icon-btn danger" @click="removeCharacter(i)" title="删除角色">✕</button>
        </div>

        <div class="char-card-body">
          <div class="form-group">
            <label>性格 / 背景特征</label>
            <input
              v-model="char.traits"
              class="input"
              placeholder="例：冷静、理性、腹黑，隐藏身份"
              @input="markDirty"
            />
          </div>
          <div class="form-group">
            <div class="label-row">
              <label class="label-em">✨ 外观描述（英文，注入图片提示词）</label>
              <button
                class="btn btn-secondary btn-xs gen-appearance-btn"
                :disabled="!!char._generating"
                @click="generateAppearance(i)"
                title="使用AI根据角色信息生成外观描述"
              >
                <span v-if="char._generating">⏳ 生成中…</span>
                <span v-else>✨ AI 生成</span>
              </button>
            </div>
            <textarea
              v-model="char.appearance"
              class="input textarea appearance-input"
              rows="3"
              placeholder="e.g. tall young woman, long silver hair, red eyes, white school uniform, slender figure, delicate face"
              @input="markDirty"
            />
            <p class="field-hint">⚠ 此字段将逐字插入每张图片的提示词，请用英文逗号分隔标签。</p>
          </div>
          <div class="form-group">
            <label>负面描述（Negative，可选）</label>
            <input
              v-model="char.negative"
              class="input"
              placeholder="e.g. wrong hair color, inconsistent costume"
              @input="markDirty"
            />
          </div>
        </div>
      </div>

      <button class="btn btn-secondary add-bottom" @click="addCharacter">＋ 添加角色</button>
    </div>

    <!-- Status -->
    <div v-if="statusMsg" class="status-toast" :class="statusType">{{ statusMsg }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://127.0.0.1:18520/api'

const characters = ref([])
const isDirty  = ref(false)
const saving   = ref(false)
const syncing  = ref(false)
const statusMsg  = ref('')
const statusType = ref('')

function emptyChar() {
  return {
    name: '', role: '', traits: '', appearance: '', negative: '',
    _generating: false, _finding: false, _profiling: false
  }
}

function addCharacter() {
  characters.value.push(emptyChar())
  markDirty()
}

function removeCharacter(i) {
  if (!confirm(`确定删除角色「${characters.value[i].name || '未命名'}」？`)) return
  characters.value.splice(i, 1)
  markDirty()
}

function markDirty() {
  isDirty.value = true
  window.__lumiUnsaved = true
  emit('dirty')
}

// ── Load ──────────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/characters`)
    if (res.ok) {
      const d = await res.json()
      characters.value = (d.characters || []).map(c => ({
        name: c.name || '',
        role: c.role || '',
        traits: c.traits || '',
        appearance: c.appearance || '',
        negative: c.negative || '',
        _generating: false,
        _finding: false,
        _profiling: false,
      }))
    }
  } catch {}
  window.addEventListener('lumi:save-project', onGlobalSave)
})
onUnmounted(() => window.removeEventListener('lumi:save-project', onGlobalSave))

// ── AI generate appearance ─────────────────────────────────────────────────────
async function generateAppearance(i) {
  const char = characters.value[i]
  if (!char.name.trim() && !char.traits.trim()) {
    showStatus('请先填写角色姓名或性格特征', 'warn')
    return
  }
  char._generating = true
  char.appearance = ''
  try {
    const res = await fetch(`${API}/text-engine/generate-character-appearance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name:     char.name,
        role:     char.role,
        traits:   char.traits,
        existing: char.appearance,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      showStatus(`生成失败: ${err.detail || res.status}`, 'err')
      return
    }
    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const obj = JSON.parse(raw)
          if (obj.error) { showStatus(`生成失败: ${obj.error}`, 'err'); break }
          if (obj.text)  { char.appearance += obj.text }
        } catch {}
      }
    }
    char.appearance = char.appearance.trim()
    markDirty()
    showStatus('✓ 外观描述已生成', 'ok')
  } catch (e) {
    showStatus(`生成失败: ${e.message}`, 'err')
  } finally {
    char._generating = false
  }
}

async function lookupFromManuscript(i) {
  const char = characters.value[i]
  const name = String(char.name || '').trim()
  if (!name) {
    showStatus('请先输入角色名称', 'warn')
    return
  }
  char._finding = true
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/manuscript`)
    if (!res.ok) throw new Error('读取文案失败')
    const d = await res.json()

    // 1) Prefer exact hit from manuscript config characters.
    const cfgChars = d.config?.characters || []
    const hit = cfgChars.find(c => String(c.name || '').trim().toLowerCase() === name.toLowerCase())
    if (hit) {
      if (!char.role)   char.role = hit.role || ''
      if (!char.traits) char.traits = hit.traits || ''
      markDirty()
      showStatus('✓ 已从文案配置检索到角色信息', 'ok')
      return
    }

    // 2) Fallback: local manuscript text lookup (no LLM dependency).
    const manuscript = String(d.content || '')
    const excerpt = extractCharacterExcerpt(manuscript, name)
    if (excerpt) {
      if (!char.traits) char.traits = excerpt
      markDirty()
      showStatus('✓ 已从文案正文检索到角色线索', 'ok')
    } else {
      showStatus('未在文案中检索到该角色', 'warn')
    }
  } catch (e) {
    showStatus(`检索失败: ${e.message}`, 'err')
  } finally {
    char._finding = false
  }
}

function extractCharacterExcerpt(manuscript, name) {
  if (!manuscript || !name) return ''
  const idx = manuscript.indexOf(name)
  if (idx < 0) return ''

  const start = Math.max(0, idx - 40)
  const end = Math.min(manuscript.length, idx + name.length + 80)
  let snippet = manuscript.slice(start, end)
    .replace(/\s+/g, ' ')
    .replace(/[\r\n]/g, ' ')
    .trim()

  // keep concise to avoid stuffing too much raw manuscript into traits
  if (snippet.length > 80) snippet = snippet.slice(0, 80) + '…'
  return snippet
}

async function generateProfileFromManuscript(i, manuscriptHint = null) {
  const char = characters.value[i]
  const name = String(char.name || '').trim()
  if (!name) {
    showStatus('请先输入角色名称', 'warn')
    return
  }

  if ((char.role || '').trim() || (char.traits || '').trim()) {
    const ok = confirm('当前角色已存在描述信息，继续生成可能覆盖现有内容。是否继续？')
    if (!ok) return
  }

  char._profiling = true
  try {
    let manuscript = manuscriptHint
    if (manuscript === null) {
      const res = await fetch(`${API}/projects/${props.projectId}/manuscript`)
      if (!res.ok) throw new Error('读取文案失败')
      const d = await res.json()
      manuscript = d.content || ''
    }
    if (!String(manuscript || '').trim()) {
      showStatus('文案为空，无法生成角色描述', 'warn')
      return
    }

    const res = await fetch(`${API}/text-engine/generate-character-profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        manuscript,
        existing_role: char.role || '',
        existing_traits: char.traits || '',
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `${res.status}`)
    }
    const data = await res.json()
    if (data.role) char.role = data.role
    if (data.traits) char.traits = data.traits
    markDirty()
    showStatus('✓ 已生成角色描述', 'ok')
  } catch (e) {
    showStatus(`生成失败: ${e.message}`, 'err')
  } finally {
    char._profiling = false
  }
}

// ── Import from manuscript config (add only, no overwrite) ───────────────────
function normalizeName(name) {
  return String(name || '').trim().toLowerCase()
}

async function importFromManuscript() {
  syncing.value = true
  try {
    const res = await fetch(`${API}/projects/${props.projectId}/manuscript`)
    if (!res.ok) throw new Error('读取文案配置失败')
    const d = await res.json()
    const configChars = d.config?.characters || []
    if (!configChars.length) {
      showStatus('文案配置中没有角色', 'warn')
      return
    }

    // Only add new characters; never overwrite existing ones.
    const existingSet = new Set(characters.value.map(c => normalizeName(c.name)).filter(Boolean))
    const toAdd = []
    for (const c of configChars) {
      const name = String(c.name || '').trim()
      const key = normalizeName(name)
      if (!key || existingSet.has(key)) continue
      existingSet.add(key)
      toAdd.push({
        name,
        role: c.role || '',
        traits: c.traits || '',
        appearance: c.appearance || '',
        negative: c.negative || '',
        _generating: false,
      })
    }

    if (!toAdd.length) {
      showStatus('没有可导入的新角色（已自动跳过重复角色）', 'warn')
      return
    }

    characters.value.push(...toAdd)
    markDirty()
    showStatus(`已导入 ${toAdd.length} 个新角色（跳过重复角色）`, 'ok')
  } catch (e) {
    showStatus(e.message, 'err')
  } finally {
    syncing.value = false
  }
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function save() {
  saving.value = true
  try {
    const payload = characters.value.map(({ _generating, _finding, _profiling, ...c }) => c)
    const res = await fetch(`${API}/projects/${props.projectId}/characters`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ characters: payload }),
    })
    if (!res.ok) throw new Error(await res.text())
    isDirty.value = false
    window.__lumiUnsaved = false
    emit('saved')
    showStatus('✓ 已保存', 'ok')
  } catch (e) {
    showStatus(`保存失败: ${e.message}`, 'err')
  } finally {
    saving.value = false
  }
}

function onGlobalSave() {
  if (isDirty.value) save()
}

function showStatus(msg, type = '') {
  statusMsg.value  = msg
  statusType.value = type
  setTimeout(() => { if (statusMsg.value === msg) statusMsg.value = '' }, 3000)
}
</script>

<style scoped>
.characters-tab { height: 100%; display: flex; flex-direction: column; padding: 16px; gap: 12px; overflow: hidden; }

.char-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.toolbar-left { display: flex; flex-direction: column; gap: 2px; }
.toolbar-right { display: flex; gap: 8px; }
.toolbar-title { font-size: 15px; font-weight: 700; margin: 0; }

.char-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 10px; color: var(--color-text-muted);
}
.empty-icon { font-size: 48px; }

.char-list {
  flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px;
  padding-right: 4px;
}

.char-card { padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }

.char-card-header {
  display: flex; align-items: center; gap: 12px;
}
.char-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: var(--color-accent); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; flex-shrink: 0;
}
.char-basic { flex: 1; display: flex; gap: 8px; min-width: 0; }
.char-name-input { flex: 1; min-width: 0; font-weight: 600; }
.char-role-input { flex: 1.4; min-width: 0; }
.char-actions-inline { display: flex; gap: 6px; flex-shrink: 0; }

.char-card-body { display: flex; flex-direction: column; gap: 10px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 12px; color: var(--color-text-muted); }
.label-row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.gen-appearance-btn { font-size: 11px; padding: 2px 8px; height: 22px; white-space: nowrap; flex-shrink: 0; }
.label-em { color: var(--color-accent) !important; font-weight: 600; }
.appearance-input { font-family: monospace; font-size: 12px; line-height: 1.6; }
.field-hint { font-size: 11px; color: var(--color-warning); margin: 0; }

.add-bottom { width: 100%; justify-content: center; margin-top: 4px; }

.icon-btn { width: 28px; height: 28px; padding: 0; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
.danger:hover { color: var(--color-error); }

.status-toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  padding: 8px 18px; border-radius: var(--radius); font-size: 13px;
  background: var(--color-surface); border: 1px solid var(--color-border);
  box-shadow: 0 4px 12px rgba(0,0,0,.2); z-index: 999;
}
.status-toast.ok   { color: var(--color-success); }
.status-toast.err  { color: var(--color-error); }
.status-toast.warn { color: var(--color-warning); }
</style>
