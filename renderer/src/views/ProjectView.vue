<template>
  <div class="project-layout">
    <!-- Project header -->
    <div class="project-header">
      <button class="btn btn-ghost btn-sm" @click="goBack">← 返回</button>
      <div class="project-header-info">
        <h2 class="project-header-name">{{ meta?.name ?? '加载中...' }}</h2>
        <span v-if="isDirty" class="unsaved-badge">● 未保存</span>
      </div>
      <button class="btn btn-primary btn-sm" :disabled="!isDirty || saving" @click="saveProject">
        {{ saving ? '保存中...' : '💾 保存' }}
      </button>
    </div>

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
    </div>

    <!-- Tab content -->
    <div class="tab-content">
      <Component :is="currentTabComponent" :project-id="projectId" @dirty="isDirty = true" @saved="isDirty = false" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { defineAsyncComponent } from 'vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id)

const meta = ref(null)
const isDirty = ref(false)
const saving = ref(false)
const activeTab = ref('manuscript')

const TABS = [
  { key: 'manuscript', label: '文案创建', icon: '📝' },
  { key: 'scenes',     label: '分镜设计', icon: '🎞' },
  { key: 'images',     label: '图片生成', icon: '🖼' },
  { key: 'audio',      label: '音频生成', icon: '🎙' },
  { key: 'video',      label: '视频生成', icon: '🎬' },
]

// Load tab components lazily
const TAB_COMPONENTS = {
  manuscript: defineAsyncComponent(() => import('../components/tabs/ManuscriptTab.vue')),
  scenes:     defineAsyncComponent(() => import('../components/tabs/ScenesTab.vue')),
  images:     defineAsyncComponent(() => import('../components/tabs/ImagesTab.vue')),
  audio:      defineAsyncComponent(() => import('../components/tabs/AudioTab.vue')),
  video:      defineAsyncComponent(() => import('../components/tabs/VideoTab.vue')),
}

const currentTabComponent = computed(() => TAB_COMPONENTS[activeTab.value])

async function saveProject() {
  saving.value = true
  window.dispatchEvent(new CustomEvent('lumi:save-project'))
  await new Promise(r => setTimeout(r, 300))
  isDirty.value = false
  saving.value = false
}

function goBack() {
  if (isDirty.value) {
    window.__lumiUnsaved = true
    window.electronAPI?.windowClose()
    return
  }
  router.push('/')
}

onMounted(async () => {
  // Load project meta from backend
  try {
    const res = await fetch(`http://127.0.0.1:18520/api/projects/${projectId.value}`)
    meta.value = await res.json()
  } catch {}

  window.__lumiUnsaved = false
  window.electronAPI?.onMenuSaveProject(() => saveProject())
})

onUnmounted(() => {
  window.__lumiUnsaved = false
  window.electronAPI?.removeAllListeners('menu:save-project')
})
</script>

<style scoped>
.project-layout { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.project-header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; border-bottom: 1px solid var(--color-border);
  background: var(--color-surface); flex-shrink: 0;
}
.project-header-info { flex: 1; display: flex; align-items: center; gap: 10px; }
.project-header-name { font-size: 15px; font-weight: 700; }
.unsaved-badge { font-size: 12px; color: var(--color-warning); }

.tab-bar {
  display: flex; gap: 2px; padding: 8px 16px 0;
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

.tab-content { flex: 1; overflow: hidden; background: var(--color-bg); }
</style>
