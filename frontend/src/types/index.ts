// 推理结果相关类型
export interface BoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export interface Person {
  id: string
  activity: string
  bbox: [number, number, number, number]
}

export interface Vehicle {
  id: string
  type: string
  status: string
  bbox: [number, number, number, number]
}

export interface InferenceResult {
  timestamp: string
  people_count: number
  vehicle_count: number
  people: Person[]
  vehicles: Vehicle[]
  summary: string
  video_path?: string
  creation_time?: string
}

// 视频信息相关类型
export interface VideoInfo {
  video_path: string
  frame_count: number
  start_timestamp: string
  end_timestamp: string
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
  result?: string
  video_info?: VideoInfo
  inference_start_time?: number
  inference_end_time?: number
  inference_start_timestamp?: string
  inference_end_timestamp?: string
  inference_duration?: number
  result_received_at?: number
  parsed_result?: InferenceResult
  
  // 新增字段（来自后端）
  video_id?: string
  has_inference_result?: boolean
  timestamp?: string
  creation_timestamp?: string
  total_frames?: number
  frames_per_second?: number
  target_duration?: number
  sampled_frames?: any[]
  creation_time?: string
  session_dir?: string
  filename?: string
  
  // AI推理结果字段
  people_count?: number
  vehicle_count?: number
  people?: Person[]
  vehicles?: Vehicle[]
  summary?: string
  raw_result?: string
  
  // 新增：AI回答相关字段
  user_question?: string  // 用户问题
  ai_response?: string    // AI回答（从raw_result中提取）
  response?: string       // 兼容字段，指向ai_response
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
  type: 'video_frame' | 'inference_result' | 'status_update' | 'stream_status' | 'error'
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
  latestPlayableInference: InferenceLogItem | null // 最新的可播放推理结果（有AI分析的）
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