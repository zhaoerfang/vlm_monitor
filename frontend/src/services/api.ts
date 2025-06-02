import type { ApiResponse, ExperimentLog, InferenceLogItem } from '@/types'

// 基础fetch封装
async function apiRequest<T = any>(url: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
  try {
    console.log('API请求:', options.method || 'GET', url)
    
    const response = await fetch(`/api${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    })

    console.log('API响应:', response.status, url)
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const data = await response.json()
    return data as ApiResponse<T>
  } catch (error) {
    console.error('API请求失败:', error)
    return {
      success: false,
      error: error instanceof Error ? error.message : String(error),
      timestamp: Date.now() / 1000
    }
  }
}

// API方法
export const apiService = {
  // 通用GET请求
  async get(url: string): Promise<ApiResponse> {
    return apiRequest(url)
  },

  // 获取系统状态
  async getSystemStatus(): Promise<ApiResponse> {
    return apiRequest('/status')
  },

  // 获取实验日志
  async getExperimentLog(): Promise<ApiResponse<ExperimentLog>> {
    return apiRequest('/experiment-log')
  },

  // 获取推理历史
  async getInferenceHistory(limit = 50): Promise<ApiResponse<InferenceLogItem[]>> {
    return apiRequest(`/inference-history?limit=${limit}`)
  },

  // 获取最新推理结果
  async getLatestInference(): Promise<ApiResponse<InferenceLogItem>> {
    return apiRequest('/latest-inference')
  },

  // 获取最新的已完成AI分析的推理结果
  async getLatestInferenceWithAI(): Promise<ApiResponse<InferenceLogItem>> {
    return apiRequest('/latest-inference-with-ai')
  },

  // 获取视频文件列表
  async getVideoList(): Promise<ApiResponse<string[]>> {
    return apiRequest('/videos')
  },

  // 获取特定视频的详情
  async getVideoDetails(videoId: string): Promise<ApiResponse> {
    return apiRequest(`/videos/${videoId}/details`)
  },

  // 启动视频流
  async startStream(): Promise<ApiResponse> {
    return apiRequest('/stream/start', { method: 'POST' })
  },

  // 停止视频流
  async stopStream(): Promise<ApiResponse> {
    return apiRequest('/stream/stop', { method: 'POST' })
  },

  // 获取流状态
  async getStreamStatus(): Promise<ApiResponse> {
    return apiRequest('/stream/status')
  },

  // 清空历史数据
  async clearHistory(): Promise<ApiResponse> {
    return apiRequest('/history', { method: 'DELETE' })
  }
}

export default apiService 