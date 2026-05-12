import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Each tab: { id: String (projectId), name: String, isDirty: Boolean }
 */
export const useTabsStore = defineStore('tabs', () => {
  const tabs      = ref([])          // open project tabs
  const activeId  = ref(null)        // currently visible project id
  const innerTabs = ref({})          // projectId → active inner tab key

  function openTab(projectId, projectName) {
    const existing = tabs.value.find(t => t.id === projectId)
    if (existing) {
      activeId.value = projectId
      return
    }
    tabs.value.push({ id: projectId, name: projectName || '项目', isDirty: false })
    activeId.value = projectId
  }

  function activateTab(projectId) {
    activeId.value = projectId
  }

  /** Returns true if the tab was cleanly closed, false if cancelled */
  function closeTab(projectId) {
    const idx = tabs.value.findIndex(t => t.id === projectId)
    if (idx === -1) return true
    tabs.value.splice(idx, 1)
    // Clean up inner tab state
    const it = { ...innerTabs.value }
    delete it[projectId]
    innerTabs.value = it
    // Switch to nearest remaining tab
    if (activeId.value === projectId) {
      const next = tabs.value[Math.max(0, idx - 1)]
      activeId.value = next ? next.id : null
    }
    return true
  }

  function setInnerTab(projectId, tabKey) {
    innerTabs.value = { ...innerTabs.value, [projectId]: tabKey }
  }

  function getInnerTab(projectId) {
    return innerTabs.value[projectId] || 'manuscript'
  }

  function setDirty(projectId, dirty) {
    const t = tabs.value.find(t => t.id === projectId)
    if (t) t.isDirty = dirty
  }

  function setName(projectId, name) {
    const t = tabs.value.find(t => t.id === projectId)
    if (t) t.name = name
  }

  return { tabs, activeId, innerTabs, openTab, activateTab, closeTab, setInnerTab, getInnerTab, setDirty, setName }
})
