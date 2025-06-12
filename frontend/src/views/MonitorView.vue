<template>
  <div class="monitor-view">
    <header class="monitor-header">
      <h1>视频监控系统</h1>
      <div class="header-controls">
        <button @click="refreshData" :disabled="isLoading" class="btn btn-primary">
          {{ isLoading ? '刷新中...' : '刷新' }}
        </button>
        <button 
          @click="toggleSentryMode" 
          :disabled="sentryModeLoading"
          :class="['btn', 'sentry-mode-btn', sentryModeEnabled ? 'btn-success' : 'btn-secondary']"
        >
          <span class="sentry-icon">🛡️</span>
          {{ sentryModeLoading ? '切换中...' : (sentryModeEnabled ? '哨兵模式 ON' : '哨兵模式 OFF') }}
        </button>
        <button @click="debugVideos" class="btn btn-secondary">调试视频</button>
        <button @click="clearHistory" class="btn btn-warning">清空历史</button>
      </div>
    </header>

    <main class="monitor-main">
      <section class="live-section">
        <div class="panel">
          <div class="panel-header">
            <h3>实时视频流</h3>
            <div class="status-indicators">
              <span class="status-tag" :class="connectionStatus">
                {{ connectionText }}
              </span>
              <span v-if="stats.fps > 0" class="status-tag info">
                {{ stats.fps }} FPS
              </span>
            </div>
          </div>
          
          <div class="video-container">
            <div v-if="!store.isStreaming && !streamLoaded" class="placeholder">
              <div class="placeholder-content">
                <div class="icon">📹</div>
                <p>实时视频流</p>
                <p class="hint">等待连接...</p>
                <button class="btn btn-primary" @click="startStream">开始播放</button>
              </div>
            </div>
            
            <div v-else-if="store.isStreaming && !streamLoaded" class="placeholder">
              <div class="placeholder-content">
                <div class="icon">⏳</div>
                <p>等待视频信号...</p>
                <p class="hint">正在接收数据流...</p>
                <button class="btn btn-danger" @click="stopStream">停止</button>
              </div>
            </div>
            
            <div v-else class="video-display">
              <!-- 使用Canvas显示WebSocket传来的实时视频帧 -->
              <canvas 
                ref="liveVideoCanvas"
                class="video-stream"
                width="640"
                height="360"
                @click="onCanvasClick"
              ></canvas>
              
              <div class="video-overlay">
                <div class="frame-info">
                  <span>实时视频流</span>
                  <span v-if="stats.totalFrames > 0">帧数: {{ stats.totalFrames }}</span>
                  <span v-if="streamFps > 0" class="fps-counter">{{ streamFps.toFixed(1) }} FPS</span>
                </div>
              </div>
            </div>
          </div>
          
          <div class="control-panel">
            <div class="control-group">
              <button class="btn btn-primary" @click="startStream">开始播放</button>
              <button class="btn btn-danger" @click="stopStream">停止播放</button>
              <button class="btn btn-secondary">全屏</button>
            </div>
            
            <div class="stats-group">
              <span>总帧数: {{ stats.totalFrames }}</span>
              <span>帧号: 0</span>
              <span>延迟: 0ms</span>
            </div>
          </div>
        </div>
      </section>
      
      <div class="divider"></div>
      
      <section class="inference-section">
        <div class="panel">
          <div class="panel-header">
            <h3>推理结果</h3>
            <div class="inference-status">
              <span v-if="latestInference" class="status-tag success">
                最新推理: {{ formatTime(getInferenceTime(latestInference)) }}
              </span>
              <span v-if="stats.latency > 0" class="status-tag info">
                平均延迟: {{ Math.round(stats.latency) }}s
              </span>
            </div>
          </div>
          
          <div class="inference-container">
            <div v-if="!currentInference" class="placeholder">
              <div class="placeholder-content">
                <div class="icon">🤖</div>
                <p>推理结果</p>
                <p class="hint">等待推理结果...</p>
                <p class="hint">推理需要约12秒时间</p>
              </div>
            </div>
            
            <div v-else class="inference-display">
              <div class="left-section">
                <div class="video-section">
                  <div class="video-player-container">
                    <!-- 图像显示 -->
                    <div v-if="isCurrentInferenceImage" class="inference-image-container">
                      <img 
                        ref="inferenceImage"
                        :src="getMediaUrl(currentInference.filename || getVideoFileName(currentInference.video_path))"
                        class="inference-image"
                        @load="onStreamLoad"
                        @error="onStreamError"
                      />
                      
                      <!-- 图像覆盖层用于显示bbox -->
                      <canvas 
                        v-if="currentInference.has_inference_result && (currentInference.people || currentInference.vehicles)"
                        ref="bboxCanvas"
                        class="bbox-overlay"
                        @click="toggleBboxDisplay"
                      ></canvas>
                    </div>
                    
                    <!-- 视频显示 -->
                    <div v-else class="inference-video-container">
                      <video 
                        v-if="currentInference.video_path"
                        ref="inferenceVideo"
                        :src="getVideoUrl(currentInference.video_path)"
                        controls
                        autoplay
                        loop
                        muted
                        class="inference-video"
                        @loadedmetadata="onVideoLoaded"
                        @error="onVideoError"
                        @loadstart="onVideoLoadStart"
                        @resize="onVideoResize"
                      ></video>
                      
                      <!-- 视频覆盖层用于显示bbox -->
                      <canvas 
                        v-if="currentInference.has_inference_result && (currentInference.people || currentInference.vehicles)"
                        ref="bboxCanvas"
                        class="bbox-overlay"
                        @click="toggleBboxDisplay"
                      ></canvas>
                    </div>
                    
                    <div class="media-info">
                      <p v-if="isCurrentInferenceImage">
                        <strong>图像文件:</strong> {{ currentInference.filename || getVideoFileName(currentInference.video_path) }}
                      </p>
                      <p v-else>
                        <strong>视频文件:</strong> {{ getVideoFileName(currentInference.video_path) }}
                      </p>
                      
                      <p v-if="currentInference.frame_number">
                        <strong>帧号:</strong> {{ currentInference.frame_number }}
                      </p>
                      <p v-if="currentInference.total_frames">
                        <strong>总帧数:</strong> {{ currentInference.total_frames }}
                      </p>
                      <p v-if="currentInference.sampled_frames">
                        <strong>采样帧数:</strong> {{ currentInference.sampled_frames.length }}
                      </p>
                      
                      <p v-if="currentInference.has_inference_result" class="ai-status success">✅ AI分析完成</p>
                      <p v-else class="ai-status pending">⏳ 等待AI分析</p>
                    </div>
                  </div>
                </div>
                
                <div class="info-panel">
                  <h4>推理详情</h4>
                  
                  <!-- 思考与行动区域 - 放在最顶部 -->
                  <div v-if="currentInference.has_mcp_result" class="detail-section mcp-action-section">
                    <h5>思考与行动</h5>
                    <div class="mcp-action-content">
                      <div v-if="currentInference.mcp_reason" class="mcp-thinking">
                        <strong>思考过程：</strong>
                        <div class="thinking-text">{{ currentInference.mcp_reason }}</div>
                      </div>
                      <div v-if="currentInference.mcp_result" class="mcp-action">
                        <strong>执行行动：</strong>
                        <div class="action-text">{{ currentInference.mcp_result }}</div>
                      </div>
                      <div v-if="currentInference.mcp_tool_name" class="mcp-tool-info">
                        <div class="tool-details">
                          <span class="tool-name">工具: {{ currentInference.mcp_tool_name }}</span>
                          <span class="tool-status" :class="{ 'success': currentInference.mcp_success, 'failed': !currentInference.mcp_success }">
                            {{ currentInference.mcp_success ? '✅ 成功' : '❌ 失败' }}
                          </span>
                        </div>
                        <div v-if="currentInference.mcp_arguments && Object.keys(currentInference.mcp_arguments).length > 0" class="tool-arguments">
                          <strong>参数：</strong>
                          <span v-for="(value, key) in currentInference.mcp_arguments" :key="key" class="argument-item">
                            {{ key }}: {{ value }}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <!-- AI回答区域 -->
                  <div class="detail-section ai-response-section">
                    <h5>AI回答</h5>
                    <div class="ai-response-content">
                      <div v-if="currentInference.user_question" class="user-question">
                        <strong>用户问题：</strong>{{ currentInference.user_question }}
                      </div>
                      <div v-else class="no-question">
                        <span class="no-question-text">暂无用户问题</span>
                      </div>
                      <div class="ai-answer">
                        <strong>AI回答：</strong>
                        <div class="response-text">
                          <span v-if="currentInference.response || currentInference.ai_response || extractAIResponse(currentInference.raw_result)">
                            {{ currentInference.response || currentInference.ai_response || extractAIResponse(currentInference.raw_result) }}
                          </span>
                          <span v-else class="no-response-text">
                            暂无AI回答（用户未提问）
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div class="detail-section">
                    <h5>基本信息</h5>
                    <div class="detail-item">
                      <label>推理耗时:</label>
                      <span>{{ getInferenceDuration(currentInference) }}秒</span>
                    </div>
                    <div class="detail-item">
                      <label>视频时长:</label>
                      <span>{{ currentInference.target_duration || 3 }}秒</span>
                    </div>
                    <div class="detail-item">
                      <label>采样帧数:</label>
                      <span>{{ currentInference.sampled_frames?.length || 0 }}帧</span>
                    </div>
                  </div>
                  
                  <div v-if="currentInference.has_inference_result" class="detail-section">
                    <h5>AI分析结果</h5>
                    <div class="detail-item">
                      <label>检测人数:</label>
                      <span class="highlight">{{ currentInference.people_count || 0 }}人</span>
                    </div>
                    <div class="detail-item">
                      <label>检测车辆:</label>
                      <span class="highlight">{{ currentInference.vehicle_count || 0 }}辆</span>
                    </div>
                    <div class="detail-item">
                      <label>场景描述:</label>
                      <span>{{ currentInference.summary || '无描述' }}</span>
                    </div>
                    
                    <div v-if="currentInference.people && currentInference.people.length > 0" class="people-list">
                      <h6>人员详情</h6>
                      <div v-for="(person, index) in currentInference.people" :key="index" class="person-item">
                        <div class="person-header">
                          <span class="person-id">人员 {{ person.id || (index + 1) }}</span>
                          <span class="person-activity">{{ person.activity || '未知活动' }}</span>
                        </div>
                        <div class="person-bbox" v-if="person.bbox">
                          位置: [{{ person.bbox.map((v: number) => Math.round(v * 100) / 100).join(', ') }}]
                        </div>
                      </div>
                    </div>
                    
                    <div v-if="currentInference.vehicles && currentInference.vehicles.length > 0" class="vehicles-list">
                      <h6>车辆详情</h6>
                      <div v-for="(vehicle, index) in currentInference.vehicles" :key="index" class="vehicle-item">
                        <div class="vehicle-header">
                          <span class="vehicle-id">{{ vehicle.type }} {{ vehicle.id || (index + 1) }}</span>
                          <span class="vehicle-status">{{ vehicle.status || '未知状态' }}</span>
                        </div>
                        <div class="vehicle-bbox" v-if="vehicle.bbox">
                          位置: [{{ vehicle.bbox.map((v: number) => Math.round(v * 100) / 100).join(', ') }}]
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  <div v-else class="detail-section">
                    <h5>等待AI分析</h5>
                    <p class="waiting-message">视频已采样完成，正在等待AI模型分析结果...</p>
                    <p class="waiting-hint">通常需要10-15秒时间</p>
                  </div>
                </div>
              </div>
              
              <!-- 右侧历史记录区域 -->
              <div class="right-section">
                <div class="history-section">
                  <div class="history-header">
                    <h4>历史记录</h4>
                    <div class="history-controls">
                      <button @click="loadMediaHistory" :disabled="isLoadingHistory" class="btn btn-sm btn-secondary">
                        {{ isLoadingHistory ? '加载中...' : '刷新历史' }}
                      </button>
                      <span class="history-count">{{ mediaHistory.length }} 项</span>
                    </div>
                  </div>
                  
                  <div class="history-container">
                    <div v-if="mediaHistory.length === 0" class="history-placeholder">
                      <div class="placeholder-content">
                        <div class="icon">📂</div>
                        <p>暂无历史记录</p>
                        <p class="hint">推理结果将显示在这里</p>
                      </div>
                    </div>
                    
                    <div v-else class="history-scroll">
                      <div 
                        v-for="(item, index) in mediaHistory" 
                        :key="item.filename"
                        class="history-item"
                        :class="{ 'active': selectedHistoryItem?.filename === item.filename }"
                        @click="selectHistoryItem(item)"
                      >
                        <div class="history-thumbnail">
                          <div v-if="item.type === 'image'" class="thumbnail-image">
                            <img 
                              :src="getMediaUrl(item.filename)" 
                              :alt="item.filename"
                              @error="onThumbnailError"
                            />
                            <div class="media-type-badge image">📷</div>
                          </div>
                          <div v-else class="thumbnail-video">
                            <video 
                              :src="getMediaUrl(item.filename)"
                              muted
                              preload="metadata"
                              @error="onThumbnailError"
                            ></video>
                            <div class="media-type-badge video">🎬</div>
                          </div>
                        </div>
                        
                        <div class="history-info">
                          <div class="history-title">
                            {{ item.type === 'image' ? `帧 ${item.frame_number}` : `视频 ${index + 1}` }}
                          </div>
                          <div class="history-time">
                            {{ formatHistoryTime(item.timestamp || item.creation_timestamp) }}
                          </div>
                          <div class="history-status">
                            <span v-if="item.has_inference_result && item.has_mcp_result" class="status-badge success">
                              ✅ {{ item.people_count || 0 }}人 {{ item.vehicle_count || 0 }}车
                            </span>
                            <span v-else-if="item.has_inference_result && !item.has_mcp_result" class="status-badge partial">
                              🔄 等待行动
                            </span>
                            <span v-else class="status-badge pending">⏳ 等待分析</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer class="monitor-footer">
      <div class="stats-group">
        <span>总帧数: {{ stats.totalFrames }}</span>
        <span>推理数: {{ stats.inferenceCount }}</span>
        <span>FPS: {{ stats.fps }}</span>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useMonitorStore } from '@/stores/monitor'
import apiService, { sentryModeApi } from '@/services/api'
import websocketService from '@/services/websocket'

const store = useMonitorStore()
const isLoading = ref(false)
const inferenceVideo = ref<HTMLVideoElement>()
const bboxCanvas = ref<HTMLCanvasElement>()
const liveVideoCanvas = ref<HTMLCanvasElement>()

// 哨兵模式状态
const sentryModeEnabled = ref(true)
const sentryModeLoading = ref(false)

// 实时视频流相关状态
const streamLoaded = ref(false)
const streamFps = ref(0)

// FPS计算相关
let frameLoadTimes: number[] = []
let lastFpsUpdate = 0

// 定时器引用
let statusCheckInterval: number | null = null
let inferenceCheckInterval: number | null = null

// bbox显示状态
const showBbox = ref(true)

// 历史记录相关状态
const mediaHistory = ref<any[]>([])
const selectedHistoryItem = ref<any>(null)
const isLoadingHistory = ref(false)

const stats = computed(() => store.stats)
const latestInference = computed(() => store.latestInference)
const currentInference = computed(() => store.playableInference)

const connectionStatus = computed(() => {
  return store.isConnected ? 'success' : 'danger'
})

const connectionText = computed(() => {
  return store.isConnected ? '已连接' : '未连接'
})

// 判断当前推理结果是否为图像
const isCurrentInferenceImage = computed(() => {
  if (!currentInference.value) return false
  
  // 检查是否有type字段
  if (currentInference.value.type === 'image') return true
  
  // 检查是否有frame_number字段（图像模式特有）
  if (currentInference.value.frame_number !== undefined) return true
  
  // 检查文件扩展名
  const filename = currentInference.value.filename || currentInference.value.video_path || ''
  return /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(filename)
})

const parsedResult = computed(() => {
  if (!currentInference.value) return null
  
  // 新格式：直接从推理结果中获取信息
  if (currentInference.value.sampled_frames) {
    return {
      people_count: currentInference.value.sampled_frames?.length || 0,
      summary: `视频包含 ${currentInference.value.total_frames} 帧，采样了 ${currentInference.value.sampled_frames?.length || 0} 帧`,
      video_path: currentInference.value.video_path,
      creation_time: currentInference.value.creation_time
    }
  }
  
  // 旧格式：从result字段解析JSON
  if (!currentInference.value.result) return null
  
  try {
    let resultText = currentInference.value.result
    
    if (resultText.includes('```json')) {
      const start = resultText.indexOf('```json') + 7
      const end = resultText.indexOf('```', start)
      if (end > start) {
        resultText = resultText.substring(start, end).trim()
      }
    }
    
    return JSON.parse(resultText)
  } catch (error) {
    console.error('解析推理结果失败:', error)
    return null
  }
})

onMounted(async () => {
  console.log('🎬 MonitorView 组件已挂载')
  
  // 初始化WebSocket连接
  await initializeWebSocket()
  
  // 加载初始数据
  await loadMediaHistory()
  
  // 加载哨兵模式状态
  await loadSentryModeStatus()
  
  // 设置自动刷新历史记录的定时器（每10秒刷新一次）
  const historyRefreshInterval = setInterval(async () => {
    if (!isLoadingHistory.value) {
      console.log('⏰ 定时刷新历史记录...')
      await loadMediaHistory()
    }
  }, 10000) // 10秒刷新一次，避免过于频繁
  
  // 保存定时器引用以便清理
  ;(window as any).historyRefreshInterval = historyRefreshInterval
})

onUnmounted(() => {
  console.log('🔌 MonitorView 组件即将卸载，清理资源...')
  
  // 清理WebSocket连接
  websocketService.disconnect()
  
  // 清理定时器
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval)
    statusCheckInterval = null
  }
  
  if (inferenceCheckInterval) {
    clearInterval(inferenceCheckInterval)
    inferenceCheckInterval = null
  }
  
  // 清理重连定时器
  if ((window as any).historyRefreshInterval) {
    clearInterval((window as any).historyRefreshInterval)
    delete (window as any).historyRefreshInterval
  }
})

// WebSocket视频帧处理函数
function onVideoFrameReceived(frameData: any) {
  console.log('🎥 收到视频帧')
  streamLoaded.value = true
  
  // 高性能FPS计算
  const now = performance.now()  // 使用高精度时间
  frameLoadTimes.push(now)
  
  // 保持最近60帧的时间记录（减少内存使用）
  if (frameLoadTimes.length > 60) {
    frameLoadTimes = frameLoadTimes.slice(-60)
  }
  
  // 每200ms更新一次FPS显示（提高响应性）
  if (now - lastFpsUpdate > 200) {
    // 计算最近1秒内的帧数
    const oneSecondAgo = now - 1000
    const recentFrames = frameLoadTimes.filter(time => time > oneSecondAgo)
    streamFps.value = recentFrames.length
    lastFpsUpdate = now
    
    // 性能优化：如果FPS过低，提示用户（调整阈值以适应低帧率摄像头）
    if (streamFps.value < 2 && frameLoadTimes.length > 10) {
      console.warn(`⚠️ 视频流FPS较低: ${streamFps.value}fps，可能需要优化`)
    }
  }
  
  // 在canvas上绘制视频帧
  drawVideoFrame(frameData)
}

function drawVideoFrame(frameData: any) {
  if (!liveVideoCanvas.value) return
  
  const canvas = liveVideoCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  try {
    // 创建图像对象
    const img = new Image()
    img.onload = () => {
      // 计算适合canvas的尺寸，保持纵横比
      const canvasWidth = canvas.width
      const canvasHeight = canvas.height
      const imgAspect = img.width / img.height
      const canvasAspect = canvasWidth / canvasHeight
      
      let drawWidth, drawHeight, drawX, drawY
      
      if (imgAspect > canvasAspect) {
        // 图像更宽，以宽度为准
        drawWidth = canvasWidth
        drawHeight = canvasWidth / imgAspect
        drawX = 0
        drawY = (canvasHeight - drawHeight) / 2
      } else {
        // 图像更高，以高度为准
        drawHeight = canvasHeight
        drawWidth = canvasHeight * imgAspect
        drawX = (canvasWidth - drawWidth) / 2
        drawY = 0
      }
      
      // 清空canvas并绘制新帧
      ctx.clearRect(0, 0, canvasWidth, canvasHeight)
      ctx.drawImage(img, drawX, drawY, drawWidth, drawHeight)
    }
    
    // 设置base64图像数据
    img.src = `data:image/jpeg;base64,${frameData.data}`
    
  } catch (error) {
    console.error('❌ 绘制视频帧失败:', error)
  }
}

function onStreamError() {
  console.error('❌ 视频流错误')
  streamLoaded.value = false
  streamFps.value = 0
  
  // 清空FPS计算数据
  frameLoadTimes = []
}

function onCanvasClick() {
  if (!store.isStreaming) {
    startStream()
  }
}

async function initializeWebSocket() {
  console.log('初始化WebSocket连接...')
  
  // 设置WebSocket事件回调
  websocketService.onConnected(() => {
    console.log('✅ WebSocket连接成功')
    store.setConnectionStatus(true)
  })
  
  websocketService.onDisconnected(() => {
    console.log('❌ WebSocket连接断开')
    store.setConnectionStatus(false)
  })
  
  websocketService.onFrame((frame) => {
    console.log('📹 收到视频帧:', frame.frame_number)
    store.updateCurrentFrame(frame)
    // 处理实时视频显示
    onVideoFrameReceived(frame)
  })
  
  websocketService.onInference((inference) => {
    console.log('🤖 收到推理结果')
    store.addInferenceResult(inference)
  })
  
  websocketService.onStatus((status) => {
    console.log('📊 收到状态更新:', status)
  })
  
  websocketService.onError((error) => {
    console.error('❌ WebSocket错误:', error)
  })
  
  // 尝试连接
  const connected = await websocketService.connect()
  if (connected) {
    console.log('🎉 WebSocket连接建立成功')
  } else {
    console.warn('⚠️ WebSocket连接失败，将稍后重试')
  }
}

async function loadExperimentLog() {
  console.log('加载实验日志...')
  try {
    const response = await apiService.getExperimentLog()
    console.log('API响应:', response.success ? 200 : 'error', '/experiment-log')
    
    if (response.success && response.data) {
      console.log('✅ 实验日志加载成功')
      store.initializeFromExperimentLog(response.data)
    } else {
      console.warn('⚠️ 实验日志加载失败:', response.error)
      // 尝试获取推理历史
      await loadInferenceHistory()
    }
  } catch (error) {
    console.warn('❌ 加载历史数据失败:', error)
    // 尝试获取推理历史
    await loadInferenceHistory()
  }
}

async function loadInferenceHistory() {
  console.log('加载推理历史...')
  try {
    const response = await apiService.getInferenceHistory(20)
    if (response.success && response.data) {
      console.log('✅ 推理历史加载成功，数量:', response.data.length)
      // 将推理历史数据转换为实验日志格式
      const experimentLog = {
        session_id: 'current',
        start_time: response.data.length > 0 ? (response.data[0] as any).timestamp || (response.data[0] as any).creation_timestamp : null,
        inference_log: response.data,
        total_inferences: response.data.length,
        status: 'running'
      }
      store.initializeFromExperimentLog(experimentLog)
    } else {
      console.warn('⚠️ 推理历史加载失败:', response.error)
    }
  } catch (error) {
    console.warn('❌ 加载推理历史失败:', error)
  }
}

async function loadLatestInference() {
  try {
    // 优先获取最新的已完成AI分析且有MCP结果的推理结果
    const aiResponse = await apiService.getLatestInferenceWithAI()
    if (aiResponse.success && aiResponse.data) {
      console.log('✅ 获取到最新完整推理结果用于播放:', (aiResponse.data as any).filename || (aiResponse.data as any).video_id, '时间:', (aiResponse.data as any).creation_timestamp || (aiResponse.data as any).timestamp)
      store.addInferenceResult(aiResponse.data)
      return
    }
    
    // 如果没有完整的推理结果，检查是否有任何推理结果（用于显示状态）
    const response = await apiService.getLatestInference()
    if (response.success && response.data) {
      console.log('✅ 获取到推理结果（等待完整分析）:', (response.data as any).video_id, '时间:', (response.data as any).creation_timestamp)
      // 只更新状态，但不用于播放
      store.addInferenceResult(response.data)
      
      // 如果没有完整的推理结果，继续使用之前有完整结果的进行播放
      if (!response.data.has_inference_result) {
        console.log('⏳ 当前推理结果还在等待完整分析（AI分析+MCP行动），继续播放上一个完整结果')
      }
    } else {
      console.log('⚠️ 没有获取到推理结果:', response.error)
    }
  } catch (error) {
    console.debug('获取最新推理结果失败:', error)
  }
}

async function checkInferenceCount() {
  try {
    const response = await apiService.get('/inference-count')
    if (response.success && response.data) {
      const currentCount = store.stats.inferenceCount
      const newCount = response.data.count
      
      console.log(`🔍 检查推理数量: 当前=${currentCount}, 服务器=${newCount}, 会话=${response.data.session_dir}`)
      
      if (newCount > currentCount) {
        console.log(`🆕 发现新推理结果: ${currentCount} -> ${newCount}`)
        await loadLatestInference()
        await loadInferenceHistory()  // 重新加载历史记录
      } else if (newCount > 0 && currentCount === 0) {
        // 初次加载时也要获取推理结果
        console.log(`🔄 初次加载推理结果: ${newCount}`)
        await loadLatestInference()
        await loadInferenceHistory()
      } else if (newCount > 0) {
        // 检查最新推理结果是否有AI分析结果
        await checkLatestInferenceResult()
      }
    }
  } catch (error) {
    console.debug('检查推理数量失败:', error)
  }
}

async function checkLatestInferenceResult() {
  try {
    // 首先检查是否有新的AI分析完成的推理结果
    const aiResponse = await apiService.getLatestInferenceWithAI()
    if (aiResponse.success && aiResponse.data) {
      const latestAIResult = aiResponse.data
      const currentResult = store.latestInference
      
      // 检查是否是新的AI分析结果
      if (!currentResult || 
          latestAIResult.video_id !== currentResult.video_id ||
          (latestAIResult.has_inference_result && !currentResult.has_inference_result)) {
        
        console.log(`🔄 AI分析结果更新: ${latestAIResult.video_id}, AI分析: ${latestAIResult.has_inference_result}`)
        store.addInferenceResult(latestAIResult)
        
        if (latestAIResult.has_inference_result) {
          console.log(`✅ AI分析完成: 检测到${latestAIResult.people_count}人, ${latestAIResult.summary}`)
        }
        return
      }
    }
    
    // 如果没有新的AI分析结果，检查是否有新的推理结果（可能还在等待AI分析）
    const response = await apiService.getLatestInference()
    if (response.success && response.data) {
      const latestResult = response.data
      const currentResult = store.latestInference
      
      // 检查是否是新的推理结果或者AI分析状态发生变化
      if (!currentResult || 
          latestResult.video_id !== currentResult.video_id ||
          latestResult.has_inference_result !== currentResult.has_inference_result) {
        
        console.log(`🔄 推理结果状态更新: ${latestResult.video_id}, AI分析: ${latestResult.has_inference_result}`)
        store.addInferenceResult(latestResult)
        
        if (latestResult.has_inference_result) {
          console.log(`✅ AI分析完成: 检测到${latestResult.people_count}人, ${latestResult.summary}`)
        }
      }
    }
  } catch (error) {
    console.debug('检查最新推理结果失败:', error)
  }
}

async function checkSystemStatus() {
  try {
    const response = await apiService.getSystemStatus()
    if (response.success) {
      console.log('📊 系统状态:', response.data)
    }
  } catch (error) {
    console.warn('检查系统状态失败:', error)
  }
}

async function refreshData() {
  isLoading.value = true
  try {
    await loadExperimentLog()
    await loadLatestInference()
    console.log('✅ 数据刷新完成')
  } catch (error) {
    console.error('❌ 数据刷新失败')
  } finally {
    isLoading.value = false
  }
}

async function clearHistory() {
  try {
    const response = await apiService.clearHistory()
    if (response.success) {
      store.clearAllData()
      console.log('✅ 历史数据已清空')
    }
  } catch (error) {
    console.error('❌ 清空历史失败')
  }
}

async function startStream() {
  console.log('🚀 开始视频流...')
  
  if (!store.isConnected) {
    console.warn('WebSocket未连接，尝试重新连接...')
    await initializeWebSocket()
  }
  
  if (store.isConnected) {
    websocketService.startVideoStream()
    store.setStreamingStatus(true)
    console.log('✅ 视频流启动请求已发送')
  } else {
    console.error('❌ 无法启动视频流：WebSocket未连接')
  }
}

async function stopStream() {
  console.log('⏹️ 停止视频流...')
  websocketService.stopVideoStream()
  store.setStreamingStatus(false)
  console.log('✅ 视频流停止请求已发送')
}

// 哨兵模式相关函数
async function loadSentryModeStatus() {
  try {
    const response = await sentryModeApi.getStatus()
    if (response.success && response.data) {
      sentryModeEnabled.value = response.data.enabled
      console.log('🛡️ 哨兵模式状态已加载:', response.data.status)
    }
  } catch (error) {
    console.error('❌ 加载哨兵模式状态失败:', error)
  }
}

async function toggleSentryMode() {
  if (sentryModeLoading.value) return
  
  sentryModeLoading.value = true
  try {
    const response = await sentryModeApi.toggle()
    if (response.success && response.data) {
      sentryModeEnabled.value = response.data.enabled
      console.log('🛡️ 哨兵模式已切换:', response.data.message)
      
      // 可以在这里添加成功提示
      // showNotification(response.data.message, 'success')
    } else {
      console.error('❌ 切换哨兵模式失败:', response.error)
      // showNotification('切换哨兵模式失败', 'error')
    }
  } catch (error) {
    console.error('❌ 切换哨兵模式失败:', error)
    // showNotification('切换哨兵模式失败', 'error')
  } finally {
    sentryModeLoading.value = false
  }
}

function formatTime(timestamp: number | string): string {
  if (!timestamp) return '未知时间'
  
  let date: Date
  
  if (typeof timestamp === 'string') {
    // ISO格式时间戳
    date = new Date(timestamp)
  } else {
    // Unix时间戳（秒）
    date = new Date(timestamp * 1000)
  }
  
  if (isNaN(date.getTime())) {
    return '无效时间'
  }
  
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatLatency(timestamp: number): number {
  const now = Date.now() / 1000
  return Math.round((now - timestamp) * 1000)
}

function getInferenceTime(inference: any): number | string {
  // 优先使用creation_timestamp（ISO格式）
  if (inference.creation_timestamp) {
    return inference.creation_timestamp
  }
  
  // 其次使用timestamp字段
  if (inference.timestamp) {
    return inference.timestamp
  }
  
  // 最后使用inference_end_time
  if (inference.inference_end_time) {
    return inference.inference_end_time
  }
  
  return Date.now() / 1000
}

function getInferenceDuration(inference: any): string {
  const duration = inference.inference_duration || inference.creation_time || 0
  return (Math.round(duration * 100) / 100).toString()
}

function extractAIResponse(rawResult: string): string {
  if (!rawResult) return ''
  
  // 如果raw_result包含用户问题的回答，尝试提取
  // 这里可以根据实际的AI回答格式进行调整
  
  // 方法1: 如果AI回答在JSON之外的文本中
  if (rawResult.includes('```json')) {
    const beforeJson = rawResult.substring(0, rawResult.indexOf('```json')).trim()
    const afterJson = rawResult.substring(rawResult.lastIndexOf('```') + 3).trim()
    
    // 优先返回JSON前的文本（通常是对用户问题的直接回答）
    if (beforeJson && beforeJson.length > 10) {
      return beforeJson
    }
    
    // 其次返回JSON后的文本
    if (afterJson && afterJson.length > 10) {
      return afterJson
    }
  }
  
  // 方法2: 如果整个raw_result就是回答文本（没有JSON结构）
  if (!rawResult.includes('```json') && !rawResult.includes('{') && rawResult.length > 10) {
    return rawResult.trim()
  }
  
  // 方法3: 尝试从JSON中提取response字段
  try {
    let jsonText = rawResult
    if (rawResult.includes('```json')) {
      const start = rawResult.indexOf('```json') + 7
      const end = rawResult.indexOf('```', start)
      if (end > start) {
        jsonText = rawResult.substring(start, end).trim()
      }
    }
    
    const parsed = JSON.parse(jsonText)
    if (parsed.response) {
      return parsed.response
    }
    if (parsed.answer) {
      return parsed.answer
    }
    if (parsed.user_response) {
      return parsed.user_response
    }
  } catch (e) {
    // JSON解析失败，忽略
  }
  
  return ''
}

function getVideoFileName(videoPath: string): string {
  if (!videoPath) return ''
  const parts = videoPath.split('/')
  return parts[parts.length - 1]
}

function getVideoUrl(videoPath: string): string {
  if (!videoPath) return ''
  
  const filename = getVideoFileName(videoPath)
  
  // 在开发环境中，直接指向后端服务器
  if (import.meta.env.DEV) {
    return `http://localhost:8080/api/videos/${filename}`
  }
  
  // 在生产环境中，使用相对路径（通过代理）
  return `/api/videos/${filename}`
}

function onVideoLoaded() {
  const video = inferenceVideo.value
  if (!video) return
  
  console.log('📹 推理视频加载完成:', {
    videoWidth: video.videoWidth,
    videoHeight: video.videoHeight,
    clientWidth: video.clientWidth,
    clientHeight: video.clientHeight,
    readyState: video.readyState,
    duration: video.duration,
    src: video.src
  })
  
  // 视频加载完成后绘制bbox
  nextTick(() => {
    drawBboxOverlay()
  })
}

function onVideoResize() {
  console.log('📹 视频尺寸变化，重新绘制bbox')
  nextTick(() => {
    drawBboxOverlay()
  })
}

function toggleBboxDisplay() {
  showBbox.value = !showBbox.value
  drawBboxOverlay()
}

function drawBboxOverlay() {
  if (!bboxCanvas.value || !currentInference.value) return
  
  const canvas = bboxCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  let mediaElement: HTMLVideoElement | HTMLImageElement | null = null
  let mediaWidth = 0
  let mediaHeight = 0
  let containerWidth = 0
  let containerHeight = 0
  
  // 根据当前推理结果类型获取对应的媒体元素
  if (isCurrentInferenceImage.value) {
    // 图像模式
    mediaElement = document.querySelector('.inference-image') as HTMLImageElement
    if (!mediaElement || !mediaElement.complete) {
      console.log('⏳ 图像未加载完成，等待中...')
      return
    }
    mediaWidth = mediaElement.naturalWidth
    mediaHeight = mediaElement.naturalHeight
    containerWidth = mediaElement.clientWidth
    containerHeight = mediaElement.clientHeight
  } else {
    // 视频模式
    mediaElement = inferenceVideo.value
    if (!mediaElement || (mediaElement as HTMLVideoElement).readyState < 1) {
      console.log('⏳ 视频元数据未加载完成，等待中...')
      return
    }
    mediaWidth = (mediaElement as HTMLVideoElement).videoWidth
    mediaHeight = (mediaElement as HTMLVideoElement).videoHeight
    containerWidth = mediaElement.clientWidth
    containerHeight = mediaElement.clientHeight
  }
  
  if (!mediaElement || mediaWidth === 0 || mediaHeight === 0) {
    console.warn('⚠️ 媒体元素尺寸无效')
    return
  }
  
  console.log(`📐 ${isCurrentInferenceImage.value ? '图像' : '视频'}显示计算详情:`, {
    mediaOriginal: { 
      width: mediaWidth, 
      height: mediaHeight
    },
    container: { 
      width: containerWidth, 
      height: containerHeight
    }
  })
  
  // 设置canvas尺寸与容器一致（现在容器就是媒体的实际显示尺寸）
  canvas.width = containerWidth
  canvas.height = containerHeight
  
  // 设置canvas样式尺寸
  canvas.style.width = `${containerWidth}px`
  canvas.style.height = `${containerHeight}px`
  
  // 设置canvas的绝对定位，覆盖整个媒体元素
  canvas.style.position = 'absolute'
  canvas.style.top = '0px'
  canvas.style.left = '0px'
  
  // 清除之前的绘制
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  if (!showBbox.value || (!currentInference.value.people && !currentInference.value.vehicles)) return
  
  const totalObjects = (currentInference.value.people?.length || 0) + (currentInference.value.vehicles?.length || 0)
  
  console.log('📏 bbox绘制信息:', {
    peopleCount: currentInference.value.people?.length || 0,
    vehicleCount: currentInference.value.vehicles?.length || 0,
    totalObjects: totalObjects,
    canvasSize: { 
      width: containerWidth, 
      height: containerHeight
    }
  })
  
  // 坐标转换函数：将模型坐标转换为显示坐标
  function convertModelCoordsToDisplay(modelX: number, modelY: number): [number, number] {
    // 获取图像尺寸信息
    const imageDimensions = currentInference.value.image_dimensions
    
    if (imageDimensions && imageDimensions.model_width > 0 && imageDimensions.model_height > 0) {
      // 图像模式：有尺寸信息，进行坐标转换
      const modelWidth = imageDimensions.model_width
      const modelHeight = imageDimensions.model_height
      
      // 将模型坐标转换为相对坐标(0-1)
      const relativeX = modelX / modelWidth
      const relativeY = modelY / modelHeight
      
      // 将相对坐标转换为显示坐标（直接映射到容器尺寸）
      const displayX = relativeX * containerWidth
      const displayY = relativeY * containerHeight
      
      console.log(`🔄 坐标转换: 模型(${modelX}, ${modelY}) -> 相对(${relativeX.toFixed(3)}, ${relativeY.toFixed(3)}) -> 显示(${displayX.toFixed(1)}, ${displayY.toFixed(1)})`)
      console.log(`📐 尺寸信息: 模型${modelWidth}x${modelHeight}, 容器${containerWidth}x${containerHeight}`)
      
      return [displayX, displayY]
    } else {
      // 视频模式或没有尺寸信息：假设坐标已经是相对坐标(0-1)
      if (modelX >= 0 && modelX <= 1 && modelY >= 0 && modelY <= 1) {
        const displayX = modelX * containerWidth
        const displayY = modelY * containerHeight
        
        console.log(`🔄 相对坐标转换: (${modelX}, ${modelY}) -> 显示(${displayX.toFixed(1)}, ${displayY.toFixed(1)})`)
        
        return [displayX, displayY]
      } else {
        // 绝对坐标，根据媒体原始尺寸进行转换
        const relativeX = modelX / mediaWidth
        const relativeY = modelY / mediaHeight
        const displayX = relativeX * containerWidth
        const displayY = relativeY * containerHeight
        
        console.log(`🔄 绝对坐标转换: (${modelX}, ${modelY}) -> 相对(${relativeX.toFixed(3)}, ${relativeY.toFixed(3)}) -> 显示(${displayX.toFixed(1)}, ${displayY.toFixed(1)})`)
        console.log(`📐 媒体尺寸: ${mediaWidth}x${mediaHeight}, 容器尺寸: ${containerWidth}x${containerHeight}`)
        
        return [displayX, displayY]
      }
    }
  }
  
  // 绘制每个人的bbox
  if (currentInference.value.people) {
    currentInference.value.people.forEach((person: any, index: number) => {
      if (!person.bbox) return
      
      const [x1, y1, x2, y2] = person.bbox
      
      // 转换坐标
      const [displayX1, displayY1] = convertModelCoordsToDisplay(x1, y1)
      const [displayX2, displayY2] = convertModelCoordsToDisplay(x2, y2)
      
      const boxX = Math.min(displayX1, displayX2)
      const boxY = Math.min(displayY1, displayY2)
      const boxWidth = Math.abs(displayX2 - displayX1)
      const boxHeight = Math.abs(displayY2 - displayY1)
      
      // 边界检查（确保在媒体显示区域内）
      const clampedBoxX = Math.max(0, Math.min(boxX, containerWidth - 1))
      const clampedBoxY = Math.max(0, Math.min(boxY, containerHeight - 1))
      const clampedBoxWidth = Math.max(1, Math.min(boxWidth, containerWidth - clampedBoxX))
      const clampedBoxHeight = Math.max(1, Math.min(boxHeight, containerHeight - clampedBoxY))
      
      console.log(`👤 人员${index + 1} bbox绘制:`, {
        原始坐标: [x1, y1, x2, y2],
        显示坐标: [displayX1.toFixed(1), displayY1.toFixed(1), displayX2.toFixed(1), displayY2.toFixed(1)],
        计算框: { x: boxX.toFixed(1), y: boxY.toFixed(1), w: boxWidth.toFixed(1), h: boxHeight.toFixed(1) },
        限制框: { x: clampedBoxX.toFixed(1), y: clampedBoxY.toFixed(1), w: clampedBoxWidth.toFixed(1), h: clampedBoxHeight.toFixed(1) },
        显示区域: { w: containerWidth.toFixed(1), h: containerHeight.toFixed(1) }
      })
      
      // 只有当bbox有有效尺寸时才绘制
      if (clampedBoxWidth > 2 && clampedBoxHeight > 2) {
        // 设置人员样式（红色）
        ctx.strokeStyle = '#ff4757'
        ctx.lineWidth = 3
        ctx.fillStyle = 'rgba(255, 71, 87, 0.1)'
        
        // 绘制矩形
        ctx.fillRect(clampedBoxX, clampedBoxY, clampedBoxWidth, clampedBoxHeight)
        ctx.strokeRect(clampedBoxX, clampedBoxY, clampedBoxWidth, clampedBoxHeight)
        
        // 绘制标签
        const label = `人${person.id || (index + 1)}: ${person.activity || '未知'}`
        ctx.fillStyle = '#ff4757'
        ctx.font = '14px Arial'
        
        // 标签背景
        const textMetrics = ctx.measureText(label)
        const labelX = Math.max(0, Math.min(clampedBoxX, containerWidth - textMetrics.width - 8))
        const labelY = Math.max(20, clampedBoxY)
        
        ctx.fillRect(labelX, labelY - 20, textMetrics.width + 8, 20)
        
        // 标签文字
        ctx.fillStyle = 'white'
        ctx.fillText(label, labelX + 4, labelY - 6)
      } else {
        console.warn(`⚠️ 人员${index + 1} bbox尺寸过小，跳过绘制`)
      }
    })
  }
  
  // 绘制每个车辆的bbox
  if (currentInference.value.vehicles) {
    currentInference.value.vehicles.forEach((vehicle: any, index: number) => {
      if (!vehicle.bbox) return
      
      const [x1, y1, x2, y2] = vehicle.bbox
      
      // 转换坐标
      const [displayX1, displayY1] = convertModelCoordsToDisplay(x1, y1)
      const [displayX2, displayY2] = convertModelCoordsToDisplay(x2, y2)
      
      const boxX = Math.min(displayX1, displayX2)
      const boxY = Math.min(displayY1, displayY2)
      const boxWidth = Math.abs(displayX2 - displayX1)
      const boxHeight = Math.abs(displayY2 - displayY1)
      
      // 边界检查（确保在媒体显示区域内）
      const clampedBoxX = Math.max(0, Math.min(boxX, containerWidth - 1))
      const clampedBoxY = Math.max(0, Math.min(boxY, containerHeight - 1))
      const clampedBoxWidth = Math.max(1, Math.min(boxWidth, containerWidth - clampedBoxX))
      const clampedBoxHeight = Math.max(1, Math.min(boxHeight, containerHeight - clampedBoxY))
      
      console.log(`🚗 车辆${index + 1} bbox绘制:`, {
        原始坐标: [x1, y1, x2, y2],
        显示坐标: [displayX1.toFixed(1), displayY1.toFixed(1), displayX2.toFixed(1), displayY2.toFixed(1)],
        计算框: { x: boxX.toFixed(1), y: boxY.toFixed(1), w: boxWidth.toFixed(1), h: boxHeight.toFixed(1) },
        限制框: { x: clampedBoxX.toFixed(1), y: clampedBoxY.toFixed(1), w: clampedBoxWidth.toFixed(1), h: clampedBoxHeight.toFixed(1) },
        显示区域: { w: containerWidth.toFixed(1), h: containerHeight.toFixed(1) }
      })
      
      // 只有当bbox有有效尺寸时才绘制
      if (clampedBoxWidth > 2 && clampedBoxHeight > 2) {
        // 设置车辆样式（绿色）
        ctx.strokeStyle = '#2ed573'
        ctx.lineWidth = 3
        ctx.fillStyle = 'rgba(46, 213, 115, 0.1)'
        
        // 绘制矩形
        ctx.fillRect(clampedBoxX, clampedBoxY, clampedBoxWidth, clampedBoxHeight)
        ctx.strokeRect(clampedBoxX, clampedBoxY, clampedBoxWidth, clampedBoxHeight)
        
        // 绘制标签
        const label = `${vehicle.type || '车辆'}${vehicle.id || (index + 1)}: ${vehicle.status || '未知'}`
        ctx.fillStyle = '#2ed573'
        ctx.font = '14px Arial'
        
        // 标签背景
        const textMetrics = ctx.measureText(label)
        const labelX = Math.max(0, Math.min(clampedBoxX, containerWidth - textMetrics.width - 8))
        const labelY = Math.max(20, clampedBoxY)
        
        ctx.fillRect(labelX, labelY - 20, textMetrics.width + 8, 20)
        
        // 标签文字
        ctx.fillStyle = 'white'
        ctx.fillText(label, labelX + 4, labelY - 6)
      } else {
        console.warn(`⚠️ 车辆${index + 1} bbox尺寸过小，跳过绘制`)
      }
    })
  }
}

// 监听推理结果变化，重新绘制bbox
watch(currentInference, () => {
  nextTick(() => {
    drawBboxOverlay()
  })
}, { deep: true })

async function debugVideos() {
  try {
    console.log('🔍 开始调试视频文件...')
    
    // 调试当前推理结果
    if (currentInference.value) {
      console.log('🤖 当前推理结果详情:', {
        video_id: currentInference.value.video_id,
        has_inference_result: currentInference.value.has_inference_result,
        people_count: currentInference.value.people_count,
        people: currentInference.value.people,
        video_path: currentInference.value.video_path,
        summary: currentInference.value.summary
      })
      
      if (currentInference.value.people && currentInference.value.people.length > 0) {
        console.log('👥 人员检测详情:')
        currentInference.value.people.forEach((person: any, index: number) => {
          console.log(`  人员${index + 1}:`, {
            id: person.id,
            activity: person.activity,
            bbox: person.bbox,
            bbox_range: person.bbox ? {
              x_range: `${person.bbox[0]} - ${person.bbox[2]}`,
              y_range: `${person.bbox[1]} - ${person.bbox[3]}`,
              width: person.bbox[2] - person.bbox[0],
              height: person.bbox[3] - person.bbox[1]
            } : null
          })
        })
      }
    }
    
    // 首先测试后端连接
    console.log('🔗 测试后端连接...')
    try {
      const healthResponse = await fetch('http://localhost:8080/health')
      if (healthResponse.ok) {
        const healthData = await healthResponse.json()
        console.log('✅ 后端服务正常:', healthData)
      } else {
        console.error('❌ 后端服务响应异常:', healthResponse.status)
        return
      }
    } catch (error) {
      console.error('❌ 无法连接到后端服务:', error)
      console.log('💡 请确保后端服务运行在 http://localhost:8080')
      return
    }
    
    const response = await apiService.get('/debug/videos')
    if (response.success) {
      console.log('📹 视频调试信息:', response.data)
      
      // 检查当前推理结果的视频文件
      if (currentInference.value?.video_path) {
        const videoFileName = getVideoFileName(currentInference.value.video_path)
        const videoUrl = getVideoUrl(currentInference.value.video_path)
        
        console.log('🎬 当前视频信息:', {
          video_path: currentInference.value.video_path,
          video_filename: videoFileName,
          video_url: videoUrl,
          has_inference_result: currentInference.value.has_inference_result
        })
        
        // 测试视频文件直接访问
        console.log('🔗 测试视频文件访问...')
        try {
          // 使用Range请求来测试文件访问，只请求第一个字节
          const videoTestResponse = await fetch(videoUrl, { 
            method: 'GET',
            headers: {
              'Range': 'bytes=0-0'
            }
          })
          if (videoTestResponse.ok || videoTestResponse.status === 206) {
            console.log('✅ 视频文件可访问:', {
              status: videoTestResponse.status,
              contentType: videoTestResponse.headers.get('content-type'),
              contentLength: videoTestResponse.headers.get('content-length'),
              contentRange: videoTestResponse.headers.get('content-range')
            })
          } else {
            console.error('❌ 视频文件访问失败:', videoTestResponse.status, videoTestResponse.statusText)
          }
        } catch (error) {
          console.error('❌ 视频文件访问异常:', error)
        }
        
        // 检查视频文件是否在可用列表中
        const availableVideos = response.data.videos || []
        const videoExists = availableVideos.some((v: any) => v.filename === videoFileName)
        console.log('📁 视频文件存在:', videoExists)
        
        if (!videoExists) {
          console.warn('⚠️ 当前视频文件不在可用列表中')
          console.log('📋 可用视频文件:', availableVideos.map((v: any) => v.filename))
        }
      }
    } else {
      console.error('❌ 获取视频调试信息失败:', response.error)
    }
  } catch (error) {
    console.error('❌ 调试视频失败:', error)
  }
}

function onVideoError(event: Event) {
  const video = event.target as HTMLVideoElement
  console.error('❌ 视频加载错误:', {
    src: video.src,
    error: video.error?.code,
    errorMessage: getVideoErrorMessage(video.error?.code),
    networkState: video.networkState,
    readyState: video.readyState,
    currentInference: currentInference.value?.video_id
  })
  
  // 调试当前视频信息
  debugVideos()
}

function getVideoErrorMessage(errorCode?: number): string {
  if (!errorCode) return '未知错误'
  
  const errorMessages: { [key: number]: string } = {
    1: 'MEDIA_ERR_ABORTED - 用户中止了视频加载',
    2: 'MEDIA_ERR_NETWORK - 网络错误导致视频下载失败',
    3: 'MEDIA_ERR_DECODE - 视频解码错误',
    4: 'MEDIA_ERR_SRC_NOT_SUPPORTED - 视频格式不支持或文件不存在'
  }
  
  return errorMessages[errorCode] || `未知错误代码: ${errorCode}`
}

function onVideoLoadStart() {
  const videoUrl = getVideoUrl(currentInference.value?.video_path || '')
  console.log('📹 视频开始加载:', {
    video_path: currentInference.value?.video_path,
    video_url: videoUrl,
    video_id: currentInference.value?.video_id
  })
}

// 历史记录相关函数
async function loadMediaHistory() {
  isLoadingHistory.value = true
  try {
    console.log('🔄 加载媒体历史记录...')
    const response = await apiService.getMediaHistory(30)
    if (response.success && response.data) {
      const newMediaHistory = response.data.media_items || []
      console.log('✅ 媒体历史记录加载成功:', newMediaHistory.length, '项')
      
      // 检查是否有新的媒体项目
      const hasNewItems = newMediaHistory.length > mediaHistory.value.length ||
        (newMediaHistory.length > 0 && mediaHistory.value.length > 0 && 
         newMediaHistory[0].filename !== mediaHistory.value[0].filename)
      
      mediaHistory.value = newMediaHistory
      
      // 如果有新项目或者当前没有选中项目，自动选择最新的有推理结果的项目
      if (hasNewItems || !selectedHistoryItem.value) {
        autoSelectLatestInferenceItem()
      }
    } else {
      console.warn('⚠️ 媒体历史记录加载失败:', response.error)
      mediaHistory.value = []
    }
  } catch (error) {
    console.error('❌ 加载媒体历史记录失败:', error)
    mediaHistory.value = []
  } finally {
    isLoadingHistory.value = false
  }
}

function autoSelectLatestInferenceItem() {
  // 查找最新的有推理结果的项目（按时间戳排序，最新的在前）
  const inferenceItems = mediaHistory.value.filter(item => item.has_inference_result)
  const latestInferenceItem = inferenceItems.length > 0 ? inferenceItems[0] : null
  
  if (latestInferenceItem) {
    // 只有当选中的项目不同时才切换
    if (!selectedHistoryItem.value || selectedHistoryItem.value.filename !== latestInferenceItem.filename) {
      console.log('🎯 自动选择最新的推理结果:', {
        filename: latestInferenceItem.filename,
        type: latestInferenceItem.type,
        people_count: latestInferenceItem.people_count || 0,
        vehicle_count: latestInferenceItem.vehicle_count || 0,
        time: formatHistoryTime(latestInferenceItem.timestamp || latestInferenceItem.creation_timestamp)
      })
      selectHistoryItem(latestInferenceItem)
    } else {
      console.log('📋 最新推理结果已选中，无需切换')
    }
  } else {
    console.log('📋 暂无推理结果，选择最新的媒体项目')
    // 如果没有推理结果，选择最新的项目
    if (mediaHistory.value.length > 0) {
      const latestItem = mediaHistory.value[0]
      if (!selectedHistoryItem.value || selectedHistoryItem.value.filename !== latestItem.filename) {
        console.log('📄 选择最新媒体项目:', latestItem.filename, latestItem.type)
        selectHistoryItem(latestItem)
      }
    }
  }
}

function selectHistoryItem(item: any) {
  selectedHistoryItem.value = item
  console.log('📋 选择历史项目:', item.filename, item.type)
  
  // 更新当前推理结果为选中的历史项目
  const historyInference = {
    ...item,
    video_path: item.media_path,
    video_id: item.filename.replace(/\.(mp4|jpg|jpeg|png)$/, ''),
    creation_timestamp: item.timestamp_iso || item.creation_timestamp,
    has_inference_result: item.has_inference_result
  }
  
  // 使用store的方法来设置当前播放的推理结果
  store.addInferenceResult(historyInference)
  
  console.log('🎬 切换到历史推理结果:', historyInference.video_id)
}

function getMediaUrl(filename: string): string {
  return apiService.getMediaUrl(filename)
}

function formatHistoryTime(timestamp: number | string): string {
  if (!timestamp) return '未知时间'
  
  let date: Date
  
  if (typeof timestamp === 'string') {
    // ISO格式时间戳
    date = new Date(timestamp)
  } else {
    // Unix时间戳（秒）
    date = new Date(timestamp * 1000)
  }
  
  if (isNaN(date.getTime())) {
    return '无效时间'
  }
  
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function onThumbnailError(event: Event) {
  const target = event.target as HTMLImageElement | HTMLVideoElement
  console.warn('⚠️ 缩略图加载失败:', target.src)
}
</script>

<style scoped>
.monitor-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e6e6e6;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.monitor-header h1 {
  margin: 0;
  color: #303133;
  font-size: 1.8rem;
}

.header-controls {
  display: flex;
  gap: 8px;
}

/* 哨兵模式按钮样式 */
.sentry-mode-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.3s ease;
  position: relative;
}

.sentry-mode-btn.btn-success {
  background: linear-gradient(135deg, #10b981, #059669);
  border-color: #059669;
  color: white;
  box-shadow: 0 2px 4px rgba(16, 185, 129, 0.3);
}

.sentry-mode-btn.btn-success:hover {
  background: linear-gradient(135deg, #059669, #047857);
  box-shadow: 0 4px 8px rgba(16, 185, 129, 0.4);
  transform: translateY(-1px);
}

.sentry-mode-btn.btn-secondary {
  background: #6b7280;
  border-color: #6b7280;
  color: white;
}

.sentry-mode-btn.btn-secondary:hover {
  background: #4b5563;
  border-color: #4b5563;
}

.sentry-mode-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none !important;
}

.sentry-icon {
  font-size: 16px;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
}

.monitor-main {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
}

.live-section, .inference-section {
  flex: 1;
}

.panel {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e6e6e6;
}

.panel-header h3 {
  margin: 0;
  color: #303133;
}

.status-indicators, .inference-status {
  display: flex;
  gap: 8px;
}

.status-tag {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-tag.success {
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #0ea5e9;
}

.status-tag.danger {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #ef4444;
}

.status-tag.info {
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #3b82f6;
}

.video-container, .inference-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许flex收缩 */
}

.placeholder {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f8f9fa;
  margin: 16px;
  border-radius: 8px;
  border: 2px dashed #dee2e6;
}

.placeholder-content {
  text-align: center;
  color: #6c757d;
}

.placeholder-content .icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.placeholder-content p {
  margin: 0.5rem 0;
}

.placeholder-content .hint {
  font-size: 0.9rem;
  opacity: 0.7;
}

.control-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-top: 1px solid #e6e6e6;
  background: #f8f9fa;
}

.control-group {
  display: flex;
  gap: 8px;
}

.stats-group {
  display: flex;
  gap: 16px;
  font-size: 14px;
  color: #666;
}

.stats-group span {
  padding: 4px 8px;
  background: #f0f0f0;
  border-radius: 4px;
}

.divider {
  width: 2px;
  background: #e6e6e6;
  border-radius: 1px;
}

.monitor-footer {
  padding: 12px 24px;
  background: white;
  border-top: 1px solid #e6e6e6;
}

.inference-display {
  flex: 1; /* 占据可用空间 */
  display: flex;
  gap: 16px;
  padding: 16px;
  height: 100%; /* 占满父容器高度 */
  min-height: 0; /* 允许flex收缩 */
}

.left-section {
  flex: 1; /* 占据大部分空间 */
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0; /* 防止flex子项溢出 */
  height: 100%; /* 确保占满高度 */
}

.right-section {
  flex: 0 0 300px; /* 固定宽度300px */
  display: flex;
  flex-direction: column;
  min-width: 300px;
  height: 100%; /* 确保占满整个高度 */
}

.video-section {
  flex: 0 0 300px; /* 固定高度300px */
  min-width: 0; /* 防止flex子项溢出 */
  display: flex;
  flex-direction: column;
}

.video-player-container {
  position: relative;
  width: 100%;
  flex: 1; /* 占据video-section的全部高度 */
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.inference-video {
  width: auto; /* 改为自动宽度 */
  height: auto; /* 改为自动高度 */
  max-width: 100%; /* 限制最大宽度 */
  max-height: 100%; /* 限制最大高度 */
  object-fit: none; /* 改为不缩放，保持原始尺寸 */
  border-radius: 8px;
}

/* 图像显示样式 */
.inference-image-container {
  position: relative;
  width: auto; /* 改为自动宽度 */
  height: auto; /* 改为自动高度 */
  max-width: 100%; /* 限制最大宽度 */
  max-height: 100%; /* 限制最大高度 */
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent; /* 移除黑色背景 */
}

.inference-image {
  width: auto; /* 改为自动宽度 */
  height: auto; /* 改为自动高度 */
  max-width: 100%;
  max-height: 100%;
  object-fit: none; /* 改为不缩放，保持原始尺寸 */
  border-radius: 8px;
}

.inference-video-container {
  position: relative;
  width: auto; /* 改为自动宽度 */
  height: auto; /* 改为自动高度 */
  max-width: 100%; /* 限制最大宽度 */
  max-height: 100%; /* 限制最大高度 */
  display: flex;
  justify-content: center;
  align-items: center;
  background: transparent; /* 移除黑色背景 */
}

.media-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  border-radius: 0 0 8px 8px;
  font-size: 12px;
}

.media-info p {
  margin: 2px 0;
}

.video-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  border-radius: 0 0 8px 8px;
  font-size: 12px;
}

.video-info p {
  margin: 2px 0;
}

.video-display {
  flex: 1;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #000;
  margin: 16px;
  border-radius: 8px;
  overflow: hidden;
}

.video-canvas {
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.video-stream {
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  object-fit: contain;
}

.video-overlay {
  position: absolute;
  bottom: 16px;
  right: 16px;
  pointer-events: none;
}

.frame-info {
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 12px;
}

.frame-info span {
  margin-right: 16px;
}

.bbox-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: auto;
  cursor: pointer;
}

.detail-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-item:last-child {
  border-bottom: none;
}

.detail-item label {
  font-weight: 500;
  color: #606266;
  min-width: 80px;
}

.ai-status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.ai-status.success {
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #0ea5e9;
}

.ai-status.pending {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #ef4444;
}

/* AI回答区域样式 */
.ai-response-section {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 2px solid #0ea5e9;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);
}

.ai-response-section h5 {
  color: #0369a1;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

.ai-response-section h5::before {
  content: "🤖";
  margin-right: 8px;
  font-size: 18px;
}

.ai-response-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-question {
  background: rgba(255, 255, 255, 0.8);
  padding: 12px;
  border-radius: 8px;
  border-left: 4px solid #f59e0b;
  font-size: 14px;
  line-height: 1.5;
}

.user-question strong {
  color: #d97706;
}

.ai-answer {
  background: rgba(255, 255, 255, 0.9);
  padding: 12px;
  border-radius: 8px;
  border-left: 4px solid #10b981;
  font-size: 14px;
  line-height: 1.5;
}

.ai-answer strong {
  color: #059669;
  margin-bottom: 8px;
  display: block;
}

.response-text {
  color: #374151;
  white-space: pre-wrap;
  word-wrap: break-word;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 0;
}

.no-question {
  background: rgba(255, 255, 255, 0.6);
  padding: 8px 12px;
  border-radius: 6px;
  border-left: 3px solid #94a3b8;
}

.no-question-text {
  color: #64748b;
  font-style: italic;
  font-size: 13px;
}

.no-response-text {
  color: #64748b;
  font-style: italic;
  font-size: 13px;
}

/* 历史记录区域样式 */
.history-section {
  flex: 1; /* 在right-section中占据全部空间 */
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e6e6e6;
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 防止内容溢出 */
  min-height: 0; /* 允许flex收缩 */
  height: 100%; /* 确保占满父容器高度 */
}

.history-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e6e6e6;
  background: white;
}

.history-header h4 {
  margin: 0;
  color: #303133;
  font-size: 14px;
  font-weight: 600;
}

.history-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
}

.history-count {
  font-size: 12px;
  color: #909399;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
}

.history-container {
  flex: 1; /* 占据history-section的剩余空间 */
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许flex收缩 */
}

.history-placeholder {
  flex: 1; /* 占据全部可用空间 */
  display: flex;
  justify-content: center;
  align-items: center;
  background: white;
  border-radius: 6px;
  margin: 8px;
}

.history-scroll {
  flex: 1; /* 占据全部可用空间 */
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0; /* 允许flex收缩 */
}

.history-item {
  display: flex;
  gap: 12px;
  padding: 8px;
  background: white;
  border-radius: 6px;
  border: 1px solid #e6e6e6;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.1);
}

.history-item.active {
  border-color: #409eff;
  background: #f0f9ff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.history-thumbnail {
  position: relative;
  width: 60px;
  height: 45px;
  border-radius: 4px;
  overflow: hidden;
  background: #f0f0f0;
  flex-shrink: 0;
}

.thumbnail-image img,
.thumbnail-video video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.media-type-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  font-size: 10px;
  padding: 1px 3px;
  border-radius: 2px;
}

.media-type-badge.image {
  background: rgba(46, 213, 115, 0.8);
}

.media-type-badge.video {
  background: rgba(64, 158, 255, 0.8);
}

.history-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-width: 0;
}

.history-title {
  font-weight: 500;
  color: #303133;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-time {
  font-size: 11px;
  color: #909399;
}

.history-status {
  margin-top: 2px;
}

.status-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 2px;
  font-weight: 500;
}

.status-badge.success {
  background: #f0f9ff;
  color: #0369a1;
  border: 1px solid #0ea5e9;
}

.status-badge.pending {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #ef4444;
}

.status-badge.partial {
  background: #fef3c7;
  color: #d97706;
  border: 1px solid #f59e0b;
}

/* 思考与行动区域样式 */
.mcp-action-section {
  background: #f0f9ff;
  border: 1px solid #0ea5e9;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.mcp-action-section h5 {
  color: #0369a1;
  margin-bottom: 12px;
  font-weight: 600;
}

.mcp-action-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mcp-thinking, .mcp-action {
  padding: 8px 12px;
  border-radius: 6px;
  background: white;
  border-left: 3px solid #0ea5e9;
}

.thinking-text, .action-text {
  margin-top: 4px;
  color: #374151;
  font-size: 14px;
  line-height: 1.5;
}

.mcp-tool-info {
  background: white;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.tool-details {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.tool-name {
  font-weight: 500;
  color: #374151;
}

.tool-status.success {
  color: #059669;
  font-weight: 500;
}

.tool-status.failed {
  color: #dc2626;
  font-weight: 500;
}

.tool-arguments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.argument-item {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: #6b7280;
}

/* 添加info-panel的样式定义 */
.info-panel {
  flex: 1; /* 在left-section中占据剩余空间 */
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e6e6e6;
  overflow-y: auto; /* 内容过多时可滚动 */
  min-height: 0; /* 允许收缩 */
}

.info-panel h4 {
  margin: 0 0 16px 0;
  color: #303133;
  font-size: 16px;
  font-weight: 600;
  border-bottom: 2px solid #409eff;
  padding-bottom: 8px;
}

.info-panel h5 {
  margin: 16px 0 8px 0;
  color: #606266;
  font-size: 14px;
  font-weight: 600;
}

.info-panel h6 {
  margin: 12px 0 6px 0;
  color: #909399;
  font-size: 13px;
  font-weight: 600;
}

.detail-section {
  margin-bottom: 16px;
  padding: 12px;
  background: white;
  border-radius: 6px;
  border: 1px solid #e6e6e6;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.people-list, .vehicles-list {
  margin-top: 12px;
}

.person-item, .vehicle-item {
  margin-bottom: 8px;
  padding: 8px;
  background: #f0f9ff;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

.person-header, .vehicle-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.person-id, .vehicle-id {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}

.person-activity, .vehicle-status {
  font-size: 12px;
  color: #606266;
  background: white;
  padding: 2px 6px;
  border-radius: 3px;
}

.person-bbox, .vehicle-bbox {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
}

.waiting-message {
  color: #606266;
  font-size: 14px;
  margin: 8px 0;
}

.waiting-hint {
  color: #909399;
  font-size: 12px;
  font-style: italic;
}

.highlight {
  font-weight: 600;
  color: #409eff;
}
</style> 