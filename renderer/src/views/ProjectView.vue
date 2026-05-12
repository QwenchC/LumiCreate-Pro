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
      <button class="btn btn-primary btn-sm tab-save-btn" :disabled="!isDirty || saving" @click="saveProject">
        {{ saving ? '保存中...' : '💾 保存' }}
      </button>
      <span v-if="isDirty" class="unsaved-badge">● 未保存</span>
    </div>

    <!-- Tab content -->
    <div class="tab-content">
      <Component
        :is="currentTabComponent"
        :project-id="projectId"
        @dirty="onDirty"
        @saved="onSaved"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { useTabsStore } from '../stores/tabs'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['close-tab', 'go-home'])

const tabsStore = useTabsStore()

const isDirty  = ref(false)
const saving   = ref(false)
const activeTab = ref('manuscript')

const TABS = [
  { key: 'manuscript',  label: '文案创建', icon: '📝' },
  { key: 'characters',  label: '角色管理', icon: '🎭' },
  { key: 'scenes',      label: '分镜设计', icon: '🎞' },
  { key: 'images',      label: '图片生成', icon: '🖼' },
  { key: 'audio',       label: '音频生成', icon: '🎙' },
  { key: 'video',       label: '视频生成', icon: '🎬' },
  { key: 'subtitle',    label: '字幕生成', icon: '💬' },
]

const TAB_COMPONENTS = {
  manuscript:  defineAsyncComponent(() => import('../components/tabs/ManuscriptTab.vue')),
  characters:  defineAsyncComponent(() => import('../components/tabs/CharactersTab.vue')),
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
  saving.value = true
  window.dispatchEvent(new CustomEvent('lumi:save-project', { detail: { projectId: props.projectId } }))
  await new Promise(r => setTimeout(r, 300))
  isDirty.value = false
  tabsStore.setDirty(props.projectId, false)
  saving.value = false
}

onMounted(async () => {
  // Load meta to update tab name
  try {
    const res = await fetch(`http://127.0.0.1:18520/api/projects/${props.projectId}`)
    const data = await res.json()
    if (data?.name) tabsStore.setName(props.projectId, data.name)
  } catch {}
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
