/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// Element Plus 全局组件类型声明
declare module '@vue/runtime-core' {
  export interface GlobalComponents {
    ElButton: typeof import('element-plus')['ElButton']
    ElTag: typeof import('element-plus')['ElTag']
    ElIcon: typeof import('element-plus')['ElIcon']
    ElSlider: typeof import('element-plus')['ElSlider']
    ElButtonGroup: typeof import('element-plus')['ElButtonGroup']
    ElMessage: typeof import('element-plus')['ElMessage']
  }
} 