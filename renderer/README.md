# renderer - 前端应用

Vue 3 + Vite + Electron 前端应用。

更多项目信息请参看根目录的 [README.md](../README.md)

## 开发设置

```sh
npm install
npm run dev      # 启动 Vite 开发服务器（带HMR）
npm run build    # 生产构建
```

## 项目结构

- `src/views/` - 页面（HomeView、ProjectView 等）
- `src/components/` - 可复用组件
  - `tabs/` - 项目标签页（ManuscriptTab、ScenesTab、ImagesTab、AudioTab、VideoTab）
  - 通用组件（TitleBar、UnsavedDialog 等）
- `src/stores/` - Pinia 状态管理
- `src/router/` - Vue Router 路由配置
- `src/assets/` - 样式和资源文件
- `src/style/` - 全局样式（global.css 等）

## 与 Electron 集成

通过 `window.electronAPI` 访问主进程 API：
- `windowClose()` - 关闭窗口
- `windowCloseConfirmed()` - 确认关闭
- `onMenuSaveProject()` - 菜单保存项目事件
- `onBeforeClose()` - 窗口关闭前事件
- 等等...

## 样式系统

使用 CSS 变量主题（在 `style/global.css` 中定义）：
- `--color-accent` - 强调色
- `--color-success` - 成功色
- `--color-error` - 错误色
- 等等...

