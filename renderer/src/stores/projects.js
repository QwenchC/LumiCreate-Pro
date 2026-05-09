import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: 'http://127.0.0.1:18520/api' })

export const useProjectStore = defineStore('projects', () => {
  const projects = ref([])
  const loading = ref(false)

  async function fetchProjects() {
    loading.value = true
    try {
      const { data } = await api.get('/projects')
      projects.value = data
    } finally {
      loading.value = false
    }
  }

  async function createProject(name, description = '', folder_id = 'default') {
    const { data } = await api.post('/projects', { name, description, folder_id })
    projects.value.unshift(data)
    return data
  }

  async function deleteProject(id) {
    await api.delete(`/projects/${id}`)
    projects.value = projects.value.filter(p => p.id !== id)
  }

  async function renameProject(id, name) {
    const { data } = await api.put(`/projects/${id}`, { name })
    const idx = projects.value.findIndex(p => p.id === id)
    if (idx !== -1) projects.value[idx] = { ...projects.value[idx], name: data.name }
  }

  async function moveProject(id, folder_id) {
    const { data } = await api.put(`/projects/${id}`, { folder_id })
    const idx = projects.value.findIndex(p => p.id === id)
    if (idx !== -1) projects.value[idx] = { ...projects.value[idx], folder_id: data.folder_id }
  }

  return { projects, loading, fetchProjects, createProject, deleteProject, renameProject, moveProject }
})
