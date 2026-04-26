<template>
  <div class="settings-layout">
    <!-- Sidebar -->
    <aside class="settings-sidebar">
      <div class="settings-header">
        <button class="btn btn-ghost btn-sm back-btn" @click="$router.back()">← 返回</button>
        <h2 class="settings-title">设置</h2>
      </div>
      <nav class="settings-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="nav-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span>{{ tab.icon }}</span> {{ tab.label }}
          <span class="nav-status" :class="testStatus[tab.key]" />
        </button>
      </nav>
    </aside>

    <!-- Content -->
    <main class="settings-main" v-if="settings">
      <!-- General -->
      <section v-if="activeTab === 'general'" class="settings-section">
        <h3 class="section-title">通用设置</h3>
        <div class="form-group">
          <label>项目存储目录</label>
          <div class="input-row">
            <input v-model="settings.projects_dir" class="input" readonly />
            <button class="btn btn-secondary" @click="chooseDir">选择</button>
          </div>
          <p class="hint">所有项目将保存在此目录下</p>
        </div>
      </section>

      <!-- Text engine -->
      <section v-if="activeTab === 'text'" class="settings-section">
        <h3 class="section-title">文本生成引擎</h3>
        <div class="form-group">
          <label>引擎类型</label>
          <div class="radio-group">
            <label v-for="(label, val) in TEXT_ENGINES" :key="val" class="radio-item">
              <input type="radio" :value="val" v-model="settings.text_engine.engine_type" />
              {{ label }}
            </label>
          </div>
        </div>
        <div class="form-group">
          <label>API 地址</label>
          <input v-model="settings.text_engine.base_url" class="input" placeholder="http://localhost:11434" />
        </div>
        <div class="form-group" v-if="settings.text_engine.engine_type !== 'ollama' && settings.text_engine.engine_type !== 'lmstudio'">
          <label>API Key</label>
          <input v-model="settings.text_engine.api_key" class="input" type="password" placeholder="sk-..." />
        </div>
        <div class="form-group">
          <label>默认模型</label>
          <div class="input-row">
            <input v-model="settings.text_engine.model" class="input" placeholder="例：deepseek-chat" />
            <button class="btn btn-secondary" :disabled="testing" @click="fetchModels">拉取模型列表</button>
          </div>
          <div v-if="modelList.length" class="model-pills">
            <span v-for="m in modelList" :key="m" class="model-pill" @click="settings.text_engine.model = m">{{ m }}</span>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group half">
            <label>温度 ({{ settings.text_engine.temperature }})</label>
            <input type="range" min="0" max="2" step="0.05" v-model.number="settings.text_engine.temperature" class="slider" />
          </div>
          <div class="form-group half">
            <label>Top-P ({{ settings.text_engine.top_p }})</label>
            <input type="range" min="0" max="1" step="0.05" v-model.number="settings.text_engine.top_p" class="slider" />
          </div>
        </div>
      </section>

      <!-- Image engine -->
      <section v-if="activeTab === 'image'" class="settings-section">
        <h3 class="section-title">图片生成引擎（ComfyUI）</h3>
        <div class="form-group">
          <label>ComfyUI 地址</label>
          <input v-model="settings.image_engine.comfyui_url" class="input" placeholder="http://localhost:8188" />
        </div>
        <div class="form-group">
          <label>工作流本地目录 <span class="form-hint-inline">（优先于API获取，推荐填写）</span></label>
          <input
            v-model="settings.image_engine.workflow_dir"
            class="input"
            placeholder="例：F:/ComfyUI-aki/ComfyUI/user/default/workflows"
          />
          <p class="form-hint">填写 ComfyUI 工作流文件夹的绝对路径，可直接读取本地 .json 工作流，无需依赖 ComfyUI API 版本</p>
        </div>
        <div class="form-group">
          <label>默认工作流</label>
          <input v-model="settings.image_engine.default_workflow" class="input" placeholder="工作流名称（不含 .json）" />
        </div>
        <div class="form-group">
          <label>默认生成次数</label>
          <input type="number" v-model.number="settings.image_engine.default_gen_count" class="input" min="1" max="10" style="width:80px" />
        </div>
        <div class="form-group">
          <label>画面尺寸预设</label>
          <div class="preset-btns">
            <button
              v-for="p in IMG_PRESETS" :key="p.label"
              class="btn btn-sm"
              :class="isPresetActive(p) ? 'btn-primary' : 'btn-secondary'"
              @click="applyPreset(p)"
            >{{ p.label }}</button>
          </div>
          <div class="form-row" style="margin-top:8px">
            <div class="form-group half">
              <label>宽度 (px)</label>
              <input type="number" v-model.number="settings.image_engine.image_width" class="input" min="64" max="8192" step="8" />
            </div>
            <div class="form-group half">
              <label>高度 (px)</label>
              <input type="number" v-model.number="settings.image_engine.image_height" class="input" min="64" max="8192" step="8" />
            </div>
          </div>
          <p class="form-hint">当前：{{ settings.image_engine.image_width }} × {{ settings.image_engine.image_height }} px</p>
        </div>
      </section>

      <!-- Audio engine -->
      <section v-if="activeTab === 'audio'" class="settings-section">
        <h3 class="section-title">语音生成引擎</h3>
        <div class="form-group">
          <label>引擎类型</label>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" value="gptsovits" v-model="settings.audio_engine.engine_type" />
              GPT-SoVITS（本地 API）
            </label>
            <label class="radio-item">
              <input type="radio" value="manual" v-model="settings.audio_engine.engine_type" />
              手动导入音频
            </label>
          </div>
        </div>
        <div class="form-group" v-if="settings.audio_engine.engine_type === 'gptsovits'">
          <label>API 地址</label>
          <input v-model="settings.audio_engine.api_url" class="input" placeholder="http://localhost:9880" />
        </div>
        <div class="form-group">
          <label>默认生成版本数</label>
          <input type="number" v-model.number="settings.audio_engine.default_gen_count" class="input" min="1" max="10" style="width:80px" />
        </div>
      </section>

      <!-- Video engine -->
      <section v-if="activeTab === 'video'" class="settings-section">
        <h3 class="section-title">视频生成引擎（ComfyUI）</h3>
        <div class="form-group">
          <label>ComfyUI 地址</label>
          <input v-model="settings.video_engine.comfyui_url" class="input" placeholder="http://localhost:8188" />
        </div>
        <div class="form-group">
          <label>默认分辨率</label>
          <select v-model="settings.video_engine.resolution" class="input select">
            <option>1920x1080</option>
            <option>1280x720</option>
            <option>3840x2160</option>
          </select>
        </div>
        <div class="form-group">
          <label>帧率</label>
          <select v-model.number="settings.video_engine.fps" class="input select">
            <option :value="24">24 fps</option>
            <option :value="30">30 fps</option>
            <option :value="60">60 fps</option>
          </select>
        </div>
      </section>

      <!-- Footer actions -->
      <div class="settings-footer">
        <div class="footer-left">
          <button v-if="activeTab !== 'general'" class="btn btn-secondary" :disabled="testing" @click="testConnection">
            {{ testing ? '测试中...' : '测试连接' }}
          </button>
          <span v-if="testResult" class="test-result" :class="testResult.success ? 'ok' : 'err'">
            {{ testResult.success ? '✓' : '✗' }} {{ testResult.message }}
          </span>
        </div>
        <div style="display:flex;gap:10px">
          <button class="btn btn-ghost" @click="$router.back()">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>
    </main>

    <div v-else class="loading-state">
      <div class="spinner" />
      <p>加载设置中...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '../stores/settings'
import axios from 'axios'

const api = axios.create({ baseURL: 'http://127.0.0.1:18520/api' })

const store = useSettingsStore()
const settings = ref(null)
const activeTab = ref('general')
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)
const modelList = ref([])
const testStatus = ref({ text: '', image: '', audio: '', video: '' })

const tabs = [
  { key: 'general', label: '通用',     icon: '⚙' },
  { key: 'text',    label: '文本引擎', icon: '💬' },
  { key: 'image',   label: '图片引擎', icon: '🖼' },
  { key: 'audio',   label: '语音引擎', icon: '🎙' },
  { key: 'video',   label: '视频引擎', icon: '🎬' },
]

const TEXT_ENGINES = {
  ollama:       'Ollama（本地）',
  lmstudio:     'LM Studio（本地）',
  deepseek:     'DeepSeek API',
  openai_compat:'其他 OpenAI 兼容'
}

const IMG_PRESETS = [
  { label: '16:9 高清',   w: 1920, h: 1080 },
  { label: '16:9 竖版',   w: 1280, h: 720  },
  { label: '9:16 竖屏',   w: 1080, h: 1920 },
  { label: '9:16 小竖',   w: 720,  h: 1280 },
  { label: '1:1',         w: 1024, h: 1024 },
]

function isPresetActive(p) {
  return settings.value?.image_engine?.image_width  === p.w &&
         settings.value?.image_engine?.image_height === p.h
}
function applyPreset(p) {
  if (!settings.value) return
  settings.value.image_engine.image_width  = p.w
  settings.value.image_engine.image_height = p.h
}

onMounted(async () => {
  await store.fetchSettings()
  settings.value = JSON.parse(JSON.stringify(store.settings))
})

async function save() {
  saving.value = true
  try {
    await store.saveSettings(settings.value)
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  const engineMap = { text: 'text-engine', image: 'image-engine', audio: 'audio-engine', video: 'video-engine' }
  try {
    const { data } = await api.get(`/${engineMap[activeTab.value]}/test`)
    testResult.value = data
    testStatus.value[activeTab.value] = data.success ? 'ok' : 'err'
    if (data.models?.length) modelList.value = data.models
  } catch (e) {
    testResult.value = { success: false, message: e.message }
    testStatus.value[activeTab.value] = 'err'
  } finally {
    testing.value = false
  }
}

async function fetchModels() {
  await testConnection()
}

async function chooseDir() {
  const dir = await window.electronAPI?.selectFolder()
  if (dir) settings.value.projects_dir = dir
}
</script>

<style scoped>
.settings-layout { display: flex; height: 100%; overflow: hidden; }

.settings-sidebar {
  width: 200px; background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex; flex-direction: column; flex-shrink: 0;
}
.settings-header { padding: 14px 12px 8px; border-bottom: 1px solid var(--color-border); }
.settings-title { font-size: 16px; font-weight: 700; margin-top: 8px; }
.back-btn { font-size: 12px; }
.settings-nav { flex: 1; padding: 10px 8px; }
.nav-item {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 10px; border-radius: var(--radius);
  background: transparent; border: none; color: var(--color-text-muted);
  cursor: pointer; font-size: 13px; transition: background var(--transition);
  position: relative;
}
.nav-item.active, .nav-item:hover { background: var(--color-surface-2); color: var(--color-text); }
.nav-status { width: 7px; height: 7px; border-radius: 50%; background: transparent; margin-left: auto; }
.nav-status.ok { background: var(--color-success); }
.nav-status.err { background: var(--color-error); }

.settings-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.settings-section { flex: 1; padding: 24px 28px; overflow-y: auto; }
.section-title { font-size: 17px; font-weight: 700; margin-bottom: 24px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }

.form-group { margin-bottom: 18px; }
.form-group label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--color-text-muted); }
.form-row { display: flex; gap: 20px; }
.half { flex: 1; }
.input-row { display: flex; gap: 8px; }
.hint { font-size: 11px; color: var(--color-text-muted); margin-top: 5px; }
.form-hint { font-size: 11px; color: var(--color-text-muted); margin-top: 5px; }
.form-hint-inline { font-size: 11px; color: var(--color-text-muted); font-weight: 400; }
.preset-btns { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }

.radio-group { display: flex; flex-direction: column; gap: 8px; }
.radio-item { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; }
.radio-item input { accent-color: var(--color-accent); }

.slider { width: 100%; accent-color: var(--color-accent); cursor: pointer; }
.select { appearance: none; cursor: pointer; }

.model-pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.model-pill {
  padding: 3px 10px; border-radius: 99px; font-size: 11px;
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  cursor: pointer; transition: border-color var(--transition);
}
.model-pill:hover { border-color: var(--color-accent); }

.settings-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 28px; border-top: 1px solid var(--color-border); flex-shrink: 0;
}
.footer-left { display: flex; align-items: center; gap: 12px; }
.test-result { font-size: 13px; }
.test-result.ok { color: var(--color-success); }
.test-result.err { color: var(--color-error); }

.loading-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px;
  color: var(--color-text-muted);
}
.spinner {
  width: 32px; height: 32px; border-radius: 50%;
  border: 3px solid var(--color-border); border-top-color: var(--color-accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
