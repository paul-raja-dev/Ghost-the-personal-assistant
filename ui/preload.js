const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ghostAPI', {
  runPrompt: (prompt) => ipcRenderer.invoke('ghost:run-prompt', prompt),
  closeWindow: () => ipcRenderer.invoke('ghost:close-window'),
  setWindowHeight: (height, animate) => ipcRenderer.invoke('ghost:set-height', height, animate),
  savePosition: () => ipcRenderer.invoke('ghost:save-position'),
  listSessions: () => ipcRenderer.invoke('ghost:list-sessions'),
  loadSession: (id) => ipcRenderer.invoke('ghost:load-session', id),
  onResetFocus: (callback) => ipcRenderer.on('ghost:reset-focus', () => callback()),
});
