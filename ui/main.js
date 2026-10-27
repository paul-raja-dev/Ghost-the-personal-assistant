const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// Required for Ubuntu 24.04 unprivileged user namespaces
app.commandLine.appendSwitch('no-sandbox');

let mainWindow = null;
const stateFile = path.join(app.getPath('userData'), 'window-state.json');

function loadWindowState() {
  try {
    if (fs.existsSync(stateFile)) {
      return JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    }
  } catch (e) {}
  return null;
}

function saveWindowState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    const [x, y] = mainWindow.getPosition();
    if (x > 10 || y > 10) {
      fs.mkdirSync(path.dirname(stateFile), { recursive: true });
      fs.writeFileSync(stateFile, JSON.stringify({ x, y }));
    }
  } catch (e) {}
}

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
  const width = 580;
  const height = 112;

  const defaultX = Math.round((screenWidth - width) / 2);
  const defaultY = Math.round(screenHeight / 4);

  const saved = loadWindowState();
  let x = (saved && typeof saved.x === 'number') ? saved.x : defaultX;
  let y = (saved && typeof saved.y === 'number') ? saved.y : defaultY;

  if (x < 10 || x > screenWidth - 100) x = defaultX;
  if (y < 10 || y > screenHeight - 60) y = defaultY;

  mainWindow = new BrowserWindow({
    width: width,
    height: height,
    x: x,
    y: y,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: true,
    show: false,
    backgroundColor: '#00000000',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  mainWindow.once('ready-to-show', () => {
    // Explicitly apply coordinates so Linux WM does not force top-left
    mainWindow.setPosition(x, y);
    mainWindow.show();
    mainWindow.focus();

    setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.setPosition(x, y);
      }
    }, 60);
  });

  mainWindow.on('moved', () => {
    saveWindowState();
  });
}

// Single instance handling
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (!mainWindow.isVisible()) mainWindow.show();
      mainWindow.focus();
      mainWindow.webContents.send('ghost:reset-focus');
    }
  });

  let resizeInterval = null;
  ipcMain.handle('ghost:set-height', (event, newHeight, animate = false) => {
    if (!mainWindow) return;
    if (resizeInterval) {
      clearInterval(resizeInterval);
      resizeInterval = null;
    }

    const [w, currentH] = mainWindow.getSize();
    if (currentH === newHeight) return;

    if (!animate) {
      mainWindow.setSize(w, newHeight);
      return;
    }

    // Smooth interpolation across ~140ms
    const stepCount = 8;
    const diff = newHeight - currentH;
    const stepH = diff / stepCount;
    let step = 0;

    resizeInterval = setInterval(() => {
      step++;
      if (step >= stepCount) {
        clearInterval(resizeInterval);
        resizeInterval = null;
        if (mainWindow) mainWindow.setSize(w, newHeight);
      } else {
        if (mainWindow) {
          const target = Math.round(currentH + stepH * step);
          mainWindow.setSize(w, target);
        }
      }
    }, 16);
  });

  ipcMain.handle('ghost:save-position', () => {
    saveWindowState();
  });

  ipcMain.handle('ghost:run-prompt', async (event, prompt) => {
    return new Promise((resolve) => {
      const rootDir = path.join(__dirname, '..');
      const venvPython = path.join(rootDir, '.venv', 'bin', 'python');
      const pythonExec = fs.existsSync(venvPython) ? venvPython : 'python3';
      const backendScript = path.join(rootDir, 'backend', 'main.py');

      const pyProcess = spawn(pythonExec, [backendScript, prompt], { cwd: rootDir });

      let stdout = '';
      let stderr = '';

      pyProcess.stdout.on('data', (d) => { stdout += d.toString(); });
      pyProcess.stderr.on('data', (d) => { stderr += d.toString(); });

      pyProcess.on('close', () => {
        const lines = stdout.split('\n').filter((l) => {
          const t = l.trim();
          return t && !t.startsWith('Direct use of automatic function calling');
        });
        const result = lines.join('\n').trim();
        resolve(result || stderr.trim() || 'Done.');
      });

      pyProcess.on('error', (err) => {
        resolve(`Error: ${err.message}`);
      });
    });
  });

  ipcMain.handle('ghost:close-window', () => {
    saveWindowState();
    app.quit();
  });

  app.whenReady().then(createWindow);

  app.on('window-all-closed', () => {
    app.quit();
  });
}
