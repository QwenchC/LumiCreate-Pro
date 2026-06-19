<template>
  <div class="tab-panel video-tab">

    <!-- ── Toolbar ── -->
    <div class="video-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">视频生成</h3>
        <span class="text-muted" style="font-size:13px" v-if="scenes.length">
          {{ readyCount }} / {{ scenes.length }} 个分镜就绪
        </span>
        <!-- v1.4.10: 引擎来源标识 —— 提醒用户当前是本地 ComfyUI 还是云端 API -->
        <span v-if="engineType === 'volcengine_seedance'"
              class="engine-badge engine-badge-cloud"
              :title="'当前用云端火山引擎 Seedance API，每次生成消耗配额'">
          ☁ 火山引擎云端
        </span>
        <span v-else class="engine-badge engine-badge-local"
              :title="'当前用本地 ComfyUI / LTX-2.3'">
          🖥 本地
        </span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-danger btn-sm" v-if="running" @click="stopGeneration">⏹ 停止</button>
        <template v-else>
          <!-- v1.4.8: 试播预览 —— 合并前轻量串播分镜，不出文件 -->
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!scenes.length"
            :title="'按分镜顺序串播现有素材（视频优先，否则图+音频，最后只图）'"
            @click="previewOpen = true"
          >▶︎ 试播</button>
          <!-- v1.4.8: SFX 时间轴编辑 —— 给每镜次叠加点状音效 -->
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!scenes.length"
            :title="'每镜次时间轴上叠加 SFX（脚步、关门、抽刀…）。需在「图片放映」模式重新渲染才生效。'"
            @click="sfxDialogOpen = true"
          >🔊 音效</button>
          <button
            class="btn btn-success btn-sm"
            :disabled="!allVideosReady || merging"
            :title="!allVideosReady ? '所有分镜视频生成完毕后才能合并' : '合并所有分镜视频（可设过渡 + BGM）'"
            @click="openMergeOptions"
          >{{ merging ? '合并中…' : '🎬 合并视频…' }}</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!selectedWorkflow || !readyCount"
            @click="resumeGeneration"
            :title="!readyCount ? '需要首帧图片、末帧图片和合并音频' : '仅生成尚未完成的视频分镜'"
          >⏯ 继续生成</button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="!scenes.length || generatingAllVideoPrompts"
            title="为所有分镜用 LLM 自动生成视频提示词"
            @click="generateAllPrompts"
          >
            {{ generatingAllVideoPrompts
              ? `提示词 ${videoPromptProgress}/${scenes.length}…`
              : '✦ 全部生成提示词' }}
          </button>
          <button
            v-if="generatingAllVideoPrompts"
            class="btn btn-danger btn-sm"
            @click="_videoPromptAbort?.abort(); generatingAllVideoPrompts = false; generatingVideoPromptId = null"
          >⏹ 中断提示词</button>
          <!-- v1.6: 批量生成全部【多图参考(MSR)】分镜的提示词（参考图N + 动作叙述格式）-->
          <button
            v-if="videoMode === 'ltx' && msrSceneCount"
            class="btn btn-secondary btn-sm"
            :disabled="msrPromptRunning"
            title="为所有启用「多图参考」的分镜生成 MSR 视频提示词（参考图+动作叙述）"
            @click="genAllMsrPrompts"
          >
            {{ msrPromptRunning
              ? `MSR 提示词 ${msrPromptProgress}/${msrPromptTotal}…`
              : `🎬 全部MSR提示词 (${msrSceneCount})` }}
          </button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!selectedWorkflow || !readyCount"
            @click="startGeneration"
            :title="!readyCount ? '需要首帧图片、末帧图片和合并音频' : ''"
          >▶ 开始生成</button>
        </template>
      </div>
    </div>

    <!-- D1/D3: 合并设置弹窗 -->
    <Teleport to="body">
      <div v-if="mergeOptionsOpen" class="overlay" @click.self="mergeOptionsOpen = false">
        <div class="dialog card" style="width:520px;max-width:calc(100vw - 40px)">
          <h3 class="dialog-title">🎬 合并设置</h3>

          <div class="form-group">
            <label>🎚 镜间过渡</label>
            <div class="form-row">
              <select v-model="mergeTransition" class="input select" style="flex:1">
                <option value="cut">硬切（cut，无过渡 · 最快，与原版相同）</option>
                <option value="fade">渐黑（fade）</option>
                <option value="fadeblack">黑色淡入（fadeblack）</option>
                <option value="dissolve">交叉溶解（dissolve）</option>
                <option value="wipeleft">擦除-向左（wipeleft）</option>
                <option value="wiperight">擦除-向右（wiperight）</option>
                <option value="slideleft">滑动-向左（slideleft）</option>
                <option value="slideright">滑动-向右（slideright）</option>
                <option value="circleopen">圆形展开（circleopen）</option>
                <option value="circleclose">圆形闭合（circleclose）</option>
              </select>
              <input type="number" min="50" max="2000" step="50"
                     v-model.number="mergeTransitionMs" class="input"
                     :disabled="mergeTransition === 'cut'"
                     style="width:90px" title="过渡时长 (ms)" />
              <span class="text-muted" style="font-size:12px;align-self:center">ms</span>
            </div>
            <p class="form-hint">
              非 cut 时整片需要重新编码，会比硬切慢；推荐 200–500ms。
            </p>
          </div>

          <div class="form-group">
            <label>🎵 背景音乐 (BGM)</label>
            <div class="bgm-row">
              <span v-if="bgmInfo.exists" class="bgm-pill">
                ✓ {{ bgmInfo.filename }} · {{ (bgmInfo.size / 1024).toFixed(0) }} KB
              </span>
              <span v-else class="text-muted" style="font-size:12px">未上传</span>
              <button class="btn btn-secondary btn-xs" :disabled="bgmUploading" @click="pickBgmFile">
                {{ bgmUploading ? '上传中…' : (bgmInfo.exists ? '🔁 替换' : '⬆ 上传 BGM') }}
              </button>
              <button v-if="bgmInfo.exists" class="btn btn-ghost btn-xs" @click="deleteBgm">✕ 删除</button>
            </div>
            <div v-if="bgmInfo.exists" class="form-row" style="margin-top:6px;align-items:center">
              <label style="font-size:12px;min-width:64px">音量 dB</label>
              <input type="range" min="-40" max="0" step="1" v-model.number="mergeBgmVolDb" style="flex:1" />
              <span style="font-size:12px;min-width:42px;text-align:right">{{ mergeBgmVolDb }} dB</span>
            </div>
            <div v-if="bgmInfo.exists" class="form-row" style="margin-top:6px">
              <input type="number" min="0" max="5000" step="100"
                     v-model.number="mergeBgmFadeIn" class="input" style="flex:1"
                     placeholder="淡入 ms" title="BGM 淡入时长" />
              <input type="number" min="0" max="5000" step="100"
                     v-model.number="mergeBgmFadeOut" class="input" style="flex:1"
                     placeholder="淡出 ms" title="BGM 淡出时长" />
            </div>
            <p class="form-hint" v-if="bgmInfo.exists">
              BGM 会循环播放到视频结束。音量 -20 dB 通常作为人声背景音；-10 dB 接近人声前景。
            </p>
          </div>

          <div class="dialog-actions">
            <button class="btn btn-ghost" @click="mergeOptionsOpen = false">取消</button>
            <button class="btn btn-primary" :disabled="merging" @click="confirmMerge">
              {{ merging ? '合并中…' : '🎬 开始合并' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- C1: 工作流节点映射编辑器 -->
    <Teleport to="body">
      <div v-if="workflowMetaOpen" class="overlay" @click.self="workflowMetaOpen = false">
        <div class="dialog card" style="width:560px;max-width:calc(100vw - 40px)">
          <h3 class="dialog-title">⚙ 节点映射 · {{ selectedWorkflow }}</h3>
          <p class="text-muted" style="font-size:12px;margin-bottom:10px">
            填写该工作流里下列字段对应的 ComfyUI 节点 ID（LiteGraph 整数）。
            没改过工作流就保持默认即可——这些值就是 <code>flfa2i-lumicreate</code> 的原生节点 ID。
            遇到自定义工作流注入失败时，在 ComfyUI 右上角 Properties 里看节点 ID 填进来。
          </p>
          <div class="meta-grid">
            <template v-for="f in META_FIELDS" :key="f.key">
              <div class="meta-label" :title="f.desc">{{ f.label }}</div>
              <input type="number" class="input meta-input"
                     v-model.number="workflowMetaForm.node_map[f.key].node_id"
                     :placeholder="`默认 ${f.defaultId}`" />
              <input type="number" class="input meta-input meta-widget"
                     v-model.number="workflowMetaForm.node_map[f.key].widget"
                     placeholder="widget" title="widgets_values 下标，默认 0" />
            </template>
          </div>
          <div class="form-group" style="margin-top:8px">
            <label>备注</label>
            <textarea v-model="workflowMetaForm.notes" class="input textarea" rows="2"
                      placeholder="（可选）记录这个工作流的版本/来源等"></textarea>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-ghost" @click="workflowMetaOpen = false">取消</button>
            <button class="btn btn-warning btn-sm" @click="resetWorkflowMeta">↺ 恢复默认</button>
            <button class="btn btn-primary" :disabled="workflowMetaSaving" @click="saveWorkflowMeta">
              {{ workflowMetaSaving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- A1: 上次失败镜次提示 + 一键重试 -->
    <div v-if="lastErrorCount && !running" class="last-errors-banner">
      <span>⚠ 上次失败：{{ lastErrorCount }} 个视频分镜</span>
      <button class="btn btn-warning btn-xs" :disabled="!selectedWorkflow" @click="retryFailedBatch">↻ 只重试失败镜</button>
      <button class="btn btn-ghost btn-xs" @click="dismissLastErrors">✕ 忽略</button>
      <details class="last-errors-detail">
        <summary class="text-muted" style="font-size:11px;cursor:pointer">查看详情</summary>
        <ul>
          <li v-for="(msg, k) in lastErrors" :key="k"><code>{{ k }}</code>: {{ msg }}</li>
        </ul>
      </details>
    </div>

    <!-- ── Config ── -->
    <div class="video-config card" v-if="!running">
      <!-- v1.4.6: 视频引擎模式 -->
      <div class="config-row">
        <div class="config-group" style="flex:1">
          <label class="cfg-label">视频引擎</label>
          <div class="vt-mode-toggle">
            <label :class="{ active: videoMode === 'ltx' }">
              <input type="radio" v-model="videoMode" value="ltx" />
              🎬 AI 视频生成 (LTX/i2v) — 需 GPU
            </label>
            <label :class="{ active: videoMode === 'slideshow' }">
              <input type="radio" v-model="videoMode" value="slideshow" />
              📺 图片放映 — 无 GPU 也能跑，按音频时长拼图片+转场
            </label>
            <!-- v1.4.10++: 火山引擎 Seedance 2.0 云端 API -->
            <label :class="{ active: videoMode === 'volcengine' }">
              <input type="radio" v-model="videoMode" value="volcengine" />
              ☁ 火山引擎 Seedance 2.0 — 云端付费，可按分镜独立配置
            </label>
          </div>
        </div>
      </div>

      <div class="config-row" v-if="videoMode === 'ltx'">
        <div class="config-group">
          <label class="cfg-label">工作流</label>
          <select class="input select-compact" v-model="selectedWorkflow">
            <option value="">— 选择工作流 —</option>
            <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
          </select>
          <button class="btn btn-ghost btn-xs"
                  :disabled="!selectedWorkflow"
                  title="编辑该工作流的节点 ID 映射；自定义工作流改了节点后必须在此更新，否则首末帧/音频/分辨率注入会落到错节点"
                  @click="openWorkflowMeta">⚙ 节点映射</button>
        </div>
        <div class="config-group">
          <label class="cfg-label">分辨率（宽×高）</label>
          <select class="input select-compact" v-model="resolution">
            <option value="720x1280">720×1280（竖屏 HD）</option>
            <option value="1280x720">1280×720（横屏 HD）</option>
            <option value="576x1024">576×1024（竖屏 中）</option>
            <option value="1024x576">1024×576（横屏 中）</option>
            <option value="544x960">544×960（竖屏 小）</option>
            <option value="960x544">960×544（横屏 小）</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">帧率</label>
          <select class="input select-compact" v-model.number="fps" style="width:90px">
            <option :value="24">24fps</option>
            <option :value="25">25fps</option>
            <option :value="30">30fps</option>
          </select>
        </div>
        <!-- v1.6: 多图参考(MSR)视频默认时长 —— 新 MSR 镜未单独设时长时用它 -->
        <div class="config-group">
          <label class="cfg-label" title="启用「多图参考视频」的分镜，未单独设时长时用这个默认值；每镜仍可在分镜里单独调">
            多图参考默认时长
          </label>
          <input type="number" min="1" max="30" step="1"
                 class="input select-compact" style="width:72px"
                 v-model.number="msrDefaultDuration" />
          <span class="text-muted" style="font-size:12px">秒</span>
        </div>
      </div>
      <!-- v1.4.1: 工作流模式提示 + 无音频开关 -->
      <div class="config-row" v-if="workflowKind !== 'unknown'">
        <div class="config-group" style="flex:1">
          <span class="kind-badge" :class="workflowKind">
            {{ workflowFeatures.label }}
          </span>
        </div>
        <label v-if="workflowFeatures.supports_audio" class="no-audio-toggle">
          <input type="checkbox" v-model="noAudioMode" />
          🔇 无音频模式（每分镜单独设时长）
        </label>
      </div>
      <p v-if="videoMode === 'ltx'" class="config-hint">
        ⚠ 视频分辨率限制在 1280px 以内（本地算力有限），每边自动对齐至 32px 倍数
      </p>

      <!-- v1.4.6: 图片放映模式的转场设置 + 一键渲染 -->
      <div v-if="videoMode === 'slideshow'" class="config-row" style="align-items:flex-end">
        <div class="config-group">
          <label class="cfg-label">画面动态（Ken Burns）</label>
          <select class="input select-compact" v-model="slideshowMotion">
            <option value="none">无 — 静帧</option>
            <option value="zoom_in">缓慢放大</option>
            <option value="zoom_out">缓慢缩小</option>
            <option value="pan_left">向左平移</option>
            <option value="pan_right">向右平移</option>
            <option value="pan_up">向上平移</option>
            <option value="pan_down">向下平移</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">镜内转场（首帧→末帧）</label>
          <select class="input select-compact" v-model="slideshowTransition">
            <option value="fade">淡入淡出</option>
            <option value="fadeblack">淡入淡出（经黑）</option>
            <option value="fadewhite">淡入淡出（经白）</option>
            <option value="dissolve">溶解</option>
            <option value="slideleft">左滑</option>
            <option value="slideright">右滑</option>
            <option value="slideup">上滑</option>
            <option value="slidedown">下滑</option>
            <option value="wipeleft">左拭</option>
            <option value="wiperight">右拭</option>
            <option value="zoomin">放大</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">转场时长 (ms)</label>
          <input type="number" min="100" max="3000" step="100"
                 v-model.number="slideshowTransitionMs"
                 class="input" style="width:100px" />
        </div>
        <div class="config-group">
          <label class="cfg-label">分辨率（宽×高）</label>
          <select class="input select-compact" v-model="resolution">
            <option value="1920x1080">1920×1080</option>
            <option value="1280x720">1280×720</option>
            <option value="1080x1920">1080×1920（竖屏）</option>
            <option value="720x1280">720×1280（竖屏）</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">帧率</label>
          <select class="input select-compact" v-model.number="fps" style="width:90px">
            <option :value="24">24fps</option>
            <option :value="25">25fps</option>
            <option :value="30">30fps</option>
          </select>
        </div>
        <button class="btn btn-primary"
                :disabled="slideshowRunning || !scenes.length"
                @click="runSlideshow">
          {{ slideshowRunning ? '⏳ 渲染中…' : '▶ 一键生成所有分镜视频' }}
        </button>
      </div>
      <p v-if="videoMode === 'slideshow'" class="config-hint">
        ℹ 每镜时长 = 该镜音频时长；1 张图静帧、2 张图按选定转场过渡。结束后可去合并视频 + 烧字幕。
      </p>

      <!-- v1.4.10++: 火山引擎模式的全局设置（每分镜可覆盖） -->
      <div v-if="videoMode === 'volcengine'" class="config-row" style="align-items:flex-end">
        <div class="config-group">
          <label class="cfg-label">分辨率（全局）</label>
          <select class="input select-compact" v-model="volcGlobalResolution">
            <option value="480p">480p</option>
            <option value="720p">720p</option>
            <option value="1080p">1080p（更贵）</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">宽高比（全局）</label>
          <select class="input select-compact" v-model="volcGlobalRatio">
            <option value="adaptive">adaptive（自动）</option>
            <option value="16:9">16:9</option>
            <option value="9:16">9:16（竖屏）</option>
            <option value="4:3">4:3</option>
            <option value="3:4">3:4（竖屏）</option>
            <option value="1:1">1:1</option>
            <option value="21:9">21:9</option>
          </select>
        </div>
        <div class="config-group">
          <label class="cfg-label">默认时长 (s)</label>
          <input type="number" min="2" max="15"
                 v-model.number="volcGlobalDuration"
                 class="input" style="width:80px" />
        </div>
        <div class="config-group">
          <label class="cfg-label">默认模式</label>
          <select class="input select-compact" v-model="volcGlobalMode">
            <option value="t2v">文生视频（t2v）</option>
            <option value="i2v_first">图生视频-首帧</option>
            <option value="i2v_flf">图生视频-首尾帧</option>
            <option value="multi_ref">多模态参考（Seedance 2.0）</option>
          </select>
        </div>
      </div>
      <p v-if="videoMode === 'volcengine'" class="config-hint">
        ℹ 上面是默认值；下方每个分镜可独立覆盖。需在「设置 → 视频引擎」配好 API Key + 模型 ID 才能跑。
        <span v-if="!volcReady" style="color:var(--color-warning)">⚠ 未检测到 API Key 或模型 ID 配置，请先到设置页配置</span>
      </p>

      <div v-if="videoMode === 'volcengine'" class="config-row" style="margin-top:6px">
        <button class="btn btn-primary"
                :disabled="volcRunning || !scenes.length || !volcReady"
                @click="runVolcengine">
          {{ volcRunning ? '⏳ 生成中…' : '▶ 一键生成所有分镜视频（火山引擎）' }}
        </button>
        <button class="btn btn-ghost btn-sm"
                @click="applyVolcDefaultsToAll"
                title="把上面的默认值（时长 / 模式）应用到所有分镜，覆盖各镜次的独立设置">
          ⤵ 应用默认到全部分镜
        </button>
      </div>
      <div v-if="slideshowResult" class="config-hint" style="background:rgba(104,211,145,.08);padding:8px;border-radius:4px">
        ✓ 已渲染 {{ slideshowResult.rendered?.length || 0 }} 镜；
        跳过 {{ slideshowResult.skipped?.length || 0 }}，失败 {{ slideshowResult.errors?.length || 0 }}
        <details v-if="(slideshowResult.errors||[]).length || (slideshowResult.skipped||[]).length">
          <summary style="cursor:pointer;font-size:11px">详情</summary>
          <ul style="font-size:11px;margin:4px 0 0 16px">
            <li v-for="e in slideshowResult.errors" :key="'e'+e.scene_id">
              ⚠ {{ e.scene_id }}: {{ e.message }}
            </li>
            <li v-for="s in slideshowResult.skipped" :key="'s'+s.scene_id">
              – {{ s.scene_id }}: {{ s.reason }}
            </li>
          </ul>
        </details>
      </div>
    </div>

    <!-- ── Loading / Empty ── -->
    <div v-if="loadingScenes" class="empty-state"><div class="spinner" /><p class="text-muted">加载中…</p></div>
    <div v-else-if="!scenes.length" class="empty-state">
      <div class="empty-icon">🎞</div><p>请先完成「分镜设计」</p>
    </div>

    <!-- ── Overall progress ── -->
    <div v-if="(running || genFinished) && scenes.length" class="progress-wrap card">
      <div class="progress-label">
        <span>整体进度</span><span>{{ completedCount }} / {{ scenes.length }}</span>
      </div>
      <div class="progress-track"><div class="progress-fill" :style="{ width: overallPct + '%' }" /></div>
    </div>

    <!-- ── Scene master-detail（左栏列表 + 右栏当前分镜详情）── -->
    <div class="video-md" v-if="scenes.length">

      <!-- 左：分镜列表（只显示状态/审阅，不渲染视频 → 缓解多视频同页卡顿） -->
      <div class="video-md-list">
        <div v-for="scene in scenesWithData" :key="'vli'+scene.id"
             class="video-md-item"
             :class="{ active: activeVideoScene && scene.id === activeVideoScene.id }"
             @click="activeVideoSceneId = scene.id">
          <div class="vmd-num">{{ String(scene.index).padStart(2,'0') }}</div>
          <div class="vmd-body">
            <div class="vmd-desc truncate" :title="sceneFullText(scene)">{{ sceneFullText(scene) }}</div>
            <div class="vmd-tags">
              <span class="vmd-review" :class="{ ok: videoReviewed[scene.id] }">
                {{ videoReviewed[scene.id] ? '✅已审阅' : '☐未审' }}
              </span>
              <span v-if="isMsrScene(scene)" class="vmd-mini" title="多图参考视频">🎬</span>
              <span class="vmd-mini"
                    :class="{ ok: videoSrcFor(scene), warn: sceneState[scene.id]==='error' }">
                {{ videoSceneStatusIcon(scene) }}<template v-if="sceneState[scene.id]==='active'"> {{ sceneProgressPct(scene.id) }}%</template>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：当前分镜详情（只渲染 1 个视频 + 全部配置） -->
      <div class="video-md-detail">
        <div v-if="!activeVideoScene" class="text-muted" style="padding:24px;text-align:center">请选择左侧分镜</div>
        <div v-for="scene in (activeVideoScene ? [activeVideoScene] : [])" :key="scene.id" class="scene-video-card card">
        <div class="svcard-cols">

        <!-- ── 左：视频预览区域 ── -->
        <div class="svcard-col-preview">
          <div v-if="videoSrcFor(scene)" class="video-result">
            <video :src="videoSrcFor(scene)" controls preload="metadata" class="video-player" />
            <!-- 双模标识：当前预览的是旧/普通还是多图参考视频（随 MSR 开关切换） -->
            <div class="video-post-actions">
              <span class="msr-ref-tag" :class="isMsrScene(scene) ? 'ok' : ''">
                {{ isMsrScene(scene) ? '🎬 多图参考' : '🎞 普通' }}
              </span>
              <button class="btn btn-ghost btn-xs"
                      :disabled="running || redubState[scene.id] === 'running' || dewmState[scene.id] === 'running'"
                      @click="openRedub(scene)"
                      title="用 RVC 把该分镜视频的人声统一变声（音色一致性）">
                🎙 视频后期（变声）
              </button>
              <span v-if="redubState[scene.id] === 'running'" class="text-muted" style="font-size:11px">
                后期处理中… {{ redubProgressPct(scene.id) }}%
              </span>
              <span v-else-if="redubState[scene.id] === 'done'" class="msr-ref-tag ok">✓ 已变声</span>
              <span v-else-if="redubState[scene.id] === 'error'" class="msr-ref-tag warn">✗ 后期失败</span>
              <button class="btn btn-ghost btn-xs"
                      :disabled="running || dewmState[scene.id] === 'running' || redubState[scene.id] === 'running'"
                      @click="openDewm(scene)"
                      title="用 LTX V2V 去除该分镜视频的字幕/水印（按输入最长边重绘）">
                🧹 去水印去字幕
              </button>
              <span v-if="dewmState[scene.id] === 'running'" class="text-muted" style="font-size:11px">
                去水印中… {{ dewmProgressPct(scene.id) }}%
              </span>
              <span v-else-if="dewmState[scene.id] === 'done'" class="msr-ref-tag ok">✓ 已去水印</span>
              <span v-else-if="dewmState[scene.id] === 'error'" class="msr-ref-tag warn">✗ 去水印失败</span>
            </div>
          </div>
          <div v-else class="video-preview-empty">
            <span class="video-preview-empty-icon">🎬</span>
            <span>{{ isMsrScene(scene) ? '多图参考视频尚未生成' : '视频尚未生成' }}</span>
          </div>
          <!-- 本镜生成进度 -->
          <div class="scene-mini-bar-wrap" v-if="sceneState[scene.id] === 'active'">
            <div class="scene-mini-bar">
              <div class="scene-mini-fill" :style="{ width: sceneProgressPct(scene.id) + '%' }" />
            </div>
            <span class="text-muted" style="font-size:11px">{{ sceneProgressPct(scene.id) }}%</span>
          </div>
        </div>

        <!-- ── 右：分镜配置区域 ── -->
        <div class="svcard-col-config">

        <!-- Header -->
        <div class="svcard-header">
          <span class="scene-num">{{ String(scene.index).padStart(2,'0') }}</span>
          <div class="svcard-desc">{{ sceneFullText(scene) }}</div>
          <!-- v1.6.1: 人工审阅开关（纯标记，不影响任何生成/合并机制；可随时开关） -->
          <button class="review-toggle" :class="{ reviewed: videoReviewed[scene.id] }"
                  @click="toggleVideoReviewed(scene.id)"
                  :title="videoReviewed[scene.id] ? '已审阅通过（点击改回未审阅）' : '未审阅（点击标记为已审阅通过）'">
            {{ videoReviewed[scene.id] ? '✅ 已审阅' : '☐ 未审阅' }}
          </button>
          <span class="svcard-status" :class="sceneStatusClass(scene.id)">
            {{ sceneStatusLabel(scene.id) }}
          </span>
          <!-- Per-scene regen button -->
          <button
            class="btn btn-ghost btn-xs"
            :disabled="running || !sceneReady(scene)"
            @click="generateOne(scene)"
            title="单独生成此分镜"
          >↺</button>
        </div>

        <!-- Readiness indicators (随工作流类型动态显隐) -->
        <div class="asset-checks">
          <span class="asset-tag" :class="scene.hasStart ? 'ok' : 'miss'">
            {{ scene.hasStart ? '✓' : '✗' }} {{ workflowFeatures.requires_end_image ? '首帧' : '参考图' }}
          </span>
          <span v-if="workflowFeatures.requires_end_image"
                class="asset-tag" :class="scene.hasEnd ? 'ok' : 'miss'">
            {{ scene.hasEnd ? '✓' : '✗' }} 末帧
          </span>
          <span v-if="workflowFeatures.supports_audio && !noAudioMode"
                class="asset-tag" :class="scene.hasAudio ? 'ok' : 'miss'">
            {{ scene.hasAudio ? '✓' : '✗' }} 合并音频
            <template v-if="scene.hasAudio"> ({{ formatMs(scene.audioDurationMs) }})</template>
          </span>
          <span v-if="(!workflowFeatures.supports_audio || noAudioMode) && !isMsrScene(scene)"
                class="asset-tag duration-tag">
            ⏱ 时长
            <input type="number" min="1" max="30" step="1"
                   class="duration-input"
                   :value="manualDurations[scene.id] ?? 5"
                   @input="setManualDuration(scene.id, $event.target.value)" />
            <span class="text-muted" style="margin-left:2px">s</span>
          </span>
          <!-- v1.6: 背景图（无角色）—— 有则可启用 MSR 多图参考 -->
          <span v-if="videoMode === 'ltx' && scene.hasBg" class="asset-tag ok">
            ✓ 背景图
          </span>
        </div>

        <!-- Prompt section -->
        <div class="prompt-section">
          <div class="prompt-header">
            <span class="prompt-label">
              视频提示词
              <span v-if="scenePrompts[scene.id]" class="prompt-set-badge">已设置</span>
            </span>
            <div class="prompt-actions">
              <button
                class="btn btn-ghost btn-xs"
                @click="editPrompt(scene)"
                title="手动编辑视频提示词"
              >✎ 编辑</button>
              <button class="btn btn-ghost btn-xs"
                :disabled="!!generatingVideoPromptId"
                @click="generatePrompt(scene)"
                :title="generatingVideoPromptId === scene.id ? 'LLM 生成中…' : '用 LLM 生成视频提示词'"
              >
                {{ generatingVideoPromptId === scene.id ? '⏳ 生成中…' : '✦ 生成' }}
              </button>
              <button
                v-if="scenePrompts[scene.id]"
                class="btn btn-ghost btn-xs"
                @click="togglePrompt(scene.id)"
              >{{ promptVisible[scene.id] ? '收起' : '展开' }}</button>
            </div>
          </div>
          <div v-if="promptVisible[scene.id]" class="prompt-editor-wrap">
            <textarea
              class="prompt-textarea"
              :value="scenePrompts[scene.id]"
              @input="onPromptInput(scene.id, $event.target.value)"
              placeholder="输入视频生成提示词，或点击「生成」自动填写…"
              rows="3"
            />
          </div>
        </div>

        <!-- v1.4.10++: 火山引擎每分镜独立配置 -->
        <div v-if="videoMode === 'volcengine'" class="volc-scene-block">
          <div class="volc-scene-row">
            <span class="cfg-label" style="min-width:48px">模式</span>
            <select class="input input-xs" v-model="volcOpts(scene.id).mode">
              <option value="t2v">文生（t2v）</option>
              <option value="i2v_first">首帧驱动</option>
              <option value="i2v_flf">首末帧驱动</option>
              <option value="multi_ref">多参考（2.0）</option>
            </select>
            <span class="cfg-label" style="margin-left:8px">时长</span>
            <input type="number" min="2" max="15" step="1"
                   class="input input-xs" style="width:64px"
                   v-model.number="volcOpts(scene.id).duration_secs" />
            <span class="text-muted" style="font-size:11px">秒</span>
            <span class="volc-spacer"></span>
            <button class="btn btn-ghost btn-xs"
                    v-if="volcOpts(scene.id).mode !== 't2v' && scene.hasStart"
                    @click="addVolcRefSceneFrame(scene.id, 'scene_start', scene)"
                    title="把该分镜的首帧加入参考图">
              + 首帧
            </button>
            <button class="btn btn-ghost btn-xs"
                    v-if="volcOpts(scene.id).mode === 'multi_ref' && scene.hasEnd"
                    @click="addVolcRefSceneFrame(scene.id, 'scene_end', scene)"
                    title="把该分镜的末帧加入参考图">
              + 末帧
            </button>
            <button class="btn btn-secondary btn-xs"
                    v-if="volcOpts(scene.id).mode !== 't2v'"
                    @click="openRefPickerFor(scene.id)"
                    title="从角色立绘 / 元素库选参考图">
              🎨 加入参考图
            </button>
          </div>
          <!-- 已选参考图缩略图列表 -->
          <div v-if="(volcOpts(scene.id).references || []).length"
               class="volc-refs-grid">
            <div v-for="(r, ri) in volcOpts(scene.id).references"
                 :key="ri" class="volc-ref-chip">
              <img v-if="r._preview_url" :src="r._preview_url"
                   :alt="r._label || r.kind" />
              <div v-else class="volc-ref-noimg">{{ r.kind }}</div>
              <span class="volc-ref-kind">{{ refKindLabel(r.kind) }}</span>
              <button class="volc-ref-del" @click="removeVolcRef(scene.id, ri)"
                      title="移除">✕</button>
            </div>
          </div>
        </div>

        <!-- v1.6: MSR 多图参考视频（仅 LTX 模式 + 该镜有背景图时可启用） -->
        <div v-if="videoMode === 'ltx' && scene.hasBg" class="msr-scene-block">
          <label class="msr-toggle">
            <input type="checkbox"
                   :checked="!!msrEnabled[scene.id]"
                   @change="toggleMsr(scene.id, $event.target.checked)" />
            <span>🎬 多图参考视频（背景图 + 角色白底立绘，免首/末帧）</span>
          </label>
          <div v-if="msrEnabled[scene.id]" class="msr-hint">
            <span class="msr-ref-tag ok">🖼 背景图 ✓</span>
            <span v-for="nm in (scene._scene_characters || []).slice(0,3)"
                  :key="nm" class="msr-ref-tag">🎭 {{ nm }} 白底立绘</span>
            <span v-if="!(scene._scene_characters || []).length"
                  class="msr-ref-tag warn">未指定角色 → 仅用背景图驱动</span>
          </div>
          <div v-if="msrEnabled[scene.id]" class="msr-hint" style="align-items:center">
            <span class="msr-ref-tag" style="border:none;background:none;padding-left:0">⏱ 视频时长</span>
            <input type="number" min="1" max="30" step="1" class="duration-input"
                   :value="manualDurations[scene.id] ?? msrDefaultDuration"
                   @input="setManualDuration(scene.id, $event.target.value)" />
            <span class="text-muted" style="font-size:11px">秒（默认 {{ msrDefaultDuration }}s，自带音轨，可逐镜调）</span>
          </div>
          <div v-if="msrEnabled[scene.id]" class="msr-hint">
            <button class="btn btn-ghost btn-xs"
                    :disabled="msrPromptingId === scene.id || msrPromptRunning"
                    @click="genMsrPrompt(scene)"
                    title="生成该镜的多图参考视频提示词（参考图N + 动作叙述，写入上方视频提示词）">
              {{ msrPromptingId === scene.id ? '⏳ 生成中…' : '✦ 多图参考提示词' }}
            </button>
            <span class="text-muted" style="font-size:11px">写入上方「视频提示词」，作为 MSR 正向提示</span>
          </div>
        </div>

        </div><!-- /svcard-col-config -->
        </div><!-- /svcard-cols -->
      </div><!-- /scene-video-card -->
      </div><!-- /video-md-detail -->
    </div><!-- /video-md -->

    <!-- ── Error banner ── -->
    <div v-if="genError" class="error-banner">
      ⚠ {{ genError }}
      <button class="btn btn-ghost btn-xs" @click="genError = ''">关闭</button>
    </div>

    <!-- ── Merge result dialog ── -->
    <div v-if="mergeResult" class="merge-dialog-overlay" @click.self="mergeResult = null">
      <div class="merge-dialog card">
        <h4 class="merge-dialog-title">🎬 合并完成</h4>
        <p class="merge-dialog-path">{{ mergeResult.output_path }}</p>
        <div class="merge-dialog-actions">
          <button class="btn btn-primary" @click="openMergedVideo">▶ 打开视频</button>
          <button class="btn btn-secondary" @click="showMergedInFolder">📂 打开所在目录</button>
          <button class="btn btn-secondary" @click="bgmMixerOpen = true">🎵 添加 BGM</button>
          <button class="btn btn-ghost" @click="mergeResult = null">关闭</button>
        </div>
      </div>
    </div>

    <!-- v1.4.2: BGM 混音对话框（在 final_video.mp4 上叠加 BGM） -->
    <BgmMixerDialog v-if="bgmMixerOpen"
                    :project-id="projectId"
                    source="final_video"
                    @close="bgmMixerOpen = false" />

    <!-- v1.6: 视频后期 RVC 变声对话框 -->
    <div v-if="redubDialog.visible" class="merge-dialog-overlay"
         @click.self="closeRedub">
      <div class="merge-dialog card" style="max-width:520px">
        <h4 class="merge-dialog-title">🎙 视频后期 · RVC 变声（音色一致性）</h4>
        <p class="text-muted" style="font-size:12px;margin:4px 0 10px">
          分镜 {{ redubDialog.sceneId }} ·
          <span :class="redubDialog.useMsr ? 'msr-ref-tag ok' : 'msr-ref-tag'">
            {{ redubDialog.useMsr ? '🎬 多图参考视频' : '🎞 普通视频' }}
          </span>
          —— 识别分段 → 逐条 RVC 变声 → 换音轨。<b>先预览满意再确认落盘</b>；确认后原片自动备份可回退。
        </p>

        <div class="redub-field">
          <label>RVC 模型（.pth）</label>
          <div style="display:flex;gap:6px;align-items:center">
            <select class="input input-xs" style="flex:1" v-model="redubDialog.model">
              <option value="" disabled>{{ redubDialog.models.length ? '选择音色模型…' : '未找到模型' }}</option>
              <option v-for="m in redubDialog.models" :key="m" :value="m">{{ m }}</option>
            </select>
            <button class="btn btn-ghost btn-xs" @click="reloadRvcModels"
                    :disabled="redubDialog.loadingModels">↻</button>
          </div>
          <span v-if="!redubDialog.rvcExists" class="msr-ref-tag warn" style="margin-top:4px">
            RVC 目录不存在：请在设置里配置 redub_rvc_root
          </span>
        </div>

        <div class="redub-field">
          <label>Whisper 分段模型 / 语言</label>
          <div style="display:flex;gap:6px">
            <select class="input input-xs" style="flex:1" v-model="redubDialog.whisperModel">
              <option value="tiny">tiny</option>
              <option value="base">base</option>
              <option value="small">small</option>
              <option value="medium">medium</option>
              <option value="large-v3">large-v3</option>
            </select>
            <input class="input input-xs" style="width:90px" v-model="redubDialog.language"
                   placeholder="zh" />
          </div>
        </div>

        <div class="redub-field">
          <label>逐说话人映射（可选，留空=整片统一上面的模型）</label>
          <textarea class="prompt-textarea" rows="2"
                    v-model="redubDialog.voiceMapping"
                    placeholder="role1: alice.pth&#10;role2: bob.pth"></textarea>
        </div>

        <!-- v1.6: 工作流可调项 -->
        <div class="redub-field">
          <label>变声参数（RedubReVoice）</label>
          <div class="redub-params">
            <label class="redub-param">变调
              <input type="number" step="1" min="-12" max="12" v-model.number="redubDialog.transpose" />
            </label>
            <label class="redub-param">index_rate
              <input type="number" step="0.01" min="0" max="1" v-model.number="redubDialog.indexRate" />
            </label>
            <label class="redub-param">protect
              <input type="number" step="0.01" min="0" max="0.5" v-model.number="redubDialog.protect" />
            </label>
            <label class="redub-param">rms_mix
              <input type="number" step="0.01" min="0" max="1" v-model.number="redubDialog.rmsMixRate" />
            </label>
            <label class="redub-param">mixback_gain
              <input type="number" step="0.05" min="0" max="2" v-model.number="redubDialog.mixbackGain" />
            </label>
          </div>
        </div>

        <div v-if="redubDialog.error" class="error-banner" style="margin:6px 0">
          ⚠ {{ redubDialog.error }}
        </div>
        <div v-if="redubDialog.running" class="redub-field">
          <div class="scene-mini-bar"><div class="scene-mini-fill"
               :style="{ width: redubDialog.progressPct + '%' }" /></div>
          <span class="text-muted" style="font-size:11px">变声处理中… {{ redubDialog.progressPct }}%（请耐心等待）</span>
        </div>

        <!-- 预览成片：满意再确认落盘 -->
        <div v-if="redubDialog.previewUrl && !redubDialog.running" class="redub-field">
          <label>变声预览（确认前不会改动原视频）</label>
          <video :src="redubDialog.previewUrl" controls preload="metadata"
                 style="width:100%;max-height:280px;border-radius:6px;background:#000" />
        </div>

        <div class="merge-dialog-actions">
          <!-- 未出预览：生成预览 -->
          <button v-if="!redubDialog.previewUrl" class="btn btn-primary"
                  :disabled="redubDialog.running || !redubDialog.model"
                  @click="runRedub">
            {{ redubDialog.running ? '处理中…' : '生成变声预览' }}
          </button>
          <!-- 已出预览：确认 / 重新 / 取消 -->
          <template v-else>
            <button class="btn btn-primary" :disabled="redubDialog.running" @click="confirmRedub">
              ✓ 确认变声（换回视频）
            </button>
            <button class="btn btn-secondary" :disabled="redubDialog.running" @click="runRedub">
              ↻ 重新变声
            </button>
            <button class="btn btn-ghost" :disabled="redubDialog.running" @click="cancelRedub">
              ✕ 取消变声
            </button>
          </template>
          <button v-if="!redubDialog.previewUrl" class="btn btn-ghost"
                  :disabled="redubDialog.running" @click="closeRedub">关闭</button>
        </div>
      </div>
    </div>

    <!-- v1.6: 去水印/去字幕对话框 -->
    <div v-if="dewmDialog.visible" class="merge-dialog-overlay" @click.self="closeDewm">
      <div class="merge-dialog card" style="max-width:480px">
        <h4 class="merge-dialog-title">🧹 视频去水印 / 去字幕（LTX V2V 重绘）</h4>
        <p class="text-muted" style="font-size:12px;margin:4px 0 10px">
          分镜 {{ dewmDialog.sceneId }} ·
          <span :class="dewmDialog.useMsr ? 'msr-ref-tag ok' : 'msr-ref-tag'">
            {{ dewmDialog.useMsr ? '🎬 多图参考视频' : '🎞 普通视频' }}
          </span>
          —— 用 LTX IC-LoRA 去字幕+去水印重绘整段视频。
          输出最长边默认 = 输入视频最长边；显存不足可调小。原片自动备份为
          {{ dewmDialog.useMsr ? '.msr.predewm.mp4' : '.predewm.mp4' }}，可回退。
        </p>
        <div class="redub-field">
          <label>输出最长边像素上限（0 = 用输入视频原生最长边）</label>
          <input type="number" min="0" max="2048" step="64" class="input input-xs"
                 v-model.number="dewmDialog.maxLongestEdge"
                 placeholder="0（原生）；低显存可填 960 / 832 / 768" />
        </div>
        <div class="redub-field">
          <label>最大处理时长（秒，0 = 用工作流默认）</label>
          <input type="number" min="0" max="120" step="1" class="input input-xs"
                 v-model.number="dewmDialog.maxSeconds" placeholder="0" />
        </div>
        <div v-if="dewmDialog.error" class="error-banner" style="margin:6px 0">⚠ {{ dewmDialog.error }}</div>
        <div v-if="dewmDialog.running" class="redub-field">
          <div class="scene-mini-bar"><div class="scene-mini-fill"
               :style="{ width: dewmDialog.progressPct + '%' }" /></div>
          <span class="text-muted" style="font-size:11px">{{ dewmDialog.progressPct }}%（V2V 较慢，请耐心等待）</span>
        </div>
        <div class="merge-dialog-actions">
          <button class="btn btn-primary" :disabled="dewmDialog.running" @click="runDewm">
            {{ dewmDialog.running ? '处理中…' : '开始去水印去字幕' }}
          </button>
          <button class="btn btn-ghost" :disabled="dewmDialog.running" @click="closeDewm">关闭</button>
        </div>
      </div>
    </div>

    <!-- v1.4.8: 试播预览 —— 串播分镜素材，不带字幕/SFX -->
    <PreviewPlayer v-if="previewOpen"
                   :project-id="projectId"
                   :scenes="scenes"
                   :resolution="resolution"
                   @close="previewOpen = false" />

    <!-- v1.4.8: SFX 时间轴编辑器 -->
    <SfxTimelineDialog v-if="sfxDialogOpen"
                       :project-id="projectId"
                       :scenes="scenes"
                       @close="sfxDialogOpen = false" />

    <!-- v1.4.10++: 火山引擎参考图选择器 -->
    <ReferencePicker v-if="refPickerSceneId"
                     :project-id="projectId"
                     @picked="onVolcRefPicked"
                     @close="refPickerSceneId = null" />

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import { useTabsStore } from '../../stores/tabs'
import BgmMixerDialog from '../BgmMixerDialog.vue'
import PreviewPlayer from '../PreviewPlayer.vue'
import SfxTimelineDialog from '../SfxTimelineDialog.vue'
import ReferencePicker from '../ReferencePicker.vue'

// v1.4.2: BGM 混音对话框可见性
const bgmMixerOpen = ref(false)
const previewOpen   = ref(false)  // v1.4.8 试播预览
const sfxDialogOpen = ref(false)  // v1.4.8 SFX 时间轴编辑

const props = defineProps({ projectId: String })
const emit  = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

// ── state ──────────────────────────────────────────────────────────────────────
const scenes          = ref([])

// C1: 工作流节点映射编辑器
const META_FIELDS = [
  { key: 'first_frame_image', label: '首帧图片节点',   desc: 'LoadImage FIRST FRAME',  defaultId: 45  },
  { key: 'last_frame_image',  label: '末帧图片节点',   desc: 'LoadImage LAST FRAME',   defaultId: 47  },
  { key: 'audio',             label: '音频节点',       desc: 'LoadAudio',              defaultId: 232 },
  { key: 'width',             label: '宽度节点',       desc: 'INTConstant WIDTH',      defaultId: 166 },
  { key: 'height',            label: '高度节点',       desc: 'INTConstant HEIGHT',     defaultId: 167 },
  { key: 'duration_secs',     label: '时长节点（秒）', desc: 'INTConstant LENGTH',     defaultId: 169 },
  { key: 'fps',               label: '帧率节点',       desc: 'PrimitiveFloat FPS',     defaultId: 164 },
  { key: 'positive_prompt',   label: '正向提示词节点', desc: 'CLIPTextEncode pos',     defaultId: 16  },
]
const workflowMetaOpen   = ref(false)
const workflowMetaForm   = ref({ node_map: {}, notes: '', type: 'video', version: 1 })
const workflowMetaSaving = ref(false)

function _emptyMetaForm() {
  const nm = {}
  for (const f of META_FIELDS) nm[f.key] = { node_id: f.defaultId, widget: 0 }
  return { node_map: nm, notes: '', type: 'video', version: 1 }
}

async function openWorkflowMeta() {
  if (!selectedWorkflow.value) return
  workflowMetaForm.value = _emptyMetaForm()
  try {
    const r = await fetch(`${API}/image-engine/workflow-meta/${encodeURIComponent(selectedWorkflow.value)}?type=video`)
    if (r.ok) {
      const d = await r.json()
      const nm = workflowMetaForm.value.node_map
      for (const f of META_FIELDS) {
        const v = d.node_map?.[f.key]
        if (v && typeof v === 'object') {
          nm[f.key] = { node_id: v.node_id ?? f.defaultId, widget: v.widget ?? 0 }
        }
      }
      workflowMetaForm.value.notes = d.notes || ''
    }
  } catch {}
  workflowMetaOpen.value = true
}

function resetWorkflowMeta() {
  if (!confirm('恢复为内置默认节点映射？已填的值会被覆盖。')) return
  workflowMetaForm.value = _emptyMetaForm()
}

async function saveWorkflowMeta() {
  workflowMetaSaving.value = true
  try {
    const r = await fetch(`${API}/image-engine/workflow-meta/${encodeURIComponent(selectedWorkflow.value)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(workflowMetaForm.value),
    })
    if (!r.ok) throw new Error(await r.text())
    workflowMetaOpen.value = false
  } catch (e) {
    alert('保存节点映射失败: ' + e.message)
  } finally {
    workflowMetaSaving.value = false
  }
}

// A1: 上次批量失败的视频镜次
const lastErrors      = ref({})
const lastErrorCount  = computed(() => Object.keys(lastErrors.value || {}).length)

async function reloadLastErrors() {
  if (!props.projectId) return
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/last-run-errors`)
    if (!r.ok) return
    const d = await r.json()
    lastErrors.value = (d.stage === 'video' ? d.errors : null) || {}
  } catch { lastErrors.value = {} }
}

async function dismissLastErrors() {
  lastErrors.value = {}
  try { await fetch(`${API}/projects/${props.projectId}/last-run-errors`, { method: 'DELETE' }) } catch {}
}

async function retryFailedBatch() {
  if (!Object.keys(lastErrors.value).length) return
  if (!selectedWorkflow.value) return
  const failedSceneIds = new Set(Object.keys(lastErrors.value))
  // 失败镜过滤后调用 _runGeneration（已有函数）批量重做。
  // 必须用 scenesWithData（带 hasStart/hasBg/bgImageB64 等富集字段）—— 原始 scenes.value
  // 没有这些字段，会让 sceneReady/isMsrScene 全部判否，retry 静默空跑（修复既有缺陷）。
  const failedScenes = scenesWithData.value.filter(
    s => failedSceneIds.has(String(s.id)) && sceneReady(s)
  )
  if (!failedScenes.length) return
  running.value = true; genFinished.value = false; stopFlag.value = false; genError.value = ''
  try {
    await _runGeneration(failedScenes)
  } finally {
    running.value = false
    genFinished.value = true
    await reloadLastErrors()
  }
}
const imagesData      = ref({})   // slot key → base64 PNG
const imagesSelected  = ref({})   // "{scene_id}:start"|":end" → slot_index
const audioData       = ref({})   // "__stitched__{sceneId}" → {data, duration_ms}
const loadingScenes   = ref(false)
const workflows       = ref([])
const selectedWorkflow = ref('')

// v1.4.1: 工作流类型 + 特性
const workflowKind     = ref('unknown')      // 'video_flfa2i' | 'video_i2v' | 'unknown'
const workflowFeatures = ref({
  requires_start_image: true,
  requires_end_image:   true,
  supports_audio:       true,
  supports_duration:    true,
  label:                '',
})
// 无音频模式（仅 flfa2i 可选；i2v 始终无音频）
const noAudioMode = ref(false)
// 无音频时的手动时长（秒），按分镜 id 存
const manualDurations = ref({})   // { sceneId: number }
// v1.6: 多图参考(MSR)视频默认时长（秒），页面顶部可设；新 MSR 镜未单独设时长时用它。
const msrDefaultDuration = ref(10)
try {
  const _d = Number(localStorage.getItem('lumi_msr_default_duration'))
  if (_d >= 1) msrDefaultDuration.value = _d
} catch {}
watch(msrDefaultDuration, (v) => {
  const n = Math.max(1, Math.min(30, Number(v) || 10))
  if (n !== v) { msrDefaultDuration.value = n; return }
  try { localStorage.setItem('lumi_msr_default_duration', String(n)) } catch {}
})

async function loadWorkflowInfo() {
  workflowKind.value = 'unknown'
  if (!selectedWorkflow.value) return
  try {
    const r = await fetch(`${API}/video-engine/workflow-info?workflow_name=${encodeURIComponent(selectedWorkflow.value)}`)
    if (r.ok) {
      const d = await r.json()
      workflowKind.value     = d.kind || 'unknown'
      workflowFeatures.value = d
      // i2v 永远无音频
      if (workflowKind.value === 'video_i2v') noAudioMode.value = true
    }
  } catch {}
}
watch(selectedWorkflow, () => loadWorkflowInfo(), { immediate: false })
const resolution      = ref('720x1280')
const fps             = ref(25)
const running         = ref(false)
const genFinished     = ref(false)
const stopFlag        = ref(false)
const genError        = ref('')
const sceneState      = ref({})   // id → pending|active|done|error
const sceneProgress   = ref({})   // id → {value, max}
const sceneVideos     = ref({})   // id → 旧/普通视频 src（流式 URL / data URL）
const sceneVideosMsr  = ref({})   // v1.6: id → 多图参考(MSR)视频 src（与旧视频并存）

// v1.5.1: GET /videos 返回 {scene_id: url 路径}（不再 base64 整包）。
// 拼成带主机名 + 防缓存戳的完整地址，让 <video> 按需流式加载。
function _toVideoSrcMap(data) {
  const host = API.replace(/\/api\/?$/, '')
  const stamp = Date.now()
  const out = {}
  for (const [sid, v] of Object.entries(data || {})) {
    const s = String(v)
    if (!s.startsWith('/')) { out[sid] = s; continue }   // data URL 等原样
    // 已带 query(?kind=msr) 用 & 续防缓存戳，否则用 ?
    const sep = s.includes('?') ? '&' : '?'
    out[sid] = `${host}${s}${sep}t=${stamp}`
  }
  return out
}

// v1.6 双模：按该镜的 MSR 开关返回应预览/应合并的视频源 & 是否就绪
function videoSrcFor(scene) {
  return isMsrScene(scene) ? sceneVideosMsr.value[scene.id] : sceneVideos.value[scene.id]
}
function hasVideoFor(scene) { return !!videoSrcFor(scene) }

// v1.6: 同时拉旧/普通视频 + MSR 视频两套索引
async function _reloadAllVideos() {
  if (!props.projectId) return
  const [o, m] = await Promise.all([
    axios.get(`${API}/projects/${props.projectId}/videos`).catch(() => ({ data: {} })),
    axios.get(`${API}/projects/${props.projectId}/videos-msr`).catch(() => ({ data: {} })),
  ])
  sceneVideos.value = _toVideoSrcMap(o.data || {})
  sceneVideosMsr.value = _toVideoSrcMap(m.data || {})
}
const mergeResult     = ref(null) // { output_path, output_dir } once merged
const merging         = ref(false)

// ── v1.6: 视频后期 RVC 变声 ───────────────────────────────────────────────────
const redubState    = ref({})   // sceneId → 'running'|'done'|'error'
const redubProgress = ref({})   // sceneId → 0..100
function redubProgressPct(id) { return redubProgress.value[id] || 0 }

const redubDialog = ref({
  visible: false, sceneId: '', useMsr: false, model: '',
  whisperModel: 'medium', language: 'zh', voiceMapping: '',
  // 工作流可调项（暴露给用户）
  transpose: 0, indexRate: 0.66, protect: 0.33, rmsMixRate: 0.25, mixbackGain: 1.0,
  models: [], rvcExists: false, loadingModels: false,
  running: false, progressPct: 0, error: '',
  previewB64: '', previewUrl: '', previewSrcFp: '',   // 预览成片（确认前不落盘）
})

// ── v1.6.1: 视频分镜人工审阅标记（纯展示，不影响任何生成/合并机制；按项目 localStorage 持久化）──
const videoReviewed = ref({})   // sceneId → bool
function _videoReviewedKey() { return `lumi_video_reviewed_${props.projectId || ''}` }
function _loadVideoReviewed() {
  try {
    const raw = localStorage.getItem(_videoReviewedKey())
    videoReviewed.value = raw ? (JSON.parse(raw) || {}) : {}
  } catch { videoReviewed.value = {} }
}
function toggleVideoReviewed(sceneId) {
  videoReviewed.value = { ...videoReviewed.value, [sceneId]: !videoReviewed.value[sceneId] }
  try { localStorage.setItem(_videoReviewedKey(), JSON.stringify(videoReviewed.value)) } catch {}
}

async function reloadRvcModels() {
  redubDialog.value.loadingModels = true
  try {
    const { data } = await axios.get(`${API}/video-engine/rvc-models`)
    redubDialog.value.models = data?.models || []
    redubDialog.value.rvcExists = !!data?.exists
    // 默认选中第一个（若当前未选）
    if (!redubDialog.value.model && redubDialog.value.models.length) {
      redubDialog.value.model = redubDialog.value.models[0]
    }
  } catch (e) {
    redubDialog.value.models = []
    redubDialog.value.rvcExists = false
  } finally {
    redubDialog.value.loadingModels = false
  }
}

function _b64ToBlobUrl(b64, mime = 'video/mp4') {
  const bin = atob(b64); const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
  return URL.createObjectURL(new Blob([arr], { type: mime }))
}

function _clearRedubPreview() {
  const d = redubDialog.value
  if (d.previewUrl) { try { URL.revokeObjectURL(d.previewUrl) } catch {} }
  d.previewB64 = ''; d.previewUrl = ''; d.previewSrcFp = ''
}

async function openRedub(scene) {
  const sid = String(scene.id)
  const switchingScene = redubDialog.value.sceneId !== sid
  redubDialog.value.visible = true
  redubDialog.value.sceneId = sid
  // 针对该镜【当前选择的】视频：MSR 开关启用 → 对多图参考视频变声，否则对旧/普通视频
  redubDialog.value.useMsr = isMsrScene(scene)
  redubDialog.value.error = ''
  redubDialog.value.progressPct = 0
  redubDialog.value.running = false
  _clearRedubPreview()
  // 切到不同分镜时清空逐说话人映射，避免把上一镜的角色映射误带过来（model 作为便利默认保留）
  if (switchingScene) redubDialog.value.voiceMapping = ''
  // 用设置里的默认回填 whisper/语言/默认模型，否则对话框里写死的 medium/zh 会盖掉后端设置
  try {
    const { data } = await axios.get(`${API}/settings`)
    const ve = data?.video_engine || {}
    if (ve.redub_whisper_model) redubDialog.value.whisperModel = ve.redub_whisper_model
    if (ve.redub_language)      redubDialog.value.language     = ve.redub_language
    if (ve.redub_default_model && !redubDialog.value.model)
      redubDialog.value.model = ve.redub_default_model
  } catch {}
  await reloadRvcModels()
}

function closeRedub() {
  if (redubDialog.value.running) return
  _clearRedubPreview()
  redubDialog.value.visible = false
}

// 取消变声：丢弃预览、不落盘
function cancelRedub() {
  if (redubDialog.value.running) return
  const sid = redubDialog.value.sceneId
  redubState.value = { ...redubState.value, [sid]: undefined }
  closeRedub()
}

// 生成预览（不落盘）—— 对应「重新变声」也走这里
async function runRedub() {
  const d = redubDialog.value
  if (d.running || !d.model) return
  const sid = d.sceneId
  d.running = true; d.error = ''; d.progressPct = 0
  _clearRedubPreview()
  redubState.value = { ...redubState.value, [sid]: 'running' }
  redubProgress.value = { ...redubProgress.value, [sid]: 0 }
  try {
    const resp = await fetch(`${API}/video-engine/redub-stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.projectId, scene_id: sid, use_msr: !!d.useMsr,
        default_model: d.model, voice_mapping: d.voiceMapping || '',
        whisper_model: d.whisperModel || '', language: d.language || '',
        transpose: Number(d.transpose) || 0,
        index_rate: Number(d.indexRate),
        protect: Number(d.protect),
        rms_mix_rate: Number(d.rmsMixRate),
        mixback_gain: Number(d.mixbackGain),
      }),
    })
    if (!resp.ok) {
      let detail = 'HTTP ' + resp.status
      try { const j = await resp.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') continue
        let ev; try { ev = JSON.parse(raw) } catch { continue }
        if (ev.event === 'progress') {
          const pct = ev.max ? Math.round(ev.value / ev.max * 100) : 0
          d.progressPct = pct
          redubProgress.value = { ...redubProgress.value, [sid]: pct }
        } else if (ev.event === 'redub_preview' && ev.video) {
          d.previewB64 = ev.video
          d.previewSrcFp = ev.src_fp || ''
          d.previewUrl = _b64ToBlobUrl(ev.video)
        } else if (ev.event === 'redub_error') {
          d.error = ev.message || '后期处理失败'
        }
      }
    }
    // 预览就绪 → 对话框留在「预览 + 确认/重新/取消」；尚未落盘
    redubState.value = { ...redubState.value, [sid]: d.previewB64 ? undefined : 'error' }
    if (!d.previewB64 && !d.error) d.error = '后期处理结束但未返回成片'
  } catch (e) {
    d.error = e.message || String(e)
    redubState.value = { ...redubState.value, [sid]: 'error' }
  } finally {
    d.running = false
  }
}

// 确认变声：把预览成片落盘换回该镜【当前选择的】视频
async function confirmRedub() {
  const d = redubDialog.value
  if (d.running || !d.previewB64) return
  const sid = d.sceneId
  d.running = true; d.error = ''
  try {
    const r = await fetch(`${API}/video-engine/redub-apply`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.projectId, scene_id: sid,
        use_msr: !!d.useMsr, video: d.previewB64, src_fp: d.previewSrcFp || '',
      }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { const j = await r.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    redubState.value = { ...redubState.value, [sid]: 'done' }
    try { await _reloadAllVideos() } catch {}
    _clearRedubPreview()
    d.visible = false
  } catch (e) {
    d.error = e.message || String(e)
  } finally {
    d.running = false
  }
}

// ── v1.6: 去水印 / 去字幕（LTX V2V）─────────────────────────────────────────────
const dewmState    = ref({})   // sceneId → 'running'|'done'|'error'
const dewmProgress = ref({})
function dewmProgressPct(id) { return dewmProgress.value[id] || 0 }

const dewmDialog = ref({
  visible: false, sceneId: '', useMsr: false,
  maxLongestEdge: 0, maxSeconds: 0,
  running: false, progressPct: 0, error: '',
})

function openDewm(scene) {
  dewmDialog.value.visible = true
  dewmDialog.value.sceneId = String(scene.id)
  dewmDialog.value.useMsr = isMsrScene(scene)   // 针对该镜当前选择的视频
  dewmDialog.value.error = ''
  dewmDialog.value.progressPct = 0
  dewmDialog.value.running = false
}

function closeDewm() {
  if (dewmDialog.value.running) return
  dewmDialog.value.visible = false
}

async function runDewm() {
  const d = dewmDialog.value
  if (d.running) return
  const sid = d.sceneId
  d.running = true; d.error = ''; d.progressPct = 0
  dewmState.value = { ...dewmState.value, [sid]: 'running' }
  dewmProgress.value = { ...dewmProgress.value, [sid]: 0 }
  try {
    const resp = await fetch(`${API}/video-engine/dewatermark-stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: props.projectId, scene_id: sid, use_msr: !!d.useMsr,
        max_longest_edge: Number(d.maxLongestEdge) || 0,
        max_seconds: Number(d.maxSeconds) || 0,
      }),
    })
    if (!resp.ok) {
      let detail = 'HTTP ' + resp.status
      try { const j = await resp.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let ok = false
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') continue
        let ev; try { ev = JSON.parse(raw) } catch { continue }
        if (ev.event === 'progress') {
          const pct = ev.max ? Math.round(ev.value / ev.max * 100) : 0
          d.progressPct = pct
          dewmProgress.value = { ...dewmProgress.value, [sid]: pct }
        } else if (ev.event === 'dewm_done') {
          ok = true
        } else if (ev.event === 'dewm_error') {
          d.error = ev.message || '去水印失败'
        }
      }
    }
    if (ok) {
      dewmState.value = { ...dewmState.value, [sid]: 'done' }
      // 刷新【两个】索引（旧 + MSR）—— 去水印可能作用在 .msr.mp4，只刷旧索引会让 MSR 镜预览滞留旧帧
      try { await _reloadAllVideos() } catch {}
      d.visible = false
    } else {
      dewmState.value = { ...dewmState.value, [sid]: 'error' }
      if (!d.error) d.error = '去水印结束但未返回成片'
    }
  } catch (e) {
    d.error = e.message || String(e)
    dewmState.value = { ...dewmState.value, [sid]: 'error' }
  } finally {
    d.running = false
  }
}

// v1.4.10: 当前视频引擎来源（read-only，从后端 settings 拉一次）
const engineType = ref('comfyui')   // 'comfyui' | 'volcengine_seedance'
// v1.4.10++: 火山引擎状态（API Key + 模型 ID 是否配齐）
const volcReady = ref(false)
async function _loadEngineType() {
  try {
    const r = await axios.get(`${API}/settings`)
    const ve = r.data?.video_engine || {}
    engineType.value = ve.engine_type || 'comfyui'
    volcReady.value = !!(ve.volcengine_api_key && ve.volcengine_model_id)
  } catch { /* 拉失败保持默认 */ }
}
_loadEngineType()

// v1.4.10++ 火山引擎全局设置（VideoTab 内的全局默认；可在每分镜覆盖）
const volcGlobalResolution = ref('720p')
const volcGlobalRatio      = ref('adaptive')
const volcGlobalDuration   = ref(5)
const volcGlobalMode       = ref('i2v_first')   // 't2v' | 'i2v_first' | 'i2v_flf' | 'multi_ref'
const volcRunning          = ref(false)

// 每分镜火山引擎独立配置 { [sceneId]: { mode, duration_secs, references: [refObj] } }
const volcSceneOptions = ref({})

// ── v1.6: MSR 多图参考视频（按分镜开关，仅 LTX/ComfyUI 模式 + 该镜有背景图时可用）──
// { [sceneId]: bool }，按项目持久化到 localStorage，刷新后仍在。
const msrEnabled = ref({})

function _msrStoreKey() { return `lumi_msr_enabled_${props.projectId || ''}` }

function _loadMsrEnabled() {
  try {
    const raw = localStorage.getItem(_msrStoreKey())
    msrEnabled.value = raw ? (JSON.parse(raw) || {}) : {}
  } catch { msrEnabled.value = {} }
}

function _saveMsrEnabled() {
  try { localStorage.setItem(_msrStoreKey(), JSON.stringify(msrEnabled.value)) } catch {}
}

function isMsrScene(s) {
  // 仅 LTX(ComfyUI) 模式 + 该镜有背景图 + 用户已勾选
  return videoMode.value === 'ltx' && !!s.hasBg && !!msrEnabled.value[s.id]
}

function toggleMsr(sceneId, val) {
  msrEnabled.value = { ...msrEnabled.value, [sceneId]: !!val }
  _saveMsrEnabled()
}

// v1.6: 每分镜手动时长按项目持久化（与 msrEnabled 对称）—— 否则刷新/切项目后
// MSR 开关还在、时长却被清空回落 5s，用户设的值静默丢失。
function _durStoreKey() { return `lumi_msr_durations_${props.projectId || ''}` }

function _loadManualDurations() {
  try {
    const raw = localStorage.getItem(_durStoreKey())
    manualDurations.value = raw ? (JSON.parse(raw) || {}) : {}
  } catch { manualDurations.value = {} }
}

function setManualDuration(sceneId, val) {
  manualDurations.value = { ...manualDurations.value, [sceneId]: Number(val) || 5 }
  try { localStorage.setItem(_durStoreKey(), JSON.stringify(manualDurations.value)) } catch {}
}

// 角色白底立绘 b64 缓存：charName → b64（'' 表示该角色无白底立绘）
const _whiteBgCache = {}

async function _whiteBgPortraitB64(charName) {
  if (!charName) return ''
  if (charName in _whiteBgCache) return _whiteBgCache[charName]
  let b64 = ''
  try {
    const { data } = await axios.get(
      `${API}/projects/${props.projectId}/characters/${encodeURIComponent(charName)}/portraits`)
    const list = (data && data.portraits) || []
    // 优先「白底 + 主图」，否则任一白底
    const wb = list.find(p => p.white_bg && p.is_primary) || list.find(p => p.white_bg)
    if (wb && wb.url) b64 = await _srcToB64('http://localhost:18520' + wb.url)
  } catch {}
  _whiteBgCache[charName] = b64
  return b64
}

// 解析某分镜的 MSR 角色：仅保留【在角色表里且有白底立绘】的出镜角色（≤3），顺序即
// LiconMSR 槽位 / 参考图顺序。返回 [{name, appearance, b64}]。提示词与参考图都从这一份
// 列表派生，确保“提示词里的参考图N”与“喂给 LiconMSR 槽位N 的图”始终是同一个角色（修复
// 此前两处独立 .filter(Boolean) 谓词不同导致的错位）。_whiteBgPortraitB64 已做缓存，重复调用廉价。
async function _msrResolvedChars(s) {
  const byName = Object.fromEntries(allCharacters.value.map(c => [c.name, c]))
  const names = (s._scene_characters || []).slice(0, 3)
  const out = []
  for (const n of names) {
    const c = byName[n]
    if (!c) continue
    const b64 = await _whiteBgPortraitB64(n)
    if (!b64) continue   // 无白底立绘 → 同时从提示词和参考图里排除，保持对齐
    out.push({ name: c.name, appearance: c.appearance || c.traits || '', b64 })
  }
  return out
}

// 收集某分镜 MSR 参考图：角色白底立绘（与提示词同源同序）+ 背景图
async function _gatherMsrRefs(s) {
  const resolved = await _msrResolvedChars(s)
  const bgB64 = s.bgImageB64 ? await _srcToB64(s.bgImageB64) : ''
  return { char_ref_b64: resolved.map(c => c.b64), bg_ref_b64: bgB64 }
}

// ── v1.6: MSR 多图参考视频提示词（参考图N + 动作叙述，写入 scenePrompts 作正向提示）──
const msrPromptingId  = ref(null)   // 单镜生成中
const msrPromptRunning = ref(false) // 批量生成中
const msrPromptProgress = ref(0)
const msrPromptTotal    = ref(0)
const msrSceneCount = computed(() =>
  scenesWithData.value.filter(s => isMsrScene(s)).length)

// 组装 MSR 提示词请求体：角色用【解析后的同源列表】（参考图顺序 = LiconMSR 槽 1/2/3）
async function _msrPromptBody(s) {
  const resolved = await _msrResolvedChars(s)
  return {
    characters:   resolved.map(c => ({ name: c.name, appearance: c.appearance })),
    background:   s.bg_prompt || s.description || '',
    description:  s.description || '',
    dialogues:    s.dialogues || [],
    scene_index:  s.index,
    total_scenes: scenes.value.length,
  }
}

async function genMsrPrompt(scene) {
  if (msrPromptingId.value || msrPromptRunning.value) return
  msrPromptingId.value = scene.id
  try {
    const res = await fetch(`${API}/text-engine/generate-msr-video-prompt`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(await _msrPromptBody(scene)),
    })
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const data = await res.json()
    if (data.prompt) {
      scenePrompts.value  = { ...scenePrompts.value,  [scene.id]: data.prompt }
      promptVisible.value = { ...promptVisible.value, [scene.id]: true }
      _scheduleSavePrompts()
    }
  } catch (e) {
    genError.value = `MSR 提示词生成失败: ${e.message}`
  } finally {
    msrPromptingId.value = null
  }
}

async function genAllMsrPrompts() {
  if (msrPromptRunning.value) return
  const targets = scenesWithData.value.filter(s => isMsrScene(s))
  if (!targets.length) { genError.value = '没有启用「多图参考」的分镜'; return }
  msrPromptRunning.value = true
  msrPromptProgress.value = 0
  msrPromptTotal.value = targets.length
  const sceneById = {}
  targets.forEach(s => { sceneById[String(s.id)] = s })
  try {
    const bodies = await Promise.all(targets.map(_msrPromptBody))
    const resp = await fetch(`${API}/text-engine/generate-msr-video-prompts-batch`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenes: targets.map((s, i) => ({ scene_id: String(s.id), ...bodies[i] })),
        total_scenes: scenes.value.length,
      }),
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') continue
        let ev; try { ev = JSON.parse(raw) } catch { continue }
        if (ev.event === 'result' && ev.scene_id != null && ev.prompt) {
          const sid = String(ev.scene_id)
          scenePrompts.value  = { ...scenePrompts.value,  [sid]: ev.prompt }
          promptVisible.value = { ...promptVisible.value, [sid]: true }
          msrPromptProgress.value++
        } else if (ev.event === 'item_error') {
          msrPromptProgress.value++
        }
      }
    }
    _scheduleSavePrompts()
  } catch (e) {
    genError.value = `批量 MSR 提示词失败: ${e.message}`
  } finally {
    msrPromptRunning.value = false
  }
}

function volcOpts(sceneId) {
  if (!volcSceneOptions.value[sceneId]) {
    volcSceneOptions.value[sceneId] = {
      mode:          volcGlobalMode.value,
      duration_secs: volcGlobalDuration.value,
      references:    [],
    }
  }
  return volcSceneOptions.value[sceneId]
}

function applyVolcDefaultsToAll() {
  if (!confirm(`把全局默认（${volcGlobalMode.value} / ${volcGlobalDuration.value}s）应用到全部 ${scenes.value.length} 个分镜？`)) return
  for (const s of scenes.value) {
    const o = volcOpts(s.id)
    o.mode          = volcGlobalMode.value
    o.duration_secs = volcGlobalDuration.value
  }
}

// 参考图选择器：被哪个 scene 触发
const refPickerSceneId = ref(null)

function openRefPickerFor(sceneId) {
  refPickerSceneId.value = sceneId
}

function refKindLabel(kind) {
  return ({
    portrait:    '🎭 立绘',
    element:     '📦 元素',
    scene_start: '🖼 首帧',
    scene_end:   '🖼 末帧',
    b64:         '上传',
    path:        '本地',
  })[kind] || kind
}

function onVolcRefPicked(ref) {
  const sid = refPickerSceneId.value
  if (!sid) return
  const o = volcOpts(sid)
  // ref 形态：{ kind: 'portrait'|'element'|'b64', ..., _preview_url, _label }
  o.references.push({ ...ref })
  refPickerSceneId.value = null
}

async function addVolcRefSceneFrame(sceneId, kind, scene) {
  // 把分镜自身的首/末帧加入参考图；前端把 b64 一同带上，省得后端再读盘
  const o = volcOpts(sceneId)
  // 解析 src → base64（与 _runGeneration 中一致的工具）
  const srcKey = kind === 'scene_start' ? scene.startImageB64 : scene.endImageB64
  const b64 = await _srcToB64(srcKey)
  if (!b64) {
    alert(`该分镜${kind === 'scene_start' ? '首' : '末'}帧不存在`)
    return
  }
  // 用 data URL 当 preview
  o.references.push({
    kind,
    image_b64: b64,
    _preview_url: `data:image/png;base64,${b64}`,
    _label: kind === 'scene_start' ? '该分镜首帧' : '该分镜末帧',
  })
}

function removeVolcRef(sceneId, idx) {
  const o = volcOpts(sceneId)
  o.references.splice(idx, 1)
}

// 把单个 ref 转成发给后端的纯净字段（剥掉 _preview_url / _label 这些 UI-only）
function _sanitizeVolcRef(r) {
  const clean = { kind: r.kind }
  for (const k of ['project_id', 'char_name', 'filename',
                   'scope', 'element_id', 'image_b64']) {
    if (r[k] !== undefined && r[k] !== null) clean[k] = r[k]
  }
  return clean
}

// "一键生成所有分镜视频（火山引擎）" —— 复用 _runGeneration 的批量循环
async function runVolcengine() {
  if (volcRunning.value) return
  // 1) 后端 settings 切到 volcengine_seedance
  try {
    const r = await axios.get(`${API}/settings`)
    const ve = r.data?.video_engine || {}
    if (ve.engine_type !== 'volcengine_seedance') {
      ve.engine_type = 'volcengine_seedance'
      // 同步全局值
      ve.volcengine_resolution = volcGlobalResolution.value
      ve.volcengine_ratio      = volcGlobalRatio.value
      r.data.video_engine = ve
      await axios.put(`${API}/settings`, r.data)
    }
  } catch (e) {
    genError.value = '同步设置到后端失败：' + (e?.response?.data?.detail || e.message)
    return
  }
  // 2) selectedWorkflow 必须有值，否则 startGeneration 早返；用合成名 volcengine_seedance
  selectedWorkflow.value = 'volcengine_seedance'
  volcRunning.value = true
  try {
    await startGeneration()
  } finally {
    volcRunning.value = false
  }
}

// v1.4.6: 视频模式 + 图片放映状态
const videoMode             = ref('ltx')                  // 'ltx' | 'slideshow'
const slideshowTransition   = ref('fade')
const slideshowTransitionMs = ref(800)
const slideshowMotion       = ref('none')   // v1.4.6: 画面动态
const slideshowRunning      = ref(false)
const slideshowResult       = ref(null)

async function runSlideshow() {
  if (slideshowRunning.value || !scenes.value.length) return
  slideshowRunning.value = true
  slideshowResult.value  = null
  try {
    const [w, h] = String(resolution.value || '1920x1080').split('x').map(Number)
    const r = await fetch(`${API}/video-engine/render-slideshow`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        project_id:          props.projectId,
        scene_order:         scenes.value.map(s => String(s.id)),
        width:               w || 1920,
        height:              h || 1080,
        fps:                 fps.value || 25,
        intra_transition:    slideshowTransition.value,
        intra_transition_ms: slideshowTransitionMs.value,
        motion_effect:       slideshowMotion.value,
      }),
    })
    if (!r.ok) {
      let detail = 'HTTP ' + r.status
      try { const j = await r.json(); detail = j.detail || detail } catch {}
      throw new Error(detail)
    }
    slideshowResult.value = await r.json()
    // 刷新已有视频映射：让分镜卡片显示新出的 .mp4
    try { await _reloadAllVideos() } catch {}
  } catch (e) {
    alert('图片放映渲染失败: ' + (e.message || e))
  } finally {
    slideshowRunning.value = false
  }
}
const scenePrompts    = ref({})   // scene_id → prompt string
const promptVisible   = ref({})   // scene_id → bool (expanded)
let _promptSaveTimer  = null
// manuscript + characters for LLM video prompt
const manuscript             = ref('')
const allCharacters          = ref([])   // [{name, role, appearance, traits}]
// per-scene LLM generating state
const generatingVideoPromptId   = ref(null)   // scene.id being generated
const generatingAllVideoPrompts = ref(false)
const videoPromptProgress       = ref(0)

// ── derived ────────────────────────────────────────────────────────────────────
const scenesWithData = computed(() =>
  scenes.value.map(s => {
    const startKey = `${s.id}:start`
    const endKey   = `${s.id}:end`
    const startSlot = imagesSelected.value[startKey] ?? 0
    const endSlot   = imagesSelected.value[endKey]   ?? 0
    const startImg  = imagesData.value[`${startKey}:${startSlot}`] || null
    const endImg    = imagesData.value[`${endKey}:${endSlot}`]     || null
    // v1.6: 背景图（无角色），用于 MSR 多图参考视频
    const bgKey     = `${s.id}:bg`
    const bgSlot    = imagesSelected.value[bgKey] ?? 0
    const bgImg     = imagesData.value[`${bgKey}:${bgSlot}`] || null
    const stitchKey = `__stitched__${s.id}`
    const stitched  = audioData.value[stitchKey] || null
    return {
      ...s,
      hasStart:      !!startImg,
      hasEnd:        !!endImg,
      hasBg:         !!bgImg,
      hasAudio:      !!stitched,
      startImageB64: startImg || '',
      endImageB64:   endImg   || '',
      bgImageB64:    bgImg    || '',
      audioB64:      stitched?.data || '',
      audioDurationMs: stitched?.duration_ms || 0,
    }
  })
)

const readyCount = computed(() =>
  scenesWithData.value.filter(sceneReady).length
)

// v1.6.1: 左栏列表 + 右栏当前分镜详情（只渲染 1 个视频，避免几十个 <video> 同页卡顿）
const activeVideoSceneId = ref(null)
const activeVideoScene = computed(() => {
  const list = scenesWithData.value
  if (!list.length) return null
  return list.find(s => String(s.id) === String(activeVideoSceneId.value)) || list[0]
})
// 左栏每个分镜的状态摘要（不渲染视频，仅图标/文字）
function videoSceneStatusIcon(scene) {
  if (sceneState.value[scene.id] === 'active') return '⏳'
  if (sceneState.value[scene.id] === 'error')  return '✗'
  return videoSrcFor(scene) ? '🎞' : '·'
}

const completedCount = computed(() =>
  Object.values(sceneState.value).filter(v => v === 'done' || v === 'error').length
)

const overallPct = computed(() =>
  scenes.value.length ? Math.round(completedCount.value / scenes.value.length * 100) : 0
)

const allVideosReady = computed(() =>
  scenesWithData.value.length > 0 &&
  // v1.6 双模：每镜按其 MSR 开关检查对应那套视频是否就绪
  scenesWithData.value.every(s => hasVideoFor(s))
)

// v1.4.1: 按工作流类型决定 readiness
function sceneReady(s) {
  // v1.4.10++: 火山引擎用每分镜独立判定，绕开 LTX 的 readiness 检查
  if (videoMode.value === 'volcengine') {
    const o = volcSceneOptions.value[s.id]
    const mode = o?.mode || volcGlobalMode.value
    if (mode === 't2v') return true   // 纯文生不需要图
    if (mode === 'i2v_first') return !!s.hasStart
    if (mode === 'i2v_flf')   return !!s.hasStart && !!s.hasEnd
    if (mode === 'multi_ref') return (o?.references || []).length > 0 || !!s.hasStart
    return true
  }
  // v1.6: MSR 分镜由背景图 + 角色白底立绘驱动 —— 有背景图即就绪（不需要首/末帧）
  if (isMsrScene(s)) return !!s.hasBg
  if (!s.hasStart) return false
  if (workflowFeatures.value.requires_end_image && !s.hasEnd) return false
  // 音频：只有 flfa2i + 关闭无音频模式时才要求音频
  const audioRequired = workflowFeatures.value.supports_audio && !noAudioMode.value
  if (audioRequired && !s.hasAudio) return false
  return true
}

function sceneFullText(scene) {
  if (!scene) return '（无描述）'
  const desc = scene.description || ''
  const firstDialogue = (scene.dialogues || [])[0]?.text || ''
  if (firstDialogue && (desc.endsWith('…') || desc.length < firstDialogue.length)) {
    return firstDialogue
  }
  return desc || '（无描述）'
}
function sceneStatusClass(id) { return sceneState.value[id] || 'pending' }
function sceneStatusLabel(id) {
  return ({ pending: '', active: '生成中…', done: '✓ 完成', error: '✗ 错误' })[sceneState.value[id]] || ''
}
function sceneProgressPct(id) {
  const p = sceneProgress.value[id]
  return p?.max ? Math.round(p.value / p.max * 100) : 0
}
function formatMs(ms) { return ms ? `${(ms/1000).toFixed(1)}s` : '' }

// ── load ───────────────────────────────────────────────────────────────────────
async function loadData() {
  if (!props.projectId) return
  loadingScenes.value = true
  try {
    const [scenesRes, imgRes, audRes, settingsRes, wfRes, vidRes, vidMsrRes, promptsRes] = await Promise.all([
      axios.get(`${API}/projects/${props.projectId}/scenes`),
      axios.get(`${API}/projects/${props.projectId}/images`).catch(() => ({ data: { slots: [], selected: {} } })),
      axios.get(`${API}/projects/${props.projectId}/audio`).catch(() => ({ data: {} })),
      axios.get(`${API}/settings`).catch(() => ({ data: {} })),
      axios.get(`${API}/video-engine/workflows`).catch(() => ({ data: [] })),
      axios.get(`${API}/projects/${props.projectId}/videos`).catch(() => ({ data: {} })),
      axios.get(`${API}/projects/${props.projectId}/videos-msr`).catch(() => ({ data: {} })),
      axios.get(`${API}/projects/${props.projectId}/video-prompts`).catch(() => ({ data: {} })),
    ])

    scenes.value = scenesRes.data?.scenes || []

    // Build images lookup: "{sceneId}:start:{slotIndex}" → URL or data URL
    const imgLookup = {}
    for (const slot of (imgRes.data?.slots || [])) {
      const key = `${slot.scene_id}:${slot.frame_type}:${slot.slot_index}`
      if (slot.url)  imgLookup[key] = 'http://localhost:18520' + slot.url
      else if (slot.data) imgLookup[key] = 'data:image/png;base64,' + slot.data
    }
    imagesData.value    = imgLookup
    imagesSelected.value = imgRes.data?.selected || {}

    // Audio stitched data
    // Also map reading-mode MS TTS clips (__ms_reading__{id}) into the same
    // __stitched__{id} key so scenesWithData picks them up transparently.
    const aud = audRes.data || {}
    const stitched = {}
    for (const [k, v] of Object.entries(aud)) {
      if (k.startsWith('__stitched__')) {
        stitched[k] = v
      } else if (k.startsWith('__ms_reading__')) {
        const sceneId = k.slice('__ms_reading__'.length)
        // Only apply if no stitched entry already exists for this scene
        if (!stitched[`__stitched__${sceneId}`]) {
          stitched[`__stitched__${sceneId}`] = v
        }
      }
    }
    audioData.value = stitched

    // Settings
    const vCfg = settingsRes.data?.video_engine || {}
    resolution.value = vCfg.resolution || '720x1280'
    fps.value        = vCfg.fps ?? 25
    if (vCfg.default_workflow) {
      selectedWorkflow.value = vCfg.default_workflow
      // watch 在初始化前不会触发，主动加载一次工作流类型
      await loadWorkflowInfo()
    }
    workflows.value  = wfRes.data || []

    // Saved videos（流式 URL 映射，不再整包 base64）
    sceneVideos.value = _toVideoSrcMap(vidRes.data)
    sceneVideosMsr.value = _toVideoSrcMap(vidMsrRes.data)

    // Saved video prompts
    scenePrompts.value = promptsRes.data || {}

    // Load manuscript + characters for LLM prompt generation
    try {
      const msRes = await axios.get(`${API}/projects/${props.projectId}/manuscript`)
      manuscript.value = msRes.data?.content || ''
    } catch {}
    try {
      const chRes = await axios.get(`${API}/projects/${props.projectId}/characters`)
      allCharacters.value = chRes.data?.characters || []
    } catch {}

    // v1.6: 恢复每分镜 MSR 开关 + 手动时长 + 清空白底立绘缓存（切项目时重新拉）
    _loadMsrEnabled()
    _loadManualDurations()
    _loadVideoReviewed()   // v1.6.1: 恢复视频分镜审阅标记
    for (const k of Object.keys(_whiteBgCache)) delete _whiteBgCache[k]

  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
  await reloadLastErrors()   // A1
  await reloadBgm()           // D1
}

onMounted(loadData)
onUnmounted(() => { clearTimeout(_promptSaveTimer); _savePrompts(); _clearRedubPreview() })

// When this project's tab becomes active again (after being in the background),
// refresh the saved video list so any videos that finished while hidden show up.
const tabsStore = useTabsStore()
watch(() => tabsStore.activeId, async (newId) => {
  if (newId !== props.projectId) return
  if (running.value || !scenes.value.length) return
  try { await _reloadAllVideos() } catch {}
})

// ── generation ─────────────────────────────────────────────────────────────────
let currentReader = null

async function startGeneration() {
  if (!selectedWorkflow.value) return

  const existingCount = scenesWithData.value.filter(s => hasVideoFor(s)).length
  if (existingCount > 0) {
    const ok = confirm(
      `检测到已有 ${existingCount} 个分镜视频。\n` +
      `点击“确定”将覆盖重生成；点击“取消”后请使用“继续生成”仅补生成未完成分镜。`
    )
    if (!ok) return
  }

  running.value     = true
  genFinished.value = false
  stopFlag.value    = false
  genError.value    = ''

  const states = {}
  for (const s of scenes.value) states[s.id] = 'pending'
  sceneState.value    = states
  sceneProgress.value = {}

  const readyScenes = scenesWithData.value.filter(sceneReady)
  await _runGeneration(readyScenes)
}

async function resumeGeneration() {
  if (!selectedWorkflow.value) return
  running.value     = true
  genFinished.value = false
  stopFlag.value    = false
  genError.value    = ''

  const states = { ...sceneState.value }
  for (const s of scenesWithData.value) {
    if (hasVideoFor(s)) {
      states[s.id] = 'done'
    } else if (!states[s.id]) {
      states[s.id] = 'pending'
    }
  }
  sceneState.value = states

  const readyScenes = scenesWithData.value.filter(s => sceneReady(s) && !hasVideoFor(s))
  if (!readyScenes.length) {
    running.value = false
    genFinished.value = true
    return
  }
  await _runGeneration(readyScenes)
}

async function generateOne(scene) {
  if (running.value || !sceneReady(scene)) return
  running.value = true
  stopFlag.value = false
  sceneState.value = { ...sceneState.value, [scene.id]: 'pending' }
  await _runGeneration([scene])
}

function _buildPromptFallback(scene) {
  // Mechanical fallback used only when LLM is unavailable
  const base = scene.start_frame_prompt || scene.description || ''
  const dialogues = (scene.dialogues || []).filter(d => d.character && d.character !== '旁白' && d.text)
  if (!dialogues.length) return base
  const dlgParts = dialogues.map(d => `${d.character} says: "${d.text}"`)
  return base ? `${base}. ${dlgParts.join(', ')}.` : dlgParts.join(', ') + '.'
}

// Call LLM to generate a video prompt for one scene (streaming SSE), returns final text
async function _fetchVideoPromptLLM(scene, abortSignal) {
  const sceneChars = (scene._scene_characters || [])
  const chars = sceneChars.length
    ? allCharacters.value.filter(c => sceneChars.includes(c.name))
    : allCharacters.value

  const res = await fetch(`${API}/text-engine/generate-video-prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: abortSignal,
    body: JSON.stringify({
      description:        scene.description,
      dialogues:          scene.dialogues || [],
      characters:         chars,
      start_frame_prompt: scene.start_frame_prompt || '',
      end_frame_prompt:   scene.end_frame_prompt   || '',
      manuscript:         manuscript.value,
      scene_index:        scene.index,
      total_scenes:       scenes.value.length,
    }),
  })
  if (!res.ok) throw new Error(await res.text())

  const reader  = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = ''

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
        if (obj.error) throw new Error(obj.error)
        if (obj.text) result += obj.text
      } catch (e) {
        if (raw.includes('"error"')) throw e
      }
    }
  }
  return result.trim()
}

async function generatePrompt(scene) {
  if (generatingVideoPromptId.value) return
  generatingVideoPromptId.value = scene.id
  try {
    const text = await _fetchVideoPromptLLM(scene, null)
    scenePrompts.value  = { ...scenePrompts.value,  [scene.id]: text || _buildPromptFallback(scene) }
    promptVisible.value = { ...promptVisible.value, [scene.id]: true }
    _scheduleSavePrompts()
  } catch (e) {
    if (e.name !== 'AbortError') {
      // Fallback to mechanical prompt on error
      scenePrompts.value  = { ...scenePrompts.value,  [scene.id]: _buildPromptFallback(scene) }
      promptVisible.value = { ...promptVisible.value, [scene.id]: true }
      _scheduleSavePrompts()
    }
  } finally {
    generatingVideoPromptId.value = null
  }
}

function editPrompt(scene) {
  // If no prompt exists yet, prefill with a mechanical draft as editable baseline.
  if (!scenePrompts.value[scene.id]) {
    const draft = _buildPromptFallback(scene)
    scenePrompts.value = { ...scenePrompts.value, [scene.id]: draft }
    _scheduleSavePrompts()
  }
  promptVisible.value = { ...promptVisible.value, [scene.id]: true }
}

let _videoPromptAbort = null

async function generateAllPrompts() {
  // v1.4.2: 单 SSE 批量端点。绕开 Chromium 单 origin 6 连接上限——前端只开
  // 1 个 connection，并发完全由后端 settings.text_engine.concurrency 决定。
  if (generatingAllVideoPrompts.value) return
  generatingAllVideoPrompts.value = true
  videoPromptProgress.value = 0
  _videoPromptAbort = new AbortController()

  const allScenes = scenesWithData.value
  const allCharsByName = Object.fromEntries(
    allCharacters.value.map(c => [c.name, c])
  )

  // 组装每个 scene 的 payload（含 per-scene 角色子集）
  const scenePayloads = allScenes.map(s => {
    const selected = s._scene_characters || []
    const sceneChars = selected.length
      ? selected.map(n => allCharsByName[n]).filter(Boolean)
      : null
    return {
      scene_id:           String(s.id),
      description:        s.description,
      dialogues:          s.dialogues || [],
      start_frame_prompt: s.start_frame_prompt || '',
      end_frame_prompt:   s.end_frame_prompt   || '',
      scene_index:        s.index,
      ...(sceneChars ? { characters: sceneChars } : {}),
    }
  })

  try {
    const resp = await fetch(`${API}/text-engine/generate-video-prompts-batch`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal:  _videoPromptAbort.signal,
      body:    JSON.stringify({
        scenes:       scenePayloads,
        characters:   allCharacters.value,   // 共享兜底
        manuscript:   manuscript.value,
        total_scenes: allScenes.length,
      }),
    })
    if (!resp.ok) throw new Error('HTTP ' + resp.status)
    const sceneById = {}
    allScenes.forEach((s, i) => { sceneById[String(s.id)] = s })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      if (_videoPromptAbort?.signal.aborted) { try { reader.cancel() } catch {} ; break }
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n'); buf = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          const s = ev.scene_id != null ? sceneById[String(ev.scene_id)] : null
          if (ev.event === 'result' && s) {
            const txt = ev.text || _buildPromptFallback(s)
            scenePrompts.value  = { ...scenePrompts.value,  [s.id]: txt }
            promptVisible.value = { ...promptVisible.value, [s.id]: true }
            videoPromptProgress.value++
            _scheduleSavePrompts()
          } else if (ev.event === 'item_error' && s) {
            scenePrompts.value  = { ...scenePrompts.value,  [s.id]: _buildPromptFallback(s) }
            promptVisible.value = { ...promptVisible.value, [s.id]: true }
            videoPromptProgress.value++
            _scheduleSavePrompts()
          }
        } catch {}
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.warn('batch video-prompts failed', e)
    }
  } finally {
    generatingVideoPromptId.value   = null
    generatingAllVideoPrompts.value = false
    _videoPromptAbort = null
  }
}

function togglePrompt(sceneId) {
  promptVisible.value = { ...promptVisible.value, [sceneId]: !promptVisible.value[sceneId] }
}

function onPromptInput(sceneId, value) {
  scenePrompts.value = { ...scenePrompts.value, [sceneId]: value }
  _scheduleSavePrompts()
}

function _scheduleSavePrompts() {
  clearTimeout(_promptSaveTimer)
  _promptSaveTimer = setTimeout(_savePrompts, 800)
}

async function _savePrompts() {
  if (!props.projectId) return
  try {
    await axios.put(`${API}/projects/${props.projectId}/video-prompts`, scenePrompts.value)
  } catch (e) {
    console.warn('提示词保存失败:', e)
  }
}

// Resolve an image src (URL string or data-URL) to a raw base64 string.
// Uses FileReader for efficient binary→base64 conversion without string size limits.
function _srcToB64(src) {
  if (!src) return Promise.resolve('')
  if (src.startsWith('data:')) return Promise.resolve(src.replace(/^data:image\/\w+;base64,/, ''))
  return fetch(src)
    .then(r => r.ok ? r.blob() : Promise.reject(new Error('fetch ' + r.status)))
    .then(blob => new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload  = () => resolve(reader.result.replace(/^data:[^;]+;base64,/, ''))
      reader.onerror = () => reject(reader.error)
      reader.readAsDataURL(blob)
    }))
    .catch(() => '')
}

// Send one scene at a time to avoid "Invalid string length" from huge JSON payloads.
async function _runGeneration(sceneList) {
  try {
    for (const s of sceneList) {
      if (stopFlag.value) break

      // v1.6: 该分镜走 MSR 多图参考？（LTX 模式 + 有背景图 + 已勾选）
      const msrOn = isMsrScene(s)

      // v1.4.1: i2v 不需要末帧；无音频模式（i2v 始终 / flfa2i 可选）不带音频
      const needEnd = workflowFeatures.value.requires_end_image
      const dropAudio = !workflowFeatures.value.supports_audio || noAudioMode.value

      // MSR 分镜不需要首/末帧（改由参考图驱动），跳过这两张图的 b64 转换
      const [startB64, endB64] = msrOn
        ? ['', '']
        : await Promise.all([
            _srcToB64(s.startImageB64),
            needEnd ? _srcToB64(s.endImageB64) : Promise.resolve(''),
          ])

      // 时长：MSR 镜【自带 LTX 原生音轨、不依赖预合并 TTS】→ 用户手控，默认取页面顶部
      // 的「多图参考默认时长」(10s)；无音频模式手控默认 5s；有音频镜用音频时长。
      const dur_ms = msrOn
        ? Math.max(1, Number(manualDurations.value[s.id] ?? msrDefaultDuration.value)) * 1000
        : (dropAudio
            ? Math.max(1, Number(manualDurations.value[s.id] ?? 5)) * 1000
            : (s.audioDurationMs || 4000))

      // v1.4.10++: 火山引擎模式 —— 注入每分镜独立的 volcengine_options
      let volcOptions = undefined
      if (videoMode.value === 'volcengine') {
        const o = volcOpts(s.id)
        volcOptions = {
          mode:          o.mode,
          duration_secs: o.duration_secs,
          references:    (o.references || []).map(_sanitizeVolcRef),
        }
      }

      // v1.6: MSR 多图参考 —— 收集角色白底立绘 + 背景图参考
      let msrOptions = undefined
      if (msrOn) {
        const refs = await _gatherMsrRefs(s)
        if (!(refs.char_ref_b64.length || refs.bg_ref_b64)) {
          handleEvent({ event: 'scene_error', scene_id: String(s.id),
                        message: 'MSR 分镜缺少参考图（请先在角色页生成白底立绘 / 在图片页生成背景图）' })
          continue
        }
        msrOptions = { enabled: true, ...refs }
      }

      const payload = {
        workflow_name: selectedWorkflow.value,
        resolution:    resolution.value,
        fps:           fps.value,
        project_id:    props.projectId,    // A1
        scenes: [{
          scene_id:        String(s.id),
          scene_index:     s.index,
          start_image_b64: startB64,
          end_image_b64:   endB64,
          audio_b64:       dropAudio ? '' : s.audioB64,
          duration_ms:     dur_ms,
          positive_prompt: scenePrompts.value[s.id] ?? _buildPromptFallback(s),
          ...(volcOptions ? { volcengine_options: volcOptions } : {}),
          ...(msrOptions ? { msr_options: msrOptions } : {}),
        }],
      }

      let response
      try {
        response = await fetch(`${API}/video-engine/generate-stream`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify(payload),
        })
      } catch (fetchErr) {
        handleEvent({ event: 'scene_error', scene_id: String(s.id), message: fetchErr.message })
        continue
      }

      if (!response.ok) {
        let detail = 'HTTP ' + response.status
        try { const j = await response.json(); detail = j.detail || detail } catch {}
        handleEvent({ event: 'scene_error', scene_id: String(s.id), message: detail })
        continue
      }

      currentReader = response.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        if (stopFlag.value) { currentReader.cancel(); break }
        const { done, value } = await currentReader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n'); buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') break
          try { handleEvent(JSON.parse(raw)) } catch {}
        }
      }
      currentReader = null
    }
    if (!stopFlag.value) genFinished.value = true
  } catch (e) {
    if (!stopFlag.value) genError.value = `生成失败: ${e.message}`
  } finally {
    running.value = false
    currentReader = null
    emit('dirty')
    await reloadLastErrors()   // A1: 刷新失败横幅
  }
}

function handleEvent(evt) {
  const { event, scene_id } = evt
  if (event === 'scene_start') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'active' }
  } else if (event === 'progress') {
    sceneProgress.value = { ...sceneProgress.value, [scene_id]: { value: evt.value, max: evt.max } }
  } else if (event === 'scene_done') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'done' }
    if (evt.video) {
      // 即时预览：本镜刚生成的 base64 当 data URL 喂 <video>。v1.6 双模：MSR 镜写进
      // sceneVideosMsr（后端已落盘 .msr.mp4，前端不再 PUT /videos/slot 以免误写旧 .mp4）；
      // 普通镜写 sceneVideos 并增量落盘（保持旧行为）。
      const dataUrl = 'data:video/mp4;base64,' + evt.video
      if (evt.msr) {
        sceneVideosMsr.value = { ...sceneVideosMsr.value, [scene_id]: dataUrl }
      } else {
        sceneVideos.value = { ...sceneVideos.value, [scene_id]: dataUrl }
        _saveOneVideo(scene_id, evt.video)   // A3: 单镜增量保存（仅旧/普通视频）
      }
    }
  } else if (event === 'scene_retrying') {
    // VRAM offload detected — backend is freeing memory and retrying; keep scene active
    sceneProgress.value = { ...sceneProgress.value, [scene_id]: { value: 0, max: 100, retrying: true } }
    console.info(`分镜 ${scene_id}: ${evt.message}`)
  } else if (event === 'scene_error') {
    sceneState.value = { ...sceneState.value, [scene_id]: 'error' }
    genError.value = `分镜 ${scene_id} 失败: ${evt.message}`
  } else if (event === 'batch_done') {
    genFinished.value = true
  }
}

function stopGeneration() {
  stopFlag.value = true
  currentReader?.cancel()
  running.value = false
}

async function _saveVideos() {
  if (!props.projectId) return
  try {
    const slots = Object.entries(sceneVideos.value).map(([scene_id, data]) => ({ scene_id, data }))
    await axios.put(`${API}/projects/${props.projectId}/videos`, slots)
  } catch (e) {
    // Non-critical — just log, don't surface to user
    console.warn('视频保存失败:', e)
  }
}

// A3: 单镜增量保存（每镜完成立刻落盘，不再每次重新 PUT 全量）
async function _saveOneVideo(scene_id, b64) {
  if (!props.projectId || !b64) return
  try {
    await axios.put(`${API}/projects/${props.projectId}/videos/slot`, { scene_id: String(scene_id), data: b64 })
  } catch (e) {
    console.warn('单镜视频保存失败:', e)
  }
}

async function mergeVideos() {
  if (!allVideosReady.value || merging.value) return
  merging.value = true
  genError.value = ''
  try {
    const scene_order = scenes.value.map(s => String(s.id))
    // v1.6 双模：把启用「多图参考」的分镜 id 传给后端 → 这些镜合并时用 .msr.mp4
    const msr_scene_ids = scenesWithData.value.filter(s => isMsrScene(s)).map(s => String(s.id))
    const { data } = await axios.post(`${API}/video-engine/merge-project-video`, {
      project_id: props.projectId,
      scene_order,
      msr_scene_ids,
      // D3: 镜间过渡
      transition: mergeTransition.value,
      transition_duration_ms: mergeTransitionMs.value,
      // D1: BGM 混音；-100 表示不启用 BGM
      bgm_volume_db:   bgmInfo.value.exists ? mergeBgmVolDb.value : -100,
      bgm_fade_in_ms:  mergeBgmFadeIn.value,
      bgm_fade_out_ms: mergeBgmFadeOut.value,
    })
    mergeResult.value = data
  } catch (e) {
    genError.value = e?.response?.data?.detail || e.message || '合并失败'
  } finally {
    merging.value = false
  }
}

// ── D1/D3: 合并设置 ──────────────────────────────────────────────────────
const mergeOptionsOpen = ref(false)
function openMergeOptions() {
  if (!allVideosReady.value) return
  reloadBgm()
  mergeOptionsOpen.value = true
}
async function confirmMerge() {
  mergeOptionsOpen.value = false
  await mergeVideos()
}

// ── D1: BGM 上传/查询/删除 ─────────────────────────────────────────────────
const bgmInfo        = ref({ exists: false, filename: '', size: 0 })
const bgmUploading   = ref(false)
const mergeBgmVolDb  = ref(-18)
const mergeBgmFadeIn = ref(1000)
const mergeBgmFadeOut = ref(1500)
const mergeTransition   = ref('cut')
const mergeTransitionMs = ref(300)

async function reloadBgm() {
  if (!props.projectId) return
  try {
    const r = await fetch(`${API}/video-engine/bgm/${props.projectId}`)
    if (r.ok) bgmInfo.value = await r.json()
  } catch {}
}

function pickBgmFile() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.mp3,.m4a,.wav,.aac,.ogg,.flac,audio/*'
  input.onchange = async () => {
    const f = input.files?.[0]
    if (!f) return
    bgmUploading.value = true
    try {
      const arrayBuf = await f.arrayBuffer()
      // base64 编码大文件分块
      const u8 = new Uint8Array(arrayBuf)
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < u8.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK))
      }
      const b64 = btoa(bin)
      const r = await fetch(`${API}/video-engine/bgm/${props.projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: f.name, data: b64 }),
      })
      if (!r.ok) throw new Error(await r.text())
      await reloadBgm()
    } catch (e) {
      alert('BGM 上传失败: ' + e.message)
    } finally {
      bgmUploading.value = false
    }
  }
  input.click()
}

async function deleteBgm() {
  if (!confirm('删除当前 BGM？')) return
  try {
    await fetch(`${API}/video-engine/bgm/${props.projectId}`, { method: 'DELETE' })
    await reloadBgm()
  } catch (e) { alert('删除失败: ' + e.message) }
}

async function openMergedVideo() {
  if (!mergeResult.value) return
  await window.electronAPI?.openPath(mergeResult.value.output_path)
  mergeResult.value = null
}

async function showMergedInFolder() {
  if (!mergeResult.value) return
  await window.electronAPI?.showItemInFolder(mergeResult.value.output_path)
  mergeResult.value = null
}
</script>

<style scoped>
.video-tab { display:flex; flex-direction:column; height:100%; overflow:hidden; }
.last-errors-banner {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:6px 16px; background:rgba(220,60,60,.08);
  border-bottom:1px solid rgba(220,60,60,.4); font-size:12px; flex-shrink:0;
}
.last-errors-banner .last-errors-detail { width:100%; }
.last-errors-banner ul { margin:4px 0 0 18px; padding:0; font-size:11px; line-height:1.5; }
.last-errors-banner code { background:rgba(255,255,255,.08); padding:1px 4px; border-radius:3px; }
.meta-grid {
  display: grid;
  grid-template-columns: 1fr 110px 80px;
  gap: 6px 10px; align-items: center; font-size: 13px;
}
.meta-input { padding: 4px 6px; font-size: 12px; }
.meta-widget { width: 80px; }
.meta-label  { color: var(--color-text); }
.bgm-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.bgm-pill { background:rgba(60,180,90,.15); border:1px solid rgba(60,180,90,.5); padding:3px 8px; border-radius:4px; font-size:12px; }
.video-toolbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:12px 16px 8px; flex-shrink:0;
}
.toolbar-left  { display:flex; align-items:center; gap:12px; }
.engine-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  border: 1px solid var(--color-border);
  white-space: nowrap;
}
.engine-badge-cloud {
  background: rgba(102, 178, 255, 0.12);
  border-color: rgba(102, 178, 255, 0.45);
  color: #66b2ff;
}
.engine-badge-local {
  background: var(--color-surface-2, rgba(255,255,255,0.04));
  color: var(--color-text-muted);
}

/* v1.4.10++ 火山引擎每分镜配置块 */
.volc-scene-block {
  background: rgba(102, 178, 255, 0.06);
  border: 1px solid rgba(102, 178, 255, 0.25);
  border-radius: 6px;
  padding: 8px 10px;
  margin: 8px 0;
  display: flex; flex-direction: column; gap: 8px;
}
/* v1.6: MSR 多图参考视频块 */
.msr-scene-block {
  background: rgba(178, 102, 255, 0.06);
  border: 1px solid rgba(178, 102, 255, 0.28);
  border-radius: 6px;
  padding: 8px 10px;
  margin: 8px 0;
  display: flex; flex-direction: column; gap: 6px;
}
.msr-toggle {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; cursor: pointer; user-select: none;
}
.msr-toggle input { cursor: pointer; }
.msr-hint { display: flex; gap: 6px; flex-wrap: wrap; }
.msr-ref-tag {
  font-size: 11px; padding: 1px 8px; border-radius: 10px;
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  background: var(--color-surface, rgba(255,255,255,0.03));
}
.msr-ref-tag.ok   { border-color: rgba(80,200,120,0.5); color: #5bbf7b; }
.msr-ref-tag.warn { border-color: rgba(230,180,80,0.5); color: #d8a24a; }
.volc-scene-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.volc-spacer { flex: 1; }
.input-xs {
  padding: 2px 6px; font-size: 12px; height: 24px;
}
.volc-refs-grid {
  display: flex; gap: 6px; flex-wrap: wrap;
}
.volc-ref-chip {
  position: relative;
  width: 64px; height: 64px;
  border: 1px solid var(--color-border);
  border-radius: 4px; overflow: hidden;
  background: var(--color-surface, rgba(255,255,255,0.03));
}
.volc-ref-chip img { width: 100%; height: 100%; object-fit: cover; display: block; }
.volc-ref-noimg {
  display:flex; align-items:center; justify-content:center;
  width: 100%; height: 100%; font-size: 11px; color: var(--color-text-muted);
}
.volc-ref-kind {
  position: absolute; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.55); color: #fff;
  font-size: 9px; text-align: center; padding: 1px 0;
}
.volc-ref-del {
  position: absolute; top: 2px; right: 2px;
  width: 16px; height: 16px; padding: 0;
  border: none; border-radius: 3px;
  background: rgba(0,0,0,0.55); color: #fff;
  font-size: 10px; line-height: 14px; cursor: pointer;
  opacity: 0;
}
.volc-ref-chip:hover .volc-ref-del { opacity: 1; }
.volc-ref-del:hover { background: var(--color-error); }
.toolbar-right { display:flex; align-items:center; gap:8px; }
.toolbar-title { margin:0; font-size:15px; font-weight:600; }

.video-config  { flex-shrink:0; margin:0 16px 8px; padding:12px; }
.config-row    { display:flex; flex-wrap:wrap; gap:12px; }
.config-group  { display:flex; align-items:center; gap:6px; }
.cfg-label     { font-size:12px; color:var(--text-muted); white-space:nowrap; }
.select-compact { font-size:12px; }
.config-hint   { margin:8px 0 0; font-size:11px; color:var(--text-muted); }

.progress-wrap { flex-shrink:0; margin:0 16px 8px; padding:10px 12px; }
.progress-label { display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted); margin-bottom:4px; }
.progress-track { height:6px; border-radius:4px; background:var(--bg-tertiary); overflow:hidden; }
.progress-fill  { height:100%; background:var(--accent); transition:width .3s; }

.scene-video-list {
  flex:1; overflow-y:auto; padding:0 16px 16px; display:flex; flex-direction:column; gap:10px;
}
.scene-video-card { padding:12px; }

/* v1.6.1: 左栏列表 + 右栏详情（master-detail），只渲染当前分镜的视频 */
.video-md { flex:1; min-height:0; display:flex; gap:12px; padding:0 16px 16px; overflow:hidden; }
.video-md-list {
  flex:0 0 260px; max-width:260px; overflow-y:auto; display:flex; flex-direction:column; gap:4px;
  padding-right:4px;
}
.video-md-item {
  display:flex; gap:8px; align-items:flex-start; padding:7px 9px; border-radius:6px; cursor:pointer;
  border:1px solid transparent; background:var(--bg-tertiary, rgba(255,255,255,.03));
}
.video-md-item:hover { border-color:var(--border-color, #444); }
.video-md-item.active { border-color:var(--accent, #66b2ff); background:rgba(102,178,255,.10); }
.vmd-num { font-size:13px; font-weight:700; color:var(--accent, #66b2ff); min-width:22px; flex-shrink:0; }
.vmd-body { flex:1; min-width:0; display:flex; flex-direction:column; gap:3px; }
.vmd-desc { font-size:12px; line-height:1.35; }
.vmd-tags { display:flex; gap:5px; align-items:center; flex-wrap:wrap; }
.vmd-review {
  font-size:10px; padding:1px 6px; border-radius:8px; border:1px solid var(--border-color, #444);
  color:var(--color-text-muted, #999);
}
.vmd-review.ok { border-color:rgba(80,200,120,.6); color:#5bbf7b; background:rgba(80,200,120,.10); }
.vmd-mini { font-size:11px; color:var(--color-text-muted, #999); }
.vmd-mini.ok { color:#5bbf7b; }
.vmd-mini.warn { color:#d8a24a; }
.video-md-detail { flex:1; min-width:0; overflow-y:auto; }
@media (max-width: 720px) {
  .video-md { flex-direction:column; }
  .video-md-list { flex:none; max-width:100%; max-height:160px; }
}

/* v1.6: 分镜卡左右双栏 —— 左视频预览，右分镜配置 */
.svcard-cols { display:flex; gap:14px; align-items:flex-start; }
.svcard-col-preview { flex:0 0 42%; max-width:42%; display:flex; flex-direction:column; gap:8px; position:sticky; top:8px; }
.svcard-col-config  { flex:1; min-width:0; display:flex; flex-direction:column; gap:8px; }
.video-preview-empty {
  width:100%; aspect-ratio:16/10; border-radius:6px;
  border:1px dashed var(--border-color); background:var(--bg-tertiary,#1a1a1a);
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:6px; color:var(--color-text-muted); font-size:12px;
}
.video-preview-empty-icon { font-size:26px; opacity:.5; }
@media (max-width: 900px) {
  .svcard-cols { flex-direction:column; }
  .svcard-col-preview { flex:none; max-width:100%; width:100%; position:static; }
}

.svcard-header { display:flex; align-items:flex-start; gap:8px; }
.svcard-desc {
  flex:1; min-width:0; font-size:13px; font-weight:500;
  white-space:pre-wrap; word-break:break-all; cursor:default;
}
.svcard-status { font-size:12px; font-weight:600; }
/* v1.6.1: 人工审阅开关 */
.review-toggle {
  flex-shrink:0; font-size:11px; padding:2px 8px; border-radius:10px; cursor:pointer;
  border:1px solid var(--border, #444); background:transparent; color:var(--text-muted, #999);
}
.review-toggle.reviewed { border-color:rgba(80,200,120,.6); color:#5bbf7b;
  background:rgba(80,200,120,.10); }
.svcard-status.active { color:var(--accent); }
.svcard-status.done   { color:var(--color-success,#4caf50); }
.svcard-status.error  { color:var(--color-error,#f44336); }

.scene-num { font-size:11px; font-weight:700; background:var(--accent); color:#fff; border-radius:4px; padding:1px 6px; }

.asset-checks { display:flex; gap:6px; flex-wrap:wrap; }
.asset-tag { font-size:11px; padding:2px 7px; border-radius:10px; border:1px solid; font-weight:500; }
.asset-tag.ok   { border-color:var(--color-success,#4caf50); color:var(--color-success,#4caf50); }
.asset-tag.miss { border-color:var(--color-warning,#ff9800); color:var(--color-warning,#ff9800); }

.scene-mini-bar-wrap { display:flex; align-items:center; gap:8px; }
.scene-mini-bar { flex:1; height:4px; border-radius:2px; background:var(--bg-tertiary); overflow:hidden; }
.scene-mini-fill{ height:100%; background:var(--accent); transition:width .2s; }

.video-result { border-top:1px dashed var(--border-color); padding-top:8px; }
/* v1.6: 视频后期变声 */
.video-post-actions { display:flex; align-items:center; gap:8px; margin-top:6px; }
.redub-field { display:flex; flex-direction:column; gap:4px; margin:8px 0; }
.redub-field > label { font-size:12px; color: var(--color-text-muted); }
.redub-params { display:flex; flex-wrap:wrap; gap:8px; }
.redub-param { display:flex; flex-direction:column; gap:2px; font-size:11px;
  color: var(--color-text-muted); }
.redub-param > input { width:78px; padding:2px 6px; font-size:12px; }
.video-player { width:100%; max-height:320px; border-radius:6px; background:#000; }

.empty-state {
  flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; opacity:.7;
}
.empty-icon { font-size:40px; }
.spinner { width:24px; height:24px; border:2px solid var(--border-color); border-top-color:var(--accent); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }

.error-banner {
  flex-shrink:0; margin:0 16px 8px; padding:8px 12px; border-radius:6px;
  background:color-mix(in srgb, var(--color-error,#f44336) 12%, transparent);
  border:1px solid var(--color-error,#f44336);
  font-size:13px; display:flex; align-items:center; gap:8px;
}

.merge-dialog-overlay {
  position:fixed; inset:0; background:rgba(0,0,0,.5); z-index:200;
  display:flex; align-items:center; justify-content:center;
}
.merge-dialog {
  min-width:360px; max-width:520px; padding:20px 24px; display:flex; flex-direction:column; gap:14px;
  /* v1.6: 高度不超过窗口，内容超出时对话框内部滚动（否则后期/去水印面板会被截断看不到） */
  max-height:90vh; overflow-y:auto; box-sizing:border-box;
}
.merge-dialog-title { margin:0; font-size:16px; font-weight:700; }
.merge-dialog-path {
  font-size:12px; color:var(--text-muted); word-break:break-all;
  background:var(--bg-tertiary); padding:6px 10px; border-radius:4px;
}
.merge-dialog-actions { display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }

/* ── Prompt section ── */
.prompt-section {
  border-top: 1px dashed var(--border-color);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.prompt-label {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.prompt-set-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
}
.prompt-actions { display: flex; gap: 4px; }
.prompt-editor-wrap { display: flex; flex-direction: column; gap: 4px; }
.prompt-textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font-size: 12px;
  line-height: 1.5;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  min-height: 64px;
}
.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
}

/* v1.4.1: 工作流类型徽章 + 无音频开关 */
.kind-badge {
  display: inline-block;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--bg-input, rgba(255,255,255,.08));
  border: 1px solid var(--border, #333);
  color: var(--text-muted, #aaa);
}
.kind-badge.video_flfa2i {
  border-color: rgba(99,179,237,.5); color: #63b3ed;
  background: rgba(99,179,237,.08);
}
.kind-badge.video_i2v {
  border-color: rgba(183,148,244,.5); color: #b794f4;
  background: rgba(183,148,244,.08);
}
.no-audio-toggle {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--text-muted, #aaa); cursor: pointer;
}
.no-audio-toggle input { margin: 0; }

/* v1.4.6: 视频引擎模式切换 */
.vt-mode-toggle { display: flex; gap: 10px; flex-wrap: wrap; }
.vt-mode-toggle label {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; border: 1px solid var(--border);
  border-radius: 6px; cursor: pointer; font-size: 12px;
  background: var(--bg-input); color: var(--text-muted);
  transition: border-color .15s, color .15s, background .15s;
}
.vt-mode-toggle label.active {
  border-color: var(--accent); color: var(--text); font-weight: 600;
  background: rgba(99,179,237,.08);
}
.vt-mode-toggle input { margin: 0; }

.duration-tag {
  display: inline-flex; align-items: center; gap: 4px;
}
.duration-input {
  width: 48px; height: 22px; padding: 0 6px;
  border: 1px solid var(--border, #444); border-radius: 4px;
  background: var(--bg-input, #2a2a2a); color: var(--text, #ddd);
  font-size: 12px; text-align: center;
}
</style>
