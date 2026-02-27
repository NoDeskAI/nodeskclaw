/**
 * ActivityFeed 事件类型定义 - 供 ActivityFeed 组件和 useGlobalSSE composable 共享。
 */
export interface FeedEvent {
  id: string
  time: string
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
}
