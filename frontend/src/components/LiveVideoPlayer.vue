<template>
  <div class="live-video-player">
    <div class="video-header">
      <h3>实时视频流</h3>
      <div class="status-indicators">
        <el-tag :type="connectionStatus" size="small">
          {{ connectionText }}
        </el-tag>
        <el-tag v-if="stats.fps > 0" type="info" size="small">
          {{ stats.fps }} FPS
        </el-tag>
      </div>
    </div>
    
    <div class="video-container" ref="videoContainer">
      <canvas 
        ref="videoCanvas"
        :width="canvasWidth"
        :height="canvasHeight"
        @click="onCanvasClick"
      ></canvas>
      
      <!-- 视频流控制overlay -->
      <div v-if="!isStreaming" class="video-overlay">
        <div class="overlay-content">
          <el-icon size="48"><VideoPlay /></el-icon>
          <p>点击开始播放实时视频流</p>
          <el-button 
            type="primary" 
            size="large"
            :loading="isConnecting"
            @click="startStream"
          >
            {{ isConnecting ? '连接中...' : '开始播放' }}
          </el-button>
        </div>
      </div>
      
      <!-- 无信号overlay -->
      <div v-else-if="!currentFrame" class="video-overlay no-signal">
        <div class="overlay-content">
          <el-icon size="48"><Warning /></el-icon>
          <p>等待视频信号...</p>
          <el-button size="small" @click="stopStream">停止</el-button>
        </div>
      </div>
    </div>
    
    <!-- 控制面板 -->
    <div class="control-panel">
      <div class="control-group">
        <el-button 
          v-if="!isStreaming"
          type="primary" 
          :loading="isConnecting"
          @click="startStream"
        >
          开始播放
        </el-button>
        <el-button 
          v-else
          type="danger" 
          @click="stopStream"
        >
          停止播放
        </el-button>
        
        <el-button @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>
          全屏
        </el-button>
      </div>
      
      <div class="stats-group">
        <span>总帧数: {{ stats.totalFrames }}</span>
        <span v-if="currentFrame">
          帧号: {{ currentFrame.frame_number }}
        </span>
        <span v-if="currentFrame">
          延迟: {{ formatLatency(currentFrame.timestamp) }}ms
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, Warning, FullScreen } from '@element-plus/icons-vue'
import { useMonitorStore } from '@/stores/monitor'
import websocketService from '@/services/websocket'
import type { VideoFrame } from '@/types'

// Store
const store = useMonitorStore()

// 响应式状态
const videoContainer = ref<HTMLDivElement>()
const videoCanvas = ref<HTMLCanvasElement>()
const isConnecting = ref(false)
const canvasWidth = ref(640)
const canvasHeight = ref(360)

// 计算属性
const isStreaming = computed(() => store.isStreaming)
const currentFrame = computed(() => store.currentFrame)
const stats = computed(() => store.stats)

const connectionStatus = computed(() => {
  return store.isConnected ? 'success' : 'danger'
})

const connectionText = computed(() => {
  return store.isConnected ? '已连接' : '未连接'
})

// Canvas上下文
let canvasContext: CanvasRenderingContext2D | null = null

// 初始化
onMounted(async () => {
  initializeCanvas()
  setupWebSocket()
  await connectWebSocket()
})

onUnmounted(() => {
  websocketService.disconnect()
})

// 监听当前帧变化，绘制到canvas
watch(currentFrame, (frame) => {
  if (frame) {
    drawFrameToCanvas(frame)
  }
}, { immediate: true })

// 初始化Canvas
function initializeCanvas() {
  nextTick(() => {
    if (videoCanvas.value) {
      canvasContext = videoCanvas.value.getContext('2d')
      resizeCanvas()
    }
  })
}

// 调整Canvas尺寸
function resizeCanvas() {
  if (videoContainer.value) {
    const containerRect = videoContainer.value.getBoundingClientRect()
    const aspectRatio = 16 / 9 // 假设视频比例为16:9
    
    let width = Math.min(containerRect.width - 20, 800)
    let height = width / aspectRatio
    
    if (height > containerRect.height - 100) {
      height = containerRect.height - 100
      width = height * aspectRatio
    }
    
    canvasWidth.value = width
    canvasHeight.value = height
  }
}

// 设置WebSocket回调
function setupWebSocket() {
  websocketService.onConnected(() => {
    store.setConnectionStatus(true)
    ElMessage.success('WebSocket连接成功')
  })
  
  websocketService.onDisconnected(() => {
    store.setConnectionStatus(false)
    store.setStreamingStatus(false)
    ElMessage.warning('WebSocket连接断开')
  })
  
  websocketService.onFrame((frame: VideoFrame) => {
    store.updateCurrentFrame(frame)
  })
  
  websocketService.onError((error: string) => {
    ElMessage.error(`连接错误: ${error}`)
  })
}

// 连接WebSocket
async function connectWebSocket() {
  isConnecting.value = true
  try {
    const success = await websocketService.connect()
    if (!success) {
      ElMessage.error('WebSocket连接失败')
    }
  } catch (error) {
    console.error('WebSocket连接异常:', error)
    ElMessage.error('WebSocket连接异常')
  } finally {
    isConnecting.value = false
  }
}

// 开始视频流
function startStream() {
  if (!store.isConnected) {
    ElMessage.warning('请先连接WebSocket')
    connectWebSocket()
    return
  }
  
  websocketService.startVideoStream()
  store.setStreamingStatus(true)
  ElMessage.success('开始播放视频流')
}

// 停止视频流
function stopStream() {
  websocketService.stopVideoStream()
  store.setStreamingStatus(false)
  ElMessage.info('停止播放视频流')
}

// 绘制帧到Canvas
function drawFrameToCanvas(frame: VideoFrame) {
  if (!canvasContext || !videoCanvas.value) return
  
  try {
    // 创建图像对象
    const img = new Image()
    img.onload = () => {
      // 清除canvas
      canvasContext!.clearRect(0, 0, canvasWidth.value, canvasHeight.value)
      
      // 绘制图像
      canvasContext!.drawImage(
        img, 
        0, 0, 
        canvasWidth.value, 
        canvasHeight.value
      )
    }
    
    // 设置图像源（假设是base64编码）
    img.src = `data:image/jpeg;base64,${frame.data}`
    
  } catch (error) {
    console.error('绘制帧失败:', error)
  }
}

// Canvas点击事件
function onCanvasClick() {
  if (!isStreaming.value) {
    startStream()
  }
}

// 切换全屏
function toggleFullscreen() {
  if (videoContainer.value) {
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      videoContainer.value.requestFullscreen()
    }
  }
}

// 格式化延迟
function formatLatency(timestamp: number): number {
  const now = Date.now() / 1000
  return Math.round((now - timestamp) * 1000)
}

// 监听窗口大小变化
window.addEventListener('resize', resizeCanvas)
</script>

<style scoped>
.live-video-player {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.video-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e6e6e6;
}

.video-header h3 {
  margin: 0;
  color: #303133;
}

.status-indicators {
  display: flex;
  gap: 8px;
}

.video-container {
  flex: 1;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #000;
  min-height: 300px;
}

.video-container canvas {
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.video-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: center;
  align-items: center;
  color: white;
}

.video-overlay.no-signal {
  background: rgba(0, 0, 0, 0.8);
}

.overlay-content {
  text-align: center;
}

.overlay-content p {
  margin: 16px 0;
  font-size: 16px;
}

.control-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-top: 1px solid #e6e6e6;
  background: #fafafa;
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

/* 全屏样式 */
.video-container:fullscreen {
  background: #000;
}

.video-container:fullscreen canvas {
  max-width: 100vw;
  max-height: 100vh;
}
</style> 