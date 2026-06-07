<template>
  <div class="project-layout">
    <!-- Tabs -->
    <div class="tab-bar">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <span>{{ tab.icon }}</span> {{ tab.label }}
      </button>
      <div class="tab-bar-spacer" />
      <button class="btn btn-ghost btn-sm" :disabled="saving"
              title="把当前项目的对白模式/角色卡保存为模板，下次新建项目可一键复用"
              @click="saveAsTemplateOpen = true">
        📦 另存为模板
      </button>
      <button class="btn btn-secondary btn-sm tab-rocket-btn" :disabled="saving"
              title="按当前项目配置一键串跑：分镜→提示词→图片→音频→字幕"
              @click="orchestratorOpen = true">
        🚀 一键全流程
      </button>
      <button class="btn btn-primary btn-sm tab-save-btn" :disabled="!isDirty || saving" @click="saveProject">
        {{ saving ? '保存中...' : '💾 保存' }}
      </button>
      <span v-if="isDirty" class="unsaved-badge">● 未保存</span>
    </div>

    <!-- B1: Orchestrator panel -->
    <OrchestratorPanel v-if="orchestratorOpen" :project-id="projectId" @close="orchestratorOpen = false" />

    <!-- B3: 另存为模板 -->
    <Teleport to="body">
      <div v-if="saveAsTemplateOpen" class="overlay" @click.self="saveAsTemplateOpen = false">
        <div class="dialog card">
          <h3 class="dialog-title">📦 另存为模板</h3>
          <p class="text-muted" style="margin-bottom:12px;font-size:12px">
            会保存：对白模式 + 角色卡（含 voice / appearance）。<br>
            不会保存：文案正文、分镜、图片、音频、视频。<br>
            模板会出现在主屏「新建项目」对话框的"从模板新建"下拉里。
          </p>
          <div class="form-group">
            <label>模板名称 <span class="required">*</span></label>
            <input v-model="newTemplateName" class="input" placeholder="例：漫剧标准模板"
                   @keyup.enter="saveAsTemplate" autofocus />
          </div>
          <div class="form-group">
            <label>模板描述（可选）</label>
            <textarea v-model="newTemplateDesc" class="input textarea" rows="2"
                      placeholder="简要说明这个模板适用的题材或风格" />
          </div>
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="newTemplateIncludeChars" />
              包含角色卡（appearance / voice / negative）
            </label>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-primary" :disabled="!newTemplateName.trim() || saveAsTemplateBusy"
                    @click="saveAsTemplate">
              {{ saveAsTemplateBusy ? '保存中...' : '保存模板' }}
            </button>
            <button class="btn btn-ghost" @click="saveAsTemplateOpen = false">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Tab content -->
    <div class="tab-content">
      <KeepAlive>
        <Component
          :is="currentTabComponent"
          :project-id="projectId"
          @dirty="onDirty"
          @saved="onSaved"
        />
      </KeepAlive>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { useTabsStore } from '../stores/tabs'
import OrchestratorPanel from '../components/OrchestratorPanel.vue'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['close-tab', 'go-home'])

const tabsStore = useTabsStore()

const isDirty  = ref(false)
const saving   = ref(false)
const orchestratorOpen = ref(false)

// B3: 另存为模板
const saveAsTemplateOpen     = ref(false)
const saveAsTemplateBusy     = ref(false)
const newTemplateName        = ref('')
const newTemplateDesc        = ref('')
const newTemplateIncludeChars = ref(true)

async function saveAsTemplate() {
  if (!newTemplateName.value.trim() || saveAsTemplateBusy.value) return
  saveAsTemplateBusy.value = true
  try {
    const r = await fetch('http://127.0.0.1:18520/api/templates/from-project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id:         props.projectId,
        name:               newTemplateName.value.trim(),
        description:        newTemplateDesc.value.trim(),
        include_characters: newTemplateIncludeChars.value,
      }),
    })
    if (!r.ok) throw new Error(await r.text())
    saveAsTemplateOpen.value = false
    newTemplateName.value = ''
    newTemplateDesc.value = ''
    alert('✓ 模板保存成功')
  } catch (e) {
    alert('保存模板失败: ' + e.message)
  } finally {
    saveAsTemplateBusy.value = false
  }
}

// Active inner tab is stored per-project in the tabs store so it survives
// going home and back without destroying the ProjectView instance.
const activeTab = computed({
  get: () => tabsStore.getInnerTab(props.projectId),
  set: (v) => tabsStore.setInnerTab(props.projectId, v),
})

const TABS = [
  { key: 'manuscript',  label: '文案创建', icon: '📝' },
  { key: 'characters',  label: '角色管理', icon: '🎭' },
  { key: 'elements',    label: '元素库',   icon: '📦' },
  { key: 'scenes',      label: '分镜设计', icon: '🎞' },
  { key: 'images',      label: '图片生成', icon: '🖼' },
  { key: 'audio',       label: '音频生成', icon: '🎙' },
  { key: 'video',       label: '视频生成', icon: '🎬' },
  { key: 'subtitle',    label: '字幕生成', icon: '💬' },
]

const TAB_COMPONENTS = {
  manuscript:  defineAsyncComponent(() => import('../components/tabs/ManuscriptTab.vue')),
  characters:  defineAsyncComponent(() => import('../components/tabs/CharactersTab.vue')),
  elements:    defineAsyncComponent(() => import('../components/tabs/ElementsTab.vue')),
  scenes:      defineAsyncComponent(() => import('../components/tabs/ScenesTab.vue')),
  images:      defineAsyncComponent(() => import('../components/tabs/ImagesTab.vue')),
  audio:       defineAsyncComponent(() => import('../components/tabs/AudioTab.vue')),
  video:       defineAsyncComponent(() => import('../components/tabs/VideoTab.vue')),
  subtitle:    defineAsyncComponent(() => import('../components/tabs/SubtitleTab.vue')),
}

const currentTabComponent = computed(() => TAB_COMPONENTS[activeTab.value])

function onDirty() {
  isDirty.value = true
  tabsStore.setDirty(props.projectId, true)
}
function onSaved() {
  isDirty.value = false
  tabsStore.setDirty(props.projectId, false)
}

async function saveProject() {
  if (saving.value) return
  saving.value = true
  window.dispatchEvent(new CustomEvent('lumi:save-project', { detail: { projectId: props.projectId } }))
  await new Promise(r => setTimeout(r, 300))
  isDirty.value = false
  tabsStore.setDirty(props.projectId, false)
  saving.value = false
}

// B5: 项目级快捷键
//   Ctrl+S        → 保存
//   Ctrl+1-7      → 切 tab
//   Ctrl+Shift+R  → 一键全流程
//   Ctrl+Z / Y    → 由各 tab 自己处理（监听 lumi:undo / lumi:redo 事件）
//   Esc           → 关闭一键全流程面板（如打开中）
function onProjectKey(e) {
  const tag = (e.target?.tagName || '').toLowerCase()
  const inField = tag === 'input' || tag === 'textarea' || e.target?.isContentEditable
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    saveProject()
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'R' || e.key === 'r')) {
    e.preventDefault()
    orchestratorOpen.value = true
    return
  }
  // Ctrl+1-7 切 tab —— inField 时跳过，避免覆盖编辑器内的常用功能
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && /^[1-8]$/.test(e.key) && !inField) {
    const idx = Number(e.key) - 1
    if (TABS[idx]) {
      e.preventDefault()
      activeTab.value = TABS[idx].key
    }
    return
  }
  if (e.key === 'Escape' && orchestratorOpen.value) {
    orchestratorOpen.value = false
  }
  // Ctrl+Z / Ctrl+Shift+Z → 派发自定义事件给当前 tab；只在非编辑状态下接管，避免抢占 textarea 撤销
  if ((e.ctrlKey || e.metaKey) && !inField) {
    if (e.key === 'z' && !e.shiftKey) {
      e.preventDefault()
      window.dispatchEvent(new CustomEvent('lumi:undo', { detail: { tab: activeTab.value } }))
    } else if ((e.key === 'z' && e.shiftKey) || e.key === 'y') {
      e.preventDefault()
      window.dispatchEvent(new CustomEvent('lumi:redo', { detail: { tab: activeTab.value } }))
    }
  }
}

onMounted(async () => {
  // Load meta to update tab name
  try {
    const res = await fetch(`http://127.0.0.1:18520/api/projects/${props.projectId}`)
    const data = await res.json()
    if (data?.name) tabsStore.setName(props.projectId, data.name)
  } catch {}
  window.addEventListener('keydown', onProjectKey)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onProjectKey)
})
</script>

<style scoped>
.project-layout { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.tab-bar {
  display: flex; align-items: center; gap: 2px; padding: 8px 16px 0;
  background: var(--color-surface); border-bottom: 1px solid var(--color-border); flex-shrink: 0;
}
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius) var(--radius) 0 0;
  border: 1px solid transparent; border-bottom: none;
  background: transparent; color: var(--color-text-muted);
  cursor: pointer; font-size: 13px; transition: all var(--transition);
}
.tab-btn.active {
  background: var(--color-bg); color: var(--color-text);
  border-color: var(--color-border); border-bottom-color: var(--color-bg);
  margin-bottom: -1px;
}
.tab-btn:hover:not(.active) { color: var(--color-text); background: var(--color-border); }
.tab-bar-spacer { flex: 1; }
.tab-save-btn { margin-bottom: 4px; }
.unsaved-badge { font-size: 12px; color: var(--color-warning); margin-bottom: 4px; padding: 0 6px; }

.tab-content { flex: 1; overflow: hidden; background: var(--color-bg); }
</style>
