import { defineStore } from 'pinia'
import type { 
  AppState, 
  VideoFrame, 
  InferenceLogItem, 
  ExperimentLog,
  InferenceResult 
} from '@/types'

export const useMonitorStore = defineStore('monitor', {
  state: (): AppState => ({
    isConnected: false,
    isStreaming: false,
    currentFrame: null,
    latestInference: null,
    inferenceHistory: [],
    stats: {
      fps: 0,
      totalFrames: 0,
      inferenceCount: 0,
      latency: 0
    }
  }),

  getters: {
    // 获取最新推理结果的解析数据
    latestParsedResult(state): InferenceResult | null {
      if (!state.latestInference) return null
      
      // 新格式的推理结果直接包含结构化数据
      if (state.latestInference.sampled_frames) {
        return {
          timestamp: state.latestInference.timestamp || '',
          people_count: state.latestInference.sampled_frames?.length || 0,
          people: [],
          summary: `视频包含 ${state.latestInference.total_frames} 帧，采样了 ${state.latestInference.sampled_frames?.length || 0} 帧`,
          video_path: state.latestInference.video_path,
          creation_time: state.latestInference.creation_time
        } as InferenceResult
      }
      
      // 兼容旧格式
      if (!state.latestInference.result) return null
      
      try {
        let resultText = state.latestInference.result
        
        // 提取JSON部分
        if (resultText.includes('```json')) {
          const start = resultText.indexOf('```json') + 7
          const end = resultText.indexOf('```', start)
          if (end > start) {
            resultText = resultText.substring(start, end).trim()
          }
        }
        
        return JSON.parse(resultText) as InferenceResult
      } catch (error) {
        console.error('解析推理结果失败:', error)
        return null
      }
    },

    // 获取最近的推理历史（最多10个）
    recentInferences(state): InferenceLogItem[] {
      return state.inferenceHistory
        .slice(-10)
        .sort((a: any, b: any) => {
          const aTime = a.result_received_at || new Date(a.timestamp || 0).getTime() / 1000
          const bTime = b.result_received_at || new Date(b.timestamp || 0).getTime() / 1000
          return bTime - aTime
        })
    },

    // 计算平均推理延迟
    averageInferenceLatency(state): number {
      if (state.inferenceHistory.length === 0) return 0
      
      const latencies = state.inferenceHistory.map((item: any) => 
        item.inference_duration || item.creation_time || 0
      )
      return latencies.reduce((sum: number, latency: number) => sum + latency, 0) / latencies.length
    }
  },

  actions: {
    // 设置连接状态
    setConnectionStatus(connected: boolean) {
      this.isConnected = connected
      if (!connected) {
        this.isStreaming = false
        this.currentFrame = null
      }
    },

    // 设置流媒体状态
    setStreamingStatus(streaming: boolean) {
      this.isStreaming = streaming
      if (!streaming) {
        this.currentFrame = null
      }
    },

    // 更新当前帧
    updateCurrentFrame(frame: VideoFrame) {
      this.currentFrame = frame
      this.stats.totalFrames++
      
      // 计算FPS（简单实现）
      if (frame.frame_number % 30 === 0) {
        this.calculateFPS()
      }
    },

    // 添加推理结果
    addInferenceResult(inference: InferenceLogItem) {
      this.latestInference = inference
      this.inferenceHistory.push(inference)
      this.stats.inferenceCount++
      
      // 只保留最近100个结果
      if (this.inferenceHistory.length > 100) {
        this.inferenceHistory = this.inferenceHistory.slice(-100)
      }
      
      // 更新延迟统计
      this.stats.latency = this.averageInferenceLatency
    },

    // 从实验日志初始化推理历史
    initializeFromExperimentLog(experimentLog: ExperimentLog) {
      this.inferenceHistory = [...experimentLog.inference_log]
      
      // 兼容新格式和旧格式的统计信息
      if (experimentLog.statistics) {
        this.stats.inferenceCount = experimentLog.statistics.total_inferences_completed
      } else {
        // 新格式可能包含 total_inferences 字段
        const newFormatLog = experimentLog as any
        this.stats.inferenceCount = newFormatLog.total_inferences || experimentLog.inference_log.length
      }
      
      if (this.inferenceHistory.length > 0) {
        this.latestInference = this.inferenceHistory[this.inferenceHistory.length - 1]
        this.stats.latency = this.averageInferenceLatency
      }
    },

    // 计算FPS
    calculateFPS() {
      // 这里可以实现更精确的FPS计算
      // 目前使用简单的估算
      if (this.currentFrame) {
        const now = Date.now()
        const frameTime = this.currentFrame.timestamp * 1000
        const timeDiff = now - frameTime
        
        if (timeDiff > 0 && timeDiff < 10000) { // 10秒内的帧才有效
          this.stats.fps = Math.round(1000 / timeDiff * 30) // 30帧采样周期
        }
      }
    },

    // 重置统计信息
    resetStats() {
      this.stats = {
        fps: 0,
        totalFrames: 0,
        inferenceCount: 0,
        latency: 0
      }
    },

    // 清空所有数据
    clearAllData() {
      this.currentFrame = null
      this.latestInference = null
      this.inferenceHistory = []
      this.resetStats()
    }
  }
}) 