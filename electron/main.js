const { app, BrowserWindow, ipcMain, dialog, Menu, shell } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const fs = require('fs')

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

let mainWindow = null
let backendProcess = null

// ────────────────────────────────────────────────
// Backend (Python FastAPI) launch
// ────────────────────────────────────────────────
function startBackend() {
  const backendDir = isDev
    ? path.join(__dirname, '..', 'backend')
    : path.join(process.resourcesPath, 'backend')

  const pythonExe = process.platform === 'win32' ? 'python' : 'python3'
  const scriptPath = path.join(backendDir, 'main.py')

  if (!fs.existsSync(scriptPath)) {
    console.warn('[Backend] main.py not found, skipping backend start')
    return
  }

  // ── Kill stale process occupying port 18520 before starting ──────────────
  const { execSync } = require('child_process')
  try {
    if (process.platform === 'win32') {
      // netstat -ano | findstr :18520  →  get PID from last column
      const out = execSync('netstat -ano 2>nul | findstr :18520', { encoding: 'utf8' })
      const pids = new Set()
      for (const line of out.split('\n')) {
        const m = line.trim().match(/\s(\d+)$/)
        if (m && m[1] !== '0') pids.add(m[1])
      }
      for (const pid of pids) {
        try { execSync(`taskkill /PID ${pid} /F 2>nul`) } catch {}
        console.log(`[Backend] Killed stale PID ${pid} on port 18520`)
      }
    } else {
      execSync('fuser -k 18520/tcp 2>/dev/null || true')
    }
  } catch {
    // port was already free — nothing to do
  }

  backendProcess = spawn(pythonExe, [scriptPath], {
    cwd: backendDir,
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  })

  backendProcess.stdout.on('data', (data) => console.log('[Backend]', data.toString().trim()))
  backendProcess.stderr.on('data', (data) => console.error('[Backend ERR]', data.toString().trim()))
  backendProcess.on('close', (code) => console.log('[Backend] exited with code', code))
}

// ────────────────────────────────────────────────
// Main window
// ────────────────────────────────────────────────
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    title: 'LumiCreate-Local',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    frame: false,          // custom titlebar via renderer
    titleBarStyle: 'hidden'
  })

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'dist', 'index.html'))
  }

  mainWindow.on('close', (e) => {
    // Ask renderer if there are unsaved changes before closing
    e.preventDefault()
    mainWindow.webContents.send('app:before-close')
  })
}

// ────────────────────────────────────────────────
// App menu
// ────────────────────────────────────────────────
function buildMenu() {
  const template = [
    {
      label: '文件',
      submenu: [
        { label: '新建项目', accelerator: 'CmdOrCtrl+N', click: () => mainWindow.webContents.send('menu:new-project') },
        { label: '打开项目', accelerator: 'CmdOrCtrl+O', click: () => mainWindow.webContents.send('menu:open-project') },
        { label: '保存项目', accelerator: 'CmdOrCtrl+S', click: () => mainWindow.webContents.send('menu:save-project') },
        { type: 'separator' },
        { label: '退出', accelerator: 'Alt+F4', role: 'quit' }
      ]
    },
    {
      label: '编辑',
      submenu: [
        { label: '撤销', accelerator: 'CmdOrCtrl+Z', role: 'undo' },
        { label: '重做', accelerator: 'CmdOrCtrl+Shift+Z', role: 'redo' },
        { type: 'separator' },
        { label: '剪切', role: 'cut' },
        { label: '复制', role: 'copy' },
        { label: '粘贴', role: 'paste' }
      ]
    },
    {
      label: '设置',
      submenu: [
        { label: '引擎配置...', click: () => mainWindow.webContents.send('menu:open-settings') }
      ]
    },
    {
      label: '关于',
      submenu: [
        { label: '关于 LumiCreate', click: () => mainWindow.webContents.send('menu:about') },
        { label: '开源仓库', click: () => shell.openExternal('https://github.com/QwenchC/LumiCreate') },
        { type: 'separator' },
        { label: '开发者工具', accelerator: 'F12', click: () => mainWindow.webContents.toggleDevTools() }
      ]
    }
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// ────────────────────────────────────────────────
// IPC handlers
// ────────────────────────────────────────────────
ipcMain.handle('dialog:select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    title: '选择项目文件夹'
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('dialog:save-json', async (_, { defaultPath, content }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath,
    filters: [{ name: 'JSON', extensions: ['json'] }]
  })
  if (!result.canceled) {
    fs.writeFileSync(result.filePath, content, 'utf-8')
    return result.filePath
  }
  return null
})

ipcMain.handle('fs:read-projects-dir', async (_, dir) => {
  if (!dir || !fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter(d => d.isDirectory())
    .map(d => {
      const projFile = path.join(dir, d.name, 'project.json')
      if (fs.existsSync(projFile)) {
        try {
          return JSON.parse(fs.readFileSync(projFile, 'utf-8'))
        } catch { return null }
      }
      return null
    })
    .filter(Boolean)
})

ipcMain.handle('fs:read-file', async (_, filePath) => {
  if (!filePath || !fs.existsSync(filePath)) return null
  return fs.readFileSync(filePath, 'utf-8')
})

ipcMain.handle('fs:write-file', async (_, filePath, content) => {
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  fs.writeFileSync(filePath, content, 'utf-8')
  return true
})

ipcMain.handle('fs:ensure-dir', async (_, dirPath) => {
  fs.mkdirSync(dirPath, { recursive: true })
  return true
})

ipcMain.on('window:close-confirmed', () => {
  mainWindow.destroy()
})

ipcMain.on('window:minimize', () => mainWindow.minimize())
ipcMain.on('window:maximize', () => {
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize()
})
ipcMain.on('window:close', () => mainWindow.webContents.send('app:before-close'))

// ────────────────────────────────────────────────
// Lifecycle
// ────────────────────────────────────────────────
app.whenReady().then(() => {
  startBackend()
  buildMenu()
  createWindow()
})

app.on('window-all-closed', () => {
  if (backendProcess) backendProcess.kill()
  if (process.platform !== 'darwin') app.quit()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
