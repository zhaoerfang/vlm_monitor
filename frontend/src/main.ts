import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

console.log('=== main.ts 开始执行 ===')

try {
  console.log('1. 开始创建Vue应用')
  const app = createApp(App)
  console.log('2. Vue应用创建成功')
  
  console.log('3. 注册Pinia状态管理')
  app.use(createPinia())
  
  console.log('4. 注册Vue Router')
  app.use(router)
  
  console.log('5. 挂载应用到#app')
  app.mount('#app')
  console.log('6. 应用挂载成功！')
  
} catch (error) {
  console.error('❌ 启动失败:', error)
  const errorMessage = error instanceof Error ? error.message : String(error)
  const errorStack = error instanceof Error ? error.stack : ''
  
  document.body.innerHTML = `
    <div style="padding: 20px; font-family: Arial; background: #f5f5f5; min-height: 100vh;">
      <h1 style="color: red;">应用启动失败</h1>
      <p><strong>错误信息:</strong> ${errorMessage}</p>
      <p><strong>错误堆栈:</strong></p>
      <pre style="background: white; padding: 10px; border: 1px solid #ccc;">${errorStack}</pre>
    </div>
  `
} 