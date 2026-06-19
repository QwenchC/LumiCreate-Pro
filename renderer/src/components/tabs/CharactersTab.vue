<template>
  <div class="tab-panel characters-tab">

    <div class="char-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">角色管理</h3>
        <span class="text-muted" style="font-size:12px">角色外观描述将自动注入图片提示词，保持角色一致性</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-secondary btn-sm" @click="openImportFromProject" :disabled="syncing">⇨ 从其他项目导入</button>
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
          <div class="form-group" v-if="audioEngine === 'msedge'">
            <label>
              微软神经语音
              <span class="text-muted" style="font-size:11px">（仅 Edge TTS 引擎下生效）</span>
            </label>
            <select v-model="char.voice" class="input select-compact" @change="markDirty">
              <option value="">— 跟随设置默认 —</option>
              <optgroup v-for="g in voiceGroupsFor(char.voice)" :key="g.gender" :label="g.label">
                <option v-for="v in g.items" :key="v.value" :value="v.value">{{ v.label }}</option>
              </optgroup>
            </select>
            <p class="field-hint">
              不同角色配不同音色（按性别 / 年龄选）；留空则用设置里的默认音色。
              <span v-if="availableVoiceList.length">
                已按"全部测试"通过名单过滤（{{ availableVoiceList.length }} 个可用，不通过的不会出现）。
              </span>
              <span v-else style="color:var(--color-warning, #fa3)">
                还没在设置里跑过音色测试，可先到设置 → 语音引擎 → 微软神经语音 点「测试全部音色」。
              </span>
            </p>
          </div>

          <!-- 轮 4: 立绘画廊 -->
          <div class="form-group">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <label style="margin:0">🎨 立绘</label>
              <span class="text-muted" style="font-size:11px">
                角色一致性参考；主立绘 ★ 用作后续图生图的默认参考
              </span>
              <button class="btn btn-secondary btn-xs" style="margin-left:auto"
                      :disabled="!char.name?.trim()"
                      @click="openPortraitGen(char)">
                🎨 生成立绘
              </button>
            </div>
            <div class="portraits-row" v-if="(char._portraits || []).length">
              <div v-for="p in char._portraits" :key="p.filename"
                   class="portrait-card"
                   :class="{ primary: p.is_primary }"
                   @click="openPortraitPreview(char, p)"
                   title="点击放大预览">
                <img :src="portraitUrl(char.name, p.filename)" class="portrait-img" />
                <div class="portrait-actions" @click.stop>
                  <button class="portrait-mini" :title="p.is_primary ? '已是主立绘' : '设为主立绘'"
                          :disabled="p.is_primary"
                          @click.stop="setPrimaryPortrait(char, p)">
                    {{ p.is_primary ? '★' : '☆' }}
                  </button>
                  <button class="portrait-mini danger" title="删除"
                          @click.stop="deletePortrait(char, p)">🗑</button>
                </div>
                <div class="portrait-name truncate" :title="p.workflow_name">
                  {{ p.workflow_name || '—' }}
                </div>
              </div>
            </div>
            <p v-else class="text-muted" style="font-size:11px;margin:4px 0 0">
              暂无立绘 — 点上方"🎨 生成立绘"建立第一张
            </p>
          </div>
        </div>
      </div>

      <button class="btn btn-secondary add-bottom" @click="addCharacter">＋ 添加角色</button>
    </div>

    <!-- Status -->
    <div v-if="statusMsg" class="status-toast" :class="statusType">{{ statusMsg }}</div>

    <!-- 轮 4: 立绘生成弹窗 -->
    <Teleport to="body">
      <div v-if="portraitGenDialog.show" class="overlay" @click.self="portraitGenDialog.show = false">
        <div class="dialog card" style="min-width:540px;max-width:640px">
          <h3 class="dialog-title">🎨 生成立绘 · {{ portraitGenDialog.charName }}</h3>

          <div class="form-group">
            <label>工作流（文生图）</label>
            <select v-model="portraitGenDialog.workflowName" class="input">
              <option value="" disabled>请选择…</option>
              <option v-for="w in t2iWorkflows" :key="w" :value="w">{{ w }}</option>
            </select>
            <p class="field-hint" v-if="!t2iWorkflows.length">
              没有可用的文生图工作流。请到 ComfyUI 的 user/default/workflows 目录添加 t2i 工作流并刷新。
            </p>
          </div>

          <div class="form-group">
            <label>画风</label>
            <select v-model="portraitGenDialog.stylePreset" class="input">
              <option v-for="p in STYLE_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
            <input v-if="portraitGenDialog.stylePreset === '__custom__'"
                   v-model="portraitGenDialog.customStyle"
                   class="input" placeholder="输入英文画风提示词…"
                   style="margin-top:6px" />
          </div>

          <div class="form-group">
            <label>Prompt（英文，会注入角色 appearance）</label>
            <textarea v-model="portraitGenDialog.prompt"
                      class="input textarea" rows="4"
                      placeholder="character portrait, full body, white background, ..."></textarea>
            <p class="field-hint">
              默认包含该角色的 appearance 标签 + "character portrait, full body, neutral pose, plain background"；
              画风前缀在提交时自动拼到最前面。
            </p>
          </div>

          <div class="form-group">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input type="checkbox" v-model="portraitGenDialog.whiteBg"
                     :disabled="portraitGenDialog.standardPose" />
              纯白背景立绘（用于多图参考视频）
            </label>
            <p class="field-hint">
              勾选后：提交前用<strong>文本 AI 引擎</strong>把提示词优化成「单人 · 全身 · 纯白背景」，
              并附强力背景负面词 → 生成干净的纯白背景立绘,可直接作为 LTX 多图参考的角色参考图。
            </p>
          </div>

          <div class="form-group">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input type="checkbox" v-model="portraitGenDialog.standardPose" />
              标准造型（固定姿势 · 空白背景 · Z-Image ControlNet）
            </label>
            <p class="field-hint">
              勾选后：用<strong>固定标准姿势图</strong>做 ControlNet 约束 + 该角色 appearance，
              生成<strong>空白背景</strong>的标准姿势角色图（尺寸按姿势图比例自适应，不限竖幅）。
              结果自动标为白底立绘，可标星设为该角色默认参考图。<br/>
              <span v-if="portraitGenDialog.standardPose" style="color:var(--accent)">
                此模式忽略上方「工作流 / Prompt」（自动用角色 appearance + 空白背景约束），画风可保留。
              </span>
            </p>
          </div>

          <div v-if="portraitGenDialog.progress" class="form-group">
            <p style="font-size:12px">{{ portraitGenDialog.progress }}</p>
          </div>

          <div class="dialog-actions">
            <button class="btn btn-ghost" :disabled="portraitGenDialog.running"
                    @click="portraitGenDialog.show = false">取消</button>
            <button class="btn btn-primary"
                    :disabled="portraitGenDialog.running || (!portraitGenDialog.standardPose && (!portraitGenDialog.workflowName || !portraitGenDialog.prompt?.trim()))"
                    @click="runPortraitGen">
              {{ portraitGenDialog.running ? '生成中…' : (portraitGenDialog.standardPose ? '▶ 生成标准造型' : '▶ 开始生成') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Import from other project dialog -->
    <Teleport to="body">
      <div v-if="importProjectDialog.show" class="overlay" @click.self="importProjectDialog.show = false">
        <div class="dialog card" style="min-width:480px;max-width:600px">
          <h3 class="dialog-title">从其他项目导入角色</h3>

          <!-- step 1: pick project -->
          <div v-if="!importProjectDialog.sourceChars">
            <div class="form-group">
              <label>选择来源项目</label>
              <select v-model="importProjectDialog.selectedProjectId" class="input">
                <option value="">请选择…</option>
                <option v-for="p in importProjectDialog.projects" :key="p.id" :value="p.id"
                  :disabled="p.id === props.projectId">{{ p.name }}</option>
              </select>
            </div>
            <div class="dialog-actions">
              <button class="btn btn-primary" :disabled="!importProjectDialog.selectedProjectId || importProjectDialog.loading"
                @click="loadImportProjectChars">
                {{ importProjectDialog.loading ? '加载中…' : '下一步' }}
              </button>
              <button class="btn btn-ghost" @click="importProjectDialog.show = false">取消</button>
            </div>
          </div>

          <!-- step 2: pick characters -->
          <div v-else>
            <p class="text-muted" style="font-size:13px;margin-bottom:12px">
              勾选要导入的角色（已存在同名角色将询问是否覆盖）：
            </p>
            <div v-if="!importProjectDialog.sourceChars.length" class="text-muted" style="font-size:13px">
              该项目暂无角色
            </div>
            <div v-else class="import-char-list">
              <label v-for="(c, i) in importProjectDialog.sourceChars" :key="i" class="import-char-row">
                <input type="checkbox" :value="i" v-model="importProjectDialog.selectedIndices" />
                <span class="import-char-name">{{ c.name || '(无名)' }}</span>
                <span class="import-char-role text-muted">{{ c.role }}</span>
              </label>
            </div>
            <div class="dialog-actions" style="margin-top:16px">
              <button class="btn btn-primary"
                :disabled="!importProjectDialog.selectedIndices.length"
                @click="doImportFromProject">
                导入已选（{{ importProjectDialog.selectedIndices.length }}）
              </button>
              <button class="btn btn-ghost" @click="importProjectDialog.sourceChars = null; importProjectDialog.selectedIndices = []">返回</button>
              <button class="btn btn-ghost" @click="importProjectDialog.show = false">取消</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 立绘大图预览 -->
    <Teleport to="body">
      <div v-if="portraitLightbox" class="portrait-lightbox" @click.self="closePortraitPreview">
        <button class="pl-close" @click="closePortraitPreview">✕</button>
        <button class="pl-nav pl-prev" v-if="portraitLightbox.list.length > 1"
                @click="portraitLightboxNav(-1)">‹</button>
        <div class="pl-body">
          <img :src="portraitUrl(portraitLightbox.charName, portraitLightbox.list[portraitLightbox.index].filename)"
               class="pl-img" />
          <div class="pl-footer">
            {{ portraitLightbox.charName }} ·
            {{ portraitLightbox.list[portraitLightbox.index].filename }}
            <span v-if="portraitLightbox.list.length > 1">
              · {{ portraitLightbox.index + 1 }} / {{ portraitLightbox.list.length }}
            </span>
          </div>
        </div>
        <button class="pl-nav pl-next" v-if="portraitLightbox.list.length > 1"
                @click="portraitLightboxNav(1)">›</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { filterVoices, groupByGender } from '../../data/msedgeVoices'

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://127.0.0.1:18520/api'

const characters = ref([])
const isDirty  = ref(false)
const saving   = ref(false)
const syncing  = ref(false)
const statusMsg  = ref('')
const statusType = ref('')
const audioEngine = ref('indextts')  // 'indextts' | 'gptsovits' | 'msedge' | 'manual'
const availableVoiceList = ref([])    // settings.audio_engine.msedge_available_voices

// ── 轮 4: 立绘 ───────────────────────────────────────────────────────────────
const t2iWorkflows = ref([])
// 与 ImagesTab 共用一套画风预设
const STYLE_PRESETS = [
  { label: '— 无画风 —', value: '' },
  { label: '二次元动漫', value: 'anime style, 2d animation, vibrant colors, clean linework' },
  { label: '写实风格',   value: 'photorealistic, realistic, high detail, cinematic lighting' },
  { label: '水彩插画',   value: 'watercolor illustration, soft colors, painted texture, artistic' },
  { label: '赛博朋克',   value: 'cyberpunk style, neon lights, futuristic city, dark atmosphere' },
  { label: '国风水墨',   value: 'Chinese ink painting, traditional brush strokes, elegant, minimalist' },
  { label: '像素风格',   value: 'pixel art, retro 16-bit style' },
  { label: '自定义',    value: '__custom__' },
]
const portraitGenDialog = reactive({
  show: false, charName: '', workflowName: '',
  prompt: '',         // 用户编辑的主提示词（不含画风前缀）
  stylePreset: '',    // 画风预设值或 '__custom__'
  customStyle: '',    // 自定义画风文本
  whiteBg: false,     // v1.6: 纯白背景立绘（供 MSR 多图参考视频）
  standardPose: false, // v1.6.1: 标准造型（Z-Image ControlNet 固定姿势 + 空白背景）
  running: false, progress: '',
})

function portraitUrl(charName, filename) {
  const enc = encodeURIComponent(charName)
  return `${API}/projects/${props.projectId}/characters/${enc}/portraits/file/${filename}`
}

async function loadT2iWorkflows() {
  try {
    // image_engine.workflow-info 可分类；先取全部 workflow，挨个 classify
    const r = await fetch(`${API}/image-engine/workflows`)
    if (!r.ok) return
    const all = await r.json()
    const results = await Promise.all(all.map(async name => {
      try {
        const info = await fetch(`${API}/image-engine/workflow-info?workflow_name=${encodeURIComponent(name)}`)
        if (!info.ok) return null
        const j = await info.json()
        return j.kind === 't2i' ? name : null
      } catch { return null }
    }))
    t2iWorkflows.value = results.filter(Boolean)
  } catch {}
}

async function loadCharacterPortraits(char) {
  if (!char?.name) return
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/characters/${encodeURIComponent(char.name)}/portraits`)
    if (r.ok) {
      char._portraits = (await r.json()).portraits || []
    }
  } catch {}
}

async function openPortraitGen(char) {
  if (!char?.name?.trim()) return
  if (!t2iWorkflows.value.length) await loadT2iWorkflows()
  portraitGenDialog.charName = char.name
  portraitGenDialog.workflowName = t2iWorkflows.value[0] || ''
  // 默认 prompt：拼接 appearance
  const app = (char.appearance || '').trim()
  const base = 'character portrait, full body, neutral pose, plain background, masterpiece, best quality'
  portraitGenDialog.prompt = app ? `${app}, ${base}` : base
  // 从全局设置带入默认画风
  try {
    const r = await fetch(`${API}/settings`)
    if (r.ok) {
      const s = await r.json()
      const ie = s.image_engine || {}
      portraitGenDialog.stylePreset = ie.style_preset ?? ''
      portraitGenDialog.customStyle = ie.custom_style_text ?? ''
    }
  } catch {}
  portraitGenDialog.whiteBg  = false
  portraitGenDialog.standardPose = false
  portraitGenDialog.progress = ''
  portraitGenDialog.running  = false
  portraitGenDialog.show     = true
}

async function runPortraitGen() {
  const dlg = portraitGenDialog
  if (dlg.running) return
  dlg.running  = true
  dlg.progress = '提交到 ComfyUI…'
  try {
    const ch = characters.value.find(c => c.name === dlg.charName)
    const style = dlg.stylePreset === '__custom__'
      ? (dlg.customStyle || '').trim()
      : (dlg.stylePreset || '').trim()

    let resp
    // 上传立绘时用到的元数据（按模式不同）
    let uploadWhiteBg  = dlg.whiteBg
    let uploadWorkflow = dlg.workflowName
    let uploadPrompt   = dlg.prompt

    if (dlg.standardPose) {
      // v1.6.1: 标准造型 —— 固定姿势图(ControlNet) + 角色 appearance + 空白背景，尺寸自适应
      dlg.progress = '提交标准造型（Z-Image ControlNet）…'
      resp = await fetch(`${API}/image-engine/generate-standard-pose`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          appearance: (ch?.appearance || dlg.prompt || '').trim(),
          style,
        }),
      })
      uploadWhiteBg  = true                       // 空白背景 → 标记白底（供 MSR 参考）
      uploadWorkflow = 'Z-Image-Turbo-ControlNet'
      uploadPrompt   = `标准造型: ${[style, (ch?.appearance || '').trim()].filter(Boolean).join(', ')}`
    } else {
      // v1.6: 纯白背景 → 先用文本 AI 引擎优化提示词（单人/全身/纯白背景）+ 取强力背景负面词
      let promptBody = dlg.prompt.trim()
      let negative = ''
      if (dlg.whiteBg) {
        dlg.progress = '文本 AI 优化纯白背景提示词…'
        try {
          const wr = await fetch(`${API}/text-engine/optimize-white-bg-portrait`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ appearance: ch?.appearance || '', base_prompt: promptBody }),
          })
          if (wr.ok) {
            const j = await wr.json()
            if (j.prompt) promptBody = j.prompt
            negative = j.negative || ''
          }
        } catch {}
      }
      // 拼出最终 prompt：画风前缀 + 优化后/用户提示词
      const fullPrompt = [style, promptBody].filter(Boolean).join(', ')

      // 调 image-engine 单图 SSE 生成（不传 seed → 后端随机）
      dlg.progress = '提交到 ComfyUI…'
      resp = await fetch(`${API}/image-engine/generate-stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_name:   dlg.workflowName,
          scene_id:        `__portrait__${dlg.charName}`,
          frame_type:      'portrait',
          slot_index:      0,
          positive_prompt: fullPrompt,
          negative_prompt: negative,
          width:           1080, height: 1920,   // 立绘固定竖幅
        }),
      })
    }
    if (!resp.ok) throw new Error(await resp.text())

    let imageB64 = ''
    const reader = resp.body.getReader(); const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          if (ev.event === 'progress' && ev.value && ev.max) {
            dlg.progress = `生成中… ${ev.value}/${ev.max}`
          } else if (ev.event === 'completed') {
            const first = (ev.images || [])[0]
            if (first?.data) imageB64 = first.data
          } else if (ev.event === 'error') {
            throw new Error(ev.message || '生成失败')
          }
        } catch {}
      }
    }
    if (!imageB64) throw new Error('没有取到生成结果')

    // 2) 上传到角色立绘 endpoint
    dlg.progress = '保存中…'
    const up = await fetch(
      `${API}/projects/${props.projectId}/characters/${encodeURIComponent(dlg.charName)}/portraits`,
      {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          data: imageB64,
          workflow_name: uploadWorkflow,
          prompt: uploadPrompt,
          set_primary: false,   // 让后端按"无主图时第一张默认主"逻辑处理
          white_bg: uploadWhiteBg,   // v1.6: 白底立绘标记（标准造型也是空白背景，供 MSR 多图参考）
        }),
      },
    )
    if (!up.ok) throw new Error(await up.text())

    // 3) 刷新当前角色的画廊
    const char = characters.value.find(c => c.name === dlg.charName)
    if (char) await loadCharacterPortraits(char)

    dlg.progress = '✓ 完成'
    dlg.show     = false
  } catch (e) {
    dlg.progress = '✗ ' + (e.message || e)
    showStatus(dlg.progress, 'err')
  } finally {
    dlg.running = false
  }
}

async function setPrimaryPortrait(char, p) {
  try {
    await fetch(
      `${API}/projects/${props.projectId}/characters/${encodeURIComponent(char.name)}/portraits/${p.filename}/select`,
      { method: 'PUT' },
    )
    for (const x of (char._portraits || [])) x.is_primary = (x.filename === p.filename)
  } catch (e) { alert('设为主立绘失败: ' + e.message) }
}

// 轮 4: 立绘大图预览
const portraitLightbox = ref(null)   // { charName, list: [], index }

function openPortraitPreview(char, p) {
  const list = char._portraits || []
  const idx = list.findIndex(x => x.filename === p.filename)
  portraitLightbox.value = { charName: char.name, list, index: idx < 0 ? 0 : idx }
}
function closePortraitPreview() { portraitLightbox.value = null }
function portraitLightboxNav(dir) {
  const lb = portraitLightbox.value
  if (!lb) return
  const n = lb.list.length
  lb.index = (lb.index + dir + n) % n
}
function onPortraitLightboxKey(e) {
  if (!portraitLightbox.value) return
  if (e.key === 'Escape')     closePortraitPreview()
  if (e.key === 'ArrowLeft')  portraitLightboxNav(-1)
  if (e.key === 'ArrowRight') portraitLightboxNav(1)
}

async function deletePortrait(char, p) {
  if (!confirm(`删除立绘 ${p.filename}？`)) return
  try {
    await fetch(
      `${API}/projects/${props.projectId}/characters/${encodeURIComponent(char.name)}/portraits/${p.filename}`,
      { method: 'DELETE' },
    )
    await loadCharacterPortraits(char)
  } catch (e) { alert('删除失败: ' + e.message) }
}

function voiceGroupsFor(currentValue) {
  // 当前角色已选的 voice 即使不在通过名单里也要保留显示，避免"看上去丢了"
  return groupByGender(filterVoices(availableVoiceList.value, [currentValue]))
}

// ── Import from other project dialog state ────────────────────────────────────
const importProjectDialog = reactive({
  show: false,
  projects: [],
  selectedProjectId: '',
  loading: false,
  sourceChars: null,      // null = not loaded yet; [] = loaded (empty); [...] = loaded
  selectedIndices: [],    // indices into sourceChars
})

async function openImportFromProject() {
  importProjectDialog.selectedProjectId = ''
  importProjectDialog.sourceChars = null
  importProjectDialog.selectedIndices = []
  importProjectDialog.loading = false
  try {
    const res = await fetch(`${API}/projects`)
    importProjectDialog.projects = res.ok ? await res.json() : []
  } catch {
    importProjectDialog.projects = []
  }
  importProjectDialog.show = true
}

async function loadImportProjectChars() {
  if (!importProjectDialog.selectedProjectId) return
  importProjectDialog.loading = true
  try {
    const res = await fetch(`${API}/projects/${importProjectDialog.selectedProjectId}/characters`)
    const d = res.ok ? await res.json() : { characters: [] }
    importProjectDialog.sourceChars = (d.characters || []).map(c => ({
      name: c.name || '', role: c.role || '', traits: c.traits || '',
      appearance: c.appearance || '', negative: c.negative || '', voice: c.voice || '',
    }))
    importProjectDialog.selectedIndices = importProjectDialog.sourceChars.map((_, i) => i)
  } catch {
    importProjectDialog.sourceChars = []
  } finally {
    importProjectDialog.loading = false
  }
}

async function doImportFromProject() {
  const toImport = importProjectDialog.selectedIndices
    .map(i => importProjectDialog.sourceChars[i])
    .filter(Boolean)
  if (!toImport.length) return

  const existingMap = new Map(characters.value.map(c => [normalizeName(c.name), c]))
  let added = 0, overwritten = 0

  for (const src of toImport) {
    const key = normalizeName(src.name)
    if (!key) continue
    if (existingMap.has(key)) {
      const ok = confirm(`角色「${src.name}」已存在，是否用导入数据覆盖？`)
      if (!ok) continue
      const existing = existingMap.get(key)
      Object.assign(existing, { role: src.role, traits: src.traits, appearance: src.appearance, negative: src.negative })
      overwritten++
    } else {
      characters.value.push({ ...src, _generating: false, _finding: false, _profiling: false })
      existingMap.set(key, characters.value[characters.value.length - 1])
      added++
    }
  }

  if (added + overwritten > 0) {
    markDirty()
    showStatus(`导入完成：新增 ${added} 个，覆盖 ${overwritten} 个`, 'ok')
  } else {
    showStatus('未导入任何角色', 'warn')
  }
  importProjectDialog.show = false
}

function emptyChar() {
  return {
    name: '', role: '', traits: '', appearance: '', negative: '', voice: '',
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
        voice: c.voice || '',
        _portraits: [],          // 轮 4: 立绘缓存（按需懒加载）
        _generating: false,
        _finding: false,
        _profiling: false,
      }))
      // 异步并发拉每个角色的立绘列表
      for (const c of characters.value) {
        loadCharacterPortraits(c)
      }
    }
  } catch {}
  // 同时拉一次 t2i 工作流列表（生成立绘对话框用）
  loadT2iWorkflows()
  // 同时拉一次 settings 决定要不要显示音色字段
  try {
    const sr = await fetch(`${API}/settings`)
    if (sr.ok) {
      const s = await sr.json()
      audioEngine.value = s.audio_engine?.engine_type || 'indextts'
      availableVoiceList.value = s.audio_engine?.msedge_available_voices || []
    }
  } catch {}
  window.addEventListener('lumi:save-project', onGlobalSave)
  window.addEventListener('keydown', onPortraitLightboxKey)
})
onUnmounted(() => {
  window.removeEventListener('lumi:save-project', onGlobalSave)
  window.removeEventListener('keydown', onPortraitLightboxKey)
})

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
        voice: c.voice || '',
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
    // v1.5.1: 不发送 _portraits（运行期缓存）/ portraits（由专用立绘端点维护）——
    // 后端 PUT 会按角色名保留磁盘上已有的 portraits，立绘不会被角色保存抹掉。
    const payload = characters.value.map(
      ({ _generating, _finding, _profiling, _portraits, portraits, ...c }) => c
    )
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

function onGlobalSave(e) { if (e?.detail?.projectId && e.detail.projectId !== props.projectId) return;
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

/* 轮 4: 立绘画廊 */
.portraits-row {
  display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px;
}
.portrait-card {
  width: 90px; position: relative;
  border: 1px solid var(--color-border);
  border-radius: 6px; overflow: hidden;
  background: var(--color-surface);
  cursor: zoom-in;
  transition: transform .12s, border-color .12s;
}
.portrait-card:hover { transform: translateY(-1px); border-color: var(--color-accent); }
.portrait-card.primary { border-color: var(--color-accent); box-shadow: 0 0 0 1px var(--color-accent); }
/* 立绘是竖幅 9:16 */
.portrait-img { width: 100%; aspect-ratio: 9/16; object-fit: cover; display: block; background: rgba(0,0,0,.1); }
.portrait-actions {
  position: absolute; top: 4px; right: 4px;
  display: flex; gap: 3px;
  opacity: 0; transition: opacity .1s;
}
.portrait-card:hover .portrait-actions { opacity: 1; }
.portrait-card.primary .portrait-actions { opacity: 1; }
.portrait-mini {
  background: rgba(0,0,0,.6); color: #fff;
  border: none; cursor: pointer;
  width: 20px; height: 20px; border-radius: 4px;
  font-size: 11px; display: flex; align-items: center; justify-content: center;
}
.portrait-mini:disabled { background: var(--color-accent); cursor: default; }
.portrait-mini.danger:hover { background: var(--color-error); }
.portrait-name {
  padding: 2px 4px; font-size: 10px;
  color: var(--color-text-muted); text-align: center;
}
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

.import-char-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
.import-char-row  { display: flex; align-items: center; gap: 10px; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.import-char-row:hover { background: var(--bg-input); }
.import-char-name { font-weight: 600; font-size: 14px; min-width: 80px; }
.import-char-role { font-size: 12px; }

/* 立绘大图预览 */
.portrait-lightbox {
  position: fixed; inset: 0; z-index: 10001;
  background: rgba(0,0,0,.88);
  display: flex; align-items: center; justify-content: center;
}
.pl-close {
  position: absolute; top: 16px; right: 20px;
  background: rgba(255,255,255,.12); border: none; color: #fff;
  font-size: 20px; width: 36px; height: 36px; border-radius: 50%;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.pl-close:hover { background: rgba(255,255,255,.25); }
.pl-nav {
  background: rgba(255,255,255,.1); border: none; color: #fff;
  font-size: 44px; line-height: 1; width: 52px; height: 80px;
  border-radius: 6px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin: 0 12px; transition: background .15s;
}
.pl-nav:hover { background: rgba(255,255,255,.2); }
.pl-body {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  max-width: calc(100vw - 200px); max-height: calc(100vh - 80px);
}
.pl-img {
  max-width: 100%; max-height: calc(100vh - 120px);
  object-fit: contain; border-radius: 6px; display: block;
}
.pl-footer { color: rgba(255,255,255,.7); font-size: 13px; }
</style>
