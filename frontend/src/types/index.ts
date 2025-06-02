// 推理结果相关类型
export interface BoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export interface Person {
  id: number
  bbox: [number, number, number, number] // [x, y, width, height] 相对坐标 0-1
  activity: string
}

export interface InferenceResult {
  timestamp: string
  people_count: number
  people: Person[]
  summary: string
}

// 视频信息相关类型
export interface VideoInfo {
  video_path: string
  frame_count: number
  start_timestamp: number
  end_timestamp: number
  start_relative_timestamp: number
  end_relative_timestamp: number
  duration: number
  relative_duration: number
  original_frame_range: [number, number]
  video_creation_time: number
  video_creation_timestamp: string
  created_at: number
}

// 推理日志项
export interface InferenceLogItem {
  video_path: string
  result: string
  video_info: VideoInfo
  inference_start_time: number
  inference_end_time: number
  inference_start_timestamp: string
  inference_end_timestamp: string
  inference_duration: number
  result_received_at: number
  parsed_result?: InferenceResult
}

// 实验日志
export interface ExperimentLog {
  processor_config: {
    target_video_duration: number
    frames_per_second: number
    original_fps: number
    target_frames_per_video: number
    frames_to_collect_per_video: number
    max_concurrent_inferences: number
  }
  statistics: {
    total_frames_received: number
    total_videos_created: number
    total_inferences_started: number
    total_inferences_completed: number
    start_time: number
    start_timestamp: string
    total_duration: number
  }
  inference_log: InferenceLogItem[]
}

// WebSocket消息类型 - 更新以匹配FastAPI后端
export interface WebSocketMessage {
  type: 'video_frame' | 'inference_result' | 'status_update' | 'error'
  data: any
  timestamp: number
}

// 实时视频流帧
export interface VideoFrame {
  data: string // base64编码的图像数据
  timestamp: number
  frame_number: number
}

// 应用状态
export interface AppState {
  isConnected: boolean
  isStreaming: boolean
  currentFrame: VideoFrame | null
  latestInference: InferenceLogItem | null
  inferenceHistory: InferenceLogItem[]
  stats: {
    fps: number
    totalFrames: number
    inferenceCount: number
    latency: number
  }
}

// API响应类型
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
  timestamp: number
} 