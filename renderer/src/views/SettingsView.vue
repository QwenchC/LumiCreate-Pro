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
        <!-- F2: 语言切换 -->
        <div class="form-group">
          <label>Language / 语言</label>
          <select v-model="currentLocale" @change="onChangeLocale" class="input select" style="max-width:260px">
            <option v-for="l in availableLocales" :key="l.value" :value="l.value">{{ l.label }}</option>
          </select>
          <p class="hint">界面语言（重启或切换页面后部分组件文案才会同步）。</p>
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
          <p v-if="settings.text_engine.engine_type === 'bailian'" class="hint">
            百炼固定地址：<code>https://dashscope.aliyuncs.com/compatible-mode/v1</code>
          </p>
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
        <div class="form-group">
          <label>批量并发数</label>
          <input type="number" min="1" max="2500" step="1"
                 v-model.number="settings.text_engine.concurrency" class="input" style="width:120px" />
          <p class="form-hint">
            角色自动检测 / 图片提示词 / 视频提示词等批量任务的最大并发请求数。
            本地模型（Ollama、LM Studio）通常 <b>1–4</b>；
            云端高并发模型（DeepSeek v4-flash 限 2500、Bailian 等）可调到 <b>50–500</b> 大幅缩短全片生成时间。
            过高会触发供应商的速率限制并报错，按所购模型的并发上限设置即可。
          </p>
        </div>
      </section>

      <!-- Image engine -->
      <section v-if="activeTab === 'image'" class="settings-section">
        <h3 class="section-title">图片生成引擎</h3>

        <!-- v1.4.5: 引擎切换 -->
        <div class="form-group">
          <label>引擎类型</label>
          <div class="radio-group">
            <label class="radio-item">
              <input type="radio" value="comfyui" v-model="settings.image_engine.engine_type" />
              ComfyUI（本地，工作流驱动）
            </label>
            <label class="radio-item">
              <input type="radio" value="pollinations" v-model="settings.image_engine.engine_type" />
              Pollinations（云端，按模型名直生 — 适合无 GPU / 想用 Flux/GPT-Image 等托管模型）
            </label>
          </div>
        </div>

        <!-- ComfyUI 配置 -->
        <template v-if="settings.image_engine.engine_type === 'comfyui'">
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
        </template>

        <!-- v1.4.5: Pollinations 配置 -->
        <template v-else-if="settings.image_engine.engine_type === 'pollinations'">
          <div class="form-group">
            <label>Pollinations 基础地址</label>
            <input v-model="settings.image_engine.pollinations_base_url" class="input"
                   placeholder="https://gen.pollinations.ai" />
          </div>
          <div class="form-group">
            <label>API Key
              <a href="https://enter.pollinations.ai" target="_blank"
                 style="font-weight:normal;font-size:12px;margin-left:8px">
                在 enter.pollinations.ai 获取 ↗
              </a>
            </label>
            <input v-model="settings.image_engine.pollinations_api_key" class="input"
                   type="password" placeholder="sk_..." />
            <p class="form-hint">
              sk_ 是 secret key（服务端用，无 IP 限流），pk_ 是 publishable key（前端用，每 IP 每小时 1 次）。
              本应用用 secret key（sk_）即可。
            </p>
          </div>
          <div class="form-group">
            <label>默认模型</label>
            <select v-model="settings.image_engine.pollinations_model" class="input"
                    style="max-width:300px">
              <option v-for="m in pollinationsModels" :key="m" :value="m">{{ m }}</option>
            </select>
            <button class="btn btn-secondary btn-sm" style="margin-left:8px"
                    :disabled="pollLoading" @click="refreshPollinationsModels">
              {{ pollLoading ? '⏳' : '↻' }} 刷新
            </button>
            <button class="btn btn-secondary btn-sm" style="margin-left:8px"
                    :disabled="pollTesting" @click="testPollinations">
              {{ pollTesting ? '⏳' : '🔌' }} 测试连接
            </button>
            <p v-if="pollTestMsg" :class="pollTestOk ? 'form-hint' : 'form-warn'">
              {{ pollTestOk ? '✓' : '⚠' }} {{ pollTestMsg }}
            </p>
          </div>
        </template>

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
              <input type="radio" value="indextts" v-model="settings.audio_engine.engine_type" />
              IndexTTS-2.0（本地 Gradio）
            </label>
            <label class="radio-item">
              <input type="radio" value="gptsovits" v-model="settings.audio_engine.engine_type" />
              GPT-SoVITS（本地 API）
            </label>
            <label class="radio-item">
              <input type="radio" value="msedge" v-model="settings.audio_engine.engine_type" />
              微软神经语音（Edge TTS，在线，免音色参考，支持全部对白模式）
            </label>
            <label class="radio-item">
              <input type="radio" value="manual" v-model="settings.audio_engine.engine_type" />
              手动导入音频
            </label>
          </div>
        </div>

        <!-- IndexTTS settings -->
        <template v-if="settings.audio_engine.engine_type === 'indextts'">
          <div class="form-group">
            <label>IndexTTS 地址</label>
            <input v-model="settings.audio_engine.api_url" class="input" placeholder="http://localhost:7860" />
          </div>
          <div class="form-group">
            <label>音色参考文件夹</label>
            <div class="input-with-btn">
              <input v-model="settings.audio_engine.voice_ref_dir" class="input" placeholder="存放音色参考 .wav/.mp3 的文件夹路径" />
              <button class="btn btn-secondary btn-sm" @click="browseFolder('voice_ref_dir')">浏览…</button>
            </div>
          </div>
          <div class="form-group">
            <label>情感参考文件夹</label>
            <div class="input-with-btn">
              <input v-model="settings.audio_engine.emotion_ref_dir" class="input" placeholder="存放情感参考 .wav/.mp3 的文件夹路径" />
              <button class="btn btn-secondary btn-sm" @click="browseFolder('emotion_ref_dir')">浏览…</button>
            </div>
          </div>
          <div class="form-group">
            <label>默认音色参考文件名</label>
            <input v-model="settings.audio_engine.default_voice_ref" class="input" placeholder="default.wav" />
          </div>
          <div class="form-group">
            <label>默认情感权重 {{ settings.audio_engine.default_emo_weight }}</label>
            <input type="range" min="0" max="1.6" step="0.1"
              v-model.number="settings.audio_engine.default_emo_weight" class="input" style="padding:0" />
          </div>
        </template>

        <!-- GPT-SoVITS settings -->
        <div class="form-group" v-if="settings.audio_engine.engine_type === 'gptsovits'">
          <label>API 地址</label>
          <input v-model="settings.audio_engine.api_url" class="input" placeholder="http://localhost:9880" />
        </div>

        <!-- Microsoft Edge TTS settings -->
        <template v-if="settings.audio_engine.engine_type === 'msedge'">
          <div class="form-group">
            <label>默认音色（Voice）</label>
            <select v-model="settings.audio_engine.msedge_voice" class="input select">
              <optgroup v-for="g in groupedAvailableVoices" :key="g.gender" :label="g.label">
                <option v-for="v in g.items" :key="v.value" :value="v.value">{{ v.label }}</option>
              </optgroup>
            </select>
            <p class="form-hint">
              edge-tts 内置中文神经语音；可手动改成其他语言/地区代码（如 en-US-AriaNeural）。
              <span v-if="msedgeAvailableVoices.length">
                当前下拉已按"全部测试"通过名单过滤（{{ msedgeAvailableVoices.length }} 个可用）。
              </span>
              <span v-else style="color:var(--color-warning, #fa3)">
                还未运行过音色测试，下方按钮一键检测全部 14 个音色，跑过后下拉会自动只显示能用的。
              </span>
            </p>
          </div>
          <div class="form-group">
            <label>默认语速</label>
            <select v-model="settings.audio_engine.msedge_rate" class="input select">
              <option value="-25%">慢</option>
              <option value="+0%">正常</option>
              <option value="+25%">快（漫剧默认）</option>
              <option value="+50%">很快</option>
            </select>
            <p class="form-hint">非朗读模式（对白 / 旁白 / 混合）下，每段对白也会按这个语速合成。</p>
          </div>
          <div class="form-group">
            <label>🧪 全部音色测试（一次性筛掉不可用的）</label>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <button class="btn btn-primary btn-sm" :disabled="msTestAllRunning" @click="testAllMsVoices">
                {{ msTestAllRunning ? `测试中… ${msTestAllProgress}/${msTestAllTotal}` : '🧪 测试全部 14 个音色' }}
              </button>
              <span v-if="msTestAllSummary" class="text-muted" style="font-size:12px">
                {{ msTestAllSummary }}
              </span>
            </div>
            <div v-if="msTestAllResults.length" class="ms-test-grid" style="margin-top:8px;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px">
              <div v-for="r in msTestAllResults" :key="r.value"
                   :class="['ms-test-row', r.ok === true ? 'ok' : r.ok === false ? 'bad' : 'pending']"
                   :title="r.error || ''">
                <span class="ms-test-icon">{{ r.ok === true ? '✓' : r.ok === false ? '✗' : '…' }}</span>
                <span class="ms-test-label">{{ r.label }}</span>
              </div>
            </div>
            <p class="form-hint">
              通过的音色会写入 settings；之后在「角色管理」「音频生成」等下拉里，不通过的音色不会再出现，
              避免你不小心选了一个临时挂掉的音色导致整片生成失败。
            </p>
          </div>

          <div class="form-group">
            <label>试听（验证当前音色是否可用）</label>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <input v-model="msTestText" class="input" style="flex:1;min-width:200px"
                     placeholder="试听文本，例：你好，这是一段测试" />
              <button class="btn btn-secondary btn-sm" :disabled="msTesting"
                      @click="testMsVoice(settings.audio_engine.msedge_voice, settings.audio_engine.msedge_rate)">
                {{ msTesting ? '生成中…' : '▶ 试听' }}
              </button>
            </div>
            <audio v-if="msTestAudio" :key="msTestRev"
                   :src="`data:audio/mpeg;base64,${msTestAudio}`" controls
                   style="width:100%;margin-top:8px;height:36px" />
            <p v-if="msTestError" class="form-hint" style="color:var(--color-error)">
              ⚠ 试听失败：{{ msTestError }}（该音色当前可能临时不可用，请改选其他音色）
            </p>
            <p v-else class="form-hint">
              edge-tts 由微软公网服务提供，偶尔会有个别音色短时不可用——批量生成前**先点试听**，
              出图问题更省事。失败时换一个音色即可。
            </p>
          </div>
        </template>

        <!-- IndexTTS / GPT-SoVITS 也提供一个简单的连接测试 -->
        <div class="form-group" v-if="settings.audio_engine.engine_type !== 'msedge' && settings.audio_engine.engine_type !== 'manual'">
          <label>引擎连接测试</label>
          <button class="btn btn-secondary btn-sm" :disabled="ttsTesting" @click="testAudioConnection">
            {{ ttsTesting ? '测试中…' : '🔌 测试连接' }}
          </button>
          <p v-if="ttsTestMsg" class="form-hint" :style="{color: ttsTestOk ? 'var(--color-success, #6cf)' : 'var(--color-error)'}">
            {{ ttsTestMsg }}
          </p>
        </div>

        <div class="form-group">
          <label>默认生成版本数</label>
          <input type="number" v-model.number="settings.audio_engine.default_gen_count" class="input" min="1" max="10" style="width:80px" />
        </div>
      </section>

      <!-- Video engine -->
      <section v-if="activeTab === 'video'" class="settings-section">
        <h3 class="section-title">视频生成引擎</h3>
        <!-- v1.4.10: 引擎切换 —— ComfyUI 本地 vs 火山引擎云端 API -->
        <div class="form-group">
          <label>引擎模式</label>
          <div class="radio-row">
            <label class="radio">
              <input type="radio" v-model="settings.video_engine.engine_type" value="comfyui" />
              <span>ComfyUI 本地（LTX-2.3）</span>
            </label>
            <label class="radio">
              <input type="radio" v-model="settings.video_engine.engine_type" value="volcengine_seedance" />
              <span>火山引擎 Seedance 2.0（云端，付费）</span>
            </label>
          </div>
          <p class="hint">
            云端 API 不占本地显存，但每次生成会消耗你火山方舟账户余额。
            切换后到「视频生成」页跑批前，建议先在下方点「🔌 测试连接」确认配置。
          </p>
        </div>

        <!-- 火山引擎配置（engine_type === 'volcengine_seedance' 才显示） -->
        <template v-if="settings.video_engine.engine_type === 'volcengine_seedance'">
          <div class="form-group">
            <label>Ark API Base URL</label>
            <input v-model="settings.video_engine.volcengine_base_url" class="input"
                   placeholder="https://ark.cn-beijing.volces.com/api/v3" />
            <p class="hint">默认走北京区域；其它区域用户改成对应 endpoint（如 cn-shanghai）</p>
          </div>
          <div class="form-group">
            <label>API Key（ARK_API_KEY）</label>
            <input v-model="settings.video_engine.volcengine_api_key" class="input"
                   type="password" placeholder="在火山方舟控制台 → API Key 管理 创建" />
          </div>
          <div class="form-group">
            <label>模型 / Endpoint ID</label>
            <input v-model="settings.video_engine.volcengine_model_id" class="input"
                   placeholder="ep-2024xxxxxxx-xxxxx 或官方模型别名" />
            <p class="hint">
              在控制台「在线推理 → 自定义推理接入点」创建后填入；
              或直接填官方模型别名（如 <code>doubao-seedance-1.0-pro</code>，具体见 API 文档）
            </p>
          </div>
          <div class="form-group form-row">
            <div style="flex:1">
              <label>单镜时长（秒）</label>
              <input type="number" v-model.number="settings.video_engine.volcengine_duration_secs"
                     class="input" min="2" max="15" />
              <p class="hint">Seedance 2.0/1.5: 4-15；Seedance 1.0: 2-12</p>
            </div>
            <div style="flex:1">
              <label>分辨率</label>
              <select v-model="settings.video_engine.volcengine_resolution"
                      class="input select">
                <option value="480p">480p</option>
                <option value="720p">720p</option>
                <option value="1080p">1080p（更贵；Seedance 2.0 fast 不支持）</option>
              </select>
            </div>
            <div style="flex:1">
              <label>宽高比</label>
              <select v-model="settings.video_engine.volcengine_ratio"
                      class="input select">
                <option value="adaptive">adaptive（自动适配）</option>
                <option value="16:9">16:9</option>
                <option value="9:16">9:16（竖屏）</option>
                <option value="4:3">4:3</option>
                <option value="3:4">3:4（竖屏）</option>
                <option value="1:1">1:1（方形）</option>
                <option value="21:9">21:9</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label class="checkbox">
              <input type="checkbox" v-model="settings.video_engine.volcengine_use_image" />
              <span>使用首末帧驱动（i2v / flf2v）—— 取消则纯文生视频</span>
            </label>
            <label class="checkbox" style="margin-top:6px">
              <input type="checkbox" v-model="settings.video_engine.volcengine_generate_audio" />
              <span>由 Seedance 自带生成音频（漫剧 reading 模式建议关 ── 我们用 TTS 独立产出）</span>
            </label>
            <label class="checkbox" style="margin-top:6px">
              <input type="checkbox" v-model="settings.video_engine.volcengine_watermark" />
              <span>视频带"AI 生成"水印</span>
            </label>
            <label class="checkbox" style="margin-top:6px">
              <input type="checkbox" v-model="settings.video_engine.volcengine_camera_fixed" />
              <span>固定摄像头（Seedance 2.0 暂不支持）</span>
            </label>
          </div>
          <div class="form-group">
            <label>seed 种子（-1 = 随机；其它整数 = 复现）</label>
            <input type="number" v-model.number="settings.video_engine.volcengine_seed"
                   class="input" style="width:160px" min="-1" />
          </div>
          <div class="form-group form-row">
            <div style="flex:1">
              <label>轮询超时（秒）</label>
              <input type="number" v-model.number="settings.video_engine.volcengine_poll_timeout"
                     class="input" min="30" max="3600" />
            </div>
            <div style="flex:1">
              <label>轮询间隔（秒）</label>
              <input type="number" v-model.number="settings.video_engine.volcengine_poll_interval"
                     class="input" min="1" max="60" />
            </div>
          </div>
          <div class="form-group">
            <button class="btn btn-secondary" @click="testVolcengine" :disabled="volcTesting">
              {{ volcTesting ? '测试中…' : '🔌 测试连接' }}
            </button>
            <p v-if="volcTestMsg" class="form-hint"
               :style="{color: volcTestOk ? 'var(--color-success, #6cf)' : 'var(--color-error)'}">
              {{ volcTestMsg }}
            </p>
          </div>
          <hr style="border-color: var(--color-border); margin: 16px 0;" />
          <p class="hint" style="opacity:0.7">下方 ComfyUI 配置在云端模式下不生效，但保留不动 ——
            切回本地模式时无需重新填。</p>
        </template>

        <h4 class="section-subtitle" v-if="settings.video_engine.engine_type === 'volcengine_seedance'">
          ComfyUI 本地配置（备用）
        </h4>
        <div class="form-group">
          <label>ComfyUI 地址</label>
          <input v-model="settings.video_engine.comfyui_url" class="input" placeholder="http://localhost:8188" />
        </div>
        <div class="form-group">
          <label>工作流文件夹</label>
          <div class="input-with-btn">
            <input v-model="settings.video_engine.workflow_dir" class="input" placeholder="留空则使用图片引擎工作流文件夹" />
            <button class="btn btn-secondary btn-sm" @click="browseVideoWfDir">浏览…</button>
          </div>
          <p class="hint">填写 ComfyUI workflows 目录路径，留空时自动使用图片引擎的工作流目录</p>
        </div>
        <div class="form-group">
          <label>ComfyUI input 目录</label>
          <div class="input-with-btn">
            <input v-model="settings.video_engine.comfyui_input_dir" class="input" placeholder="留空则自动从工作流文件夹推断" />
            <button class="btn btn-secondary btn-sm" @click="browseVideoInputDir">浏览…</button>
          </div>
          <p class="hint">ComfyUI 的 input/ 目录路径，用于直接写入音频文件（绕过不支持 /upload/audio 的旧版本）</p>
        </div>
        <div class="form-group">
          <label>默认工作流</label>
          <input v-model="settings.video_engine.default_workflow" class="input" placeholder="flfa2i-lumicreate" />
        </div>
        <div class="form-group">
          <label>默认分辨率</label>
          <select v-model="settings.video_engine.resolution" class="input select">
            <option value="720x1280">720×1280（竖屏 HD）</option>
            <option value="1280x720">1280×720（横屏 HD）</option>
            <option value="576x1024">576×1024（竖屏 中）</option>
            <option value="1024x576">1024×576（横屏 中）</option>
            <option value="544x960">544×960（竖屏 小）</option>
            <option value="960x544">960×544（横屏 小）</option>
          </select>
          <p class="hint">⚠ 由于本地算力有限，每边最大 1280px；后端会自动对齐至 32 的倍数</p>
        </div>
        <div class="form-group">
          <label>帧率</label>
          <select v-model.number="settings.video_engine.fps" class="input select">
            <option :value="24">24 fps</option>
            <option :value="25">25 fps</option>
            <option :value="30">30 fps</option>
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
import { ref, watch, onMounted, computed } from 'vue'
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

// v1.4.5: Pollinations
const pollinationsModels = ref([
  'flux', 'gptimage', 'nanobanana', 'kontext', 'seedream', 'zimage', 'qwen-image',
])
const pollLoading  = ref(false)
const pollTesting  = ref(false)
const pollTestMsg  = ref('')
const pollTestOk   = ref(true)

async function refreshPollinationsModels() {
  pollLoading.value = true
  try {
    const r = await api.get('/image-engine/pollinations/models')
    if (r.data?.models?.length) pollinationsModels.value = r.data.models
  } catch (e) {
    console.warn('refresh pollinations models failed', e)
  } finally {
    pollLoading.value = false
  }
}
async function testPollinations() {
  pollTesting.value = true
  pollTestMsg.value = ''
  try {
    const r = await api.get('/image-engine/pollinations/test')
    pollTestOk.value  = !!r.data?.success
    pollTestMsg.value = r.data?.message || (r.data?.success ? '连接成功' : '连接失败')
  } catch (e) {
    pollTestOk.value  = false
    pollTestMsg.value = e?.response?.data?.message || e.message || String(e)
  } finally {
    pollTesting.value = false
  }
}

// ── MS Edge 试听 ──────────────────────────────────────────────────────────────
import { MSEDGE_VOICES, filterVoices, groupByGender } from '../data/msedgeVoices'
import { availableLocales, setLocale, i18n } from '../i18n'

const currentLocale = ref(i18n.global.locale.value)
function onChangeLocale() {
  setLocale(currentLocale.value)
}

const msTestText  = ref('你好，这是一段测试。')
const msTesting   = ref(false)
const msTestAudio = ref('')
const msTestRev   = ref(0)
const msTestError = ref('')

// 已通过音色测试的列表（来自 settings.audio_engine.msedge_available_voices）
const msedgeAvailableVoices = computed(
  () => settings.value?.audio_engine?.msedge_available_voices || []
)
// 设置页"默认音色"下拉用的过滤列表（保留当前选中以免被过滤掉）
const groupedAvailableVoices = computed(() => {
  const allowed = msedgeAvailableVoices.value
  const current = settings.value?.audio_engine?.msedge_voice
  return groupByGender(filterVoices(allowed, [current]))
})

// 全部音色测试
const msTestAllRunning  = ref(false)
const msTestAllResults  = ref([])     // [{value, label, ok:true|false|null, error}]
const msTestAllProgress = ref(0)
const msTestAllTotal    = ref(MSEDGE_VOICES.length)
const msTestAllSummary  = ref('')

async function testAllMsVoices() {
  msTestAllRunning.value  = true
  msTestAllSummary.value  = ''
  msTestAllProgress.value = 0
  msTestAllTotal.value    = MSEDGE_VOICES.length
  // 初始化结果矩阵（pending）
  msTestAllResults.value = MSEDGE_VOICES.map(v => ({ ...v, ok: null, error: '' }))
  try {
    const { data } = await api.post('/audio-engine/ms-tts/test-all', {
      voices: MSEDGE_VOICES.map(v => v.value),
      text: '测试',
      save: true,
    })
    // 把后端返回的 results 映射回 UI
    msTestAllResults.value = MSEDGE_VOICES.map(v => {
      const r = data.results?.[v.value] || { ok: false, error: 'no result' }
      return { ...v, ok: !!r.ok, error: r.error || '' }
    })
    msTestAllProgress.value = data.tested || msTestAllTotal.value
    // 同步 settings 内存以便下拉立即过滤（也已在后端持久化）
    if (settings.value?.audio_engine) {
      settings.value.audio_engine.msedge_available_voices = data.available || []
    }
    msTestAllSummary.value = `共测试 ${data.tested} 个，通过 ${data.passed} 个；已写入设置。`
  } catch (e) {
    msTestAllSummary.value = '测试失败：' + (e?.response?.data?.detail || e.message || '请求异常')
  } finally {
    msTestAllRunning.value = false
  }
}

async function testMsVoice(voice, rate) {
  if (!voice) { msTestError.value = '请先选择音色'; return }
  msTesting.value = true
  msTestError.value = ''
  msTestAudio.value = ''
  try {
    const { data } = await api.post('/audio-engine/ms-tts', {
      text: msTestText.value || '你好，这是一段测试。',
      voice, rate: rate || '+0%',
    })
    msTestAudio.value = data.data
    msTestRev.value++
  } catch (e) {
    msTestError.value = e?.response?.data?.detail || e.message || '请求失败'
  } finally {
    msTesting.value = false
  }
}

// ── IndexTTS / GPT-SoVITS 连接测试 ────────────────────────────────────────────
const ttsTesting = ref(false)
const ttsTestOk  = ref(false)
const ttsTestMsg = ref('')

async function testAudioConnection() {
  ttsTesting.value = true
  ttsTestMsg.value = ''
  try {
    const { data } = await api.get('/audio-engine/test')
    ttsTestOk.value  = !!data.success
    ttsTestMsg.value = (data.success ? '✓ ' : '✗ ') + (data.message || '')
  } catch (e) {
    ttsTestOk.value  = false
    ttsTestMsg.value = '✗ ' + (e?.response?.data?.detail || e.message || '请求失败')
  } finally {
    ttsTesting.value = false
  }
}

// v1.4.10: 火山引擎 Seedance 连接测试
const volcTesting = ref(false)
const volcTestOk  = ref(false)
const volcTestMsg = ref('')

async function testVolcengine() {
  volcTesting.value = true
  volcTestMsg.value = ''
  try {
    // 先保存当前设置（让 backend 看得到最新 key / url）
    await api.put('/settings', settings.value)
    const { data } = await api.get('/video-engine/volcengine-test')
    volcTestOk.value  = !!data.success
    volcTestMsg.value = (data.success ? '✓ ' : '✗ ') + (data.message || '')
  } catch (e) {
    volcTestOk.value  = false
    volcTestMsg.value = '✗ ' + (e?.response?.data?.detail || e.message || '请求失败')
  } finally {
    volcTesting.value = false
  }
}

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
  bailian:      '阿里云百炼（通义千问）',
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

// Auto-fill base_url when switching engine type
const ENGINE_URLS = {
  ollama:       'http://localhost:11434',
  lmstudio:     'http://localhost:1234',
  deepseek:     'https://api.deepseek.com',
  bailian:      'https://dashscope.aliyuncs.com/compatible-mode/v1',
  openai_compat: '',
}
watch(
  () => settings.value?.text_engine?.engine_type,
  (type, oldType) => {
    // oldType is undefined on the initial load transition (null→value); skip it
    if (!oldType || !type || !settings.value) return
    const preset = ENGINE_URLS[type]
    if (preset !== undefined) settings.value.text_engine.base_url = preset
  }
)

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

async function browseFolder(field) {
  const folder = await window.electronAPI?.selectFolder()
  if (folder) settings.value.audio_engine[field] = folder
}

async function browseVideoWfDir() {
  const folder = await window.electronAPI?.selectFolder()
  if (folder) settings.value.video_engine.workflow_dir = folder
}

async function browseVideoInputDir() {
  const folder = await window.electronAPI?.selectFolder()
  if (folder) settings.value.video_engine.comfyui_input_dir = folder
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
  // Save current UI state first so backend uses the updated engine config
  await store.saveSettings(settings.value)
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
.input-with-btn { display: flex; gap: 8px; }
.hint { font-size: 11px; color: var(--color-text-muted); margin-top: 5px; }
.form-hint { font-size: 11px; color: var(--color-text-muted); margin-top: 5px; }
.form-warn { font-size: 11px; color: var(--danger, #fc8181); margin-top: 5px; }
.ms-test-row {
  display:flex; align-items:center; gap:6px;
  padding:4px 8px; border-radius:4px; font-size:12px;
  border:1px solid var(--color-border);
}
.ms-test-row.ok      { background:rgba(64,180,90,.12);  border-color:rgba(64,180,90,.5);  }
.ms-test-row.bad     { background:rgba(220,60,60,.10);  border-color:rgba(220,60,60,.55); opacity:.7; }
.ms-test-row.pending { background:rgba(180,180,180,.10);}
.ms-test-icon  { font-weight:700; width:14px; text-align:center; }
.ms-test-label { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
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
