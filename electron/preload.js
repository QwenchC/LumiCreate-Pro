const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // Window controls
  windowMinimize: () => ipcRenderer.send('window:minimize'),
  windowMaximize: () => ipcRenderer.send('window:maximize'),
  windowClose: () => ipcRenderer.send('window:close'),
  windowCloseConfirmed: () => ipcRenderer.send('window:close-confirmed'),

  // Listeners from main
  onBeforeClose: (cb) => ipcRenderer.on('app:before-close', cb),
  onMenuNewProject: (cb) => ipcRenderer.on('menu:new-project', cb),
  onMenuOpenProject: (cb) => ipcRenderer.on('menu:open-project', cb),
  onMenuSaveProject: (cb) => ipcRenderer.on('menu:save-project', cb),
  onMenuOpenSettings: (cb) => ipcRenderer.on('menu:open-settings', cb),
  onMenuAbout: (cb) => ipcRenderer.on('menu:about', cb),

  // Dialogs
  selectFolder: () => ipcRenderer.invoke('dialog:select-folder'),
  saveJson: (opts) => ipcRenderer.invoke('dialog:save-json', opts),

  // File system
  readProjectsDir: (dir) => ipcRenderer.invoke('fs:read-projects-dir', dir),
  readFile: (filePath) => ipcRenderer.invoke('fs:read-file', filePath),
  writeFile: (filePath, content) => ipcRenderer.invoke('fs:write-file', filePath, content),
  ensureDir: (dirPath) => ipcRenderer.invoke('fs:ensure-dir', dirPath),

  // Remove listeners (cleanup)
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
})
