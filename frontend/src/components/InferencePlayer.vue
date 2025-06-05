<template>
  <div class="inference-player">
    <div class="player-header">
      <h3>推理结果</h3>
      <div class="inference-status">
        <el-tag v-if="latestInference" type="success" size="small">
          最新推理: {{ formatTime(latestInference.inference_end_time) }}
        </el-tag>
        <el-tag v-if="stats.latency > 0" type="info" size="small">
          平均延迟: {{ Math.round(stats.latency) }}s
        </el-tag>
      </div>
    </div>
    
    <div class="player-container">
      <!-- 视频播放区域 -->
      <div class="video-section" ref="videoSection">
        <div v-if="!currentInference" class="placeholder">
          <el-icon size="48"><VideoCamera /></el-icon>
          <p>等待推理结果...</p>
          <p class="hint">推理需要约12秒时间</p>
        </div>
        
        <div v-else class="video-display">
          <!-- 视频播放器 -->
          <div class="video-container" ref="videoContainer">
            <video
              ref="videoPlayer"
              :src="videoUrl"
              @loadedmetadata="onVideoLoaded"
              @timeupdate="onTimeUpdate"
              @ended="onVideoEnded"
              muted
              loop
              autoplay
            ></video>
            
            <!-- Bbox覆盖层 -->
            <div class="bbox-overlay" ref="bboxOverlay">
              <!-- 人员边界框 -->
              <div
                v-for="(person, index) in currentPeople"
                :key="`person-${index}`"
                class="bbox person-bbox"
                :style="getBboxStyle(person.bbox)"
              >
                <div class="bbox-label person-label">
                  <span class="object-id">人{{ person.id }}</span>
                  <span class="activity">{{ person.activity }}</span>
                </div>
              </div>
              
              <!-- 车辆边界框 -->
              <div
                v-for="(vehicle, index) in currentVehicles"
                :key="`vehicle-${index}`"
                class="bbox vehicle-bbox"
                :style="getBboxStyle(vehicle.bbox)"
              >
                <div class="bbox-label vehicle-label">
                  <span class="object-id">{{ vehicle.type }}{{ vehicle.id }}</span>
                  <span class="activity">{{ vehicle.status }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 视频控制 -->
          <div class="video-controls">
            <el-button-group>
              <el-button @click="togglePlay" :icon="isPlaying ? Pause : VideoPlay">
                {{ isPlaying ? '暂停' : '播放' }}
              </el-button>
              <el-button @click="restartVideo" :icon="Refresh">
                重播
              </el-button>
            </el-button-group>
            
            <div class="progress-bar">
              <el-slider
                v-model="currentTime"
                :max="videoDuration"
                :step="0.1"
                @input="seekVideo"
                :show-tooltip="false"
              />
            </div>
          </div>
        </div>
      </div>
      
      <!-- 推理信息面板 -->
      <div class="info-panel">
        <div v-if="currentInference" class="inference-details">
          <h4>推理详情</h4>
          
          <div class="detail-group">
            <label>视频时间范围:</label>
            <span>{{ formatTimeRange(currentInference.video_info) }}</span>
          </div>
          
          <div class="detail-group">
            <label>推理耗时:</label>
            <span>{{ Math.round(currentInference.inference_duration * 100) / 100 }}秒</span>
          </div>
          
          <div class="detail-group">
            <label>人数统计:</label>
            <span>{{ parsedResult?.people_count || 0 }}人</span>
          </div>
          
          <div class="detail-group">
            <label>车辆统计:</label>
            <span>{{ parsedResult?.vehicle_count || 0 }}辆</span>
          </div>
          
          <div class="detail-group">
            <label>场景描述:</label>
            <span>{{ parsedResult?.summary || '无描述' }}</span>
          </div>
          
          <!-- 人员列表 -->
          <div v-if="parsedResult?.people?.length" class="people-list">
            <h5>人员详情</h5>
            <div
              v-for="(person, index) in parsedResult.people"
              :key="`info-person-${index}`"
              class="person-item"
              @mouseenter="highlightPerson(index)"
              @mouseleave="unhighlightPerson()"
            >
              <div class="person-header">
                <span class="person-id">人员 {{ person.id }}</span>
                <span class="person-activity">{{ person.activity }}</span>
              </div>
              <div class="person-bbox">
                位置: [{{ person.bbox.map((v: number) => Math.round(v * 100) / 100).join(', ') }}]
              </div>
            </div>
          </div>
          
          <!-- 车辆列表 -->
          <div v-if="parsedResult?.vehicles?.length" class="vehicles-list">
            <h5>车辆详情</h5>
            <div
              v-for="(vehicle, index) in parsedResult.vehicles"
              :key="`info-vehicle-${index}`"
              class="vehicle-item"
              @mouseenter="highlightVehicle(index)"
              @mouseleave="unhighlightVehicle()"
            >
              <div class="vehicle-header">
                <span class="vehicle-id">{{ vehicle.type }} {{ vehicle.id }}</span>
                <span class="vehicle-status">{{ vehicle.status }}</span>
              </div>
              <div class="vehicle-bbox">
                位置: [{{ vehicle.bbox.map((v: number) => Math.round(v * 100) / 100).join(', ') }}]
              </div>
            </div>
          </div>
        </div>
        
        <!-- 历史推理列表 -->
        <div class="history-section">
          <h4>推理历史</h4>
          <div class="history-list">
            <div
              v-for="(inference, index) in recentInferences"
              :key="`history-${index}`"
              class="history-item"
              :class="{ active: inference === currentInference }"
              @click="selectInference(inference)"
            >
              <div class="history-time">
                {{ formatTime(inference.inference_end_time) }}
              </div>
              <div class="history-info">
                <span>帧范围: {{ inference.video_info.original_frame_range.join('-') }}</span>
                <span>{{ getInferencePeopleCount(inference) }}人</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { VideoCamera, VideoPlay, Pause, Refresh } from '@element-plus/icons-vue'
import { useMonitorStore } from '@/stores/monitor'
import type { InferenceLogItem, InferenceResult, Person, Vehicle } from '@/types'

const store = useMonitorStore()

const videoPlayer = ref<HTMLVideoElement>()
const currentInference = ref<InferenceLogItem | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const videoDuration = ref(0)
const highlightedPersonIndex = ref(-1)

const latestInference = computed(() => store.latestInference)
const recentInferences = computed(() => store.recentInferences)
const stats = computed(() => store.stats)

// 监听可播放推理结果的变化
const playableInference = computed(() => store.playableInference)

const parsedResult = computed((): InferenceResult | null => {
  if (!currentInference.value?.result) return null
  
  try {
    let resultText = currentInference.value.result
    
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
})

const currentPeople = computed((): Person[] => {
  return parsedResult.value?.people || []
})

const currentVehicles = computed((): Vehicle[] => {
  return parsedResult.value?.vehicles || []
})

const videoUrl = computed(() => {
  if (!currentInference.value) return ''
  const videoPath = currentInference.value.video_path
  const fileName = videoPath.split('/').pop()
  return `/api/videos/${fileName}`
})

watch(playableInference, (newInference) => {
  if (newInference && (!currentInference.value || 
      (newInference as any).video_id !== (currentInference.value as any).video_id)) {
    console.log('🎬 切换到新的可播放推理结果:', (newInference as any).video_id)
    selectInference(newInference)
  }
}, { immediate: true })

onMounted(() => {
  if (latestInference.value) {
    selectInference(latestInference.value)
  }
})

function selectInference(inference: InferenceLogItem) {
  currentInference.value = inference
  nextTick(() => {
    if (videoPlayer.value) {
      videoPlayer.value.load()
    }
  })
}

function onVideoLoaded() {
  if (videoPlayer.value) {
    videoDuration.value = videoPlayer.value.duration
    isPlaying.value = !videoPlayer.value.paused
  }
}

function onTimeUpdate() {
  if (videoPlayer.value) {
    currentTime.value = videoPlayer.value.currentTime
  }
}

function onVideoEnded() {
  isPlaying.value = false
}

function togglePlay() {
  if (videoPlayer.value) {
    if (videoPlayer.value.paused) {
      videoPlayer.value.play()
      isPlaying.value = true
    } else {
      videoPlayer.value.pause()
      isPlaying.value = false
    }
  }
}

function restartVideo() {
  if (videoPlayer.value) {
    videoPlayer.value.currentTime = 0
    videoPlayer.value.play()
    isPlaying.value = true
  }
}

function seekVideo(time: number) {
  if (videoPlayer.value) {
    videoPlayer.value.currentTime = time
  }
}

function getBboxStyle(bbox: [number, number, number, number]) {
  const [x1, y1, x2, y2] = bbox
  const width = x2 - x1
  const height = y2 - y1
  return {
    left: `${x1 * 100}%`,
    top: `${y1 * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
    opacity: highlightedPersonIndex.value === -1 ? 1 : 0.3
  }
}

function highlightPerson(index: number) {
  highlightedPersonIndex.value = index
}

function unhighlightPerson() {
  highlightedPersonIndex.value = -1
}

function highlightVehicle(index: number) {
  // Implementation needed
}

function unhighlightVehicle() {
  // Implementation needed
}

function formatTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleTimeString()
}

function formatTimeRange(videoInfo: any): string {
  const start = Math.round(videoInfo.start_relative_timestamp * 10) / 10
  const end = Math.round(videoInfo.end_relative_timestamp * 10) / 10
  return `${start}s - ${end}s`
}

function getInferencePeopleCount(inference: InferenceLogItem): number {
  try {
    let resultText = inference.result
    if (resultText.includes('```json')) {
      const start = resultText.indexOf('```json') + 7
      const end = resultText.indexOf('```', start)
      if (end > start) {
        resultText = resultText.substring(start, end).trim()
      }
    }
    const result = JSON.parse(resultText) as InferenceResult
    return result.people_count || 0
  } catch {
    return 0
  }
}
</script>

<style scoped>
.inference-player {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.player-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e6e6e6;
}

.player-header h3 {
  margin: 0;
  color: #303133;
}

.inference-status {
  display: flex;
  gap: 8px;
}

.player-container {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
}

.video-section {
  flex: 2;
  display: flex;
  flex-direction: column;
}

.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: #f5f5f5;
  border: 2px dashed #ddd;
  border-radius: 8px;
  color: #999;
}

.video-display {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.video-container {
  position: relative;
  flex: 1;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}

.video-container video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.bbox-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
}

.bbox {
  position: absolute;
  border: 2px solid #ff4757;
  background: rgba(255, 71, 87, 0.1);
  transition: opacity 0.3s;
}

.person-bbox {
  border-color: #ff4757;
  background: rgba(255, 71, 87, 0.1);
}

.vehicle-bbox {
  border-color: #2ed573;
  background: rgba(46, 213, 115, 0.1);
}

.bbox-label {
  position: absolute;
  top: -30px;
  left: 0;
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.person-label {
  background: #ff4757;
}

.vehicle-label {
  background: #2ed573;
}

.video-controls {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 0 0 8px 8px;
}

.progress-bar {
  margin-top: 8px;
}

.info-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}

.inference-details {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.inference-details h4 {
  margin: 0 0 16px 0;
  color: #303133;
}

.detail-group {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e6e6e6;
}

.detail-group label {
  font-weight: 500;
  color: #606266;
}

.people-list {
  margin-top: 16px;
}

.people-list h5 {
  margin: 0 0 8px 0;
  color: #303133;
}

.person-item {
  background: white;
  border: 1px solid #e6e6e6;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.person-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.2);
}

.person-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.person-id {
  font-weight: bold;
  color: #ff4757;
}

.person-activity {
  color: #606266;
}

.person-bbox {
  font-size: 12px;
  color: #909399;
}

.vehicles-list {
  margin-top: 16px;
}

.vehicles-list h5 {
  margin: 0 0 8px 0;
  color: #303133;
}

.vehicle-item {
  background: white;
  border: 1px solid #e6e6e6;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.vehicle-item:hover {
  border-color: #409eff;
}

.vehicle-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.vehicle-id {
  font-weight: bold;
  color: #ff4757;
}

.vehicle-status {
  color: #606266;
}

.vehicle-bbox {
  font-size: 12px;
  color: #909399;
}

.history-section {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.history-section h4 {
  margin: 0 0 16px 0;
  color: #303133;
}

.history-list {
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  background: white;
  border: 1px solid #e6e6e6;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.history-item:hover {
  border-color: #409eff;
}

.history-item.active {
  border-color: #409eff;
  background: #ecf5ff;
}

.history-time {
  font-weight: bold;
  color: #303133;
  margin-bottom: 4px;
}

.history-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}
</style> 