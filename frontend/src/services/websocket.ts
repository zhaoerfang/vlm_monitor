import type { WebSocketMessage, VideoFrame, InferenceLogItem } from '@/types'

export class WebSocketService {
  private socket: WebSocket | null = null
  private isConnected = false
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 3000

  // 事件回调
  private onFrameCallback?: (frame: VideoFrame) => void
  private onInferenceCallback?: (inference: InferenceLogItem) => void
  private onStatusCallback?: (status: any) => void
  private onErrorCallback?: (error: string) => void
  private onConnectedCallback?: () => void
  private onDisconnectedCallback?: () => void

  constructor(private url: string = 'ws://localhost:8080/ws') {}

  // 连接WebSocket
  connect(): Promise<boolean> {
    return new Promise((resolve) => {
      if (this.isConnected && this.socket) {
        resolve(true)
        return
      }

      try {
        this.socket = new WebSocket(this.url)

        // 连接成功
        this.socket.onopen = () => {
          console.log('WebSocket连接已建立')
          this.isConnected = true
          this.reconnectAttempts = 0
          this.onConnectedCallback?.()
          resolve(true)
        }

        // 连接失败
        this.socket.onerror = (error) => {
          console.error('WebSocket连接失败:', error)
          this.isConnected = false
          resolve(false)
        }

        // 断开连接
        this.socket.onclose = (event) => {
          console.log('WebSocket连接已断开:', event.reason)
          this.isConnected = false
          this.onDisconnectedCallback?.()
          
          if (event.code !== 1000) { // 非正常关闭
            this.handleReconnect()
          }
        }

        // 接收消息
        this.socket.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as WebSocketMessage
            this.handleMessage(message)
          } catch (error) {
            console.error('解析WebSocket消息失败:', error)
          }
        }

        // 连接超时
        setTimeout(() => {
          if (!this.isConnected) {
            console.log('WebSocket连接超时')
            resolve(false)
          }
        }, 10000)

      } catch (error) {
        console.error('创建WebSocket连接失败:', error)
        resolve(false)
      }
    })
  }

  // 处理收到的消息
  private handleMessage(message: WebSocketMessage) {
    console.log('收到WebSocket消息:', message.type)
    
    switch (message.type) {
      case 'video_frame':
        this.onFrameCallback?.(message.data as VideoFrame)
        break
      case 'inference_result':
        this.onInferenceCallback?.(message.data as InferenceLogItem)
        break
      case 'status_update':
      case 'stream_status':
        this.onStatusCallback?.(message.data)
        break
      case 'error':
        this.onErrorCallback?.(message.data as string)
        break
      default:
        console.warn('未知消息类型:', message.type)
    }
  }

  // 断开连接
  disconnect() {
    if (this.socket) {
      this.socket.close(1000) // 正常关闭
      this.socket = null
    }
    this.isConnected = false
  }

  // 处理重连
  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`)
      
      setTimeout(() => {
        this.connect()
      }, this.reconnectDelay)
    } else {
      console.error('达到最大重连次数，停止重连')
      this.onErrorCallback?.('连接失败，已达到最大重连次数')
    }
  }

  // 发送消息
  send(type: string, data: any) {
    if (this.socket && this.isConnected && this.socket.readyState === WebSocket.OPEN) {
      const message = {
        type,
        data,
        timestamp: Date.now() / 1000
      }
      this.socket.send(JSON.stringify(message))
      console.log('发送WebSocket消息:', type)
    } else {
      console.warn('WebSocket未连接，无法发送消息')
    }
  }

  // 请求开始视频流
  startVideoStream() {
    this.send('start_stream', {})
  }

  // 请求停止视频流
  stopVideoStream() {
    this.send('stop_stream', {})
  }

  // 请求最新推理结果
  requestLatestInference() {
    this.send('get_latest_inference', {})
  }

  // 设置回调函数
  onFrame(callback: (frame: VideoFrame) => void) {
    this.onFrameCallback = callback
  }

  onInference(callback: (inference: InferenceLogItem) => void) {
    this.onInferenceCallback = callback
  }

  onStatus(callback: (status: any) => void) {
    this.onStatusCallback = callback
  }

  onError(callback: (error: string) => void) {
    this.onErrorCallback = callback
  }

  onConnected(callback: () => void) {
    this.onConnectedCallback = callback
  }

  onDisconnected(callback: () => void) {
    this.onDisconnectedCallback = callback
  }

  // 获取连接状态
  getConnectionStatus() {
    return {
      isConnected: this.isConnected,
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts
    }
  }
}

// 创建全局WebSocket服务实例
export const websocketService = new WebSocketService()

export default websocketService 