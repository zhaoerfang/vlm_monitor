<template>
  <div class="monitor-view">
    <header class="monitor-header">
      <h1>视频监控系统</h1>
      <div class="header-controls">
        <button @click="refreshData" :disabled="isLoading" class="btn btn-primary">
          {{ isLoading ? '刷新中...' : '刷新' }}
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
            <div v-if="!store.isStreaming && !currentFrame" class="placeholder">
              <div class="placeholder-content">
                <div class="icon">📹</div>
                <p>实时视频流</p>
                <p class="hint">等待连接...</p>
                <button class="btn btn-primary" @click="startStream">开始播放</button>
              </div>
            </div>
            
            <div v-else-if="store.isStreaming && !currentFrame" class="placeholder">
              <div class="placeholder-content">
                <div class="icon">⏳</div>
                <p>等待视频信号...</p>
                <p class="hint">正在接收数据流...</p>
                <button class="btn btn-danger" @click="stopStream">停止</button>
              </div>
            </div>
            
            <div v-else class="video-display">
              <canvas 
                ref="videoCanvas"
                :width="640"
                :height="360"
                @click="onCanvasClick"
                class="video-canvas"
              ></canvas>
              
              <div class="video-overlay">
                <div class="frame-info">
                  <span>帧号: {{ currentFrame.frame_number }}</span>
                  <span>延迟: {{ formatLatency(currentFrame.timestamp) }}ms</span>
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
              <div class="video-section">
                <div class="video-player-container">
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
                  
                  <div class="video-info">
                    <p><strong>视频文件:</strong> {{ getVideoFileName(currentInference.video_path) }}</p>
                    <p v-if="currentInference.total_frames"><strong>总帧数:</strong> {{ currentInference.total_frames }}</p>
                    <p v-if="currentInference.sampled_frames"><strong>采样帧数:</strong> {{ currentInference.sampled_frames.length }}</p>
                    <p v-if="currentInference.has_inference_result" class="ai-status success">✅ AI分析完成</p>
                    <p v-else class="ai-status pending">⏳ 等待AI分析</p>
                  </div>
                </div>
              </div>
              
              <div class="info-panel">
                <h4>推理详情</h4>
                
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
import apiService from '@/services/api'
import websocketService from '@/services/websocket'

const store = useMonitorStore()
const isLoading = ref(false)
const videoCanvas = ref<HTMLCanvasElement>()
const inferenceVideo = ref<HTMLVideoElement>()
const bboxCanvas = ref<HTMLCanvasElement>()

// 定时器引用
let statusCheckInterval: number | null = null
let inferenceCheckInterval: number | null = null

// bbox显示状态
const showBbox = ref(true)

const stats = computed(() => store.stats)
const latestInference = computed(() => store.latestInference)
const currentInference = computed(() => store.playableInference)
const currentFrame = computed(() => store.currentFrame)

const connectionStatus = computed(() => {
  return store.isConnected ? 'success' : 'danger'
})

const connectionText = computed(() => {
  return store.isConnected ? '已连接' : '未连接'
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

// 监听当前帧变化，绘制到canvas
watch(currentFrame, (frame) => {
  if (frame) {
    drawFrameToCanvas(frame)
  }
}, { immediate: true })

onMounted(async () => {
  console.log('MonitorView 组件已挂载，开始初始化...')
  
  // 初始化WebSocket连接
  await initializeWebSocket()
  
  // 加载历史数据
  await loadExperimentLog()
  
  // 定期检查系统状态
  statusCheckInterval = setInterval(checkSystemStatus, 5000)
  
  // 定期检查推理结果（更频繁地检查）
  inferenceCheckInterval = setInterval(checkInferenceCount, 2000)
})

onUnmounted(() => {
  // 断开WebSocket连接
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
})

// 绘制帧到Canvas
function drawFrameToCanvas(frame: any) {
  if (!videoCanvas.value) return
  
  const canvas = videoCanvas.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  try {
    // 创建图像对象
    const img = new Image()
    img.onload = () => {
      // 清除canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      
      // 绘制图像
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    }
    
    // 设置图像源（假设是base64编码）
    img.src = `data:image/jpeg;base64,${frame.data}`
    
  } catch (error) {
    console.error('绘制帧失败:', error)
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
        start_time: response.data.length > 0 ? response.data[0].timestamp : null,
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
    // 优先获取最新的已完成AI分析的推理结果（有inference_result.json的）
    const aiResponse = await apiService.getLatestInferenceWithAI()
    if (aiResponse.success && aiResponse.data) {
      console.log('🎬 获取到最新AI分析结果用于播放:', aiResponse.data.video_id, '时间:', aiResponse.data.creation_timestamp)
      store.addInferenceResult(aiResponse.data)
      return
    }
    
    // 如果没有AI分析结果，检查是否有任何推理结果（用于显示状态）
    const response = await apiService.getLatestInference()
    if (response.success && response.data) {
      console.log('📋 获取到推理结果（等待AI分析）:', response.data.video_id, '时间:', response.data.creation_timestamp)
      // 只更新状态，但不用于播放
      store.addInferenceResult(response.data)
      
      // 如果没有AI分析结果，继续使用之前有AI分析的结果进行播放
      if (!response.data.has_inference_result) {
        console.log('⏳ 当前推理结果还在等待AI分析，继续播放上一个有AI结果的视频')
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

function onCanvasClick() {
  if (!store.isStreaming) {
    startStream()
  }
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
  if (!bboxCanvas.value || !inferenceVideo.value || !currentInference.value) return
  
  const canvas = bboxCanvas.value
  const video = inferenceVideo.value
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  
  // 等待视频元数据加载完成
  if (video.readyState < 1) {
    console.log('⏳ 视频元数据未加载完成，等待中...')
    return
  }
  
  // 获取视频的原始分辨率和容器尺寸
  const videoWidth = video.videoWidth
  const videoHeight = video.videoHeight
  const containerWidth = video.clientWidth
  const containerHeight = video.clientHeight
  
  // 计算视频在容器中的实际显示尺寸和位置（考虑object-fit: contain）
  const videoAspectRatio = videoWidth / videoHeight
  const containerAspectRatio = containerWidth / containerHeight
  
  let displayWidth, displayHeight, offsetX, offsetY
  
  if (videoAspectRatio > containerAspectRatio) {
    // 视频更宽，以容器宽度为准，高度按比例缩放
    displayWidth = containerWidth
    displayHeight = containerWidth / videoAspectRatio
    offsetX = 0
    offsetY = (containerHeight - displayHeight) / 2
  } else {
    // 视频更高或比例相同，以容器高度为准，宽度按比例缩放
    displayWidth = containerHeight * videoAspectRatio
    displayHeight = containerHeight
    offsetX = (containerWidth - displayWidth) / 2
    offsetY = 0
  }
  
  console.log('📐 视频显示计算详情:', {
    videoOriginal: { 
      width: videoWidth, 
      height: videoHeight, 
      aspectRatio: videoAspectRatio.toFixed(3) 
    },
    container: { 
      width: containerWidth, 
      height: containerHeight, 
      aspectRatio: containerAspectRatio.toFixed(3) 
    },
    comparison: {
      videoWider: videoAspectRatio > containerAspectRatio,
      ratiosDiff: (videoAspectRatio - containerAspectRatio).toFixed(3)
    },
    actualDisplay: { 
      width: Math.round(displayWidth), 
      height: Math.round(displayHeight), 
      offsetX: Math.round(offsetX), 
      offsetY: Math.round(offsetY) 
    },
    blackBars: {
      top: Math.round(offsetY),
      bottom: Math.round(offsetY),
      left: Math.round(offsetX),
      right: Math.round(offsetX)
    },
    videoSrc: video.src.split('/').pop()
  })
  
  // 设置canvas尺寸与容器一致
  canvas.width = containerWidth
  canvas.height = containerHeight
  
  // 设置canvas样式尺寸
  canvas.style.width = `${containerWidth}px`
  canvas.style.height = `${containerHeight}px`
  
  // 清除之前的绘制
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  
  // 可选：绘制视频显示区域的边界（调试用）
  if (import.meta.env.DEV) {
    ctx.strokeStyle = 'rgba(255, 0, 0, 0.3)'
    ctx.lineWidth = 2
    ctx.strokeRect(offsetX, offsetY, displayWidth, displayHeight)
  }
  
  if (!showBbox.value || (!currentInference.value.people && !currentInference.value.vehicles)) return
  
  const totalObjects = (currentInference.value.people?.length || 0) + (currentInference.value.vehicles?.length || 0)
  
  console.log('📏 bbox绘制信息:', {
    peopleCount: currentInference.value.people?.length || 0,
    vehicleCount: currentInference.value.vehicles?.length || 0,
    totalObjects: totalObjects,
    displayArea: { 
      width: Math.round(displayWidth), 
      height: Math.round(displayHeight), 
      offsetX: Math.round(offsetX), 
      offsetY: Math.round(offsetY) 
    }
  })
  
  // 绘制每个人的bbox
  if (currentInference.value.people) {
    currentInference.value.people.forEach((person: any, index: number) => {
      if (!person.bbox) return
      
      const [x1, y1, x2, y2] = person.bbox
      
      // 验证bbox坐标有效性
      if (x1 < 0 || x1 > 1 || y1 < 0 || y1 > 1 || x2 < 0 || x2 > 1 || y2 < 0 || y2 > 1) {
        console.warn(`⚠️ 人员${index + 1} bbox坐标超出范围:`, person.bbox)
      }
      
      // 将归一化坐标转换为视频实际显示区域的坐标
      const boxX = offsetX + x1 * displayWidth
      const boxY = offsetY + y1 * displayHeight
      const boxWidth = (x2 - x1) * displayWidth
      const boxHeight = (y2 - y1) * displayHeight
      
      // 边界检查（确保在视频显示区域内）
      const clampedBoxX = Math.max(offsetX, Math.min(boxX, offsetX + displayWidth - 1))
      const clampedBoxY = Math.max(offsetY, Math.min(boxY, offsetY + displayHeight - 1))
      const clampedBoxWidth = Math.max(1, Math.min(boxWidth, offsetX + displayWidth - clampedBoxX))
      const clampedBoxHeight = Math.max(1, Math.min(boxHeight, offsetY + displayHeight - clampedBoxY))
      
      console.log(`👤 人员${index + 1} bbox详情:`, {
        originalBbox: person.bbox,
        normalizedCoords: { x1: x1.toFixed(3), y1: y1.toFixed(3), x2: x2.toFixed(3), y2: y2.toFixed(3) },
        calculatedCoords: { 
          boxX: Math.round(boxX), 
          boxY: Math.round(boxY), 
          boxWidth: Math.round(boxWidth), 
          boxHeight: Math.round(boxHeight) 
        },
        clampedCoords: {
          boxX: Math.round(clampedBoxX),
          boxY: Math.round(clampedBoxY),
          boxWidth: Math.round(clampedBoxWidth),
          boxHeight: Math.round(clampedBoxHeight)
        },
        activity: person.activity,
        withinVideoArea: {
          x: boxX >= offsetX && (boxX + boxWidth) <= (offsetX + displayWidth),
          y: boxY >= offsetY && (boxY + boxHeight) <= (offsetY + displayHeight)
        },
        adjustmentNeeded: {
          x: boxX !== clampedBoxX || boxWidth !== clampedBoxWidth,
          y: boxY !== clampedBoxY || boxHeight !== clampedBoxHeight
        }
      })
      
      // 使用修正后的坐标
      const finalBoxX = clampedBoxX
      const finalBoxY = clampedBoxY
      const finalBoxWidth = clampedBoxWidth
      const finalBoxHeight = clampedBoxHeight
      
      // 设置人员样式（红色）
      ctx.strokeStyle = '#ff4757'
      ctx.lineWidth = 3
      ctx.fillStyle = 'rgba(255, 71, 87, 0.1)'
      
      // 绘制矩形
      ctx.fillRect(finalBoxX, finalBoxY, finalBoxWidth, finalBoxHeight)
      ctx.strokeRect(finalBoxX, finalBoxY, finalBoxWidth, finalBoxHeight)
      
      // 绘制标签
      const label = `人${person.id || (index + 1)}: ${person.activity || '未知'}`
      ctx.fillStyle = '#ff4757'
      ctx.font = '14px Arial'
      
      // 标签背景
      const textMetrics = ctx.measureText(label)
      const labelX = Math.max(offsetX, Math.min(finalBoxX, offsetX + displayWidth - textMetrics.width - 8))
      const labelY = Math.max(offsetY + 20, finalBoxY)
      
      ctx.fillRect(labelX, labelY - 20, textMetrics.width + 8, 20)
      
      // 标签文字
      ctx.fillStyle = 'white'
      ctx.fillText(label, labelX + 4, labelY - 6)
    })
  }
  
  // 绘制每个车辆的bbox
  if (currentInference.value.vehicles) {
    currentInference.value.vehicles.forEach((vehicle: any, index: number) => {
      if (!vehicle.bbox) return
      
      const [x1, y1, x2, y2] = vehicle.bbox
      
      // 验证bbox坐标有效性
      if (x1 < 0 || x1 > 1 || y1 < 0 || y1 > 1 || x2 < 0 || x2 > 1 || y2 < 0 || y2 > 1) {
        console.warn(`⚠️ 车辆${index + 1} bbox坐标超出范围:`, vehicle.bbox)
      }
      
      // 将归一化坐标转换为视频实际显示区域的坐标
      const boxX = offsetX + x1 * displayWidth
      const boxY = offsetY + y1 * displayHeight
      const boxWidth = (x2 - x1) * displayWidth
      const boxHeight = (y2 - y1) * displayHeight
      
      // 边界检查（确保在视频显示区域内）
      const clampedBoxX = Math.max(offsetX, Math.min(boxX, offsetX + displayWidth - 1))
      const clampedBoxY = Math.max(offsetY, Math.min(boxY, offsetY + displayHeight - 1))
      const clampedBoxWidth = Math.max(1, Math.min(boxWidth, offsetX + displayWidth - clampedBoxX))
      const clampedBoxHeight = Math.max(1, Math.min(boxHeight, offsetY + displayHeight - clampedBoxY))
      
      console.log(`🚗 车辆${index + 1} bbox详情:`, {
        originalBbox: vehicle.bbox,
        type: vehicle.type,
        status: vehicle.status,
        normalizedCoords: { x1: x1.toFixed(3), y1: y1.toFixed(3), x2: x2.toFixed(3), y2: y2.toFixed(3) },
        calculatedCoords: { 
          boxX: Math.round(boxX), 
          boxY: Math.round(boxY), 
          boxWidth: Math.round(boxWidth), 
          boxHeight: Math.round(boxHeight) 
        },
        clampedCoords: {
          boxX: Math.round(clampedBoxX),
          boxY: Math.round(clampedBoxY),
          boxWidth: Math.round(clampedBoxWidth),
          boxHeight: Math.round(clampedBoxHeight)
        },
        withinVideoArea: {
          x: boxX >= offsetX && (boxX + boxWidth) <= (offsetX + displayWidth),
          y: boxY >= offsetY && (boxY + boxHeight) <= (offsetY + displayHeight)
        },
        adjustmentNeeded: {
          x: boxX !== clampedBoxX || boxWidth !== clampedBoxWidth,
          y: boxY !== clampedBoxY || boxHeight !== clampedBoxHeight
        }
      })
      
      // 使用修正后的坐标
      const finalBoxX = clampedBoxX
      const finalBoxY = clampedBoxY
      const finalBoxWidth = clampedBoxWidth
      const finalBoxHeight = clampedBoxHeight
      
      // 设置车辆样式（绿色）
      ctx.strokeStyle = '#2ed573'
      ctx.lineWidth = 3
      ctx.fillStyle = 'rgba(46, 213, 115, 0.1)'
      
      // 绘制矩形
      ctx.fillRect(finalBoxX, finalBoxY, finalBoxWidth, finalBoxHeight)
      ctx.strokeRect(finalBoxX, finalBoxY, finalBoxWidth, finalBoxHeight)
      
      // 绘制标签
      const label = `${vehicle.type || '车辆'}${vehicle.id || (index + 1)}: ${vehicle.status || '未知'}`
      ctx.fillStyle = '#2ed573'
      ctx.font = '14px Arial'
      
      // 标签背景
      const textMetrics = ctx.measureText(label)
      const labelX = Math.max(offsetX, Math.min(finalBoxX, offsetX + displayWidth - textMetrics.width - 8))
      const labelY = Math.max(offsetY + 20, finalBoxY)
      
      ctx.fillRect(labelX, labelY - 20, textMetrics.width + 8, 20)
      
      // 标签文字
      ctx.fillStyle = 'white'
      ctx.fillText(label, labelX + 4, labelY - 6)
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
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px;
}

.video-section {
  flex: 2;
}

.video-player-container {
  position: relative;
  width: 100%;
  height: 400px; /* 设置固定高度 */
  max-height: 500px;
  min-height: 300px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.inference-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 8px;
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

.info-panel {
  flex: 1;
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.info-panel h4 {
  margin: 0 0 16px 0;
  color: #303133;
}

.detail-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e6e6e6;
}

.detail-section:last-child {
  border-bottom: none;
}

.detail-section h5 {
  margin: 0 0 12px 0;
  color: #303133;
  font-size: 14px;
  font-weight: 600;
}

.detail-section h6 {
  margin: 12px 0 8px 0;
  color: #606266;
  font-size: 13px;
  font-weight: 500;
}

.highlight {
  color: #409eff;
  font-weight: 600;
}

.waiting-message {
  color: #909399;
  font-style: italic;
  margin: 8px 0;
}

.waiting-hint {
  color: #c0c4cc;
  font-size: 12px;
  margin: 4px 0;
}

.people-list {
  margin-top: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.vehicles-list {
  margin-top: 12px;
  padding: 12px;
  background: #f0f9ff;
  border-radius: 6px;
}

.person-item {
  margin-bottom: 12px;
  padding: 8px;
  background: white;
  border-radius: 4px;
  border: 1px solid #e6e6e6;
}

.vehicle-item {
  margin-bottom: 12px;
  padding: 8px;
  background: white;
  border-radius: 4px;
  border: 1px solid #e6e6e6;
}

.person-item:last-child,
.vehicle-item:last-child {
  margin-bottom: 0;
}

.person-header,
.vehicle-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.person-id,
.vehicle-id {
  font-weight: 600;
  color: #303133;
  font-size: 13px;
}

.person-activity {
  font-size: 12px;
  color: #409eff;
  background: #f0f9ff;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #b3d8ff;
}

.vehicle-status {
  font-size: 12px;
  color: #2ed573;
  background: #f0fff4;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #95de64;
}

.person-bbox,
.vehicle-bbox {
  margin-top: 6px;
  padding: 6px 8px;
  background: #f5f7fa;
  border-radius: 3px;
  font-size: 11px;
  color: #606266;
  font-family: monospace;
}

/* 按钮样式 */
.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: #409eff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #337ecc;
}

.btn-danger {
  background: #f56c6c;
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: #f24c4c;
}

.btn-warning {
  background: #e6a23c;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #cf9236;
}

.btn-secondary {
  background: #909399;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #82848a;
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
</style> 