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
      <!-- 使用img元素显示MJPEG流 - 不依赖WebSocket状态 -->
      <img 
        :src="mjpegStreamUrl"
        class="video-stream"
        @load="onStreamLoad"
        @error="onStreamError"
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
const mjpegStreamUrl = ref('/api/video-stream')
const showPlaceholder = ref(false)
const placeholderText = ref('正在加载视频流...')
const streamLoaded = ref(false)

// 计算属性
const isConnected = computed(() => store.isConnected)
const isStreaming = computed(() => store.isStreaming)
const stats = computed(() => store.stats)

// 生命周期
onMounted(async () => {
  setupWebSocket()
  await connectWebSocket()
  
  // 添加时间戳避免缓存问题
  mjpegStreamUrl.value = `/api/video-stream?t=${Date.now()}`
  console.log('组件已挂载，MJPEG流URL:', mjpegStreamUrl.value)
})

onUnmounted(() => {
  websocketService.disconnect()
})

// 设置WebSocket回调
function setupWebSocket() {
  websocketService.onConnected(() => {
    store.setConnectionStatus(true)
    ElMessage.success('WebSocket连接成功')
    console.log('WebSocket已连接，MJPEG流URL:', mjpegStreamUrl.value)
  })
  
  websocketService.onDisconnected(() => {
    store.setConnectionStatus(false)
    store.setStreamingStatus(false)
    ElMessage.warning('WebSocket连接断开')
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

// MJPEG流事件
function onStreamLoad() {
  console.log('MJPEG流加载成功')
  streamLoaded.value = true
  showPlaceholder.value = false
  ElMessage.success('视频流加载成功')
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