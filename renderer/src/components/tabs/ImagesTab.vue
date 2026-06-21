<template>
  <div class="tab-panel images-tab">

    <!-- == Toolbar == -->
    <div class="img-toolbar">
      <div class="toolbar-left">
        <h3 class="toolbar-title">图片生成</h3>
        <span class="scene-count text-muted" v-if="scenes.length">
          {{ scenes.length }} 个分镜 · 每帧 {{ genCount }} 张 · {{ imgWidth }}×{{ imgHeight }}</span>
      </div>
      <div class="toolbar-right">
        <select class="input select-compact" v-model="selectedWorkflow" :disabled="running">
          <option value="">— 选择工作流 —</option>
          <option v-for="wf in workflows" :key="wf" :value="wf">{{ wf }}</option>
        </select>
        <div class="style-select-group">
          <label class="text-muted" style="font-size:12px;white-space:nowrap">画风</label>
          <select class="input select-compact style-preset-select" v-model="stylePreset" :disabled="running">
            <option v-for="p in STYLE_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
          <input v-if="stylePreset === '__custom__'" class="input style-custom-input"
            placeholder="输入英文画风提示词…" v-model="customStyleText" :disabled="running" />
        </div>
        <div class="gen-count-group">
          <label class="text-muted" style="font-size:12px;white-space:nowrap">每帧张数</label>
          <input class="input input-num" type="number" min="1" max="10" step="1"
            v-model.number="genCount" :disabled="running" />
        </div>
        <template v-if="running && !paused">
          <button class="btn btn-warning btn-sm" @click="pauseBatch">⏸ 暂停</button>
        </template>
        <template v-else-if="paused">
          <button class="btn btn-primary btn-sm" @click="resumeBatch">▶ 继续</button>
          <button class="btn btn-secondary btn-sm" @click="cancelBatch">✕ 取消</button>
        </template>
        <template v-else>
          <button class="btn btn-primary btn-sm"
            :disabled="!selectedWorkflow || !scenes.length" @click="startBatch">▶ 全部生成</button>
        </template>
      </div>
    </div>

    <!-- v1.4.6: 比例提醒 banner -->
    <div class="ratio-info-banner">
      📐 当前画面尺寸 <code>{{ imgWidth }} × {{ imgHeight }}</code>
      （{{ (imgWidth / imgHeight).toFixed(3) }}:1）
      — 导入图片会被剪裁到此比例；要改请去
      <a href="#" @click.prevent="goSettings">设置 → 图片引擎</a>
    </div>

    <!-- A1: 上次失败镜次提示 + 一键重试 -->
    <div v-if="lastErrorCount && !running" class="last-errors-banner">
      <span>⚠ 上次失败：{{ lastErrorCount }} 个分镜</span>
      <button class="btn btn-warning btn-xs" :disabled="!selectedWorkflow" @click="retryFailedBatch">
        ↻ 只重试失败镜
      </button>
      <button class="btn btn-ghost btn-xs" @click="dismissLastErrors">✕ 忽略</button>
      <details class="last-errors-detail">
        <summary class="text-muted" style="font-size:11px;cursor:pointer">查看详情</summary>
        <ul>
          <li v-for="(msg, k) in lastErrors" :key="k"><code>{{ k }}</code>: {{ msg }}</li>
        </ul>
      </details>
    </div>

    <!-- v1.4.4: SD 工作流高级参数面板（仅在 sd_default_workflow 选中时） -->
    <SdParamsPanel v-if="isSdWorkflow"
                   v-model="sdParams"
                   v-model:negativePrompt="sdNegativePrompt" />

    <!-- == Progress bar == -->
    <div v-if="running || paused || batchDone" class="batch-progress-bar-wrap">
      <div class="batch-progress-label">
        <span v-if="paused">⏸ 已暂停 · 下次从第 {{ batchResumeFrom + 1 }} 个分镜继续</span>
        <span v-else-if="running && batchCurrentIdx >= 0">生成中 · 第 {{ batchCurrentIdx + 1 }}/{{ scenes.length }} 个分镜</span>
        <span v-else-if="batchDone">✔ 生成完成</span>
        <span v-else>准备中…</span>
        <span>{{ completedCount }} / {{ totalCount }}</span>
      </div>
      <div class="batch-progress-track">
        <div class="batch-progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
    </div>

    <!-- == States == -->
    <div v-if="loadError" class="full-state error-state">
      <div class="state-icon">⚠</div><p>{{ loadError }}</p>
      <button class="btn btn-secondary btn-sm" @click="loadData">重试</button>
    </div>
    <div v-else-if="!scenes.length && !loadingScenes" class="full-state empty-state">
      <div class="state-icon">🎞</div><p>请先在「分镜设计」完成分镜并保存</p>
    </div>
    <div v-else-if="loadingScenes" class="full-state empty-state">
      <div class="spinner" /><p class="text-muted">加载分镜中…</p>
    </div>

    <!-- == Main: left list + right detail == -->
    <div v-else class="images-main">

      <!-- Left panel: scene list -->
      <div class="scene-list-panel">
        <div
          v-for="scene in scenes" :key="scene.id"
          class="scene-list-item"
          :class="{
            active: activeSceneId === scene.id,
            generating: !!sceneGenerating[scene.id],
            'batch-current': batchCurrentIdx >= 0 && scenes[batchCurrentIdx]?.id === scene.id
          }"
          @click="activeSceneId = scene.id"
        >
          <div class="scene-list-thumbs">
            <div class="mini-thumb">
              <img v-if="getImage(scene.id, 'start', scene._selected_start)"
                   :src="getImage(scene.id, 'start', scene._selected_start)" />
              <div v-else-if="isLoading(scene.id, 'start', scene._selected_start)" class="mini-spinner"><div class="spinner spinner-xs"/></div>
              <div v-else class="mini-empty">首</div>
            </div>
            <div class="mini-thumb">
              <img v-if="getImage(scene.id, 'end', scene._selected_end)"
                   :src="getImage(scene.id, 'end', scene._selected_end)" />
              <div v-else-if="isLoading(scene.id, 'end', scene._selected_end)" class="mini-spinner"><div class="spinner spinner-xs"/></div>
              <div v-else class="mini-empty">尾</div>
            </div>
          </div>
          <div class="scene-list-info">
            <div class="scene-list-num">{{ String(scene.index).padStart(2,'0') }}</div>
            <div class="scene-list-desc truncate" :title="scene.description">{{ scene.description || '(无描述)' }}</div>
            <div class="scene-list-status">
              <span v-if="imgReviewed[scene.id]" class="status-dot" title="已审阅">✅</span>
              <span v-if="sceneGenerating[scene.id]" class="status-dot dot-active">⏳</span>
              <span v-else-if="hasAnyImage(scene)" class="status-dot dot-done">✓</span>
            </div>
          </div>
          <button class="scene-list-gen-btn"
            :disabled="running || !!sceneGenerating[scene.id] || !selectedWorkflow"
            @click.stop="generateOneScene(scene)" :title="'生成此分镜'">
            <span v-if="sceneGenerating[scene.id]">⏳</span>
            <span v-else>▶</span>
          </button>
        </div>
      </div>

      <!-- Right panel: detail -->
      <div class="scene-detail-panel" v-if="activeScene">
        <div class="detail-header">
          <div class="detail-header-top">
            <span class="detail-num">{{ String(activeScene.index).padStart(2,'0') }}</span>
            <button class="btn btn-secondary btn-sm"
            :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
            @click="generateOneScene(activeScene)">
            <span v-if="sceneGenerating[activeScene.id]">⏳ 生成中…</span>
            <span v-else>▶ 重新生成此分镜</span>
          </button>
          <!-- v1.6.1: 人工审阅开关（纯标记，不影响任何生成机制；可随时开关） -->
          <button class="review-toggle" :class="{ reviewed: imgReviewed[activeScene.id] }"
                  @click="toggleImgReviewed(activeScene.id)"
                  :title="imgReviewed[activeScene.id] ? '已审阅通过（点击改回未审阅）' : '未审阅（点击标记为已审阅通过）'">
            {{ imgReviewed[activeScene.id] ? '✅ 已审阅' : '☐ 未审阅' }}
          </button>
          </div>
          <div class="detail-desc-block">{{ sceneFullText(activeScene) }}</div>
        </div>

        <!-- Start frame -->
        <div class="detail-frame-section">
          <div class="detail-frame-header">
            <span class="frame-badge badge-blue">首帧</span>
            <button class="btn btn-ghost btn-xs" :disabled="running || regenPromptingId === activeScene.id + ':start'"
              @click="regenPromptOnly(activeScene,'start')" title="重新生成首帧提示词">
              {{ regenPromptingId === activeScene.id + ':start' ? '⏳' : '↺' }} 提示词
            </button>
            <!-- v1.4.12: Ideogram 4 结构化提示词构建器 -->
            <button v-if="isIdeogram" class="btn btn-ghost btn-xs"
              @click="openIdeogramBuilder(activeScene, 'start')"
              title="用可视化构建器生成 Ideogram 4 结构化 JSON 提示词">🧩 构建器</button>
            <button class="btn btn-ghost btn-xs" :disabled="running" @click="regenFrame(activeScene,'start')">↺ 重新生成所有</button>
          </div>
          <textarea
            class="input textarea frame-prompt-edit"
            rows="3"
            placeholder="首帧提示词（英文）…"
            :value="activeScene.start_frame_prompt"
            @input="onPromptInput(activeScene, 'start', $event.target.value)"
          />
          <!-- 轮 5: i2i 参考图槽位（首帧） -->
          <div v-if="isI2I" class="ref-slots-row">
            <span class="ref-slots-label">📎 参考图</span>
            <div v-for="i in workflowRefCount" :key="'sref'+(i-1)"
                 class="ref-slot"
                 @click="openRefPicker(activeScene, 'start', i-1)">
              <img v-if="refSlotPreview(activeScene, 'start', i-1)?._preview_url"
                   :src="refSlotPreview(activeScene, 'start', i-1)._preview_url" />
              <div v-else class="ref-slot-empty">＋ ref {{ i }}</div>
              <button v-if="refSlotPreview(activeScene, 'start', i-1)"
                      class="ref-slot-clear"
                      @click.stop="clearRef(activeScene, 'start', i-1)" title="清除">✕</button>
              <div v-if="refSlotPreview(activeScene, 'start', i-1)?._label"
                   class="ref-slot-label" :title="refSlotPreview(activeScene,'start',i-1)._label">
                {{ refSlotPreview(activeScene,'start',i-1)._label }}
              </div>
            </div>
          </div>
          <div class="image-slots" :style="slotVars">
            <div
              v-for="slot in getFrameSlotCount(activeScene.id, 'start')" :key="slot-1"
              class="image-slot"
              :class="{
                selected: activeScene._selected_start === slot-1,
                loading:  isLoading(activeScene.id,'start',slot-1),
                errored:  isErrored(activeScene.id,'start',slot-1)
              }"
              @click="selectImage(activeScene,'start',slot-1)"
            >
              <img v-if="getImage(activeScene.id,'start',slot-1)"
                   :src="getImage(activeScene.id,'start',slot-1)" alt="首帧" />
              <div v-else-if="isLoading(activeScene.id,'start',slot-1)" class="slot-loading">
                <div class="spinner spinner-sm"/>
                <span class="slot-progress-text">{{ getProgress(activeScene.id,'start',slot-1) }}</span>
              </div>
              <div v-else-if="isErrored(activeScene.id,'start',slot-1)" class="slot-error">
                <span>⚠</span><span class="slot-err-msg">{{ getError(activeScene.id,'start',slot-1) }}</span>
              </div>
              <div v-else class="slot-empty"><span>{{ slot }}</span></div>
              <div v-if="getImage(activeScene.id,'start',slot-1)" class="slot-overlay">
                <button class="slot-overlay-btn" @click.stop="openPreview(activeScene,'start',slot-1)" :title="'预览'">⛶</button>
                <button class="slot-overlay-btn slot-overlay-del" @click.stop="deleteSlot(activeScene,'start',slot-1)" :title="'删除'">🗑</button>
              </div>
              <!-- v1.4.3: 空槽 / 错误槽也允许删除（用户主诉：失败遗留空槽无法清理）-->
              <div v-else-if="!isLoading(activeScene.id,'start',slot-1)" class="slot-overlay slot-overlay-empty">
                <button class="slot-overlay-btn slot-overlay-del"
                        @click.stop="deleteSlot(activeScene,'start',slot-1)"
                        :title="'删除此槽位'">🗑</button>
              </div>
              <div class="selected-badge" v-if="activeScene._selected_start === slot-1">✓</div>
            </div>
            <button class="image-slot slot-add"
              :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
              @click="addOneMore(activeScene,'start')" :title="'再生成一张'">＋</button>
            <!-- v1.4.6: 导入本地图片（自动按设置页比例剪裁） -->
            <button class="image-slot slot-import"
              :disabled="running"
              @click="triggerImport(activeScene, 'start')"
              :title="'导入本地图片（自动按比例剪裁）'">📥</button>
          </div>
        </div>

        <!-- End frame -->
        <div class="detail-frame-section">
          <div class="detail-frame-header">
            <span class="frame-badge badge-purple">尾帧</span>
            <button class="btn btn-ghost btn-xs" :disabled="running || regenPromptingId === activeScene.id + ':end'"
              @click="regenPromptOnly(activeScene,'end')" title="重新生成尾帧提示词">
              {{ regenPromptingId === activeScene.id + ':end' ? '⏳' : '↺' }} 提示词
            </button>
            <!-- v1.4.12: Ideogram 4 结构化提示词构建器 -->
            <button v-if="isIdeogram" class="btn btn-ghost btn-xs"
              @click="openIdeogramBuilder(activeScene, 'end')"
              title="用可视化构建器生成 Ideogram 4 结构化 JSON 提示词">🧩 构建器</button>
            <button class="btn btn-ghost btn-xs" :disabled="running" @click="regenFrame(activeScene,'end')">↺ 重新生成所有</button>
          </div>
          <textarea
            class="input textarea frame-prompt-edit"
            rows="3"
            placeholder="尾帧提示词（英文）…"
            :value="activeScene.end_frame_prompt"
            @input="onPromptInput(activeScene, 'end', $event.target.value)"
          />
          <!-- 轮 5: i2i 参考图槽位（尾帧） -->
          <div v-if="isI2I" class="ref-slots-row">
            <span class="ref-slots-label">📎 参考图</span>
            <div v-for="i in workflowRefCount" :key="'eref'+(i-1)"
                 class="ref-slot"
                 @click="openRefPicker(activeScene, 'end', i-1)">
              <img v-if="refSlotPreview(activeScene, 'end', i-1)?._preview_url"
                   :src="refSlotPreview(activeScene, 'end', i-1)._preview_url" />
              <div v-else class="ref-slot-empty">＋ ref {{ i }}</div>
              <button v-if="refSlotPreview(activeScene, 'end', i-1)"
                      class="ref-slot-clear"
                      @click.stop="clearRef(activeScene, 'end', i-1)" title="清除">✕</button>
              <div v-if="refSlotPreview(activeScene, 'end', i-1)?._label"
                   class="ref-slot-label" :title="refSlotPreview(activeScene,'end',i-1)._label">
                {{ refSlotPreview(activeScene,'end',i-1)._label }}
              </div>
            </div>
          </div>
          <div class="image-slots" :style="slotVars">
            <div
              v-for="slot in getFrameSlotCount(activeScene.id, 'end')" :key="slot-1"
              class="image-slot"
              :class="{
                selected: activeScene._selected_end === slot-1,
                loading:  isLoading(activeScene.id,'end',slot-1),
                errored:  isErrored(activeScene.id,'end',slot-1)
              }"
              @click="selectImage(activeScene,'end',slot-1)"
            >
              <img v-if="getImage(activeScene.id,'end',slot-1)"
                   :src="getImage(activeScene.id,'end',slot-1)" alt="尾帧" />
              <div v-else-if="isLoading(activeScene.id,'end',slot-1)" class="slot-loading">
                <div class="spinner spinner-sm"/>
                <span class="slot-progress-text">{{ getProgress(activeScene.id,'end',slot-1) }}</span>
              </div>
              <div v-else-if="isErrored(activeScene.id,'end',slot-1)" class="slot-error">
                <span>⚠</span><span class="slot-err-msg">{{ getError(activeScene.id,'end',slot-1) }}</span>
              </div>
              <div v-else class="slot-empty"><span>{{ slot }}</span></div>
              <div v-if="getImage(activeScene.id,'end',slot-1)" class="slot-overlay">
                <button class="slot-overlay-btn" @click.stop="openPreview(activeScene,'end',slot-1)" :title="'预览'">⛶</button>
                <button class="slot-overlay-btn slot-overlay-del" @click.stop="deleteSlot(activeScene,'end',slot-1)" :title="'删除'">🗑</button>
              </div>
              <!-- v1.4.3: 空槽 / 错误槽也允许删除 -->
              <div v-else-if="!isLoading(activeScene.id,'end',slot-1)" class="slot-overlay slot-overlay-empty">
                <button class="slot-overlay-btn slot-overlay-del"
                        @click.stop="deleteSlot(activeScene,'end',slot-1)"
                        :title="'删除此槽位'">🗑</button>
              </div>
              <div class="selected-badge" v-if="activeScene._selected_end === slot-1">✓</div>
            </div>
            <button class="image-slot slot-add"
              :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
              @click="addOneMore(activeScene,'end')" :title="'再生成一张'">＋</button>
            <!-- v1.4.6 -->
            <button class="image-slot slot-import"
              :disabled="running"
              @click="triggerImport(activeScene, 'end')"
              :title="'导入本地图片（自动按比例剪裁）'">📥</button>
          </div>
        </div>

        <!-- v1.6: 背景图(无角色) — 供 MSR 多图参考视频用 -->
        <div class="detail-frame-section">
          <div class="detail-frame-header">
            <span class="frame-badge" style="background:#2f855a;color:#fff">背景图</span>
            <span class="text-muted" style="font-size:11px">无角色背景图 · 供多图参考视频(LTX MSR)用</span>
            <button class="btn btn-ghost btn-xs" :disabled="running || regenPromptingId === activeScene.id + ':bg'"
              @click="regenPromptOnly(activeScene,'bg')" title="用 LLM 生成无角色的纯环境背景提示词">
              {{ regenPromptingId === activeScene.id + ':bg' ? '⏳' : '↺' }} 提示词
            </button>
            <button class="btn btn-ghost btn-xs" :disabled="running" @click="regenFrame(activeScene,'bg')">↺ 重新生成所有</button>
            <span class="bg-batch-sep" />
            <button class="btn btn-secondary btn-xs"
              :disabled="running || bgPromptRunning || !scenes.length"
              @click="genAllBgPrompts"
              title="为【全部分镜】批量生成无角色背景提示词（跳过已有）">
              {{ bgPromptRunning ? `✦ 提示词 ${bgPromptProgress}/${scenes.length}…` : '✦ 全部分镜提示词' }}
            </button>
            <button class="btn btn-secondary btn-xs"
              :disabled="running || bgImageRunning || !selectedWorkflow || !scenes.length"
              @click="genAllBgImages"
              title="为【全部分镜】批量生成背景图（仅含已有背景提示词的分镜，跳过已出图）">
              {{ bgImageRunning ? `🖼 背景图 ${bgImageProgress}/${bgImageTotal}…` : '🖼 全部分镜背景图' }}
            </button>
          </div>
          <textarea
            class="input textarea frame-prompt-edit"
            rows="3"
            placeholder="背景图提示词（英文，纯环境无人物）…"
            :value="activeScene.bg_prompt"
            @input="onPromptInput(activeScene, 'bg', $event.target.value)"
          />
          <div class="image-slots" :style="slotVars">
            <div
              v-for="slot in getFrameSlotCount(activeScene.id, 'bg')" :key="'bg'+(slot-1)"
              class="image-slot"
              :class="{
                selected: activeScene._selected_bg === slot-1,
                loading:  isLoading(activeScene.id,'bg',slot-1),
                errored:  isErrored(activeScene.id,'bg',slot-1)
              }"
              @click="selectImage(activeScene,'bg',slot-1)"
            >
              <img v-if="getImage(activeScene.id,'bg',slot-1)"
                   :src="getImage(activeScene.id,'bg',slot-1)" alt="背景图" />
              <div v-else-if="isLoading(activeScene.id,'bg',slot-1)" class="slot-loading">
                <div class="spinner spinner-sm"/>
                <span class="slot-progress-text">{{ getProgress(activeScene.id,'bg',slot-1) }}</span>
              </div>
              <div v-else-if="isErrored(activeScene.id,'bg',slot-1)" class="slot-error">
                <span>⚠</span><span class="slot-err-msg">{{ getError(activeScene.id,'bg',slot-1) }}</span>
              </div>
              <div v-else class="slot-empty"><span>{{ slot }}</span></div>
              <div v-if="getImage(activeScene.id,'bg',slot-1)" class="slot-overlay">
                <button class="slot-overlay-btn" @click.stop="openPreview(activeScene,'bg',slot-1)" title="预览">⛶</button>
                <button class="slot-overlay-btn slot-overlay-del" @click.stop="deleteSlot(activeScene,'bg',slot-1)" title="删除">🗑</button>
              </div>
              <div v-else-if="!isLoading(activeScene.id,'bg',slot-1)" class="slot-overlay slot-overlay-empty">
                <button class="slot-overlay-btn slot-overlay-del"
                        @click.stop="deleteSlot(activeScene,'bg',slot-1)" title="删除此槽位">🗑</button>
              </div>
              <div class="selected-badge" v-if="activeScene._selected_bg === slot-1">✓</div>
            </div>
            <button class="image-slot slot-add"
              :disabled="running || !!sceneGenerating[activeScene.id] || !selectedWorkflow"
              @click="addOneMore(activeScene,'bg')" title="再生成一张">＋</button>
            <button class="image-slot slot-import"
              :disabled="running"
              @click="triggerImport(activeScene, 'bg')"
              title="导入本地背景图（自动按比例剪裁）">📥</button>
          </div>
        </div>

        <!-- Character selector panel -->
        <div v-if="characters.length" class="char-select-panel">
          <div class="char-select-header">
            <span class="char-select-title">🎭 出镜角色</span>
            <span class="char-select-hint text-muted">选择在此分镜画面中出现的角色</span>
            <button
              class="btn btn-secondary btn-xs"
              :disabled="suggestingChars"
              @click="suggestChars(activeScene)"
              title="用AI分析分镜描述和台词，自动推荐出镜角色"
            >{{ suggestingChars ? '分析中…' : '✦ AI 自动选' }}</button>
          </div>
          <div class="char-chips">
            <label
              v-for="c in characters" :key="c.name"
              class="char-chip"
              :class="{ selected: (activeScene._scene_characters || []).includes(c.name) }"
            >
              <input
                type="checkbox"
                :value="c.name"
                :checked="(activeScene._scene_characters || []).includes(c.name)"
                @change="toggleSceneChar(activeScene, c.name)"
              />
              {{ c.name }}
            </label>
          </div>
          <p v-if="!(activeScene._scene_characters || []).length" class="char-select-fallback text-muted">
            未选择角色时，生成提示词将不包含角色外观描述
          </p>
          <!-- v1.6.3: 每角色外观（此分镜用哪个形象；仅在该角色有多个外观时出现） -->
          <div v-if="sceneCharsWithLooks(activeScene).length" class="char-looks">
            <span class="char-looks-title text-muted">🎭 本镜形象</span>
            <div v-for="c in sceneCharsWithLooks(activeScene)" :key="c.name" class="char-look-row">
              <span class="char-look-name truncate">{{ c.name }}</span>
              <select class="input select-compact char-look-select"
                      :value="effAppId(activeScene, c.name)"
                      @change="setSceneLook(activeScene, c.name, $event.target.value)">
                <option v-for="a in c.appearances" :key="a.id" :value="a.id">
                  {{ a.name || '外观' }}{{ a.is_default ? '（常态）' : '' }}
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Right panel: no scene selected -->
      <div v-else class="scene-detail-panel empty-detail">
        <div class="state-icon">👈</div>
        <p class="text-muted">从左侧选择一个分镜</p>
      </div>
    </div>

    <!-- == Lightbox == -->
    <div v-if="lightbox" class="lightbox-overlay" @click.self="closePreview">
      <button class="lightbox-close" @click="closePreview">✕</button>
      <button class="lightbox-nav lightbox-prev" @click="lightboxNav(-1)">‹</button>
      <div class="lightbox-body">
        <img :src="lightbox.src" class="lightbox-img" />
        <div class="lightbox-footer">{{ lightboxTitle }} · 第 {{ lightbox.slotIndex + 1 }} 张</div>
      </div>
      <button class="lightbox-nav lightbox-next" @click="lightboxNav(1)">›</button>
    </div>

    <!-- 轮 5: 参考图选择器 -->
    <ReferencePicker
      v-if="refPickerOpen"
      :project-id="projectId"
      @picked="onRefPicked"
      @close="refPickerOpen = false"
    />

    <!-- v1.4.6: 导入图片用的隐藏 file input + 剪裁对话框 -->
    <input ref="importFileInput" type="file" accept="image/*"
           style="display:none" @change="onFilePicked" />
    <ImageCropDialog v-if="cropOpen"
                     :src="cropSrc"
                     :target-w="imgWidth"
                     :target-h="imgHeight"
                     @cropped="onCropped"
                     @cancel="cancelCrop" />
    <!-- v1.4.12: Ideogram 4 提示词构建器（v1.4.13: 画布跟随设置尺寸 + AI 生成） -->
    <Ideogram4PromptBuilder v-if="ideogramBuilderOpen"
                            :initial-json="ideogramInitial"
                            :initial-w="imgWidth"
                            :initial-h="imgHeight"
                            :scene-hint="ideogramSceneHint"
                            :scene-characters="ideogramSceneChars"
                            @apply="onIdeogramApply"
                            @close="ideogramBuilderOpen = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, onActivated } from 'vue'
import axios from 'axios'
import ReferencePicker from '../ReferencePicker.vue'
import SdParamsPanel from '../SdParamsPanel.vue'
import ImageCropDialog from '../ImageCropDialog.vue'
import Ideogram4PromptBuilder from '../Ideogram4PromptBuilder.vue'
import { useRouter } from 'vue-router'

// v1.4.6: 导入图片 + 比例剪裁
const importFileInput = ref(null)
const cropOpen   = ref(false)
const cropSrc    = ref('')
let _importTarget = null   // { scene, frameType, slotIndex } — 选好图后写入这里
const router = useRouter()

function goSettings() {
  router.push('/settings?tab=image')
}

function triggerImport(scene, frameType) {
  // 自动写到该帧的下一个空槽（追加在末尾）
  const slotIndex = getFrameSlotCount(scene.id, frameType)
  _importTarget = { sceneId: scene.id, frameType, slotIndex }
  importFileInput.value?.click()
}

function onFilePicked(ev) {
  const f = ev.target.files?.[0]
  ev.target.value = ''
  if (!f) return
  const reader = new FileReader()
  reader.onload = () => {
    cropSrc.value = String(reader.result || '')
    cropOpen.value = true
  }
  reader.onerror = () => alert('图片读取失败')
  reader.readAsDataURL(f)
}

function cancelCrop() {
  cropOpen.value = false
  cropSrc.value  = ''
  _importTarget  = null
}

async function onCropped({ base64, dataUrl }) {
  if (!_importTarget) return
  const { sceneId, frameType, slotIndex } = _importTarget
  // 写入 slotImages + 落盘
  const key = slotKey(sceneId, frameType, slotIndex)
  slotImages.value[key] = dataUrl
  // 扩槽 + 自动选中
  setFrameSlotCount(sceneId, frameType, slotIndex + 1)
  const scene = scenes.value.find(s => s.id === sceneId)
  if (scene) {
    if (frameType === 'start')   scene._selected_start = slotIndex
    else if (frameType === 'bg') scene._selected_bg    = slotIndex
    else                          scene._selected_end   = slotIndex
  }
  // PUT 到后端落盘
  try {
    await axios.put(API + '/projects/' + props.projectId + '/images/slot', {
      scene_id:   sceneId,
      frame_type: frameType,
      slot_index: slotIndex,
      data:       base64,
    })
    emit('dirty')
    // 同时 update images/metadata 让 counts 持久化
    await saveImages()
  } catch (e) {
    alert('保存失败: ' + (e.message || e))
  } finally {
    cropOpen.value = false
    cropSrc.value  = ''
    _importTarget  = null
  }
}

const props = defineProps({ projectId: String })
const emit = defineEmits(['dirty', 'saved'])

const API = 'http://localhost:18520/api'

const scenes          = ref([])
const loadingScenes   = ref(false)
const loadError       = ref('')
const workflows       = ref([])
const selectedWorkflow = ref('')
const genCount        = ref(3)
const imgWidth        = ref(1920)
const imgHeight       = ref(1080)

// v1.5.1: 槽位按图片宽高比显示（竖幅自动变高窄，看清整张内容）
const slotVars = computed(() => {
  const w = imgWidth.value || 1, h = imgHeight.value || 1
  const r = w / h
  if (r >= 1) {                       // 横 / 方：宽固定 192
    return { '--slot-w': '192px', '--slot-h': Math.round(192 / r) + 'px' }
  }
  const sh = 240                       // 竖：高固定 240，给足高度
  return { '--slot-w': Math.round(sh * r) + 'px', '--slot-h': sh + 'px' }
})

const characters      = ref([])   // from /characters endpoint
const manuscript      = ref('')   // for pronoun-aware LLM suggestions
const suggestingChars = ref(false)

// Returns the best available full text for a scene:
// pure-reading scenes may have description truncated in old data — fall back to dialogue text.
function sceneFullText(scene) {
  if (!scene) return '(无描述)'
  const desc = scene.description || ''
  // If dialogues exist and description looks like a truncated label (ends with … or very short),
  // prefer the first dialogue's full text.
  const firstDialogue = (scene.dialogues || [])[0]?.text || ''
  if (firstDialogue && (desc.endsWith('…') || desc.length < firstDialogue.length)) {
    return firstDialogue
  }
  return desc || '(无描述)'
}

function toggleSceneChar(scene, charName) {
  const current = scene._scene_characters || []
  scene._scene_characters = current.includes(charName)
    ? current.filter(n => n !== charName)
    : [...current, charName]
  emit('dirty')
}

// ── v1.6.3: 每分镜每角色「外观」选择 ──────────────────────────────────────────────
function _charByName(name) { return (characters.value || []).find(c => c.name === name) }
function _appsOf(c) { return (c && Array.isArray(c.appearances) && c.appearances.length) ? c.appearances : null }
function _defAppId(c) {
  const apps = _appsOf(c); if (!apps) return 'default'
  return (apps.find(a => a.is_default) || apps[0]).id
}
function sceneLook(scene, charName) {
  return (scene && scene._scene_character_looks && scene._scene_character_looks[charName]) || ''
}
function setSceneLook(scene, charName, appId) {
  if (!scene._scene_character_looks) scene._scene_character_looks = {}
  const def = _defAppId(_charByName(charName))
  if (!appId || appId === def) delete scene._scene_character_looks[charName]   // 默认不落键，保持精简
  else scene._scene_character_looks[charName] = appId
  emit('dirty')
  saveScenes()    // v1.6.3: 立即落盘（同 onRefPicked），否则切走再切回 onActivated 重拉会覆盖丢失
}
function effAppId(scene, charName) {
  const c = _charByName(charName)
  const apps = _appsOf(c)
  const sel = sceneLook(scene, charName)
  if (sel && apps && apps.some(a => a.id === sel)) return sel
  return _defAppId(c)
}
function appTextFor(c, appId) {
  const apps = _appsOf(c)
  if (apps) {
    const a = apps.find(x => x.id === appId) || apps.find(x => x.is_default) || apps[0]
    if (a) return (a.text || '').trim()
  }
  return (c?.appearance || '').trim()
}
// 该分镜该角色的有效外观文本
function sceneCharText(scene, c) { return appTextFor(c, effAppId(scene, c.name)) }
// 出镜且 >1 外观的角色（用于显示外观下拉）
function sceneCharsWithLooks(scene) {
  const names = scene?._scene_characters || []
  return (characters.value || []).filter(c => names.includes(c.name) && (_appsOf(c) || []).length > 1)
}
// 发给后端的角色对象：appearance 换成所选外观文本，并带 appearance_id
function sceneCharsForBackend(scene) {
  const names = scene?._scene_characters || []
  return (characters.value || []).filter(c => names.includes(c.name)).map(c => {
    const appId = effAppId(scene, c.name)
    return { name: c.name, role: c.role || '', traits: c.traits || '',
             appearance: appTextFor(c, appId), appearance_id: appId }
  })
}

async function suggestChars(scene) {
  if (!scene || suggestingChars.value) return
  suggestingChars.value = true
  try {
    const res = await axios.post(API + '/text-engine/suggest-scene-characters', {
      description: scene.description,
      dialogues:   scene.dialogues || [],
      all_names:   characters.value.map(c => c.name),
      manuscript:  manuscript.value,
    })
    scene._scene_characters = res.data.characters || []
    emit('dirty')
  } catch (e) {
    console.error('suggestChars failed', e)
  } finally {
    suggestingChars.value = false
  }
}

// ── Style consistency ────────────────────────────────────────────────────────
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
const stylePreset     = ref('')
const customStyleText = ref('')
const effectiveStyle  = computed(() =>
  stylePreset.value === '__custom__' ? customStyleText.value.trim() : stylePreset.value
)

const activeSceneId = ref(null)
const activeScene   = computed(() => scenes.value.find(s => s.id === activeSceneId.value) ?? null)
const regenPromptingId = ref('')   // "{sceneId}:start" or "{sceneId}:end" while regenerating prompt only

// 轮 5: 工作流类型检测（决定是否需要参考图）
const workflowKind = ref('t2i')      // 't2i' | 'i2i_single' | 'i2i_double' | 'video'
const workflowRefCount = ref(0)
// v1.4.3: i2i_multi 支持任意张参考图（>=3）
const isI2I = computed(() => /^i2i_(single|double|multi)$/.test(workflowKind.value))

// v1.4.4: SD 工作流（sd_default_workflow）专用高级参数
const isSdWorkflow = computed(() => selectedWorkflow.value === 'sd_default_workflow')

// v1.4.12: Ideogram 4 工作流 → 显示 JSON 提示词构建器入口
const isIdeogram = computed(() => selectedWorkflow.value === 'image_ideogram4_t2i')
const ideogramBuilderOpen = ref(false)
const ideogramInitial = ref('')
const ideogramSceneHint = ref('')    // v1.4.13: AI 生成的默认描述
const ideogramSceneChars = ref([])   // v1.4.13: 出镜角色卡（带 appearance）
let _ideogramTarget = null   // { scene, frameType }

function openIdeogramBuilder(scene, frameType) {
  _ideogramTarget = { scene, frameType }
  const cur = frameType === 'start' ? scene.start_frame_prompt : scene.end_frame_prompt
  ideogramInitial.value = (cur || '').trim()
  // v1.4.13: AI 生成上下文 —— 分镜描述 + 该镜出镜角色（hydrate 成完整对象）
  ideogramSceneHint.value = scene.description || ''
  const names = scene._scene_characters || []
  ideogramSceneChars.value = names.length
    ? sceneCharsForBackend(scene)        // v1.6.3: 带该分镜所选外观文本
    : []
  ideogramBuilderOpen.value = true
}
function onIdeogramApply(jsonStr) {
  if (!_ideogramTarget) return
  onPromptInput(_ideogramTarget.scene, _ideogramTarget.frameType, jsonStr)
}
const sdParams = ref({
  checkpoint:   '',
  loras:        [],          // [{name, strength}]
  steps:        0,
  cfg:          0,
  sampler_name: '',
  scheduler:    '',
})
const sdNegativePrompt = ref('')   // SD 工作流的负面提示词（所有镜次共用）

async function loadWorkflowInfo() {
  workflowKind.value = 't2i'; workflowRefCount.value = 0
  if (!selectedWorkflow.value) return
  try {
    const r = await fetch(`${API}/image-engine/workflow-info?workflow_name=${encodeURIComponent(selectedWorkflow.value)}`)
    if (r.ok) {
      const d = await r.json()
      workflowKind.value = d.kind || 't2i'
      workflowRefCount.value = d.ref_count || 0
    }
  } catch {}
}
watch(selectedWorkflow, () => loadWorkflowInfo(), { immediate: false })

// 轮 5: 参考图选择器状态
const refPickerOpen = ref(false)
const refPickerCtx  = ref(null)   // { sceneId, frameType, refIndex }

function openRefPicker(scene, frameType, refIndex) {
  refPickerCtx.value = { sceneId: scene.id, frameType, refIndex }
  refPickerOpen.value = true
}
function onRefPicked(ref) {
  const ctx = refPickerCtx.value
  refPickerOpen.value = false
  if (!ctx || !ref) return
  const scene = scenes.value.find(s => s.id === ctx.sceneId)
  if (!scene) return
  if (!scene._frame_refs) scene._frame_refs = { start: [], end: [] }
  if (!scene._frame_refs[ctx.frameType]) scene._frame_refs[ctx.frameType] = []
  const arr = scene._frame_refs[ctx.frameType].slice()
  while (arr.length <= ctx.refIndex) arr.push(null)
  arr[ctx.refIndex] = ref
  scene._frame_refs[ctx.frameType] = arr.slice(0, workflowRefCount.value)
  emit('dirty')
  saveScenes()
}
function clearRef(scene, frameType, refIndex) {
  if (!scene._frame_refs?.[frameType]) return
  const arr = scene._frame_refs[frameType].slice()
  arr[refIndex] = null
  scene._frame_refs[frameType] = arr
  emit('dirty')
  saveScenes()
}
function getFrameRefs(scene, frameType) {
  const refs = scene._frame_refs?.[frameType] || []
  const cleaned = []
  for (let i = 0; i < workflowRefCount.value; i++) {
    const r = refs[i] || null
    // 剥掉前端 _preview_url/_label 等私有字段后才能发后端
    cleaned.push(r ? { kind: r.kind, project_id: r.project_id, char_name: r.char_name,
                       filename: r.filename, scope: r.scope, element_id: r.element_id } : null)
  }
  return cleaned
}
function getFrameRefsForBackend(scene, frameType) {
  return getFrameRefs(scene, frameType).filter(Boolean)
}
function refSlotPreview(scene, frameType, refIndex) {
  return scene._frame_refs?.[frameType]?.[refIndex] || null
}
watch(scenes, (list) => { if (list.length && !activeSceneId.value) activeSceneId.value = list[0].id }, { immediate: true })

// Persist selected workflow back to global settings whenever user changes it
let _workflowWatchInitialized = false
watch(selectedWorkflow, async (val) => {
  if (!_workflowWatchInitialized) { _workflowWatchInitialized = true; return }
  try {
    const res = await axios.get(API + '/settings')
    const s = res.data
    s.image_engine = { ...(s.image_engine || {}), default_workflow: val }
    await axios.post(API + '/settings', s)
  } catch {}
})

// Persist genCount, stylePreset, customStyleText
let _imgCfgWatchInitialized = false
watch([genCount, stylePreset, customStyleText], async ([count, preset, custom]) => {
  if (!_imgCfgWatchInitialized) { _imgCfgWatchInitialized = true; return }
  try {
    const res = await axios.get(API + '/settings')
    const s = res.data
    s.image_engine = {
      ...(s.image_engine || {}),
      default_gen_count: count,
      style_preset: preset,
      custom_style_text: custom,
    }
    await axios.post(API + '/settings', s)
  } catch {}
})

function hasAnyImage(scene) {
  for (const ft of ['start', 'end']) {
    const count = getFrameSlotCount(scene.id, ft)
    for (let s = 0; s < count; s++) {
      if (getImage(scene.id, ft, s)) return true
    }
  }
  return false
}

const running          = ref(false)
const paused           = ref(false)
const batchDone        = ref(false)
const batchCurrentIdx  = ref(-1)
const batchResumeFrom  = ref(0)

// A1: 上次批量失败的镜次 { "scene_id:frame_type": "<error msg>" }
const lastErrors      = ref({})
const lastErrorCount  = computed(() => Object.keys(lastErrors.value || {}).length)

async function reloadLastErrors() {
  if (!props.projectId) return
  try {
    const r = await fetch(`${API}/projects/${props.projectId}/last-run-errors`)
    if (!r.ok) return
    const d = await r.json()
    // 只关心 images stage 的失败镜
    lastErrors.value = (d.stage === 'images' ? d.errors : null) || {}
  } catch { lastErrors.value = {} }
}

async function dismissLastErrors() {
  lastErrors.value = {}
  try { await fetch(`${API}/projects/${props.projectId}/last-run-errors`, { method: 'DELETE' }) } catch {}
}

async function retryFailedBatch() {
  if (!Object.keys(lastErrors.value).length) return
  // key 格式："scene_id:frame_type"；提取唯一 scene_id 集合
  const failedSceneIds = new Set(
    Object.keys(lastErrors.value).map(k => k.split(':')[0])
  )
  const failedScenes = scenes.value.filter(s => failedSceneIds.has(s.id))
  if (!failedScenes.length) return

  // 按这些 scene 串行重新走 generateSceneSlots（最大限度复用现有逻辑）
  // skipExisting:false 让 start 和 end 都重做——简化逻辑，宁可多生成
  running.value = true; batchDone.value = false; paused.value = false
  batchCurrentIdx.value = -1
  slotError.value = {}; slotProgress.value = {}
  try {
    for (let i = 0; i < failedScenes.length; i++) {
      if (paused.value) break
      batchCurrentIdx.value = scenes.value.findIndex(s => s.id === failedScenes[i].id)
      try {
        await generateSceneSlots(failedScenes[i], { skipExisting: false })
      } catch (e) {
        if (!paused.value) { loadError.value = e.message; break }
      }
    }
  } finally {
    running.value = false; batchCurrentIdx.value = -1
    batchDone.value = true
    await saveImages()
    await reloadLastErrors()
  }
}
const sceneGenerating  = ref({})
const frameSlotCounts  = ref({})

// v1.6.1: 图片分镜人工审阅标记（纯展示，不影响任何生成机制；按项目 localStorage 持久化）
const imgReviewed = ref({})   // sceneId → bool
function _imgReviewedKey() { return `lumi_img_reviewed_${props.projectId || ''}` }
function _loadImgReviewed() {
  try {
    const raw = localStorage.getItem(_imgReviewedKey())
    imgReviewed.value = raw ? (JSON.parse(raw) || {}) : {}
  } catch { imgReviewed.value = {} }
}
function toggleImgReviewed(sceneId) {
  imgReviewed.value = { ...imgReviewed.value, [sceneId]: !imgReviewed.value[sceneId] }
  try { localStorage.setItem(_imgReviewedKey(), JSON.stringify(imgReviewed.value)) } catch {}
}

const lightbox = ref(null)
const lightboxTitle = computed(() => {
  if (!lightbox.value) return ''
  const s = scenes.value.find(x => x.id === lightbox.value.sceneId)
  const label = lightbox.value.frameType === 'start' ? '首帧' : '尾帧'
  return s ? ('分镜 ' + String(s.index).padStart(2,'0') + ' · ' + label) : label
})

const slotImages    = ref({})
const slotLoading   = ref({})
const slotError     = ref({})
const slotProgress  = ref({})

function getFrameSlotCount(sceneId, frameType) {
  // v1.4.3: 自动剪掉尾部空槽（如 stored=3 但只有 slot 0/1 有图，剪到 2）。
  // 仍保持 ≥ genCount.value 以便空网格有合理占位。
  // 中间被删的空槽（如 slot 1 是空、slot 2 有图）保留，避免位置错位。
  const stored = frameSlotCounts.value[sceneId + ':' + frameType]
  if (stored == null) return genCount.value
  let lastActive = -1
  for (let s = 0; s < stored; s++) {
    const k = slotKey(sceneId, frameType, s)
    if (slotImages.value[k] || slotLoading.value[k] || slotError.value[k]) {
      lastActive = s
    }
  }
  return Math.max(lastActive + 1, genCount.value)
}
function setFrameSlotCount(sceneId, frameType, n) {
  frameSlotCounts.value = { ...frameSlotCounts.value, [sceneId + ':' + frameType]: n }
}
function slotKey(sceneId, frameType, slot) {
  return sceneId + ':' + frameType + ':' + slot
}
function getImage(sceneId, frameType, slot) {
  return slotImages.value[slotKey(sceneId, frameType, slot)] || null
}
function isLoading(sceneId, frameType, slot) {
  return !!slotLoading.value[slotKey(sceneId, frameType, slot)]
}
function isErrored(sceneId, frameType, slot) {
  return !!slotError.value[slotKey(sceneId, frameType, slot)]
}
function getError(sceneId, frameType, slot) {
  return slotError.value[slotKey(sceneId, frameType, slot)] || ''
}
function getProgress(sceneId, frameType, slot) {
  return slotProgress.value[slotKey(sceneId, frameType, slot)] || ''
}

const totalCount = computed(() => scenes.value.length * 2 * genCount.value)
const completedCount = computed(() =>
  Object.values(slotImages.value).filter(Boolean).length +
  Object.values(slotError.value).filter(Boolean).length
)
const progressPct = computed(() =>
  totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0
)

async function loadData() {
  loadError.value = ''
  loadingScenes.value = true
  _loadImgReviewed()   // v1.6.1: 恢复图片分镜审阅标记
  try {
    const [scenesRes, settingsRes, workflowsRes, imagesRes, charsRes] = await Promise.all([
      axios.get(API + '/projects/' + props.projectId + '/scenes'),
      axios.get(API + '/settings'),
      axios.get(API + '/image-engine/workflows').catch(() => ({ data: [] })),
      axios.get(API + '/projects/' + props.projectId + '/images').catch(() => ({ data: { slots: [], counts: {}, selected: {} } })),
      axios.get(API + '/projects/' + props.projectId + '/characters').catch(() => ({ data: { characters: [] } })),
    ])
    scenes.value = ((scenesRes.data?.scenes) || []).map(s => ({
      ...s,
      bg_prompt:       s.bg_prompt        ?? '',
      _selected_start: s._selected_start ?? 0,
      _selected_end:   s._selected_end   ?? 0,
      _selected_bg:    s._selected_bg    ?? 0,
      _frame_refs:     s._frame_refs     ?? { start: [], end: [] },
    }))
    const imgCfg = settingsRes.data?.image_engine || {}
    genCount.value  = imgCfg.default_gen_count ?? 3
    imgWidth.value  = imgCfg.image_width  ?? 1920
    imgHeight.value = imgCfg.image_height ?? 1080
    if (imgCfg.default_workflow) {
      selectedWorkflow.value = imgCfg.default_workflow
      // 触发 workflow-info 加载（watch 在初始化前不会触发，主动调用一次）
      await loadWorkflowInfo()
    }
    if (imgCfg.style_preset !== undefined) stylePreset.value = imgCfg.style_preset
    if (imgCfg.custom_style_text !== undefined) customStyleText.value = imgCfg.custom_style_text
    workflows.value = workflowsRes.data || []
    characters.value = charsRes.data?.characters || []
    // load manuscript for pronoun-aware character suggestions
    try {
      const msRes = await axios.get(API + '/projects/' + props.projectId + '/manuscript')
      manuscript.value = msRes.data?.content || ''
    } catch {}
    const imgState = imagesRes.data
    const newSlotImages = {}
    for (const slot of imgState.slots || []) {
      if (slot.url) {
        newSlotImages[slotKey(slot.scene_id, slot.frame_type, slot.slot_index)] =
          'http://localhost:18520' + slot.url
      } else if (slot.data) {
        newSlotImages[slotKey(slot.scene_id, slot.frame_type, slot.slot_index)] =
          'data:image/png;base64,' + slot.data
      }
    }
    slotImages.value = newSlotImages
    frameSlotCounts.value = imgState.counts || {}
    const selectedMap = imgState.selected || {}
    for (const scene of scenes.value) {
      const ss = selectedMap[scene.id + ':start']
      const se = selectedMap[scene.id + ':end']
      const sb = selectedMap[scene.id + ':bg']
      if (ss !== undefined) scene._selected_start = ss
      if (se !== undefined) scene._selected_end = se
      if (sb !== undefined) scene._selected_bg = sb     // v1.6: 背景图选中
    }
  } catch (e) {
    loadError.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loadingScenes.value = false
  }
}

const _SLOT_PARALLEL = 10  // concurrent per-slot save requests

let _imgSaving = false
async function saveImages() {
  if (_imgSaving) return
  _imgSaving = true

  // Build a snapshot of all current slot keys + their data-urls (references, not copies)
  const entries = Object.entries(slotImages.value).filter(([, v]) => Boolean(v))

  const selected = {}
  for (const scene of scenes.value) {
    selected[scene.id + ':start'] = scene._selected_start ?? 0
    selected[scene.id + ':end']   = scene._selected_end   ?? 0
    selected[scene.id + ':bg']    = scene._selected_bg    ?? 0   // v1.6: 背景图
  }

  try {
    // Only upload entries that are freshly generated (base64 data URLs).
    // Entries loaded from disk are already URL strings — no need to re-upload them.
    const newEntries = entries.filter(([, v]) => v.startsWith('data:'))

    for (let i = 0; i < newEntries.length; i += _SLOT_PARALLEL) {
      const batch = newEntries.slice(i, i + _SLOT_PARALLEL)
      await Promise.all(batch.map(([key, dataUrl]) => {
        const [sceneId, frameType, slotIdx] = key.split(':')
        return axios.put(API + '/projects/' + props.projectId + '/images/slot', {
          scene_id:   sceneId,
          frame_type: frameType,
          slot_index: Number(slotIdx),
          data:       dataUrl.replace(/^data:image\/\w+;base64,/, ''),
        })
      }))
    }

    // Rebuild images.json with the complete slot manifest + counts/selected.
    // The backend verifies each file exists before including it.
    await axios.put(API + '/projects/' + props.projectId + '/images/metadata', {
      counts:    frameSlotCounts.value,
      selected,
      slot_keys: entries.map(([key]) => {
        const [sceneId, frameType, slotIdx] = key.split(':')
        return { scene_id: sceneId, frame_type: frameType, slot_index: Number(slotIdx) }
      }),
    })

    emit('saved')
  } catch (e) {
    console.error('Failed to save images:', e)
    alert('图片保存失败：' + (e?.response?.data?.detail || e.message || '未知错误'))
  } finally {
    _imgSaving = false
  }
}

function onKeyDown(e) {
  if (!lightbox.value) return
  if (e.key === 'Escape')      closePreview()
  if (e.key === 'ArrowLeft')   lightboxNav(-1)
  if (e.key === 'ArrowRight')  lightboxNav(1)
}
onMounted(() => {
  loadData()
  reloadLastErrors()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('lumi:save-project', _onGlobalSave)
})
// Re-fetch scenes when this tab is re-activated after being kept alive.
// Lightweight: only requests the scenes endpoint; preserves loaded images and selected state.
onActivated(async () => {
  if (running.value || paused.value) return
  try {
    const res = await axios.get(API + '/projects/' + props.projectId + '/scenes')
    const fresh = ((res.data?.scenes) || []).map(s => ({
      ...s,
      _selected_start: s._selected_start ?? 0,
      _selected_end:   s._selected_end   ?? 0,
    }))
    // Preserve in-memory image selection indices so thumbnails don't reset
    const oldMap = new Map(scenes.value.map(s => [s.id, s]))
    for (const ns of fresh) {
      const old = oldMap.get(ns.id)
      if (old) {
        ns._selected_start = old._selected_start ?? 0
        ns._selected_end   = old._selected_end   ?? 0
        // v1.6.3 防御：服务器快照若尚不含本地刚选的「本镜形象」，保留内存值，避免被旧快照覆盖
        if (old._scene_character_looks && !ns._scene_character_looks)
          ns._scene_character_looks = old._scene_character_looks
      }
    }
    scenes.value = fresh
  } catch {}
})
function _onGlobalSave(e) { if (e?.detail?.projectId && e.detail.projectId !== props.projectId) return; saveImages(); saveScenes() }
onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('lumi:save-project', _onGlobalSave)
  clearTimeout(_promptSaveTimer)
  saveScenes()
})

let currentReader = null

function handleSlotEvent(evt) {
  const { event, scene_id, frame_type, slot_index } = evt
  if (!scene_id) return
  const key = slotKey(scene_id, frame_type, slot_index)
  if (event === 'progress') {
    slotProgress.value[key] = evt.value + '/' + evt.max
  } else if (event === 'completed') {
    slotLoading.value[key]  = false
    slotProgress.value[key] = ''
    const first = (evt.images || [])[0]
    if (first?.data) slotImages.value[key] = 'data:image/png;base64,' + first.data
  } else if (event === 'error') {
    slotLoading.value[key] = false
    slotError.value[key]   = evt.message || '错误'
  }
}

async function generateSceneSlots(scene, { skipExisting = false } = {}) {
  let frames = []
  const _style = effectiveStyle.value

  // Build character appearance prefix for this scene's selected characters
  const selectedNames = scene._scene_characters || []
  const sceneChars = characters.value.filter(c =>
    selectedNames.length === 0 ? false : selectedNames.includes(c.name)
  )
  const charPrefix = sceneChars
    .map(c => sceneCharText(scene, c))     // v1.6.3: 该分镜所选外观的文本
    .filter(Boolean)
    .join(', ')

  const _buildPrompt = (rawPrompt) => {
    // v1.4.12: Ideogram 工作流提示词必须是纯 JSON caption —— 禁止前缀注入
    // 画风/角色 appearance（会破坏 JSON 格式）。画风/角色信息应在「🧩 构建器」
    // 的 AI 生成里融入 caption，而不是这里拼字符串。
    if (isIdeogram.value) return rawPrompt || ''
    const parts = []
    if (_style) parts.push(_style)
    if (charPrefix) parts.push(charPrefix)
    if (rawPrompt) parts.push(rawPrompt)
    return parts.join(', ')
  }

  if (scene.start_frame_prompt) {
    const f = { scene_id: scene.id, frame_type: 'start', prompt: _buildPrompt(scene.start_frame_prompt) }
    if (isI2I.value) f.refs = getFrameRefsForBackend(scene, 'start')
    frames.push(f)
  }
  if (scene.end_frame_prompt) {
    const f = { scene_id: scene.id, frame_type: 'end', prompt: _buildPrompt(scene.end_frame_prompt) }
    if (isI2I.value) f.refs = getFrameRefsForBackend(scene, 'end')
    frames.push(f)
  }
  if (!frames.length) return

  // v1.4.3: i2i 模式下至少要 1 张参考图（不再强制等于槽位数）；
  // 后端会自动把单张 ref 复制填满所有 LoadImage 槽（用作"单图编辑"语义），
  // 双图工作流照样可只用 1 张参考图驱动。
  if (isI2I.value) {
    for (const f of frames) {
      const got = (f.refs || []).length
      if (got < 1) {
        const which = f.frame_type === 'start' ? '首帧' : '尾帧'
        const msg = `${which} 至少需要 1 张参考图 — 请先在参考图槽位选择`
        alert(msg)
        throw new Error(msg)
      }
    }
  }

  if (skipExisting) {
    frames = frames.filter(f => {
      for (let s = 0; s < genCount.value; s++) {
        if (!slotImages.value[slotKey(f.scene_id, f.frame_type, s)]) return true
      }
      return false
    })
    if (!frames.length) return
  }

  for (const f of frames) {
    // When doing a full regeneration (not skipExisting), purge ALL old slot entries
    // including those beyond the new genCount (stale URLs from a previous higher-count run),
    // and reset the selection so the user sees the freshly generated slot 0.
    if (!skipExisting) {
      const prevCount = frameSlotCounts.value[f.scene_id + ':' + f.frame_type] ?? 0
      const imgs = { ...slotImages.value }
      for (let s = 0; s < prevCount; s++) delete imgs[slotKey(f.scene_id, f.frame_type, s)]
      slotImages.value = imgs
      const scene = scenes.value.find(sc => sc.id === f.scene_id)
      if (scene) {
        if (f.frame_type === 'start') scene._selected_start = 0
        else                          scene._selected_end   = 0
      }
    }
    setFrameSlotCount(f.scene_id, f.frame_type, genCount.value)
    for (let s = 0; s < genCount.value; s++) {
      const key = slotKey(f.scene_id, f.frame_type, s)
      slotLoading.value[key]  = true
      slotImages.value[key]   = undefined
      slotError.value[key]    = ''
      slotProgress.value[key] = ''
    }
  }

  function markFramesError(msg) {
    for (const f of frames) {
      for (let s = 0; s < genCount.value; s++) {
        const key = slotKey(f.scene_id, f.frame_type, s)
        slotLoading.value[key] = false
        slotError.value[key]   = msg
      }
    }
  }

  let response
  try {
    response = await fetch(API + '/image-engine/generate-batch-stream', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name:   selectedWorkflow.value,
        gen_count:       genCount.value,
        negative_prompt: isSdWorkflow.value ? sdNegativePrompt.value : '',
        width:           imgWidth.value,
        height:          imgHeight.value,
        frames,
        project_id:      props.projectId,   // A1: 让后端持久化失败镜次
        ...(isSdWorkflow.value ? { sd_params: sdParams.value } : {}),
      })
    })
  } catch (e) {
    const msg = '网络错误: ' + e.message
    markFramesError(msg)
    throw new Error(msg)
  }

  if (!response.ok) {
    let detail = 'HTTP ' + response.status
    try { const j = await response.json(); detail = j.detail || detail } catch {}
    markFramesError(detail)
    throw new Error(detail)
  }

  await new Promise((resolve) => {
    ;(async () => {
      const reader  = response.body.getReader()
      currentReader = reader
      const decoder = new TextDecoder()
      let buffer = ''
      try {
        while (true) {
          let result
          try { result = await reader.read() } catch { break }
          const { done, value } = result
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const raw = line.slice(6).trim()
            if (raw === '[DONE]') { resolve(); return }
            try { handleSlotEvent(JSON.parse(raw)) } catch {}
          }
        }
      } finally {
        for (const f of frames) {
          for (let s = 0; s < genCount.value; s++) {
            const key = slotKey(f.scene_id, f.frame_type, s)
            if (slotLoading.value[key]) slotLoading.value[key] = false
          }
        }
        currentReader = null
        resolve()
      }
    })()
  })
}

async function _runBatchFrom(fromIdx) {
  running.value         = true
  paused.value          = false
  batchCurrentIdx.value = -1
  for (let i = fromIdx; i < scenes.value.length; i++) {
    if (paused.value) { batchResumeFrom.value = i; break }
    batchCurrentIdx.value = i
    batchResumeFrom.value = i
    try {
      await generateSceneSlots(scenes.value[i], { skipExisting: true })
    } catch (e) {
      if (!paused.value) { loadError.value = e.message; batchResumeFrom.value = i; paused.value = true }
      break
    }
    if (paused.value) { batchResumeFrom.value = i; break }
  }
  running.value         = false
  batchCurrentIdx.value = -1
  if (!paused.value) {
    batchDone.value = true
    await saveImages()   // auto-save on batch complete; emits 'saved' on success
    await reloadLastErrors()   // A1: 后端在 batch_done 时已写盘，前端拉一次更新红色横幅
  } else {
    emit('dirty')        // paused: mark dirty so user can manually save later
  }
}

function startBatch() {
  slotError.value = {}; slotProgress.value = {}
  slotLoading.value = {}
  batchDone.value = false; batchResumeFrom.value = 0
  _runBatchFrom(0)
}
function pauseBatch()  { paused.value = true; currentReader?.cancel() }
function resumeBatch() { batchDone.value = false; _runBatchFrom(batchResumeFrom.value) }
function cancelBatch() {
  paused.value = false; running.value = false; batchDone.value = false
  batchCurrentIdx.value = -1; currentReader?.cancel(); currentReader = null
}

async function generateOneScene(scene) {
  if (running.value || sceneGenerating.value[scene.id]) return
  sceneGenerating.value = { ...sceneGenerating.value, [scene.id]: true }
  try {
    await generateSceneSlots(scene)
    await saveImages()   // auto-save after single-scene generation
  } finally {
    const next = { ...sceneGenerating.value }
    delete next[scene.id]
    sceneGenerating.value = next
  }
}

// v1.6: 统一取原始提示词 + 构建最终提示词（含 bg 无角色背景图分支）
function _rawFramePrompt(scene, frameType) {
  if (frameType === 'start') return scene.start_frame_prompt
  if (frameType === 'bg')    return scene.bg_prompt
  return scene.end_frame_prompt
}
function _buildFramePrompt(scene, frameType, rawPrompt) {
  if (isIdeogram.value) return rawPrompt || ''   // Ideogram 送纯 JSON
  if (frameType === 'bg') {
    // 背景图：不拼角色外观，强调空场景无人物
    return [effectiveStyle.value, rawPrompt,
      'empty scene, environment only, no people, no characters, no person'
    ].filter(Boolean).join(', ')
  }
  const selectedNames = scene._scene_characters || []
  const charPrefix = characters.value
    .filter(c => selectedNames.includes(c.name))
    .map(c => sceneCharText(scene, c))     // v1.6.3: 该分镜所选外观
    .filter(Boolean).join(', ')
  return [effectiveStyle.value, charPrefix, rawPrompt].filter(Boolean).join(', ')
}

async function regenFrame(scene, frameType) {
  const rawPrompt = _rawFramePrompt(scene, frameType)
  if (!rawPrompt || !selectedWorkflow.value) return
  const prompt = _buildFramePrompt(scene, frameType, rawPrompt)
  setFrameSlotCount(scene.id, frameType, genCount.value)
  for (let s = 0; s < genCount.value; s++) {
    const key = slotKey(scene.id, frameType, s)
    slotLoading.value[key] = true; slotImages.value[key] = undefined
    slotError.value[key] = ''; slotProgress.value[key] = ''
  }
  const promises = Array.from({ length: genCount.value }, (_, s) =>
    runSingleSlot(scene.id, frameType, s, prompt)
  )
  await Promise.allSettled(promises)
  emit('dirty')
}

// ── v1.6: 批量【全部分镜】背景图（无角色）提示词 + 图片 ────────────────────────
const bgPromptRunning  = ref(false)
const bgPromptProgress = ref(0)
const bgImageRunning   = ref(false)
const bgImageProgress  = ref(0)
const bgImageTotal     = ref(0)

// 为全部分镜批量生成无角色背景提示词（复用 batch 端点，characters:[] → 纯环境；
// 取 start_frame_prompt 作为 bg_prompt，与单镜「✦ 提示词」一致）。跳过已有 bg_prompt。
async function genAllBgPrompts() {
  if (bgPromptRunning.value || !scenes.value.length) return
  const targets = scenes.value.filter(s => !(s.bg_prompt || '').trim())
  if (!targets.length) {
    alert('全部分镜都已有背景提示词（如需重写，请清空对应分镜的背景提示词后再试）')
    return
  }
  bgPromptRunning.value = true
  bgPromptProgress.value = scenes.value.length - targets.length   // 已有的算作完成
  const sceneIdxById = {}
  scenes.value.forEach((s, i) => { sceneIdxById[String(s.id)] = i })
  try {
    // v1.6: 走【专用无角色背景端点】—— 强约束只描述空场景、彻底排除人物
    const resp = await fetch(`${API}/text-engine/generate-bg-prompts-batch`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        scenes: targets.map(s => ({
          scene_id:    String(s.id),
          description: s.description,
          scene_index: s.index,
        })),
        manuscript:   manuscript.value,
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
        if (raw === '[DONE]') break
        try {
          const ev = JSON.parse(raw)
          if (ev.event === 'result' && ev.scene_id != null) {
            const i = sceneIdxById[String(ev.scene_id)]
            if (i != null && ev.bg_prompt) {
              scenes.value[i].bg_prompt = ev.bg_prompt
            }
            bgPromptProgress.value++
            emit('dirty')
          } else if (ev.event === 'item_error') {
            bgPromptProgress.value++
          }
        } catch {}
      }
    }
    // bg_prompt 是 scene 字段 → 必须 saveScenes 才落盘（saveImages 不含 scene 提示词）；
    // 否则切走再切回 Images 页（onActivated 重拉 /scenes）会把刚生成的 bg_prompt 覆盖丢失。
    await saveScenes()
  } catch (e) {
    if (e.name !== 'AbortError') loadError.value = e.message || '批量背景提示词失败'
  } finally {
    bgPromptRunning.value = false
  }
}

// 为全部分镜批量生成背景图：只对【已有 bg_prompt】的分镜出图，跳过已出图的分镜。
async function genAllBgImages() {
  if (bgImageRunning.value || !selectedWorkflow.value) return
  const _hasBgImg = (sid) => {
    for (let s = 0; s < getFrameSlotCount(sid, 'bg'); s++) {
      if (getImage(sid, 'bg', s)) return true
    }
    return false
  }
  const targets = scenes.value.filter(s => (s.bg_prompt || '').trim() && !_hasBgImg(s.id))
  if (!targets.length) {
    alert('没有需要生成的背景图（仅对【有背景提示词且尚未出图】的分镜生效；可先点「✦ 全部分镜提示词」）')
    return
  }
  bgImageRunning.value = true
  bgImageTotal.value = targets.length
  bgImageProgress.value = 0
  try {
    for (const scene of targets) {
      const prompt = _buildFramePrompt(scene, 'bg', _rawFramePrompt(scene, 'bg'))
      setFrameSlotCount(scene.id, 'bg', genCount.value)
      for (let s = 0; s < genCount.value; s++) {
        const key = slotKey(scene.id, 'bg', s)
        slotLoading.value[key] = true; slotImages.value[key] = undefined
        slotError.value[key] = ''; slotProgress.value[key] = ''
      }
      const promises = Array.from({ length: genCount.value }, (_, s) =>
        runSingleSlot(scene.id, 'bg', s, prompt)
      )
      await Promise.allSettled(promises)
      bgImageProgress.value++
      emit('dirty')
    }
    await saveImages()
  } catch (e) {
    loadError.value = e.message || '批量背景图失败'
  } finally {
    bgImageRunning.value = false
  }
}

// ── Prompt editing: linked with ScenesTab via shared /scenes endpoint ─────────
let _promptSaveTimer = null
function onPromptInput(scene, frameType, value) {
  if (frameType === 'start')   scene.start_frame_prompt = value
  else if (frameType === 'bg') scene.bg_prompt          = value
  else                          scene.end_frame_prompt   = value
  emit('dirty')
  clearTimeout(_promptSaveTimer)
  _promptSaveTimer = setTimeout(() => saveScenes(), 800)
}

async function saveScenes() {
  try {
    const payload = scenes.value.map(s => {
      const { _selected_start, _selected_end, _scene_characters, _frame_refs, ...rest } = s
      return { ...rest, _selected_start, _selected_end, _scene_characters, _frame_refs }
    })
    await axios.put(API + '/projects/' + props.projectId + '/scenes', { scenes: payload })
  } catch {}
}

async function regenPromptOnly(scene, frameType) {
  const key = scene.id + ':' + frameType
  if (regenPromptingId.value === key) return
  regenPromptingId.value = key
  try {
    const isBg = frameType === 'bg'
    const chars = isBg ? [] : sceneCharsForBackend(scene)   // v1.6.3: 带所选外观文本 + appearance_id

    // v1.6: 背景图走【专用无角色端点】—— LLM 被强约束只描述空场景、彻底排除人物
    if (isBg) {
      const res = await fetch(API + '/text-engine/generate-bg-prompt', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description:  scene.description,
          manuscript:   manuscript.value,
          scene_index:  scene.index,
          total_scenes: scenes.value.length,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      if (data.prompt) { scene.bg_prompt = data.prompt; emit('dirty'); saveScenes() }
      return
    }

    // 轮 6: i2i 工作流走专门的 img2img 提示词端点（要求至少有 refs）
    let endpoint, body
    if (isI2I.value && !isBg) {
      const refs = getFrameRefsForBackend(scene, frameType)
      if (!refs.length) {
        alert('图生图工作流需要先选择参考图，才能生成对应的提示词')
        return
      }
      endpoint = API + '/text-engine/generate-img2img-prompt'
      body = {
        description:   scene.description,
        dialogues:     scene.dialogues || [],
        characters:    chars,
        refs,
        workflow_kind: workflowKind.value,
        project_id:    props.projectId,
        manuscript:    manuscript.value,
        scene_index:   scene.index,
        total_scenes:  scenes.value.length,
      }
    } else {
      endpoint = API + '/text-engine/generate-frame-prompts'
      body = {
        description:  scene.description,
        dialogues:    scene.dialogues || [],
        characters:   chars,
        manuscript:   manuscript.value,
        scene_index:  scene.index,
        total_scenes: scenes.value.length,
      }
    }

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    if (frameType === 'start' && data.start_frame_prompt) {
      scene.start_frame_prompt = data.start_frame_prompt
    } else if (frameType === 'end' && data.end_frame_prompt) {
      scene.end_frame_prompt = data.end_frame_prompt
    }
    emit('dirty')
    saveScenes()
  } catch (e) {
    alert('提示词生成失败：' + e.message)
  } finally {
    regenPromptingId.value = ''
  }
}

async function runSingleSlot(sceneId, frameType, slotIndex, prompt) {
  const key = slotKey(sceneId, frameType, slotIndex)
  // v1.4.3: 单 slot 重生也带 refs；i2i 模式只要 ≥ 1 张就放行（后端会复制填满槽位）
  let refs = []
  if (isI2I.value) {
    const sc = scenes.value.find(s => s.id === sceneId)
    if (sc) refs = getFrameRefsForBackend(sc, frameType)
    if (refs.length < 1) {
      slotError.value[key] = '至少需要 1 张参考图'
      slotLoading.value[key] = false
      return
    }
  }
  try {
    const response = await fetch(API + '/image-engine/generate-stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflow_name: selectedWorkflow.value, positive_prompt: prompt,
        negative_prompt: isSdWorkflow.value ? sdNegativePrompt.value : '',
        width: imgWidth.value, height: imgHeight.value,
        scene_id: sceneId, frame_type: frameType, slot_index: slotIndex,
        refs,
        ...(isSdWorkflow.value ? { sd_params: sdParams.value } : {}),
      })
    })
    const reader = response.body.getReader()
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
        try { handleSlotEvent(JSON.parse(raw)) } catch {}
      }
    }
  } catch (e) {
    slotError.value[key] = e.message; slotLoading.value[key] = false
  }
}

function selectImage(scene, frameType, slotIndex) {
  if (!getImage(scene.id, frameType, slotIndex)) return
  if (frameType === 'start')   scene._selected_start = slotIndex
  else if (frameType === 'bg') scene._selected_bg    = slotIndex
  else                          scene._selected_end   = slotIndex
  emit('dirty')
}

function openPreview(scene, frameType, slotIndex) {
  const src = getImage(scene.id, frameType, slotIndex)
  if (!src) return
  lightbox.value = { src, sceneId: scene.id, frameType, slotIndex }
}
function closePreview() { lightbox.value = null }
function lightboxNav(dir) {
  if (!lightbox.value) return
  const { sceneId, frameType, slotIndex } = lightbox.value
  const count = getFrameSlotCount(sceneId, frameType)
  let next = (slotIndex + dir + count) % count
  for (let i = 0; i < count; i++) {
    const img = getImage(sceneId, frameType, next)
    if (img) { lightbox.value = { ...lightbox.value, src: img, slotIndex: next }; return }
    next = (next + dir + count) % count
  }
}

function deleteSlot(scene, frameType, slotIndex) {
  const count = getFrameSlotCount(scene.id, frameType)
  // Guard: if any slot for this frame is still loading, deleting would shift
  // the slot indices and cause the in-flight SSE response to write to the wrong key.
  for (let s = 0; s < count; s++) {
    if (isLoading(scene.id, frameType, s)) return
  }
  for (let i = slotIndex; i < count - 1; i++) {
    const from = slotKey(scene.id, frameType, i + 1)
    const to   = slotKey(scene.id, frameType, i)
    slotImages.value[to] = slotImages.value[from]; slotError.value[to] = slotError.value[from]
    slotProgress.value[to] = slotProgress.value[from]; slotLoading.value[to] = slotLoading.value[from]
  }
  const lastKey = slotKey(scene.id, frameType, count - 1)
  const imgs = { ...slotImages.value }; delete imgs[lastKey]; slotImages.value = imgs
  const errs = { ...slotError.value };  delete errs[lastKey]; slotError.value  = errs
  const prgs = { ...slotProgress.value }; delete prgs[lastKey]; slotProgress.value = prgs
  const lds  = { ...slotLoading.value };  delete lds[lastKey];  slotLoading.value  = lds
  setFrameSlotCount(scene.id, frameType, Math.max(1, count - 1))
  const selKey = frameType === 'start' ? '_selected_start'
               : frameType === 'bg'    ? '_selected_bg'
               : '_selected_end'
  if (scene[selKey] >= count - 1) scene[selKey] = Math.max(0, count - 2)
  else if (scene[selKey] > slotIndex) scene[selKey]--
  if (lightbox.value?.sceneId === scene.id && lightbox.value?.frameType === frameType
      && lightbox.value?.slotIndex === slotIndex) closePreview()
  emit('dirty')
}

async function addOneMore(scene, frameType) {
  const rawPrompt = _rawFramePrompt(scene, frameType)
  if (!rawPrompt || !selectedWorkflow.value) return
  const prompt = _buildFramePrompt(scene, frameType, rawPrompt)
  const newSlot = getFrameSlotCount(scene.id, frameType)
  setFrameSlotCount(scene.id, frameType, newSlot + 1)
  const key = slotKey(scene.id, frameType, newSlot)
  slotLoading.value[key] = true; slotImages.value[key] = undefined
  slotError.value[key] = ''; slotProgress.value[key] = ''
  await runSingleSlot(scene.id, frameType, newSlot, prompt)
  emit('dirty')
}
</script>

<style scoped>
.images-tab {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.img-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar-left  { display: flex; align-items: center; gap: 10px; min-width: 0; flex-shrink: 1; }
.toolbar-left .scene-count { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* v1.4.5: 关闭 toolbar-right 的 wrap，让所有控件挤在一行。
   选择类控件允许收缩、按钮永远不收缩；总宽度真撑爆时由 toolbar 外层 wrap 而非 right 内部 wrap。 */
.toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; min-width: 0; }
.toolbar-title { font-weight: 700; font-size: 15px; margin: 0; flex-shrink: 0; white-space: nowrap; }
/* 工作流 / 模型下拉：收紧 min-width，允许进一步收缩 */
.select-compact {
  height: 32px; padding: 0 8px;
  min-width: 120px; max-width: 220px;
  font-size: 13px;
  flex: 0 1 auto; min-width: 0;
}
/* 工作流第一个下拉占用最宽（让用户看清模型名）—— 用 nth-of-type 锁定 */
.toolbar-right > .select-compact:first-child { flex: 1 1 180px; max-width: 240px; }
.gen-count-group { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.input-num { height: 32px; width: 52px; text-align: center; padding: 0 6px; font-size: 13px; }
/* 画风组：label + select 整体 flex-shrink 跟 select 一致；
   group 不收缩到比 select 还窄，避免 select 溢出"叠"到下一个控件上 */
.style-select-group {
  display: flex; align-items: center; gap: 6px;
  flex: 0 1 auto; flex-shrink: 1; min-width: 0;
}
.style-preset-select {
  /* 用专属类避免被通用 .select-compact 的 min-width 覆盖 */
  min-width: 92px !important;
  max-width: 150px !important;
  flex: 0 1 auto;
}
.style-custom-input { height: 32px; min-width: 120px; padding: 0 8px; font-size: 13px; flex-shrink: 1; }
/* 操作按钮（▶ 全部生成 / ⏸ 暂停 / ✕ 取消 等）始终不收缩、不换行 */
.toolbar-right .btn { flex-shrink: 0; white-space: nowrap; }
.batch-progress-bar-wrap {
  padding: 8px 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.last-errors-banner {
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:6px 16px; background:rgba(220,60,60,.08);
  border-bottom:1px solid rgba(220,60,60,.4); font-size:12px;
}
.last-errors-banner .last-errors-detail { width:100%; }
.last-errors-banner ul { margin:4px 0 0 18px; padding:0; font-size:11px; line-height:1.5; }
.last-errors-banner code { background:rgba(255,255,255,.08); padding:1px 4px; border-radius:3px; }
.batch-progress-label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.batch-progress-track { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.batch-progress-fill  { height: 100%; background: var(--accent); border-radius: 2px; transition: width .3s; }
.full-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
}
.state-icon { font-size: 40px; }
.images-main {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}
.scene-list-panel {
  width: 260px;
  min-width: 200px;
  max-width: 300px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
}
.scene-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background .12s;
  min-height: 56px;
}
.scene-list-item:hover         { background: var(--bg-input); }
.scene-list-item.active        { background: rgba(99,179,237,.12); }
.scene-list-item.batch-current { background: rgba(251,191,36,.08); }
.scene-list-thumbs { display: flex; flex-direction: column; gap: 2px; flex-shrink: 0; }
.mini-thumb {
  width: 40px; height: 28px; border-radius: 3px; overflow: hidden;
  background: var(--bg-input); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
}
.mini-thumb img { width: 100%; height: 100%; object-fit: cover; }
.mini-empty  { font-size: 9px; color: var(--text-muted); font-weight: 600; }
.mini-spinner { display: flex; align-items: center; justify-content: center; }
.spinner-xs  { width: 12px; height: 12px; border-width: 1.5px; }
.scene-list-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.scene-list-num  { font-size: 18px; font-weight: 800; color: var(--accent); line-height: 1; }
.scene-list-desc { font-size: 12px; color: var(--text); line-height: 1.3; }
.scene-list-status { font-size: 11px; }
.dot-active { color: #f6ad55; }
.dot-done   { color: #68d391; }
.scene-list-gen-btn {
  flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%;
  border: 1px solid var(--border); background: var(--bg-input);
  color: var(--text); font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .12s, color .12s;
}
.scene-list-gen-btn:hover:not(:disabled) { background: var(--accent); color: #fff; border-color: var(--accent); }
.scene-list-gen-btn:disabled { opacity: .4; cursor: not-allowed; }
.scene-detail-panel {
  flex: 1; overflow-y: auto; padding: 16px 20px;
  display: flex; flex-direction: column; gap: 16px; min-width: 0;
}
.scene-detail-panel.empty-detail {
  align-items: center; justify-content: center; color: var(--text-muted);
}

/* ── Character selector panel ── */
.char-select-panel {
  border: 1px solid var(--color-border, var(--border)); border-radius: var(--radius, 8px);
  padding: 10px 14px; flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;
}
.char-select-header {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.char-select-title { font-size: 13px; font-weight: 600; }
.char-select-hint  { font-size: 11px; flex: 1; }
.char-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.char-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 99px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--color-border, var(--border));
  background: var(--color-surface, var(--bg-input));
  transition: border-color .15s, background .15s; user-select: none;
}
.char-chip input { display: none; }
.char-chip:hover { border-color: var(--color-accent, var(--accent)); }
.char-chip.selected {
  border-color: var(--color-accent, var(--accent));
  background: rgba(99,179,237,.15);
  color: var(--color-accent, var(--accent)); font-weight: 600;
}
.char-select-fallback { font-size: 11px; margin: 0; }
/* v1.6.3: 每分镜每角色外观选择 */
.char-looks { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--color-border, var(--border)); display: flex; flex-direction: column; gap: 4px; }
.char-looks-title { font-size: 11px; }
.char-look-row { display: flex; align-items: center; gap: 8px; }
.char-look-name { font-size: 12px; min-width: 64px; flex-shrink: 0; }
.char-look-select { flex: 1; max-width: 280px; min-height: 30px; font-size: 13px; line-height: 1.5; padding: 3px 8px; }
.detail-header {
  display: flex; flex-direction: column; gap: 8px;
  padding: 10px 14px; background: var(--bg-input);
  border-radius: 8px; flex-shrink: 0;
}
.detail-header-top {
  display: flex; align-items: center; gap: 10px;
}
/* v1.6.1: 人工审阅开关 */
.review-toggle {
  flex-shrink:0; font-size:12px; padding:3px 10px; border-radius:12px; cursor:pointer;
  border:1px solid var(--border, #444); background:transparent; color:var(--text-muted, #999);
}
.review-toggle.reviewed { border-color:rgba(80,200,120,.6); color:#5bbf7b;
  background:rgba(80,200,120,.10); }
.detail-num  { font-size: 22px; font-weight: 800; color: var(--accent); min-width: 32px; flex-shrink: 0; }
.detail-desc-block {
  font-size: 13px; line-height: 1.6; color: var(--text-muted);
  white-space: pre-wrap; word-break: break-all;
  background: var(--bg-panel); border-radius: 6px;
  padding: 8px 10px; border: 1px solid var(--border);
}
.detail-frame-section {
  border: 1px solid var(--border); border-radius: 8px;
  overflow: hidden; flex-shrink: 0;
}
.detail-frame-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; background: var(--bg-input);
  border-bottom: 1px solid var(--border);
}
.frame-badge  { font-size: 11px; padding: 2px 7px; border-radius: 4px; font-weight: 600; flex-shrink: 0; }
.bg-batch-sep { width: 1px; align-self: stretch; margin: 2px 4px; background: var(--border); flex-shrink: 0; }
.badge-blue   { background: rgba(99,179,237,.15); color: #63b3ed; }
.badge-purple { background: rgba(183,148,244,.15); color: #b794f4; }
.frame-prompt { font-size: 12px; flex: 1; min-width: 0; }
.frame-prompt-edit {
  width: 100%; font-size: 12px; font-family: monospace; resize: vertical;
  border-radius: 0; border: none; border-bottom: 1px solid var(--border);
  background: var(--bg-panel); padding: 8px 12px; line-height: 1.5;
}
.image-slots { display: flex; gap: 12px; flex-wrap: wrap; padding: 12px; align-items: flex-start; }
.image-slot {
  /* v1.5.1: 槽位尺寸跟随图片宽高比（竖幅→高窄，横幅→宽矮），整张可见无需逐个点开 */
  width: var(--slot-w, 192px); height: var(--slot-h, 128px); border-radius: 6px;
  border: 2px solid var(--border); overflow: hidden; cursor: pointer;
  position: relative; background: var(--bg-input);
  transition: border-color .15s, box-shadow .15s;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.image-slot:hover  { border-color: var(--accent); }
.image-slot.selected { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(99,179,237,.35); }
.image-slot.loading  { cursor: default; }
.image-slot.errored  { border-color: var(--danger, #fc8181); cursor: default; }
.image-slot img      { width: 100%; height: 100%; object-fit: contain; }
.slot-loading { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.slot-progress-text { font-size: 11px; color: var(--text-muted); }
.slot-error { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px; }
.slot-err-msg { font-size: 10px; color: var(--danger, #fc8181); text-align: center; word-break: break-word; }
.slot-empty   { font-size: 24px; color: var(--border); user-select: none; }
.selected-badge {
  position: absolute; top: 4px; right: 4px;
  background: var(--accent); color: #fff; border-radius: 50%;
  width: 18px; height: 18px; font-size: 11px;
  display: flex; align-items: center; justify-content: center; font-weight: 700;
}
.slot-overlay {
  position: absolute; inset: 0; background: rgba(0,0,0,.55);
  display: flex; align-items: center; justify-content: center; gap: 8px;
  opacity: 0; transition: opacity .15s; border-radius: 4px; pointer-events: none;
}
.image-slot:hover .slot-overlay { opacity: 1; pointer-events: auto; }
/* v1.4.3: 空槽 / 错误槽的 overlay 透明度更低（只有删除按钮），避免遮挡 slot 编号 */
.slot-overlay-empty { background: rgba(0,0,0,.35); }

/* v1.4.6: 比例提醒 banner + 导入按钮 */
.ratio-info-banner {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 5px 12px;
  background: rgba(99,179,237,.06);
  border-bottom: 1px solid rgba(99,179,237,.2);
  font-size: 12px; color: var(--text-muted);
}
.ratio-info-banner code {
  background: var(--bg-input); padding: 1px 6px;
  border-radius: 3px; font-size: 11px; color: var(--text);
}
.ratio-info-banner a { color: #63b3ed; text-decoration: none; }
.ratio-info-banner a:hover { text-decoration: underline; }
.slot-import {
  /* v1.5.1: 尺寸继承 .image-slot 的 --slot-w/--slot-h（跟随图片宽高比，竖幅同步变高窄） */
  background: transparent;
  border: 2px dashed var(--border);
  color: var(--text-muted); font-size: 18px; cursor: pointer;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  transition: border-color .15s, color .15s;
}
.slot-import:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.slot-import:disabled { opacity: .4; cursor: not-allowed; }
.slot-overlay-btn {
  background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.35);
  color: #fff; border-radius: 4px; width: 32px; height: 32px; font-size: 15px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background .1s;
}
.slot-overlay-btn:hover  { background: rgba(255,255,255,.3); }
.slot-overlay-del:hover  { background: rgba(229,62,62,.7); }
.slot-add {
  background: transparent; border: 2px dashed var(--border);
  color: var(--text-muted); font-size: 28px; cursor: pointer;
  transition: border-color .15s, color .15s; flex-shrink: 0;
}
.slot-add:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.slot-add:disabled { opacity: .4; cursor: not-allowed; }
.spinner-sm { width: 20px; height: 20px; border-width: 2px; }
.truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.btn-xs { padding: 2px 6px; font-size: 12px; height: 24px; line-height: 1; }
.btn-warning { background: #d97706; color: #fff; border-color: #d97706; }
.btn-warning:hover { opacity: .85; }
.lightbox-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.88); display: flex; align-items: center; justify-content: center;
}
.lightbox-close {
  position: absolute; top: 16px; right: 20px;
  background: rgba(255,255,255,.12); border: none; color: #fff;
  font-size: 20px; width: 36px; height: 36px; border-radius: 50%;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.lightbox-close:hover { background: rgba(255,255,255,.25); }
.lightbox-nav {
  background: rgba(255,255,255,.1); border: none; color: #fff;
  font-size: 44px; line-height: 1; width: 52px; height: 80px;
  border-radius: 6px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; margin: 0 12px; transition: background .15s;
}
.lightbox-nav:hover { background: rgba(255,255,255,.2); }
.lightbox-body {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  max-width: calc(100vw - 160px); max-height: calc(100vh - 80px);
}
.lightbox-img {
  max-width: 100%; max-height: calc(100vh - 120px);
  object-fit: contain; border-radius: 6px; display: block;
}
.lightbox-footer { color: rgba(255,255,255,.6); font-size: 13px; }

/* 轮 5: i2i 参考图槽位 */
.ref-slots-row {
  display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap;
  padding: 10px 12px; background: rgba(99,179,237,.05);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.ref-slots-label { font-size: 12px; color: var(--text-muted); padding-top: 6px; flex-shrink: 0; }
.ref-slot {
  position: relative; width: 96px; height: 96px;
  border: 1px dashed var(--border); border-radius: 6px;
  background: var(--bg-input); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-direction: column; gap: 2px; overflow: hidden;
  transition: border-color .15s;
}
.ref-slot:hover { border-color: var(--accent); }
.ref-slot img { width: 100%; height: 100%; object-fit: cover; }
.ref-slot-empty { font-size: 11px; color: var(--text-muted); user-select: none; }
.ref-slot-clear {
  position: absolute; top: 2px; right: 2px;
  background: rgba(0,0,0,.6); color: #fff; border: none;
  width: 18px; height: 18px; border-radius: 50%;
  font-size: 10px; cursor: pointer; line-height: 1;
}
.ref-slot-clear:hover { background: rgba(229,62,62,.85); }
.ref-slot-label {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(0,0,0,.55); color: #fff;
  font-size: 10px; padding: 1px 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
</style>
