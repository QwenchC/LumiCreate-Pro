<template>
  <Teleport to="body">
    <div class="pp-overlay" @click.self="close">
      <div class="pp-modal">
        <div class="pp-header">
          <h3>▶︎ 试播 — {{ currentLabel }}</h3>
          <span class="text-muted pp-progress">
            {{ index + 1 }} / {{ playlist.length }}
          </span>
          <button class="btn btn-ghost btn-xs" @click="close">✕</button>
        </div>

        <div class="pp-stage" :style="stageStyle">
          <!-- 有 mp4 时直接放 -->
          <video
            v-if="currentKind === 'video'"
            ref="videoEl"
            class="pp-video"
            :src="currentSrc"
            autoplay
            @ended="next"
            @error="onMediaError"
          />
          <!-- 没视频但有图 + 音频 -->
          <template v-else-if="currentKind === 'image_audio'">
            <img class="pp-img" :src="currentImageSrc" />
            <audio
              ref="audioEl"
              :src="currentAudioSrc"
              autoplay
              @ended="next"
              @error="onMediaError"
            />
          </template>
          <!-- 只有图 -->
          <img v-else-if="currentKind === 'image_only'" class="pp-img" :src="currentImageSrc" />
          <!-- 没素材 -->
          <div v-else class="pp-empty">该分镜尚无素材</div>
        </div>

        <div class="pp-controls">
          <button class="btn btn-ghost btn-sm" :disabled="index <= 0" @click="prev">⏮ 上一镜</button>
          <button class="btn btn-secondary btn-sm" @click="togglePause">
            {{ paused ? '▶ 继续' : '⏸ 暂停' }}
          </button>
          <button class="btn btn-ghost btn-sm" :disabled="index >= playlist.length - 1" @click="next">下一镜 ⏭</button>
          <span class="pp-hint text-muted">仅串播分镜，不带字幕 / SFX</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'

const props = defineProps({
  projectId: { type: String, required: true },
  scenes:    { type: Array,  required: true },   // [{id, ...}]
  videosMap: { type: Object, default: () => ({}) },   // {scene_id: 完整可播视频URL}（父组件按每镜有效来源算好，覆盖四引擎槽）
  resolution: { type: String, default: '720x1280' },  // 仅用于舞台比例
})
const emit = defineEmits(['close'])

const API = 'http://localhost:18520/api'

// playlist[i] = { sceneId, kind, videoSrc?, imageSrc?, audioSrc?, fallbackMs }
const playlist = ref([])
const index    = ref(0)
const paused   = ref(false)
const videoEl  = ref(null)
const audioEl  = ref(null)
let imageFallbackTimer = null
const FALLBACK_MS = 4000

// v1.6.2: 四引擎视频槽 asset_type（ltx 仍叫 'video'）
const VIDEO_ASSET_TYPES = ['video', 'video_msr', 'video_slideshow', 'video_seedance']
function _videoUrl(sceneId, assetType = 'video') {
  return `${API}/projects/${props.projectId}/assets/file/${sceneId}/${assetType}`
}
function _imageUrl(sceneId) {
  return `${API}/projects/${props.projectId}/assets/file/${sceneId}/image_start`
}
function _audioUrl(sceneId) {
  return `${API}/projects/${props.projectId}/assets/file/${sceneId}/audio`
}

async function buildPlaylist() {
  // 一次性拉全项目 asset 清单 —— 不能用 HEAD 探活，因为后端 GET 路由
  // 不接受 HEAD（FastAPI @router.get 只注册 GET，HEAD 返 405）。
  // 注意：/assets 端点返回 {assets, count}，不是 {items}（SFX 端点才用 items）
  let inventory = {}
  try {
    const r = await axios.get(`${API}/projects/${props.projectId}/assets`)
    const items = r.data?.assets || r.data?.items || []
    for (const it of items) {
      const sid = it.scene_id
      if (!sid) continue
      if (!inventory[sid]) inventory[sid] = {}
      // asset_type ∈ {video, video_msr, video_slideshow, video_seedance, image_start, image_end, audio}
      inventory[sid][it.asset_type] = true
      // 任一视频槽 → 记下具体 asset_type，回退时按该槽取文件（覆盖四引擎）
      if (VIDEO_ASSET_TYPES.includes(it.asset_type) && !inventory[sid]._videoType) {
        inventory[sid]._videoType = it.asset_type
      }
    }
  } catch (e) {
    console.warn('[preview] failed to fetch asset inventory:', e)
  }

  const items = []
  for (const s of props.scenes) {
    const sid = s.id
    const inv = inventory[sid] || {}
    // v1.6.2: 优先用父组件下发的「每镜有效来源」完整可播 URL —— 覆盖 ltx/msr/图片放映/seedance
    // 四引擎槽（.mp4/.msr.mp4/.slideshow.mp4/.seedance.mp4），修复非默认引擎试播显示「无素材」。
    const mappedVideo = props.videosMap[sid]
    if (mappedVideo) {
      items.push({ sceneId: sid, kind: 'video', videoSrc: mappedVideo })
      continue
    }
    if (inv._videoType) {   // 回退：按实际视频槽 asset_type 取文件（ltx/msr/放映/seedance 四引擎）
      items.push({ sceneId: sid, kind: 'video', videoSrc: _videoUrl(sid, inv._videoType) })
      continue
    }
    const hasImg   = !!inv.image_start
    const hasAudio = !!inv.audio
    if (hasImg && hasAudio) {
      items.push({ sceneId: sid, kind: 'image_audio',
                   imageSrc: _imageUrl(sid), audioSrc: _audioUrl(sid) })
    } else if (hasImg) {
      items.push({ sceneId: sid, kind: 'image_only',
                   imageSrc: _imageUrl(sid), fallbackMs: FALLBACK_MS })
    } else {
      items.push({ sceneId: sid, kind: 'empty', fallbackMs: 1500 })
    }
  }
  playlist.value = items
}

const currentKind  = computed(() => playlist.value[index.value]?.kind || 'empty')
const currentSrc   = computed(() => playlist.value[index.value]?.videoSrc || '')
const currentImageSrc = computed(() => playlist.value[index.value]?.imageSrc || '')
const currentAudioSrc = computed(() => playlist.value[index.value]?.audioSrc || '')
const currentLabel = computed(() => {
  const s = props.scenes[index.value]
  return s ? (s.title || s.id) : ''
})

const stageStyle = computed(() => {
  const [w, h] = (props.resolution || '720x1280').split('x').map(Number)
  if (!w || !h) return {}
  // 锁死舞台比例与视频分辨率一致
  return { aspectRatio: `${w} / ${h}` }
})

function _clearImageFallback() {
  if (imageFallbackTimer) {
    clearTimeout(imageFallbackTimer)
    imageFallbackTimer = null
  }
}

function _armImageFallback() {
  _clearImageFallback()
  const cur = playlist.value[index.value]
  if (!cur) return
  if (cur.kind === 'image_only' || cur.kind === 'empty') {
    imageFallbackTimer = setTimeout(() => { next() }, cur.fallbackMs || FALLBACK_MS)
  }
}

function next() {
  _clearImageFallback()
  if (index.value < playlist.value.length - 1) {
    index.value += 1
  } else {
    // 播完整片
    close()
  }
}

function prev() {
  _clearImageFallback()
  if (index.value > 0) index.value -= 1
}

function togglePause() {
  paused.value = !paused.value
  const v = videoEl.value, a = audioEl.value
  if (paused.value) {
    v?.pause(); a?.pause()
    _clearImageFallback()
  } else {
    v?.play(); a?.play()
    _armImageFallback()
  }
}

function onMediaError(e) {
  // 单镜素材坏了直接跳过，不让整个预览卡住
  console.warn('[preview] media error on scene', currentLabel.value, e)
  next()
}

function close() {
  _clearImageFallback()
  emit('close')
}

watch(index, () => {
  paused.value = false
  // 切镜后下一帧再 arm，让 DOM 更新到新元素
  setTimeout(_armImageFallback, 0)
})

onMounted(async () => {
  await buildPlaylist()
  if (playlist.value.length === 0) {
    close(); return
  }
  _armImageFallback()
})

onBeforeUnmount(_clearImageFallback)
</script>

<style scoped>
.pp-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.78);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999;
}
.pp-modal {
  background: var(--color-background, #1a1a1a);
  border-radius: 8px;
  padding: 16px;
  width: min(90vw, 1100px);
  max-height: 92vh;
  display: flex; flex-direction: column; gap: 12px;
}
.pp-header {
  display: flex; align-items: center; gap: 12px;
}
.pp-header h3 { margin: 0; flex: 1; }
.pp-progress { font-size: 13px; }
.pp-stage {
  background: #000;
  border-radius: 4px;
  display: flex; align-items: center; justify-content: center;
  max-height: 70vh;
  overflow: hidden;
  position: relative;
}
.pp-video, .pp-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.pp-empty {
  color: #888; padding: 40px;
}
.pp-controls {
  display: flex; align-items: center; gap: 8px;
}
.pp-hint { margin-left: auto; font-size: 12px; }
</style>
