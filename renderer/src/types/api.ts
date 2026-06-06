/**
 * 后端 API 公共类型（F1 起步）。
 * 当前只列出最常用的，后续逐步补全。前端使用 TS 时 import 这些即可。
 */

export type DialogueMode = 'reading' | 'narration' | 'dialogue' | 'mixed'

export interface ProjectMeta {
  id: string
  name: string
  description: string
  folder_id: string
  created_at: string
  updated_at: string
  progress?: {
    manuscript: number
    scenes: number
    images: number
    audio: number
    video: number
  }
  has_final_video?: boolean
}

export interface SceneCharacterRef {
  name: string
  role?: string
  traits?: string
  appearance?: string
  negative?: string
  voice?: string   // msedge voice
}

export interface Scene {
  id: string
  index: number
  description: string
  duration_estimate: number
  start_frame_prompt: string
  end_frame_prompt: string
  _scene_characters: string[]
  dialogues: Dialogue[]
}

export interface Dialogue {
  character: string
  text: string
  emotion?: string
}

export interface LastRunErrors {
  stage: 'images' | 'audio' | 'video' | 'prompts' | ''
  ts: string
  errors: Record<string, string>
}

export interface TaskHistoryRecord {
  id: string
  type: 'images' | 'audio' | 'video' | 'merge' | 'subtitle' | 'prompts'
  project_id: string
  project_name: string
  started_at: string
  ended_at: string
  duration_ms: number
  items: number
  errors: number
  status: 'ok' | 'partial' | 'error'
  note: string
}

export interface LogLine {
  id: number
  ts: number
  level: 'info' | 'error'
  text: string
}
