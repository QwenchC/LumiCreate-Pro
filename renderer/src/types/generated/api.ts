/* ──────────────────────────────────────────────────────────────────────
 *  AUTO-GENERATED — do not edit by hand.
 *  Source: backend/openapi.snapshot.json (or running backend if --live)
 *  Regenerate: cd renderer && npm run typegen[:live]
 * ──────────────────────────────────────────────────────────────────────
 */
/* eslint-disable */
export type paths = {
    "/api/settings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Settings */
        get: operations["get_settings_api_settings_get"];
        put?: never;
        /** Update Settings */
        post: operations["update_settings_api_settings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Projects */
        get: operations["list_projects_api_projects_get"];
        put?: never;
        /** Create Project */
        post: operations["create_project_api_projects_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Project */
        get: operations["get_project_api_projects__project_id__get"];
        /** Update Project */
        put: operations["update_project_api_projects__project_id__put"];
        post?: never;
        /** Delete Project */
        delete: operations["delete_project_api_projects__project_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/copy-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Copy Config From Project
         * @description Copy manuscript_config.json and characters.json from source to target project.
         */
        post: operations["copy_config_from_project_api_projects__project_id__copy_config_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/assets/file/{scene_id}/{asset_type}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Asset File */
        get: operations["get_asset_file_api_projects__project_id__assets_file__scene_id___asset_type__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/assets/file/{scene_id}/{asset_type}/{slot_index}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Asset File Slot */
        get: operations["get_asset_file_slot_api_projects__project_id__assets_file__scene_id___asset_type___slot_index__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Assets
         * @description 列出某项目（或某镜）的所有资产 — 用于前端 URL 寻址，避免 base64。
         */
        get: operations["list_assets_api_projects__project_id__assets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project Events
         * @description E1: 查项目的事件流。可按 trace_id / task_id / scene_id / level 过滤。
         *     用于"任务回放"——选一次任务的 trace_id 就能看到完整时间线。
         */
        get: operations["get_project_events_api_projects__project_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/traces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Recent Traces */
        get: operations["list_recent_traces_api_projects__project_id__traces_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project Status
         * @description A1: 返回项目级状态机视图（项目阶段 + scene 计数 + 资产计数）。
         */
        get: operations["get_project_status_api_projects__project_id__status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/manuscript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Manuscript */
        get: operations["get_manuscript_api_projects__project_id__manuscript_get"];
        /** Save Manuscript */
        put: operations["save_manuscript_api_projects__project_id__manuscript_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Load Images */
        get: operations["load_images_api_projects__project_id__images_get"];
        /** Save Images */
        put: operations["save_images_api_projects__project_id__images_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/images/file/{filename}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Serve Image File
         * @description Serve a single PNG image file directly (avoids large base64 JSON payloads).
         */
        get: operations["serve_image_file_api_projects__project_id__images_file__filename__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/images/slot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Save Image Slot
         * @description Save a single image slot file to disk + A2 双写到 scene_assets。
         */
        put: operations["save_image_slot_api_projects__project_id__images_slot_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/images/metadata": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Save Image Metadata
         * @description Rebuild images.json from the provided slot_keys list + save counts/selected.
         */
        put: operations["save_image_metadata_api_projects__project_id__images_metadata_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/scenes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Scenes */
        get: operations["get_scenes_api_projects__project_id__scenes_get"];
        /** Save Scenes */
        put: operations["save_scenes_api_projects__project_id__scenes_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/audio": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Audio */
        get: operations["get_audio_api_projects__project_id__audio_get"];
        /** Save Audio */
        put: operations["save_audio_api_projects__project_id__audio_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/audio/slot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Put Audio Slot */
        put: operations["put_audio_slot_api_projects__project_id__audio_slot_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/videos": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Load Videos */
        get: operations["load_videos_api_projects__project_id__videos_get"];
        /** Save Videos */
        put: operations["save_videos_api_projects__project_id__videos_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/videos/slot": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Put Video Slot */
        put: operations["put_video_slot_api_projects__project_id__videos_slot_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/video-prompts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Load Video Prompts */
        get: operations["load_video_prompts_api_projects__project_id__video_prompts_get"];
        /** Save Video Prompts */
        put: operations["save_video_prompts_api_projects__project_id__video_prompts_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/last-run-errors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Last Run Errors */
        get: operations["get_last_run_errors_api_projects__project_id__last_run_errors_get"];
        /** Put Last Run Errors */
        put: operations["put_last_run_errors_api_projects__project_id__last_run_errors_put"];
        post?: never;
        /** Clear Last Run Errors */
        delete: operations["clear_last_run_errors_api_projects__project_id__last_run_errors_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/projects/{project_id}/characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Characters */
        get: operations["get_characters_api_projects__project_id__characters_get"];
        /** Save Characters */
        put: operations["save_characters_api_projects__project_id__characters_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Test Connection */
        get: operations["test_connection_api_text_engine_test_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-manuscript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Manuscript */
        post: operations["generate_manuscript_api_text_engine_generate_manuscript_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-scenes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Scenes */
        post: operations["generate_scenes_api_text_engine_generate_scenes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-frame-prompts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Frame Prompts */
        post: operations["generate_frame_prompts_api_text_engine_generate_frame_prompts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-character-appearance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Character Appearance */
        post: operations["generate_character_appearance_api_text_engine_generate_character_appearance_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-character-profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Character Profile */
        post: operations["generate_character_profile_api_text_engine_generate_character_profile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/suggest-scene-characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Suggest Scene Characters */
        post: operations["suggest_scene_characters_api_text_engine_suggest_scene_characters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/text-engine/generate-video-prompt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Video Prompt */
        post: operations["generate_video_prompt_api_text_engine_generate_video_prompt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/precheck": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Precheck Workflow
         * @description 生成前校验工作流：ComfyUI 是否在线 + 节点 class_type 是否齐 + 资源引用统计。
         */
        get: operations["precheck_workflow_api_image_engine_precheck_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Test Connection */
        get: operations["test_connection_api_image_engine_test_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/workflows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workflows */
        get: operations["get_workflows_api_image_engine_workflows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/workflow/{workflow_name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workflow */
        get: operations["get_workflow_api_image_engine_workflow__workflow_name__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/workflow-meta/{workflow_name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Workflow Meta */
        get: operations["get_workflow_meta_api_image_engine_workflow_meta__workflow_name__get"];
        /** Put Workflow Meta */
        put: operations["put_workflow_meta_api_image_engine_workflow_meta__workflow_name__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/generate-stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Single Stream */
        post: operations["generate_single_stream_api_image_engine_generate_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/image-engine/generate-batch-stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Batch Stream
         * @description Launch len(frames) * gen_count concurrent generation tasks.
         *     Multiplex all events into one SSE stream.
         *
         *     Event types: queued | progress | completed | error | batch_done
         *     Each carries: scene_id, frame_type, slot_index
         *     completed carries: images = [{filename, data(base64), type}]
         */
        post: operations["generate_batch_stream_api_image_engine_generate_batch_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Test Connection
         * @description C2: 走统一 adapter，路由 engine_type 的分支逻辑收敛进 adapter factory。
         */
        get: operations["test_connection_api_audio_engine_test_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/voice-refs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Voice Refs */
        get: operations["get_voice_refs_api_audio_engine_voice_refs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/emotion-refs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Emotion Refs */
        get: operations["get_emotion_refs_api_audio_engine_emotion_refs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/generate-stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Single Stream */
        post: operations["generate_single_stream_api_audio_engine_generate_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/generate-batch-stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Batch Stream */
        post: operations["generate_batch_stream_api_audio_engine_generate_batch_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/stitch-scene": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Stitch Scene
         * @description Merge clips for one scene into a single WAV (with pre/post silence).
         */
        post: operations["stitch_scene_api_audio_engine_stitch_scene_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/ms-tts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ms Tts
         * @description Generate a single TTS clip with Microsoft Edge neural voices.
         *     Returns base64 MP3 by default; pass format="wav" for stitch-scene compatible WAV.
         */
        post: operations["ms_tts_api_audio_engine_ms_tts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/audio-engine/ms-tts/test-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ms Tts Test All
         * @description 逐一测试 Microsoft Edge neural voices；返回 {voice: ok/err}，
         *     并将通过的 voice 列表写入 settings.audio_engine.msedge_available_voices。
         */
        post: operations["ms_tts_test_all_api_audio_engine_ms_tts_test_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/precheck": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Precheck Video Workflow Endpoint */
        get: operations["precheck_video_workflow_endpoint_api_video_engine_precheck_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Test Connection */
        get: operations["test_connection_api_video_engine_test_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/workflows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Video Workflows */
        get: operations["get_video_workflows_api_video_engine_workflows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/generate-stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Generate Video Stream */
        post: operations["generate_video_stream_api_video_engine_generate_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/bgm/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Project Bgm
         * @description 返回 BGM 元信息：是否存在、文件名。
         */
        get: operations["get_project_bgm_api_video_engine_bgm__project_id__get"];
        /**
         * Upload Project Bgm
         * @description 上传 BGM。前端读取本地文件 → base64 → 此接口。
         */
        put: operations["upload_project_bgm_api_video_engine_bgm__project_id__put"];
        post?: never;
        /** Delete Project Bgm */
        delete: operations["delete_project_bgm_api_video_engine_bgm__project_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/video-engine/merge-project-video": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Merge Project Video
         * @description Concatenate all scene MP4 files in order into one final video using ffmpeg concat demuxer.
         */
        post: operations["merge_project_video_api_video_engine_merge_project_video_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subtitle-engine/status/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Subtitle Status */
        get: operations["subtitle_status_api_subtitle_engine_status__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subtitle-engine/script/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Script
         * @description Return subtitle script lines extracted from the project's scenes (dialogue / description).
         */
        get: operations["get_script_api_subtitle_engine_script__project_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subtitle-engine/preprocess-text": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preprocess Text Endpoint */
        post: operations["preprocess_text_endpoint_api_subtitle_engine_preprocess_text_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subtitle-engine/generate-srt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate Srt Endpoint
         * @description SSE stream: normalize video → extract audio → align → write SRT.
         */
        post: operations["generate_srt_endpoint_api_subtitle_engine_generate_srt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/subtitle-engine/embed": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Embed Subtitles Endpoint
         * @description Burn subtitles.srt into final_video.mp4 → final_video_subbed.mp4.
         */
        post: operations["embed_subtitles_endpoint_api_subtitle_engine_embed_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/orchestrator/generate-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Generate All
         * @description SSE：按顺序跑所有 stage。前端接事件流，实时显示进度。
         */
        post: operations["generate_all_api_orchestrator_generate_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Templates */
        get: operations["list_templates_api_templates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/templates/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Template */
        get: operations["get_template_api_templates__template_id__get"];
        put?: never;
        post?: never;
        /** Delete Template */
        delete: operations["delete_template_api_templates__template_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/templates/from-project": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create From Project */
        post: operations["create_from_project_api_templates_from_project_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/templates/{template_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Template */
        post: operations["apply_template_api_templates__template_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/templates/{template_id}/spawn-project": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Spawn Project From Template */
        post: operations["spawn_project_from_template_api_templates__template_id__spawn_project_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/logs/recent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Recent */
        get: operations["recent_api_logs_recent_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/logs/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Stream
         * @description SSE: 实时推送新日志行。
         */
        get: operations["stream_api_logs_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/logs/clear": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Clear */
        delete: operations["clear_api_logs_clear_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tasks */
        get: operations["list_tasks_api_tasks_get"];
        put?: never;
        /** Submit Task */
        post: operations["submit_task_api_tasks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Task */
        get: operations["get_task_api_tasks__task_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Task */
        post: operations["cancel_task_api_tasks__task_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/tasks/{task_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Stream Task Events
         * @description SSE：先回放历史事件（id > last_event_id），再实时推送新事件。
         *
         *     - 断网重连：前端 EventSource 自动带上 Last-Event-ID header → 服务端从那以后回放
         *     - 历史持久化在 SQLite events 表，任务结束后仍可看完整时间线
         */
        get: operations["stream_task_events_api_tasks__task_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/task-history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Records */
        get: operations["list_records_api_task_history_get"];
        put?: never;
        post?: never;
        /** Clear All */
        delete: operations["clear_all_api_task_history_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/task-history/stats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stats */
        get: operations["stats_api_task_history_stats_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
};
export type webhooks = Record<string, never>;
export type components = {
    schemas: {
        /** AppSettings */
        AppSettings: {
            /**
             * Projects Dir
             * @default C:\Users\LumiTree\LumiCreate-Projects
             */
            projects_dir: string;
            text_engine?: components["schemas"]["TextEngineConfig"];
            image_engine?: components["schemas"]["ImageEngineConfig"];
            audio_engine?: components["schemas"]["AudioEngineConfig"];
            video_engine?: components["schemas"]["VideoEngineConfig"];
        };
        /** ApplyTemplateRequest */
        ApplyTemplateRequest: {
            /** Project Id */
            project_id: string;
        };
        /** AudioEngineConfig */
        AudioEngineConfig: {
            /**
             * Engine Type
             * @default indextts
             * @enum {string}
             */
            engine_type: "gptsovits" | "indextts" | "msedge" | "manual";
            /**
             * Api Url
             * @default http://localhost:7860
             */
            api_url: string;
            /**
             * Default Gen Count
             * @default 3
             */
            default_gen_count: number;
            /**
             * Voice Ref Dir
             * @default
             */
            voice_ref_dir: string;
            /**
             * Emotion Ref Dir
             * @default
             */
            emotion_ref_dir: string;
            /**
             * Default Voice Ref
             * @default
             */
            default_voice_ref: string;
            /**
             * Default Emo Weight
             * @default 0.8
             */
            default_emo_weight: number;
            /**
             * Msedge Voice
             * @default zh-CN-XiaoxiaoNeural
             */
            msedge_voice: string;
            /**
             * Msedge Rate
             * @default +25%
             */
            msedge_rate: string;
            /** Msedge Available Voices */
            msedge_available_voices?: string[];
        };
        /** AudioSlotPayload */
        AudioSlotPayload: {
            /** Key */
            key: string;
            /** Entry */
            entry: {
                [key: string]: unknown;
            };
        };
        /** BatchDialogue */
        BatchDialogue: {
            /** Scene Id */
            scene_id: string;
            /** Dialogue Id */
            dialogue_id: string;
            /** Text */
            text: string;
            /** Voice Ref */
            voice_ref?: string | null;
            /** Emo Ref */
            emo_ref?: string | null;
            /**
             * Emo Weight
             * @default 0.8
             */
            emo_weight: number;
            /**
             * Lang
             * @default zh
             */
            lang: string;
            /** Speaker */
            speaker?: string | null;
            /** Msedge Voice */
            msedge_voice?: string | null;
            /** Msedge Rate */
            msedge_rate?: string | null;
        };
        /** CancelResponse */
        CancelResponse: {
            /** Ok */
            ok: boolean;
            /**
             * Message
             * @default
             */
            message: string;
        };
        /** CharactersData */
        CharactersData: {
            /** Characters */
            characters: unknown[];
        };
        /** CopyConfigRequest */
        CopyConfigRequest: {
            /** Source Project Id */
            source_project_id: string;
        };
        /** CreateProjectRequest */
        CreateProjectRequest: {
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Folder Id
             * @default default
             */
            folder_id: string;
        };
        /** CreateTemplateRequest */
        CreateTemplateRequest: {
            /** Project Id */
            project_id: string;
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Include Characters
             * @default true
             */
            include_characters: boolean;
        };
        /** EmbedRequest */
        EmbedRequest: {
            /** Project Id */
            project_id: string;
            /**
             * Font Name
             * @default 等线 Bold
             */
            font_name: string;
            /**
             * Font Size
             * @default 18
             */
            font_size: number;
            /**
             * Primary Colour
             * @default #FFFFFF
             */
            primary_colour: string;
            /**
             * Outline Colour
             * @default #000000
             */
            outline_colour: string;
            /**
             * Outline Width
             * @default 2
             */
            outline_width: number;
            /**
             * Shadow Depth
             * @default 0
             */
            shadow_depth: number;
            /**
             * Margin V
             * @default 30
             */
            margin_v: number;
            /**
             * Position
             * @default bottom
             */
            position: string;
            /**
             * Bold
             * @default true
             */
            bold: boolean;
            /**
             * Italic
             * @default false
             */
            italic: boolean;
        };
        /** GenerateCharacterAppearanceRequest */
        GenerateCharacterAppearanceRequest: {
            /**
             * Name
             * @default
             */
            name: string;
            /**
             * Role
             * @default
             */
            role: string;
            /**
             * Traits
             * @default
             */
            traits: string;
            /**
             * Existing
             * @default
             */
            existing: string;
        };
        /** GenerateCharacterProfileRequest */
        GenerateCharacterProfileRequest: {
            /**
             * Name
             * @default
             */
            name: string;
            /**
             * Manuscript
             * @default
             */
            manuscript: string;
            /**
             * Existing Role
             * @default
             */
            existing_role: string;
            /**
             * Existing Traits
             * @default
             */
            existing_traits: string;
        };
        /** GenerateFramePromptsRequest */
        GenerateFramePromptsRequest: {
            /** Description */
            description: string;
            /**
             * Dialogues
             * @default []
             */
            dialogues: unknown[];
            /**
             * Characters
             * @default []
             */
            characters: unknown[];
            /**
             * Manuscript
             * @default
             */
            manuscript: string;
            /**
             * Scene Index
             * @default 0
             */
            scene_index: number;
            /**
             * Total Scenes
             * @default 0
             */
            total_scenes: number;
        };
        /** GenerateManuscriptRequest */
        GenerateManuscriptRequest: {
            config: components["schemas"]["ManuscriptConfig"];
            /**
             * Existing Content
             * @default
             */
            existing_content: string;
        };
        /** GenerateScenesRequest */
        GenerateScenesRequest: {
            /** Manuscript */
            manuscript: string;
            /**
             * Dialogue Mode
             * @default mixed
             */
            dialogue_mode: string;
            /**
             * Characters
             * @default []
             */
            characters: unknown[];
            /**
             * Force Llm
             * @default false
             */
            force_llm: boolean;
        };
        /** GenerateSrtRequest */
        GenerateSrtRequest: {
            /** Project Id */
            project_id: string;
            /** Lines */
            lines: string[];
            /**
             * Fps
             * @default 24
             */
            fps: number;
            /**
             * Manual Advance
             * @default 0
             */
            manual_advance: number;
            /**
             * Model Name
             * @default base
             */
            model_name: string;
        };
        /** GenerateVideoPromptRequest */
        GenerateVideoPromptRequest: {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Dialogues
             * @default []
             */
            dialogues: unknown[];
            /**
             * Characters
             * @default []
             */
            characters: unknown[];
            /**
             * Start Frame Prompt
             * @default
             */
            start_frame_prompt: string;
            /**
             * End Frame Prompt
             * @default
             */
            end_frame_prompt: string;
            /**
             * Manuscript
             * @default
             */
            manuscript: string;
            /**
             * Scene Index
             * @default 0
             */
            scene_index: number;
            /**
             * Total Scenes
             * @default 0
             */
            total_scenes: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImageEngineConfig */
        ImageEngineConfig: {
            /**
             * Comfyui Url
             * @default http://localhost:8188
             */
            comfyui_url: string;
            /**
             * Workflow Dir
             * @default
             */
            workflow_dir: string;
            /**
             * Default Workflow
             * @default
             */
            default_workflow: string;
            /**
             * Default Gen Count
             * @default 3
             */
            default_gen_count: number;
            /**
             * Image Width
             * @default 1920
             */
            image_width: number;
            /**
             * Image Height
             * @default 1080
             */
            image_height: number;
            /**
             * Style Preset
             * @default
             */
            style_preset: string;
            /**
             * Custom Style Text
             * @default
             */
            custom_style_text: string;
        };
        /** ImageMetadataUpdate */
        ImageMetadataUpdate: {
            /** Counts */
            counts: {
                [key: string]: unknown;
            };
            /** Selected */
            selected: {
                [key: string]: unknown;
            };
            /**
             * Slot Keys
             * @default []
             */
            slot_keys: components["schemas"]["SlotKey"][];
        };
        /** ImageSlot */
        ImageSlot: {
            /** Scene Id */
            scene_id: string;
            /** Frame Type */
            frame_type: string;
            /** Slot Index */
            slot_index: number;
            /** Data */
            data: string;
        };
        /** ImagesState */
        ImagesState: {
            /** Slots */
            slots: components["schemas"]["ImageSlot"][];
            /** Counts */
            counts: {
                [key: string]: unknown;
            };
            /** Selected */
            selected: {
                [key: string]: unknown;
            };
        };
        /** LastRunErrors */
        LastRunErrors: {
            /**
             * Stage
             * @default
             */
            stage: string;
            /**
             * Ts
             * @default
             */
            ts: string;
            /**
             * Errors
             * @default {}
             */
            errors: {
                [key: string]: unknown;
            };
        };
        /** ManuscriptConfig */
        ManuscriptConfig: {
            /**
             * Length
             * @default medium
             */
            length: string;
            /**
             * Audience
             * @default
             */
            audience: string;
            /**
             * Style
             * @default
             */
            style: string;
            /**
             * Tone
             * @default
             */
            tone: string;
            /**
             * Theme
             * @default
             */
            theme: string;
            /**
             * Worldview
             * @default
             */
            worldview: string;
            /**
             * Characters
             * @default []
             */
            characters: unknown[];
            /**
             * Dialogue Mode
             * @default mixed
             */
            dialogue_mode: string;
        };
        /** ManuscriptData */
        ManuscriptData: {
            /** Content */
            content: string;
            /**
             * Config
             * @default {}
             */
            config: {
                [key: string]: unknown;
            };
        };
        /** MergeVideoRequest */
        MergeVideoRequest: {
            /** Project Id */
            project_id: string;
            /** Scene Order */
            scene_order: string[];
            /**
             * Transition
             * @default cut
             */
            transition: string;
            /**
             * Transition Duration Ms
             * @default 300
             */
            transition_duration_ms: number;
            /**
             * Bgm Volume Db
             * @default -20
             */
            bgm_volume_db: number;
            /**
             * Bgm Fade In Ms
             * @default 1000
             */
            bgm_fade_in_ms: number;
            /**
             * Bgm Fade Out Ms
             * @default 1500
             */
            bgm_fade_out_ms: number;
        };
        /** MergeVideoResult */
        MergeVideoResult: {
            /** Output Path */
            output_path: string;
            /** Output Dir */
            output_dir: string;
        };
        /** MsTtsRequest */
        MsTtsRequest: {
            /** Text */
            text: string;
            /**
             * Voice
             * @default zh-CN-XiaoxiaoNeural
             */
            voice: string;
            /**
             * Rate
             * @default +0%
             */
            rate: string;
            /**
             * Format
             * @default mp3
             */
            format: string;
        };
        /** NewProjectFromTemplateRequest */
        NewProjectFromTemplateRequest: {
            /** Template Id */
            template_id: string;
            /** Name */
            name: string;
            /**
             * Folder Id
             * @default default
             */
            folder_id: string;
        };
        /** OrchestratorRequest */
        OrchestratorRequest: {
            /** Project Id */
            project_id: string;
            /**
             * Stages
             * @default [
             *       "scenes",
             *       "prompts",
             *       "images",
             *       "audio",
             *       "video",
             *       "merge",
             *       "subtitle"
             *     ]
             */
            stages: string[];
            /**
             * Image Workflow
             * @default
             */
            image_workflow: string;
            /**
             * Video Workflow
             * @default
             */
            video_workflow: string;
            /**
             * Subtitle Font
             * @default 等线 Bold
             */
            subtitle_font: string;
            /**
             * Subtitle Font Size
             * @default 0
             */
            subtitle_font_size: number;
            /**
             * Manual Split
             * @default false
             */
            manual_split: boolean;
            /**
             * Max Chars Per Scene
             * @default 50
             */
            max_chars_per_scene: number;
            /**
             * Rate
             * @default +25%
             */
            rate: string;
            /**
             * Fps
             * @default 24
             */
            fps: number;
        };
        /** PreprocessRequest */
        PreprocessRequest: {
            /** Text */
            text: string;
        };
        /** ProjectMeta */
        ProjectMeta: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Created At */
            created_at: string;
            /** Updated At */
            updated_at: string;
            /**
             * @default {
             *       "manuscript": 0,
             *       "scenes": 0,
             *       "images": 0,
             *       "audio": 0,
             *       "video": 0
             *     }
             */
            progress: components["schemas"]["ProjectProgress"];
            /**
             * Has Final Video
             * @default false
             */
            has_final_video: boolean;
            /**
             * Folder Id
             * @default default
             */
            folder_id: string;
        };
        /** ProjectProgress */
        ProjectProgress: {
            /**
             * Manuscript
             * @default 0
             */
            manuscript: number;
            /**
             * Scenes
             * @default 0
             */
            scenes: number;
            /**
             * Images
             * @default 0
             */
            images: number;
            /**
             * Audio
             * @default 0
             */
            audio: number;
            /**
             * Video
             * @default 0
             */
            video: number;
        };
        /** SceneVideoRequest */
        SceneVideoRequest: {
            /** Scene Id */
            scene_id: string;
            /** Scene Index */
            scene_index: number;
            /**
             * Start Image B64
             * @default
             */
            start_image_b64: string;
            /**
             * End Image B64
             * @default
             */
            end_image_b64: string;
            /**
             * Audio B64
             * @default
             */
            audio_b64: string;
            /**
             * Duration Ms
             * @default 4000
             */
            duration_ms: number;
            /**
             * Positive Prompt
             * @default
             */
            positive_prompt: string;
        };
        /** ScenesData */
        ScenesData: {
            /** Scenes */
            scenes: unknown[];
        };
        /** SlotKey */
        SlotKey: {
            /** Scene Id */
            scene_id: string;
            /** Frame Type */
            frame_type: string;
            /** Slot Index */
            slot_index: number;
        };
        /** StitchClip */
        StitchClip: {
            /** Data */
            data: string;
            /**
             * Pre Silence Ms
             * @default 0
             */
            pre_silence_ms: number;
            /**
             * Post Silence Ms
             * @default 0
             */
            post_silence_ms: number;
        };
        /** StitchRequest */
        StitchRequest: {
            /** Clips */
            clips: components["schemas"]["StitchClip"][];
        };
        /** SubmitTaskRequest */
        SubmitTaskRequest: {
            /** Project Id */
            project_id: string;
            /** Type */
            type: string;
            /** Request */
            request: {
                [key: string]: unknown;
            };
        };
        /** SubtitleStatus */
        SubtitleStatus: {
            /** Has Final Video */
            has_final_video: boolean;
            /** Has Fixed Cfr */
            has_fixed_cfr: boolean;
            /** Has Srt */
            has_srt: boolean;
            /** Has Embedded */
            has_embedded: boolean;
            /**
             * Srt Path
             * @default
             */
            srt_path: string;
            /**
             * Embedded Path
             * @default
             */
            embedded_path: string;
        };
        /** SuggestSceneCharactersRequest */
        SuggestSceneCharactersRequest: {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Dialogues
             * @default []
             */
            dialogues: unknown[];
            /**
             * All Names
             * @default []
             */
            all_names: unknown[];
            /**
             * Manuscript
             * @default
             */
            manuscript: string;
        };
        /** TemplateMeta */
        TemplateMeta: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Created At
             * @default
             */
            created_at: string;
            /**
             * Source Project Id
             * @default
             */
            source_project_id: string;
            /**
             * Has Characters
             * @default false
             */
            has_characters: boolean;
            /**
             * Has Engine Snapshot
             * @default false
             */
            has_engine_snapshot: boolean;
        };
        /** TestAllRequest */
        TestAllRequest: {
            /** Voices */
            voices?: string[] | null;
            /**
             * Text
             * @default 测试
             */
            text: string;
            /**
             * Save
             * @default true
             */
            save: boolean;
        };
        /** TextEngineConfig */
        TextEngineConfig: {
            /**
             * Engine Type
             * @default ollama
             * @enum {string}
             */
            engine_type: "ollama" | "lmstudio" | "deepseek" | "bailian" | "openai_compat";
            /**
             * Base Url
             * @default http://localhost:11434
             */
            base_url: string;
            /** Api Key */
            api_key?: string | null;
            /**
             * Model
             * @default
             */
            model: string;
            /**
             * Temperature
             * @default 0.7
             */
            temperature: number;
            /**
             * Top P
             * @default 0.9
             */
            top_p: number;
            /**
             * Concurrency
             * @default 4
             */
            concurrency: number;
        };
        /** UploadBgmRequest */
        UploadBgmRequest: {
            /** Filename */
            filename: string;
            /** Data */
            data: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** VideoEngineConfig */
        VideoEngineConfig: {
            /**
             * Comfyui Url
             * @default http://localhost:8188
             */
            comfyui_url: string;
            /**
             * Workflow Dir
             * @default
             */
            workflow_dir: string;
            /**
             * Comfyui Input Dir
             * @default
             */
            comfyui_input_dir: string;
            /**
             * Default Workflow
             * @default flfa2i-lumicreate
             */
            default_workflow: string;
            /**
             * Resolution
             * @default 720x1280
             */
            resolution: string;
            /**
             * Fps
             * @default 25
             */
            fps: number;
        };
        /** VideoGenerateRequest */
        VideoGenerateRequest: {
            /** Workflow Name */
            workflow_name: string;
            /**
             * Resolution
             * @default 720x1280
             */
            resolution: string;
            /**
             * Fps
             * @default 25
             */
            fps: number;
            /** Scenes */
            scenes: components["schemas"]["SceneVideoRequest"][];
            /**
             * Project Id
             * @default
             */
            project_id: string;
        };
        /** VideoSlot */
        VideoSlot: {
            /** Scene Id */
            scene_id: string;
            /** Data */
            data: string;
        };
        /** WorkflowMetaPayload */
        WorkflowMetaPayload: {
            /** Node Map */
            node_map: {
                [key: string]: unknown;
            };
            /**
             * Notes
             * @default
             */
            notes: string;
            /**
             * Type
             * @default video
             */
            type: string;
            /**
             * Version
             * @default 1
             */
            version: number;
        };
        /** BatchGenerateRequest */
        routers__audio_engine__BatchGenerateRequest: {
            /**
             * Gen Count
             * @default 3
             */
            gen_count: number;
            /**
             * Speed
             * @default 1
             */
            speed: number;
            /** Dialogues */
            dialogues: components["schemas"]["BatchDialogue"][];
            /**
             * Project Id
             * @default
             */
            project_id: string;
        };
        /** ConnectionTestResult */
        routers__audio_engine__ConnectionTestResult: {
            /** Success */
            success: boolean;
            /** Message */
            message: string;
        };
        /** SingleGenerateRequest */
        routers__audio_engine__SingleGenerateRequest: {
            /** Text */
            text: string;
            /** Voice Ref */
            voice_ref?: string | null;
            /** Emo Ref */
            emo_ref?: string | null;
            /**
             * Emo Weight
             * @default 0.8
             */
            emo_weight: number;
            /**
             * Lang
             * @default zh
             */
            lang: string;
            /** Speaker */
            speaker?: string | null;
            /**
             * Speed
             * @default 1
             */
            speed: number;
            /**
             * Scene Id
             * @default
             */
            scene_id: string;
            /**
             * Dialogue Id
             * @default
             */
            dialogue_id: string;
            /**
             * Slot Index
             * @default 0
             */
            slot_index: number;
            /** Msedge Voice */
            msedge_voice?: string | null;
            /** Msedge Rate */
            msedge_rate?: string | null;
        };
        /** BatchGenerateRequest */
        routers__image_engine__BatchGenerateRequest: {
            /** Workflow Name */
            workflow_name: string;
            /**
             * Gen Count
             * @default 3
             */
            gen_count: number;
            /**
             * Negative Prompt
             * @default
             */
            negative_prompt: string;
            /**
             * Width
             * @default 0
             */
            width: number;
            /**
             * Height
             * @default 0
             */
            height: number;
            /** Frames */
            frames: {
                [key: string]: unknown;
            }[];
            /**
             * Project Id
             * @default
             */
            project_id: string;
        };
        /** ConnectionTestResult */
        routers__image_engine__ConnectionTestResult: {
            /** Success */
            success: boolean;
            /** Message */
            message: string;
        };
        /** SingleGenerateRequest */
        routers__image_engine__SingleGenerateRequest: {
            /** Workflow Name */
            workflow_name: string;
            /** Positive Prompt */
            positive_prompt: string;
            /**
             * Negative Prompt
             * @default
             */
            negative_prompt: string;
            /** Seed */
            seed?: number | null;
            /**
             * Width
             * @default 0
             */
            width: number;
            /**
             * Height
             * @default 0
             */
            height: number;
            /**
             * Scene Id
             * @default
             */
            scene_id: string;
            /**
             * Frame Type
             * @default
             */
            frame_type: string;
            /**
             * Slot Index
             * @default 0
             */
            slot_index: number;
        };
        /** ConnectionTestResult */
        routers__text_engine__ConnectionTestResult: {
            /** Success */
            success: boolean;
            /** Message */
            message: string;
            /**
             * Models
             * @default []
             */
            models: string[];
        };
        /** ConnectionTestResult */
        routers__video_engine__ConnectionTestResult: {
            /** Success */
            success: boolean;
            /** Message */
            message: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
};
export type $defs = Record<string, never>;
export interface operations {
    get_settings_api_settings_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppSettings"];
                };
            };
        };
    };
    update_settings_api_settings_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AppSettings"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppSettings"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_projects_api_projects_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"][];
                };
            };
        };
    };
    create_project_api_projects_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProjectRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_api_projects__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_project_api_projects__project_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_project_api_projects__project_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    copy_config_from_project_api_projects__project_id__copy_config_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CopyConfigRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_asset_file_api_projects__project_id__assets_file__scene_id___asset_type__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                scene_id: string;
                asset_type: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_asset_file_slot_api_projects__project_id__assets_file__scene_id___asset_type___slot_index__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                scene_id: string;
                asset_type: string;
                slot_index: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_assets_api_projects__project_id__assets_get: {
        parameters: {
            query?: {
                scene_id?: string | null;
                asset_type?: string | null;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_events_api_projects__project_id__events_get: {
        parameters: {
            query?: {
                trace_id?: string | null;
                task_id?: string | null;
                scene_id?: string | null;
                level?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_recent_traces_api_projects__project_id__traces_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_status_api_projects__project_id__status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_manuscript_api_projects__project_id__manuscript_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_manuscript_api_projects__project_id__manuscript_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ManuscriptData"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    load_images_api_projects__project_id__images_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_images_api_projects__project_id__images_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImagesState"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    serve_image_file_api_projects__project_id__images_file__filename__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
                filename: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_image_slot_api_projects__project_id__images_slot_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImageSlot"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_image_metadata_api_projects__project_id__images_metadata_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImageMetadataUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_scenes_api_projects__project_id__scenes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_scenes_api_projects__project_id__scenes_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScenesData"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_audio_api_projects__project_id__audio_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_audio_api_projects__project_id__audio_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_audio_slot_api_projects__project_id__audio_slot_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AudioSlotPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    load_videos_api_projects__project_id__videos_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_videos_api_projects__project_id__videos_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VideoSlot"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_video_slot_api_projects__project_id__videos_slot_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VideoSlot"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    load_video_prompts_api_projects__project_id__video_prompts_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_video_prompts_api_projects__project_id__video_prompts_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_last_run_errors_api_projects__project_id__last_run_errors_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_last_run_errors_api_projects__project_id__last_run_errors_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LastRunErrors"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clear_last_run_errors_api_projects__project_id__last_run_errors_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_characters_api_projects__project_id__characters_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    save_characters_api_projects__project_id__characters_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CharactersData"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_connection_api_text_engine_test_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["routers__text_engine__ConnectionTestResult"];
                };
            };
        };
    };
    generate_manuscript_api_text_engine_generate_manuscript_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateManuscriptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_scenes_api_text_engine_generate_scenes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateScenesRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_frame_prompts_api_text_engine_generate_frame_prompts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateFramePromptsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_character_appearance_api_text_engine_generate_character_appearance_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateCharacterAppearanceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_character_profile_api_text_engine_generate_character_profile_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateCharacterProfileRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    suggest_scene_characters_api_text_engine_suggest_scene_characters_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SuggestSceneCharactersRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_video_prompt_api_text_engine_generate_video_prompt_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateVideoPromptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    precheck_workflow_api_image_engine_precheck_get: {
        parameters: {
            query: {
                workflow_name: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_connection_api_image_engine_test_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["routers__image_engine__ConnectionTestResult"];
                };
            };
        };
    };
    get_workflows_api_image_engine_workflows_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
        };
    };
    get_workflow_api_image_engine_workflow__workflow_name__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_workflow_meta_api_image_engine_workflow_meta__workflow_name__get: {
        parameters: {
            query?: {
                type?: string;
            };
            header?: never;
            path: {
                workflow_name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_workflow_meta_api_image_engine_workflow_meta__workflow_name__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowMetaPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_single_stream_api_image_engine_generate_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["routers__image_engine__SingleGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_batch_stream_api_image_engine_generate_batch_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["routers__image_engine__BatchGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_connection_api_audio_engine_test_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["routers__audio_engine__ConnectionTestResult"];
                };
            };
        };
    };
    get_voice_refs_api_audio_engine_voice_refs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
        };
    };
    get_emotion_refs_api_audio_engine_emotion_refs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
        };
    };
    generate_single_stream_api_audio_engine_generate_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["routers__audio_engine__SingleGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_batch_stream_api_audio_engine_generate_batch_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["routers__audio_engine__BatchGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stitch_scene_api_audio_engine_stitch_scene_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StitchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ms_tts_api_audio_engine_ms_tts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MsTtsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ms_tts_test_all_api_audio_engine_ms_tts_test_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TestAllRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    precheck_video_workflow_endpoint_api_video_engine_precheck_get: {
        parameters: {
            query: {
                workflow_name: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_connection_api_video_engine_test_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["routers__video_engine__ConnectionTestResult"];
                };
            };
        };
    };
    get_video_workflows_api_video_engine_workflows_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string[];
                };
            };
        };
    };
    generate_video_stream_api_video_engine_generate_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VideoGenerateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_project_bgm_api_video_engine_bgm__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_project_bgm_api_video_engine_bgm__project_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UploadBgmRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_project_bgm_api_video_engine_bgm__project_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    merge_project_video_api_video_engine_merge_project_video_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MergeVideoRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MergeVideoResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    subtitle_status_api_subtitle_engine_status__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SubtitleStatus"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_script_api_subtitle_engine_script__project_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preprocess_text_endpoint_api_subtitle_engine_preprocess_text_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreprocessRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_srt_endpoint_api_subtitle_engine_generate_srt_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GenerateSrtRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    embed_subtitles_endpoint_api_subtitle_engine_embed_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmbedRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    generate_all_api_orchestrator_generate_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrchestratorRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_templates_api_templates_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateMeta"][];
                };
            };
        };
    };
    get_template_api_templates__template_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_template_api_templates__template_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_from_project_api_templates_from_project_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTemplateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateMeta"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    apply_template_api_templates__template_id__apply_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApplyTemplateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    spawn_project_from_template_api_templates__template_id__spawn_project_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NewProjectFromTemplateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    recent_api_logs_recent_get: {
        parameters: {
            query?: {
                limit?: number;
                after_id?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_api_logs_stream_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    clear_api_logs_clear_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    list_tasks_api_tasks_get: {
        parameters: {
            query: {
                project_id: string;
                status?: string | null;
                type?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_task_api_tasks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SubmitTaskRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_task_api_tasks__task_id__get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_task_api_tasks__task_id__cancel_post: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: never;
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CancelResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_task_events_api_tasks__task_id__events_get: {
        parameters: {
            query: {
                project_id: string;
            };
            header?: {
                "Last-Event-ID"?: string | null;
            };
            path: {
                task_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_records_api_task_history_get: {
        parameters: {
            query?: {
                limit?: number;
                project_id?: string | null;
                type?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clear_all_api_task_history_delete: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    stats_api_task_history_stats_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
