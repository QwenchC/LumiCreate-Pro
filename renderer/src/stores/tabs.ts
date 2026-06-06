import { defineStore } from 'pinia'
import { ref } from 'vue'

interface ProjectTab {
  id: string          // projectId
  name: string
  isDirty: boolean
}

/**
 * Open project tabs store. Migrated to TypeScript in F1.
 * No behavior change vs. the previous tabs.js.
 */
export const useTabsStore = defineStore('tabs', () => {
  const tabs      = ref<ProjectTab[]>([])
  const activeId  = ref<string | null>(null)
  const innerTabs = ref<Record<string, string>>({})

  function openTab(projectId: string, projectName?: string) {
    const existing = tabs.value.find(t => t.id === projectId)
    if (existing) {
      activeId.value = projectId
      return
    }
    tabs.value.push({ id: projectId, name: projectName || '项目', isDirty: false })
    activeId.value = projectId
  }

  function activateTab(projectId: string) {
    activeId.value = projectId
  }

  /** Returns true if the tab was cleanly closed, false if cancelled */
  function closeTab(projectId: string): boolean {
    const idx = tabs.value.findIndex(t => t.id === projectId)
    if (idx === -1) return true
    tabs.value.splice(idx, 1)
    const it = { ...innerTabs.value }
    delete it[projectId]
    innerTabs.value = it
    if (activeId.value === projectId) {
      const next = tabs.value[Math.max(0, idx - 1)]
      activeId.value = next ? next.id : null
    }
    return true
  }

  function setInnerTab(projectId: string, tabKey: string) {
    innerTabs.value = { ...innerTabs.value, [projectId]: tabKey }
  }

  function getInnerTab(projectId: string): string {
    return innerTabs.value[projectId] || 'manuscript'
  }

  function setDirty(projectId: string, dirty: boolean) {
    const t = tabs.value.find(t => t.id === projectId)
    if (t) t.isDirty = dirty
  }

  function setName(projectId: string, name: string) {
    const t = tabs.value.find(t => t.id === projectId)
    if (t) t.name = name
  }

  return {
    tabs, activeId, innerTabs,
    openTab, activateTab, closeTab,
    setInnerTab, getInnerTab,
    setDirty, setName,
  }
})
