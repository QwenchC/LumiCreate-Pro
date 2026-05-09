<template>
  <div class="tab-panel characters-tab">

    <div class="char-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">角色管理</h3>
        <span class="text-muted" style="font-size:12px">角色外观描述将自动注入图片提示词，保持角色一致性</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-secondary btn-sm" @click="syncFromManuscript" :disabled="syncing">
          {{ syncing ? '同步中...' : '↓ 从文案配置同步' }}
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
      <p class="text-muted" style="font-size:12px">点击「从文案配置同步」可从文案配置中导入角色，<br/>或手动点击「添加角色」创建。</p>
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
            <label class="label-em">✨ 外观描述（英文，注入图片提示词）</label>
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
  return { name: '', role: '', traits: '', appearance: '', negative: '' }
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
      }))
    }
  } catch {}
  window.addEventListener('lumi:save-project', onGlobalSave)
})
onUnmounted(() => window.removeEventListener('lumi:save-project', onGlobalSave))

// ── Sync from manuscript config ───────────────────────────────────────────────
async function syncFromManuscript() {
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
    // Merge: keep existing appearance/negative fields, update name/role/traits
    const existing = Object.fromEntries(characters.value.map(c => [c.name, c]))
    characters.value = configChars.map(c => ({
      name:       c.name       || '',
      role:       c.role       || '',
      traits:     c.traits     || '',
      appearance: existing[c.name]?.appearance || '',
      negative:   existing[c.name]?.negative   || '',
    }))
    markDirty()
    showStatus(`已同步 ${characters.value.length} 个角色`, 'ok')
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
    const res = await fetch(`${API}/projects/${props.projectId}/characters`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ characters: characters.value }),
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

.char-card-body { display: flex; flex-direction: column; gap: 10px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 12px; color: var(--color-text-muted); }
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
