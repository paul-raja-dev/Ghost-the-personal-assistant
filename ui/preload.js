const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ghostAPI', {
  runPrompt: (prompt) => ipcRenderer.invoke('ghost:run-prompt', prompt),
  closeWindow: () => ipcRenderer.invoke('ghost:close-window'),
  setWindowHeight: (height, animate) => ipcRenderer.invoke('ghost:set-height', height, animate),
  savePosition: () => ipcRenderer.invoke('ghost:save-position'),
  onResetFocus: (callback) => ipcRenderer.on('ghost:reset-focus', () => callback()),
});
