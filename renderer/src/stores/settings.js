import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: 'http://127.0.0.1:18520/api' })

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(null)
  const loading = ref(false)

  async function fetchSettings() {
    loading.value = true
    try {
      const { data } = await api.get('/settings')
      settings.value = data
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(newSettings) {
    const { data } = await api.post('/settings', newSettings)
    settings.value = data
  }

  async function testEngine(engine) {
    const { data } = await api.get(`/${engine}/test`)
    return data
  }

  return { settings, loading, fetchSettings, saveSettings, testEngine }
})
