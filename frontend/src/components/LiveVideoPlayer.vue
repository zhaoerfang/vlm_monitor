<template>
  <div class="live-video-player">
    <div class="video-header">
      <h3>实时视频流</h3>
      <div class="controls">
        <el-button 
          :type="isStreaming ? 'danger' : 'primary'"
          :loading="isConnecting"
          @click="toggleStream"
        >
          {{ isStreaming ? '停止' : '开始' }}
        </el-button>
        <el-button 
          type="info" 
          :disabled="!isConnected"
          @click="refreshConnection"
        >
          刷新连接
        </el-button>
      </div>
    </div>
    
    <div class="video-container" ref="videoContainer">
      <!-- 使用Canvas显示WebSocket传来的实时视频流 -->
      <canvas 
        ref="videoCanvas"
        class="video-stream"
        width="640"
        height="360"
        v-show="streamLoaded"
        alt="实时视频流"
      />
      
      <!-- 错误占位符 -->
      <div v-if="showPlaceholder" class="video-placeholder">
        <el-icon size="64"><VideoCamera /></el-icon>
        <p>{{ placeholderText }}</p>
      </div>
    </div>
    
    <div class="video-info">
      <div class="status-item">
        <span class="label">WebSocket:</span>
        <el-tag :type="isConnected ? 'success' : 'danger'">
          {{ isConnected ? '已连接' : '未连接' }}
        </el-tag>
      </div>
      <div class="status-item">
        <span class="label">视频流:</span>
        <el-tag :type="isStreaming ? 'success' : 'info'">
          {{ isStreaming ? '播放中' : '已停止' }}
        </el-tag>
      </div>
      <div class="status-item">
        <span class="label">MJPEG流:</span>
        <el-tag :type="streamLoaded ? 'success' : 'warning'">
          {{ streamLoaded ? '已加载' : '加载中' }}
        </el-tag>
      </div>
      <div class="status-item" v-if="stats.totalFrames > 0">
        <span class="label">总帧数:</span>
        <span>{{ stats.totalFrames }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// @ts-ignore
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElButton, ElTag, ElIcon } from 'element-plus'
import { VideoCamera } from '@element-plus/icons-vue'
import { useMonitorStore } from '@/stores/monitor'
import { websocketService } from '@/services/websocket'

const store = useMonitorStore()

// 响应式状态
const isConnecting = ref(false)
const showPlaceholder = ref(false)
const placeholderText = ref('正在加载视频流...')
const streamLoaded = ref(false)
const videoCanvas = ref<HTMLCanvasElement>()

// 计算属性
const isConnected = computed(() => store.isConnected)
const isStreaming = computed(() => store.isStreaming)
const stats = computed(() => store.stats)

// 生命周期
onMounted(async () => {
  setupWebSocket()
  await connectWebSocket()
  
  console.log('LiveVideoPlayer组件已挂载')
})

onUnmounted(() => {
  websocketService.disconnect()
})

// 设置WebSocket回调
function setupWebSocket() {
  websocketService.onConnected(() => {
    store.setConnectionStatus(true)
    ElMessage.success('WebSocket连接成功')
    console.log('WebSocket已连接')
  })
  
  websocketService.onDisconnected(() => {
    store.setConnectionStatus(false)
    store.setStreamingStatus(false)
    ElMessage.warning('WebSocket连接断开')
  })
  
  websocketService.onFrame((frameData: any) => {
    console.log('收到视频帧:', frameData.frame_number)
    if (frameData.frame_number) {
      store.stats.totalFrames = frameData.frame_number
    }
    // 处理视频帧显示
    onVideoFrameReceived(frameData)
  })
  
  websocketService.onStatus((data: any) => {
    console.log('收到状态更新:', data)
    if (data.streaming !== undefined) {
      store.setStreamingStatus(data.streaming)
      console.log('更新流状态:', data.streaming)
    }
    if (data.frame_number) {
      store.stats.totalFrames = data.frame_number
    }
  })
  
  websocketService.onError((error: string) => {
    ElMessage.error(`连接错误: ${error}`)
    onStreamError()
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

// 切换视频流
async function toggleStream() {
  if (!isConnected.value) {
    ElMessage.warning('请先连接WebSocket')
    return
  }
  
  try {
    if (isStreaming.value) {
      websocketService.stopVideoStream()
      ElMessage.info('正在停止视频流...')
    } else {
      websocketService.startVideoStream()
      ElMessage.info('正在启动视频流...')
    }
  } catch (error) {
    console.error('切换视频流失败:', error)
    ElMessage.error('操作失败')
  }
}

// 刷新连接
async function refreshConnection() {
  await connectWebSocket()
}

// 视频帧处理
function onVideoFrameReceived(frameData: any) {
  console.log('🎥 LiveVideoPlayer收到视频帧')
  
  if (!videoCanvas.value) return
  
  const canvas = videoCanvas.value
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
      
      // 更新状态
      streamLoaded.value = true
      showPlaceholder.value = false
    }
    
    img.onerror = () => {
      console.error('视频帧图像加载失败')
      onStreamError()
    }
    
    // 设置base64图像数据
    img.src = `data:image/jpeg;base64,${frameData.data}`
    
  } catch (error) {
    console.error('❌ 绘制视频帧失败:', error)
    onStreamError()
  }
}

function onStreamError() {
  console.error('MJPEG流加载失败')
  streamLoaded.value = false
  showPlaceholder.value = true
  placeholderText.value = '视频流加载失败，请检查后端服务器状态'
  ElMessage.error('视频流加载失败')
}
</script>

<style scoped>
.live-video-player {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.video-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.video-header h3 {
  margin: 0;
  color: #303133;
}

.controls {
  display: flex;
  gap: 10px;
}

.video-container {
  position: relative;
  width: 100%;
  height: 400px;
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-stream {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 4px;
}

.video-placeholder {
  text-align: center;
  color: #909399;
}

.video-placeholder p {
  margin-top: 16px;
  font-size: 14px;
}

.video-info {
  display: flex;
  gap: 20px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-item .label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}
</style> 