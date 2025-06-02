<template>
  <div id="app">
    <div v-if="isLoading" class="loading-screen">
      <h2>🚀 正在加载监控系统...</h2>
      <p>请稍候</p>
    </div>
    <router-view v-else />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

console.log('App.vue 组件已加载')

const isLoading = ref(true)

onMounted(() => {
  // 模拟加载时间
  setTimeout(() => {
    isLoading.value = false
    console.log('路由视图已准备就绪')
  }, 1000)
})
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

#app {
  height: 100vh;
}

.loading-screen {
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  text-align: center;
}

.loading-screen h2 {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.loading-screen p {
  font-size: 1.2rem;
  opacity: 0.8;
}
</style> 