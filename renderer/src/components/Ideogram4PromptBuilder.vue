<template>
  <Teleport to="body">
    <div class="ig-overlay" @click.self="$emit('close')">
      <div class="ig-modal">
        <div class="ig-header">
          <h3>🧩 Ideogram 4 提示词构建器</h3>
          <span class="ig-hint text-muted">
            画布拖拽画区域 · 选中后设类型/描述/配色 · 右侧填风格 · 生成结构化 JSON caption
          </span>
          <button class="btn btn-ghost btn-xs" @click="$emit('close')">✕</button>
        </div>

        <div class="ig-body">
          <!-- ── 左：画布 ── -->
          <div class="ig-canvas-col">
            <div class="ig-canvas-toolbar">
              <label>宽<input type="number" v-model.number="canvasW" min="16" step="16" class="ig-inp-num" /></label>
              <label>高<input type="number" v-model.number="canvasH" min="16" step="16" class="ig-inp-num" /></label>
              <span class="text-muted ig-tip">Ideogram 4 需 16 的倍数 · 拖拽画框</span>
              <button class="btn btn-ghost btn-xs" @click="clearRegions" :disabled="!regions.length">清空区域</button>
            </div>
            <div ref="stageRef" class="ig-stage"
                 :style="stageStyle"
                 @mousedown="onStageDown">
              <div v-for="(r, i) in regions" :key="i"
                   class="ig-region"
                   :class="{ active: i === activeIdx, 'is-text': r.type === 'text' }"
                   :style="regionStyle(r)"
                   @mousedown.stop="onRegionDown($event, i)">
                <span class="ig-region-tag">{{ i + 1 }}·{{ r.type }}</span>
                <!-- 8 个缩放手柄（仅选中区域显示）-->
                <template v-if="i === activeIdx">
                  <span v-for="h in RESIZE_HANDLES" :key="h"
                        class="ig-handle" :class="'ig-h-' + h"
                        @mousedown.stop="onHandleDown($event, i, h)"></span>
                </template>
              </div>
              <!-- 正在拖拽的临时框 -->
              <div v-if="draft" class="ig-region drafting" :style="regionStyle(draft)"></div>
            </div>
            <p class="ig-coord-hint text-muted">
              bbox 自动归一化到 0–1000 网格（[ymin,xmin,ymax,xmax]）输出
            </p>
          </div>

          <!-- ── 中：区域列表 + 选中编辑 ── -->
          <div class="ig-mid-col">
            <div class="ig-section-title">区域（{{ regions.length }}）</div>
            <ul class="ig-region-list">
              <li v-for="(r, i) in regions" :key="i"
                  :class="{ active: i === activeIdx }"
                  @click="activeIdx = i">
                <span class="ig-rl-idx">{{ i + 1 }}</span>
                <span class="ig-rl-type" :class="r.type">{{ r.type }}</span>
                <span class="ig-rl-desc">{{ r.desc || r.text || '（未描述）' }}</span>
                <button class="ig-rl-del" @click.stop="removeRegion(i)">✕</button>
              </li>
              <li v-if="!regions.length" class="ig-empty">在左侧画布拖拽出第一个区域</li>
            </ul>

            <div v-if="activeRegion" class="ig-region-editor">
              <div class="ig-section-title">区域 {{ activeIdx + 1 }} 设置</div>
              <div class="ig-field-row">
                <label class="ig-field" style="flex:0 0 auto">
                  类型
                  <select v-model="activeRegion.type" class="ig-inp">
                    <option value="obj">obj（物体/主体）</option>
                    <option value="text">text（图中文字）</option>
                  </select>
                </label>
              </div>
              <label v-if="activeRegion.type === 'text'" class="ig-field">
                文字内容（literal）
                <input v-model="activeRegion.text" class="ig-inp"
                       placeholder="要渲染进画面的文字" />
              </label>
              <label class="ig-field">
                描述 desc
                <textarea v-model="activeRegion.desc" class="ig-inp" rows="2"
                          placeholder="详细描述该元素"></textarea>
              </label>
              <div class="ig-field-row">
                <label class="ig-field-sm">ymin<input type="number" v-model.number="activeRegion.bbox[0]" class="ig-inp-num" min="0" max="1000" /></label>
                <label class="ig-field-sm">xmin<input type="number" v-model.number="activeRegion.bbox[1]" class="ig-inp-num" min="0" max="1000" /></label>
                <label class="ig-field-sm">ymax<input type="number" v-model.number="activeRegion.bbox[2]" class="ig-inp-num" min="0" max="1000" /></label>
                <label class="ig-field-sm">xmax<input type="number" v-model.number="activeRegion.bbox[3]" class="ig-inp-num" min="0" max="1000" /></label>
              </div>
              <PaletteEditor v-model="activeRegion.color_palette" :max="5" label="区域配色（≤5）" />
            </div>
          </div>

          <!-- ── 右：全局字段 ── -->
          <div class="ig-right-col">
            <!-- v1.4.13: AI 分步生成整个 caption -->
            <div class="ig-ai-block">
              <div class="ig-section-title">✨ AI 生成（文本引擎）</div>
              <!-- 参考角色：只读展示「出镜角色」选择器已选中的角色（带外观），不在此处重复做选择器 -->
              <div v-if="sceneCharacters.length" class="ig-ai-chars">
                <span class="ig-ai-chars-label">参考角色（来自出镜角色选择，含外观）：</span>
                <span v-for="c in sceneCharacters" :key="c.name"
                      class="ig-ai-char-chip"
                      :title="c.appearance || c.traits || '（未填写外观）'">
                  {{ c.name }}{{ (c.appearance || c.traits) ? '' : ' ⚠' }}
                </span>
              </div>
              <p v-else class="ig-tip text-muted" style="margin:0">
                未选择出镜角色 · 在右侧「🎭 出镜角色」勾选后，AI 生成会按其外观保持角色一致性
              </p>
              <textarea v-model="aiDesc" class="ig-inp" rows="2"
                        placeholder="用中文/英文描述画面，AI 分两步生成整个 JSON（概览+风格 → 元素布局）"></textarea>
              <div class="ig-ai-row">
                <button class="btn btn-primary btn-sm"
                        :disabled="aiBusy || !aiDesc.trim()"
                        @click="runAiGenerate">
                  {{ aiBusy ? (aiStep || '生成中…') : '✨ AI 生成全部字段' }}
                </button>
                <span v-if="aiError" class="ig-ai-error">⚠ {{ aiError }}</span>
              </div>
              <p class="ig-tip text-muted" style="margin:0">
                生成后所有字段可继续手动微调；区域 bbox 可在画布上拖拽
              </p>
            </div>

            <div class="ig-section-title">整体描述</div>
            <label class="ig-field">
              high_level_description（一句话总览，强烈推荐）
              <textarea v-model="highLevel" class="ig-inp" rows="2"
                        placeholder="A medium-shot photograph of …"></textarea>
            </label>
            <label class="ig-field">
              background 背景（必填）
              <textarea v-model="background" class="ig-inp" rows="2"
                        placeholder="描述背景 / 环境"></textarea>
            </label>

            <div class="ig-section-title">风格 style_description</div>
            <div class="ig-field-row">
              <label class="ig-field" style="flex:1">
                类型
                <select v-model="styleType" class="ig-inp">
                  <option value="photo">photo（摄影）</option>
                  <option value="art_style">art_style（绘画/插画/3D）</option>
                  <option value="none">不指定 style</option>
                </select>
              </label>
            </div>
            <template v-if="styleType !== 'none'">
              <label class="ig-field">
                aesthetics 美学
                <input v-model="aesthetics" class="ig-inp" placeholder="moody, cinematic, desaturated" />
              </label>
              <label class="ig-field">
                lighting 光照
                <input v-model="lighting" class="ig-inp" placeholder="golden hour, rim light" />
              </label>
              <label v-if="styleType === 'photo'" class="ig-field">
                photo 相机/镜头
                <input v-model="photo" class="ig-inp" placeholder="35mm, f/1.4, bokeh" />
              </label>
              <label v-else class="ig-field">
                art_style 画风
                <input v-model="artStyle" class="ig-inp" placeholder="flat vector illustration, bold outlines" />
              </label>
              <label class="ig-field">
                medium 媒介
                <input v-model="medium" class="ig-inp"
                       :placeholder="styleType === 'photo' ? 'photograph' : 'illustration / 3d_render / painting …'" />
              </label>
              <PaletteEditor v-model="stylePalette" :max="16" label="整体配色（≤16，#RRGGBB）" />
            </template>
          </div>
        </div>

        <!-- ── 底：预览 + 应用 ── -->
        <div class="ig-footer">
          <details class="ig-json-preview">
            <summary>预览 JSON（{{ tokenEstimate }} 估算 token）</summary>
            <pre>{{ prettyJson }}</pre>
          </details>
          <div class="ig-footer-actions">
            <button class="btn btn-ghost btn-sm" @click="copyJson">📋 复制 JSON</button>
            <button class="btn btn-ghost" @click="$emit('close')">取消</button>
            <button class="btn btn-primary" @click="apply">✓ 应用到提示词框</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import axios from 'axios'
import PaletteEditor from './PaletteEditor.vue'

const props = defineProps({
  // 初始 JSON（编辑已有提示词时回填）
  initialJson: { type: String, default: '' },
  // v1.4.13: 画布尺寸跟随设置页图片引擎的 image_width/height
  initialW: { type: Number, default: 1024 },
  initialH: { type: Number, default: 1024 },
  // v1.4.13: AI 生成的默认描述（分镜描述）+ 出镜角色卡（带 appearance）
  sceneHint:       { type: String, default: '' },
  sceneCharacters: { type: Array,  default: () => [] },
})
const emit = defineEmits(['apply', 'close'])

const API = 'http://localhost:18520/api'

// 画布尺寸（决定长宽比 + 像素网格）—— 初始值来自设置页
const canvasW = ref(props.initialW || 1024)
const canvasH = ref(props.initialH || 1024)

// 区域： { type, bbox:[ymin,xmin,ymax,xmax] (0-1000), desc, text, color_palette:[] }
const regions = ref([])
const activeIdx = ref(-1)
const activeRegion = computed(() => regions.value[activeIdx.value] || null)

// 全局字段
const highLevel = ref('')
const background = ref('')
const styleType = ref('photo')        // 'photo' | 'art_style' | 'none'
const aesthetics = ref('')
const lighting = ref('')
const photo = ref('')
const artStyle = ref('')
const medium = ref('')
const stylePalette = ref([])

// ── 画布舞台几何 ──────────────────────────────────────────────────────────
const stageRef = ref(null)
const STAGE_MAX = 420   // 舞台最长边像素
const stageStyle = computed(() => {
  const w = canvasW.value || 1, h = canvasH.value || 1
  const scale = STAGE_MAX / Math.max(w, h)
  return { width: Math.round(w * scale) + 'px', height: Math.round(h * scale) + 'px' }
})

function regionStyle(r) {
  // bbox 是 0-1000 归一化；舞台是 stageStyle 的像素尺寸
  const [ymin, xmin, ymax, xmax] = r.bbox
  return {
    left:   (xmin / 1000 * 100) + '%',
    top:    (ymin / 1000 * 100) + '%',
    width:  ((xmax - xmin) / 1000 * 100) + '%',
    height: ((ymax - ymin) / 1000 * 100) + '%',
  }
}

// ── 拖拽画新区域 ──────────────────────────────────────────────────────────
const draft = ref(null)
let dragStart = null

function _stagePoint(e) {
  const rect = stageRef.value.getBoundingClientRect()
  const x = Math.min(Math.max(e.clientX - rect.left, 0), rect.width)
  const y = Math.min(Math.max(e.clientY - rect.top, 0), rect.height)
  return { x: x / rect.width * 1000, y: y / rect.height * 1000, rect }
}

function onStageDown(e) {
  const p = _stagePoint(e)
  dragStart = p
  draft.value = { type: 'obj', bbox: [p.y, p.x, p.y, p.x], desc: '', text: '', color_palette: [] }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragUp)
}

function onDragMove(e) {
  if (!dragStart || !draft.value) return
  const p = _stagePoint(e)
  const ymin = Math.min(dragStart.y, p.y), ymax = Math.max(dragStart.y, p.y)
  const xmin = Math.min(dragStart.x, p.x), xmax = Math.max(dragStart.x, p.x)
  draft.value.bbox = [Math.round(ymin), Math.round(xmin), Math.round(ymax), Math.round(xmax)]
}

function onDragUp() {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
  if (draft.value) {
    const [ymin, xmin, ymax, xmax] = draft.value.bbox
    // 太小的拖拽忽略（视为误点）
    if (ymax - ymin > 20 && xmax - xmin > 20) {
      regions.value.push({ ...draft.value, bbox: [...draft.value.bbox] })
      activeIdx.value = regions.value.length - 1
    }
  }
  draft.value = null
  dragStart = null
}

// ── 拖拽移动已有区域 ──────────────────────────────────────────────────────
let moveCtx = null
function onRegionDown(e, i) {
  activeIdx.value = i
  const p = _stagePoint(e)
  moveCtx = { i, startX: p.x, startY: p.y, orig: [...regions.value[i].bbox] }
  window.addEventListener('mousemove', onRegionMove)
  window.addEventListener('mouseup', onRegionUp)
}
function onRegionMove(e) {
  if (!moveCtx) return
  const p = _stagePoint(e)
  const dx = p.x - moveCtx.startX, dy = p.y - moveCtx.startY
  let [ymin, xmin, ymax, xmax] = moveCtx.orig
  const h = ymax - ymin, w = xmax - xmin
  ymin = Math.min(Math.max(ymin + dy, 0), 1000 - h)
  xmin = Math.min(Math.max(xmin + dx, 0), 1000 - w)
  regions.value[moveCtx.i].bbox = [Math.round(ymin), Math.round(xmin),
                                    Math.round(ymin + h), Math.round(xmin + w)]
}
function onRegionUp() {
  window.removeEventListener('mousemove', onRegionMove)
  window.removeEventListener('mouseup', onRegionUp)
  moveCtx = null
}

// ── 缩放已有区域（8 手柄，bbox = [ymin,xmin,ymax,xmax]）─────────────────────
const RESIZE_HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
let resizeCtx = null
const MIN_SIZE = 10   // 0-1000 网格下最小边长

function onHandleDown(e, i, handle) {
  activeIdx.value = i
  const p = _stagePoint(e)
  resizeCtx = { i, handle, startX: p.x, startY: p.y, orig: [...regions.value[i].bbox] }
  window.addEventListener('mousemove', onHandleMove)
  window.addEventListener('mouseup', onHandleUp)
}
function onHandleMove(e) {
  if (!resizeCtx) return
  const p = _stagePoint(e)
  let [ymin, xmin, ymax, xmax] = resizeCtx.orig
  const h = resizeCtx.handle
  if (h.includes('n')) ymin = Math.min(p.y, ymax - MIN_SIZE)
  if (h.includes('s')) ymax = Math.max(p.y, ymin + MIN_SIZE)
  if (h.includes('w')) xmin = Math.min(p.x, xmax - MIN_SIZE)
  if (h.includes('e')) xmax = Math.max(p.x, xmin + MIN_SIZE)
  const clamp = v => Math.round(Math.min(1000, Math.max(0, v)))
  regions.value[resizeCtx.i].bbox = [clamp(ymin), clamp(xmin), clamp(ymax), clamp(xmax)]
}
function onHandleUp() {
  window.removeEventListener('mousemove', onHandleMove)
  window.removeEventListener('mouseup', onHandleUp)
  resizeCtx = null
}

function removeRegion(i) {
  regions.value.splice(i, 1)
  if (activeIdx.value >= regions.value.length) activeIdx.value = regions.value.length - 1
}
function clearRegions() {
  regions.value = []
  activeIdx.value = -1
}

// ── 组装 caption JSON（严格 key 顺序，按 prompting.md） ──────────────────
const captionObj = computed(() => {
  const out = {}
  if (highLevel.value.trim()) out.high_level_description = highLevel.value.trim()

  // style_description（key 顺序依 photo / art_style 而定）
  if (styleType.value !== 'none' && (aesthetics.value || lighting.value || medium.value
      || photo.value || artStyle.value || stylePalette.value.length)) {
    const sd = {}
    if (aesthetics.value.trim()) sd.aesthetics = aesthetics.value.trim()
    if (lighting.value.trim())   sd.lighting   = lighting.value.trim()
    if (styleType.value === 'photo') {
      if (photo.value.trim())  sd.photo  = photo.value.trim()
      if (medium.value.trim()) sd.medium = medium.value.trim()
    } else {
      if (medium.value.trim())   sd.medium    = medium.value.trim()
      if (artStyle.value.trim()) sd.art_style = artStyle.value.trim()
    }
    if (stylePalette.value.length) sd.color_palette = stylePalette.value.slice(0, 16)
    if (Object.keys(sd).length) out.style_description = sd
  }

  // compositional_deconstruction（必填）
  const cd = { background: background.value.trim() }
  cd.elements = regions.value.map(r => {
    const el = { type: r.type }
    // key 顺序：obj → type,bbox,desc,color_palette ; text → type,bbox,text,desc,color_palette
    if (r.bbox && r.bbox.length === 4) el.bbox = r.bbox.map(v => Math.round(v))
    if (r.type === 'text') {
      el.text = r.text || ''
      el.desc = r.desc || ''
    } else {
      el.desc = r.desc || ''
    }
    if (r.color_palette && r.color_palette.length) el.color_palette = r.color_palette.slice(0, 5)
    return el
  })
  out.compositional_deconstruction = cd
  return out
})

const prettyJson = computed(() => JSON.stringify(captionObj.value, null, 2))
const compactJson = computed(() => JSON.stringify(captionObj.value))
const tokenEstimate = computed(() => Math.round(compactJson.value.length / 4) + ' ~')

// ── 回填初始 JSON ─────────────────────────────────────────────────────────
function loadFromJson(str) {
  let obj
  try { obj = JSON.parse(str) } catch { return false }
  if (!obj || typeof obj !== 'object') return false
  highLevel.value = obj.high_level_description || ''
  const sd = obj.style_description || {}
  aesthetics.value = sd.aesthetics || ''
  lighting.value   = sd.lighting || ''
  if (sd.photo !== undefined) { styleType.value = 'photo'; photo.value = sd.photo || '' }
  else if (sd.art_style !== undefined) { styleType.value = 'art_style'; artStyle.value = sd.art_style || '' }
  else if (!obj.style_description) { styleType.value = 'none' }
  medium.value = sd.medium || ''
  stylePalette.value = Array.isArray(sd.color_palette) ? [...sd.color_palette] : []
  const cd = obj.compositional_deconstruction || {}
  background.value = cd.background || ''
  regions.value = (cd.elements || []).map(el => ({
    type: el.type === 'text' ? 'text' : 'obj',
    bbox: Array.isArray(el.bbox) && el.bbox.length === 4 ? el.bbox.map(Number) : [100, 100, 400, 400],
    desc: el.desc || '',
    text: el.text || '',
    color_palette: Array.isArray(el.color_palette) ? [...el.color_palette] : [],
  }))
  activeIdx.value = regions.value.length ? 0 : -1
  return true
}

// ── v1.4.13: AI 分步生成整个 caption（overview → elements 两次小响应）────────
const aiDesc  = ref(props.sceneHint || '')
const aiBusy  = ref(false)
const aiStep  = ref('')
const aiError = ref('')

async function runAiGenerate() {
  const desc = aiDesc.value.trim()
  if (!desc || aiBusy.value) return
  aiBusy.value = true
  aiError.value = ''
  try {
    // 第 1 步：概览（high_level / background / style）
    aiStep.value = '1/2 生成概览与风格…'
    const r1 = await axios.post(`${API}/text-engine/generate-ideogram-caption`, {
      description: desc,
      step: 'overview',
      style_type: styleType.value === 'art_style' ? 'art_style' : 'photo',
      characters: props.sceneCharacters,
    })
    const ov = r1.data?.data || {}
    if (ov.high_level_description) highLevel.value = ov.high_level_description
    if (ov.background)             background.value = ov.background
    const sd = ov.style_description || {}
    if (sd.aesthetics !== undefined) aesthetics.value = sd.aesthetics || ''
    if (sd.lighting   !== undefined) lighting.value   = sd.lighting || ''
    if (sd.photo !== undefined)      { styleType.value = 'photo';     photo.value    = sd.photo || '' }
    else if (sd.art_style !== undefined) { styleType.value = 'art_style'; artStyle.value = sd.art_style || '' }
    if (sd.medium !== undefined)     medium.value = sd.medium || ''
    if (Array.isArray(sd.color_palette)) stylePalette.value = [...sd.color_palette]

    // 第 2 步：空间元素（bbox 布局）
    aiStep.value = '2/2 生成元素布局…'
    const r2 = await axios.post(`${API}/text-engine/generate-ideogram-caption`, {
      description: desc,
      step: 'elements',
      width: canvasW.value, height: canvasH.value,
      overview: ov,
      characters: props.sceneCharacters,
    })
    const els = r2.data?.data?.elements || []
    regions.value = els.map(el => ({
      type: el.type === 'text' ? 'text' : 'obj',
      bbox: Array.isArray(el.bbox) && el.bbox.length === 4
        ? el.bbox.map(Number) : [100, 100, 600, 600],
      desc: el.desc || '',
      text: el.text || '',
      color_palette: Array.isArray(el.color_palette) ? [...el.color_palette] : [],
    }))
    activeIdx.value = regions.value.length ? 0 : -1
    aiStep.value = ''
  } catch (e) {
    aiError.value = e?.response?.data?.detail || e.message || '生成失败'
    aiStep.value = ''
  } finally {
    aiBusy.value = false
  }
}

// ── 操作 ──────────────────────────────────────────────────────────────────
async function copyJson() {
  try { await navigator.clipboard.writeText(compactJson.value) } catch {}
}
function apply() {
  emit('apply', compactJson.value)
  emit('close')
}

onMounted(() => {
  if (props.initialJson && props.initialJson.trim().startsWith('{')) {
    loadFromJson(props.initialJson.trim())
  }
})
</script>

<style scoped>
.ig-overlay {
  position: fixed; inset: 0; z-index: 10020;
  background: rgba(0,0,0,0.62);
  display: flex; align-items: center; justify-content: center;
}
.ig-modal {
  background: var(--color-surface, #1e1e1e);
  color: var(--color-text, #eee);
  border: 1px solid var(--color-border, #333);
  border-radius: 10px;
  width: min(1240px, 97vw);
  max-height: 94vh;
  display: flex; flex-direction: column; gap: 10px;
  padding: 14px 16px; min-height: 0;
}
.ig-header { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; }
.ig-header h3 { margin: 0; font-size: 15px; }
.ig-hint { font-size: 11px; flex: 1; }

.ig-body {
  flex: 1 1 auto; min-height: 0;
  display: grid;
  grid-template-columns: 460px minmax(0, 1fr) 320px;
  gap: 12px;
}
.ig-canvas-col, .ig-mid-col, .ig-right-col {
  min-height: 0; min-width: 0;
  display: flex; flex-direction: column; gap: 8px;
  overflow: auto;
}
.ig-canvas-toolbar { display: flex; align-items: center; gap: 8px; font-size: 12px; flex-wrap: wrap; }
.ig-canvas-toolbar label { display: flex; align-items: center; gap: 3px; }
.ig-inp-num {
  width: 62px; padding: 2px 5px; font-size: 12px;
  background: var(--color-bg, #111); color: var(--color-text);
  border: 1px solid var(--color-border); border-radius: 3px;
}
.ig-tip { font-size: 11px; }
.ig-stage {
  position: relative;
  background: repeating-conic-gradient(#2a2a2a 0% 25%, #222 0% 50%) 50% / 24px 24px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  cursor: crosshair; user-select: none;
  margin: 0 auto;
}
.ig-region {
  position: absolute;
  border: 2px solid var(--color-accent, #4af);
  background: rgba(68,170,255,0.14);
  cursor: move;
}
.ig-region.is-text { border-color: #f5a623; background: rgba(245,166,35,0.16); }
.ig-region.active { box-shadow: 0 0 0 2px #fff inset; z-index: 3; }
.ig-region.drafting { border-style: dashed; pointer-events: none; }
.ig-region-tag {
  position: absolute; top: 0; left: 0;
  font-size: 9px; background: rgba(0,0,0,0.65); color: #fff;
  padding: 0 3px; border-radius: 0 0 3px 0; white-space: nowrap;
}
/* 缩放手柄 */
.ig-handle {
  position: absolute; width: 9px; height: 9px;
  background: #fff; border: 1px solid var(--color-accent, #4af);
  border-radius: 2px; z-index: 4;
}
.ig-h-nw { top: -5px; left: -5px;  cursor: nwse-resize; }
.ig-h-n  { top: -5px; left: 50%; margin-left: -4px; cursor: ns-resize; }
.ig-h-ne { top: -5px; right: -5px; cursor: nesw-resize; }
.ig-h-e  { top: 50%; right: -5px; margin-top: -4px; cursor: ew-resize; }
.ig-h-se { bottom: -5px; right: -5px; cursor: nwse-resize; }
.ig-h-s  { bottom: -5px; left: 50%; margin-left: -4px; cursor: ns-resize; }
.ig-h-sw { bottom: -5px; left: -5px; cursor: nesw-resize; }
.ig-h-w  { top: 50%; left: -5px; margin-top: -4px; cursor: ew-resize; }
.ig-coord-hint { font-size: 10px; }

.ig-section-title {
  font-size: 12px; font-weight: 600;
  border-bottom: 1px solid var(--color-border); padding-bottom: 4px; margin-bottom: 4px;
}
.ig-region-list { list-style: none; margin: 0; padding: 0; }
.ig-region-list li {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 6px; cursor: pointer; border-radius: 3px; font-size: 12px;
}
.ig-region-list li:hover { background: var(--color-surface-2, rgba(255,255,255,0.05)); }
.ig-region-list li.active { background: rgba(68,170,255,0.18); }
.ig-rl-idx { color: #888; min-width: 16px; }
.ig-rl-type { font-size: 10px; padding: 0 5px; border-radius: 8px; background: #345; }
.ig-rl-type.text { background: #642; }
.ig-rl-desc { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ig-rl-del { background: none; border: none; color: #888; cursor: pointer; font-size: 11px; }
.ig-rl-del:hover { color: var(--color-error, #f66); }
.ig-empty { color: #888; text-align: center; padding: 16px; cursor: default; }

.ig-region-editor { margin-top: 6px; display: flex; flex-direction: column; gap: 6px; }
.ig-field { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--color-text-muted, #aaa); }
.ig-field-row { display: flex; gap: 6px; flex-wrap: wrap; }
.ig-field-sm { display: flex; flex-direction: column; gap: 2px; font-size: 10px; color: #999; }
.ig-inp {
  background: var(--color-bg, #111); color: var(--color-text);
  border: 1px solid var(--color-border); border-radius: 3px;
  padding: 4px 6px; font-size: 12px; font-family: inherit;
}
textarea.ig-inp { resize: vertical; }

.ig-footer { flex: 0 0 auto; display: flex; flex-direction: column; gap: 8px; }
.ig-json-preview { font-size: 11px; }
.ig-json-preview summary { cursor: pointer; color: var(--color-text-muted); }
.ig-json-preview pre {
  max-height: 160px; overflow: auto; margin: 6px 0 0;
  background: var(--color-bg, #111); border: 1px solid var(--color-border);
  border-radius: 4px; padding: 8px; font-size: 11px;
}
.ig-footer-actions { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }

/* v1.4.13: AI 生成块 */
.ig-ai-block {
  display: flex; flex-direction: column; gap: 6px;
  background: rgba(68,170,255,0.07);
  border: 1px solid rgba(68,170,255,0.28);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 4px;
}
.ig-ai-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ig-ai-error { font-size: 11px; color: var(--color-error, #f66); }
.ig-ai-chars { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: 11px; }
.ig-ai-chars-label { color: var(--color-text-muted, #aaa); }
.ig-ai-char-chip {
  background: rgba(68,170,255,0.18); border: 1px solid rgba(68,170,255,0.4);
  border-radius: 10px; padding: 1px 8px; color: var(--color-text, #eee); cursor: default;
}
</style>
