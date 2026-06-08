<template>
  <Teleport to="body">
    <div class="ic-overlay" @click.self="$emit('cancel')">
      <div class="ic-modal">
        <div class="ic-header">
          <h3>✂ 剪裁导入图片</h3>
          <span class="text-muted ic-ratio-info">
            目标比例 <code>{{ targetW }} × {{ targetH }}</code>
            （{{ targetRatio.toFixed(3) }}:1）
          </span>
          <button class="btn btn-ghost btn-xs" @click="$emit('cancel')">✕</button>
        </div>

        <p class="ic-tip">
          ℹ 此比例由「设置 → 图片引擎 → 画面尺寸」决定，统一影响 AI 生成 + 手动剪裁。
          要调整请前往设置页修改。
        </p>

        <div v-if="loading" class="ic-loading">加载图片中…</div>

        <div v-else class="ic-stage-wrap">
          <div ref="stageRef" class="ic-stage"
               :style="{ width: stageW + 'px', height: stageH + 'px' }">
            <img :src="src" class="ic-img"
                 :style="{ width: stageW + 'px', height: stageH + 'px' }" draggable="false" />
            <!-- 蒙板：四块遮罩 + 中间一个透明剪裁区 -->
            <div class="ic-mask ic-mask-top"
                 :style="{ height: crop.y + 'px' }" />
            <div class="ic-mask ic-mask-bottom"
                 :style="{ top: (crop.y + crop.h) + 'px',
                           height: (stageH - crop.y - crop.h) + 'px' }" />
            <div class="ic-mask ic-mask-left"
                 :style="{ top: crop.y + 'px', height: crop.h + 'px',
                           width: crop.x + 'px' }" />
            <div class="ic-mask ic-mask-right"
                 :style="{ top: crop.y + 'px', height: crop.h + 'px',
                           left: (crop.x + crop.w) + 'px',
                           width: (stageW - crop.x - crop.w) + 'px' }" />
            <!-- 剪裁框 -->
            <div class="ic-crop"
                 :style="{ left: crop.x + 'px', top: crop.y + 'px',
                           width: crop.w + 'px', height: crop.h + 'px' }"
                 @mousedown="startDrag('move', $event)">
              <div v-for="c in ['nw','ne','sw','se']" :key="c"
                   class="ic-handle" :class="'ic-handle-' + c"
                   @mousedown.stop="startDrag(c, $event)" />
            </div>
          </div>
        </div>

        <div class="ic-actions">
          <span class="text-muted ic-pos-info" v-if="!loading">
            剪裁区域：{{ Math.round(realCrop.x) }},{{ Math.round(realCrop.y) }}
            · {{ Math.round(realCrop.w) }}×{{ Math.round(realCrop.h) }}
          </span>
          <div style="flex:1" />
          <button class="btn btn-secondary" @click="autoCenter">居中自动剪裁</button>
          <button class="btn btn-ghost" @click="$emit('cancel')">取消</button>
          <button class="btn btn-primary"
                  :disabled="loading"
                  @click="applyCrop">✓ 应用并保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  /** data:image/...;base64,... 或 http(s) URL */
  src:     { type: String, required: true },
  /** 目标输出尺寸（最终 canvas 输出 width × height） */
  targetW: { type: Number, required: true },
  targetH: { type: Number, required: true },
})
const emit = defineEmits(['cropped', 'cancel'])

const targetRatio = computed(() => props.targetW / props.targetH)

const loading = ref(true)
const imgNatural = reactive({ w: 0, h: 0 })

// 舞台显示尺寸（缩放后的图像在 modal 里占的大小）
const STAGE_MAX_W = 720
const STAGE_MAX_H = 480
const stageW = ref(0)
const stageH = ref(0)
const stageScale = ref(1)   // 显示坐标 → 原图坐标 的逆比例

// 剪裁框（舞台坐标系）
const crop = reactive({ x: 0, y: 0, w: 0, h: 0 })

// 原图坐标系下的剪裁矩形
const realCrop = computed(() => ({
  x: crop.x / stageScale.value,
  y: crop.y / stageScale.value,
  w: crop.w / stageScale.value,
  h: crop.h / stageScale.value,
}))

const stageRef = ref(null)

function loadImg() {
  const im = new Image()
  im.crossOrigin = 'anonymous'
  im.onload = () => {
    imgNatural.w = im.naturalWidth
    imgNatural.h = im.naturalHeight
    // 算舞台缩放
    const sw = Math.min(STAGE_MAX_W / imgNatural.w, STAGE_MAX_H / imgNatural.h, 1)
    stageScale.value = sw
    stageW.value = Math.round(imgNatural.w * sw)
    stageH.value = Math.round(imgNatural.h * sw)
    loading.value = false
    autoCenter()
  }
  im.onerror = () => { loading.value = false; alert('图片加载失败') }
  im.src = props.src
}

onMounted(loadImg)

// ── 居中自动剪裁 ────────────────────────────────────────────────────────────
function autoCenter() {
  // 选最大的、能 fit 进图像、保持目标比例的矩形
  const r = targetRatio.value
  let w, h
  if (stageW.value / stageH.value > r) {
    h = stageH.value
    w = h * r
  } else {
    w = stageW.value
    h = w / r
  }
  crop.w = w
  crop.h = h
  crop.x = (stageW.value - w) / 2
  crop.y = (stageH.value - h) / 2
}

// ── 拖动 / 缩放 ──────────────────────────────────────────────────────────────
let dragMode = null
let dragStart = null

function startDrag(mode, ev) {
  dragMode = mode
  const rect = stageRef.value.getBoundingClientRect()
  dragStart = {
    mouseX: ev.clientX,
    mouseY: ev.clientY,
    stageRect: rect,
    crop: { ...crop },
  }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup',   stopDrag)
  ev.preventDefault()
}

function onDrag(ev) {
  if (!dragMode || !dragStart) return
  const dx = ev.clientX - dragStart.mouseX
  const dy = ev.clientY - dragStart.mouseY
  const r  = targetRatio.value
  const SW = stageW.value, SH = stageH.value

  if (dragMode === 'move') {
    let x = dragStart.crop.x + dx
    let y = dragStart.crop.y + dy
    crop.x = Math.max(0, Math.min(x, SW - crop.w))
    crop.y = Math.max(0, Math.min(y, SH - crop.h))
    return
  }

  // 4 角缩放：保持目标比例（用主导拖拽方向 + 副轴反推）
  // 锚点 = 对角；以锚点为不动点，让 mouse 决定新的对角点
  const oldX = dragStart.crop.x, oldY = dragStart.crop.y
  const oldW = dragStart.crop.w, oldH = dragStart.crop.h
  let anchorX, anchorY
  if (dragMode === 'se') { anchorX = oldX;        anchorY = oldY }
  if (dragMode === 'sw') { anchorX = oldX + oldW; anchorY = oldY }
  if (dragMode === 'ne') { anchorX = oldX;        anchorY = oldY + oldH }
  if (dragMode === 'nw') { anchorX = oldX + oldW; anchorY = oldY + oldH }

  // 新的拖拽点 = 鼠标在 stage 中的坐标
  const mouseStageX = ev.clientX - dragStart.stageRect.left
  const mouseStageY = ev.clientY - dragStart.stageRect.top
  // 候选宽高（无符号）
  let candW = Math.abs(mouseStageX - anchorX)
  let candH = Math.abs(mouseStageY - anchorY)
  // 按目标比例锁定：以更"严格"的那一边为基准
  if (candW / candH > r) candW = candH * r
  else                    candH = candW / r
  // 新左上 = anchor - 候选宽高（按拖拽方向取符号）
  const sgnX = mouseStageX < anchorX ? -1 : 1
  const sgnY = mouseStageY < anchorY ? -1 : 1
  let newX = sgnX > 0 ? anchorX : anchorX - candW
  let newY = sgnY > 0 ? anchorY : anchorY - candH
  // clamp 到 stage
  if (newX < 0) { candW += newX; newX = 0; candH = candW / r }
  if (newY < 0) { candH += newY; newY = 0; candW = candH * r }
  if (newX + candW > SW) { candW = SW - newX; candH = candW / r }
  if (newY + candH > SH) { candH = SH - newY; candW = candH * r }
  // 写回
  if (candW > 20 && candH > 20) {
    crop.x = newX; crop.y = newY; crop.w = candW; crop.h = candH
  }
}

function stopDrag() {
  dragMode = null
  dragStart = null
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup',   stopDrag)
}

onUnmounted(() => {
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup',   stopDrag)
})

// ── 应用剪裁 → canvas 输出 base64 ────────────────────────────────────────────
function applyCrop() {
  const im = new Image()
  im.crossOrigin = 'anonymous'
  im.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width  = props.targetW
    canvas.height = props.targetH
    const ctx = canvas.getContext('2d')
    const rc = realCrop.value
    ctx.drawImage(im, rc.x, rc.y, rc.w, rc.h, 0, 0, props.targetW, props.targetH)
    const dataUrl = canvas.toDataURL('image/png')
    const base64 = dataUrl.replace(/^data:image\/\w+;base64,/, '')
    emit('cropped', { base64, dataUrl })
  }
  im.onerror = () => alert('剪裁失败：原图无法加载')
  im.src = props.src
}
</script>

<style scoped>
.ic-overlay {
  position: fixed; inset: 0; z-index: 10010;
  background: rgba(0,0,0,.6);
  display: flex; align-items: center; justify-content: center;
}
.ic-modal {
  background: var(--bg-panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px;
  width: min(820px, 96vw); max-height: 90vh;
  display: flex; flex-direction: column; gap: 10px;
}
.ic-header { display: flex; align-items: center; gap: 10px; }
.ic-header h3 { margin: 0; font-size: 15px; }
.ic-header .ic-ratio-info { flex: 1; font-size: 12px; }
.ic-header code { background: var(--bg-input); padding: 1px 6px; border-radius: 3px; font-size: 11px; }
.ic-tip {
  background: rgba(99,179,237,.08); border-left: 3px solid #63b3ed;
  padding: 6px 10px; font-size: 12px; line-height: 1.5;
  border-radius: 4px; margin: 0;
}
.ic-loading { padding: 40px; text-align: center; color: var(--text-muted); }

.ic-stage-wrap {
  background: #000; padding: 20px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  min-height: 360px;
}
.ic-stage { position: relative; user-select: none; }
.ic-img   { display: block; pointer-events: none; }
.ic-mask  { position: absolute; left: 0; right: 0; background: rgba(0,0,0,.55); pointer-events: none; }
.ic-mask-top    { top: 0; }
.ic-mask-bottom { left: 0; right: 0; }
.ic-mask-left, .ic-mask-right { top: 0; }

.ic-crop {
  position: absolute;
  border: 2px solid #63b3ed;
  cursor: move;
  box-shadow: 0 0 0 1px rgba(255,255,255,.4) inset;
}
.ic-handle {
  position: absolute; width: 12px; height: 12px;
  background: #63b3ed; border: 1px solid #fff; border-radius: 2px;
}
.ic-handle-nw { left: -7px; top: -7px;    cursor: nwse-resize; }
.ic-handle-ne { right: -7px; top: -7px;   cursor: nesw-resize; }
.ic-handle-sw { left: -7px; bottom: -7px; cursor: nesw-resize; }
.ic-handle-se { right: -7px; bottom: -7px; cursor: nwse-resize; }

.ic-actions {
  display: flex; align-items: center; gap: 8px;
  padding-top: 6px; border-top: 1px solid var(--border);
}
.ic-pos-info { font-size: 11px; }
</style>
