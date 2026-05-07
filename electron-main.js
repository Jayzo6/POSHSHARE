const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const { autoUpdater } = require("electron-updater");

const DASHBOARD_URL = "http://127.0.0.1:8000";
let pyProc = null;
let mainWindow = null;
let updateState = {
  status: "idle",
  message: "No update activity yet.",
  currentVersion: app.getVersion(),
  latestVersion: null,
  percent: 0,
  error: null
};

function sendUpdateState() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("update:status", updateState);
}

function setUpdateState(next) {
  updateState = { ...updateState, ...next };
  sendUpdateState();
}

function checkForUpdates() {
  if (!app.isPackaged) {
    setUpdateState({
      status: "disabled",
      message: "Auto-updates are available in packaged builds.",
      latestVersion: null,
      percent: 0,
      error: null
    });
    return;
  }
  setUpdateState({
    status: "checking",
    message: "Checking for updates...",
    percent: 0,
    error: null
  });
  autoUpdater.checkForUpdates().catch((err) => {
    setUpdateState({
      status: "error",
      message: "Failed to check for updates.",
      error: err.message
    });
  });
}

function waitForServer(url, timeoutMs = 20000, intervalMs = 350) {
  return new Promise((resolve, reject) => {
    const start = Date.now();

    const tryOnce = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 500) {
          resolve();
          return;
        }
        if (Date.now() - start > timeoutMs) {
          reject(new Error("Timed out waiting for dashboard server."));
          return;
        }
        setTimeout(tryOnce, intervalMs);
      });

      req.on("error", () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error("Timed out waiting for dashboard server."));
          return;
        }
        setTimeout(tryOnce, intervalMs);
      });
    };

    tryOnce();
  });
}

function startPythonServer() {
  const projectRoot = __dirname;
  const serverPath = path.join(projectRoot, "server.py");
  const pythonCmd = process.platform === "win32" ? "py" : "python3";

  pyProc = spawn(pythonCmd, [serverPath], {
    cwd: projectRoot,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  pyProc.stdout.on("data", (buf) => {
    process.stdout.write(`[python] ${buf}`);
  });

  pyProc.stderr.on("data", (buf) => {
    process.stderr.write(`[python] ${buf}`);
  });

  pyProc.on("exit", (code) => {
    console.log(`Python server exited with code ${code}`);
    pyProc = null;
    if (!app.isQuitting) {
      app.quit();
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0d0d0f",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js")
    }
  });

  mainWindow.loadURL(DASHBOARD_URL);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function setupAutoUpdater() {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("checking-for-update", () => {
    setUpdateState({
      status: "checking",
      message: "Checking for updates..."
    });
  });

  autoUpdater.on("update-available", (info) => {
    setUpdateState({
      status: "available",
      message: `Update ${info.version} is available.`,
      latestVersion: info.version,
      percent: 0,
      error: null
    });
  });

  autoUpdater.on("update-not-available", () => {
    setUpdateState({
      status: "up-to-date",
      message: "You're on the latest version.",
      latestVersion: app.getVersion(),
      percent: 100,
      error: null
    });
  });

  autoUpdater.on("download-progress", (progress) => {
    setUpdateState({
      status: "downloading",
      message: "Downloading update...",
      percent: Math.round(progress.percent || 0),
      error: null
    });
  });

  autoUpdater.on("update-downloaded", (info) => {
    setUpdateState({
      status: "downloaded",
      message: `Update ${info.version} is ready to install.`,
      latestVersion: info.version,
      percent: 100,
      error: null
    });
  });

  autoUpdater.on("error", (err) => {
    setUpdateState({
      status: "error",
      message: "Update failed.",
      error: err.message || String(err)
    });
  });

  ipcMain.handle("update:get-status", () => updateState);
  ipcMain.handle("update:check", async () => {
    checkForUpdates();
    return updateState;
  });
  ipcMain.handle("update:download", async () => {
    if (!app.isPackaged) {
      setUpdateState({
        status: "disabled",
        message: "Download is only available in packaged builds."
      });
      return updateState;
    }
    setUpdateState({
      status: "downloading",
      message: "Starting update download...",
      percent: 0,
      error: null
    });
    await autoUpdater.downloadUpdate();
    return updateState;
  });
  ipcMain.handle("update:install", () => {
    autoUpdater.quitAndInstall();
  });
}

app.on("before-quit", () => {
  app.isQuitting = true;
  if (pyProc) {
    pyProc.kill();
  }
});

app.whenReady().then(async () => {
  setupAutoUpdater();
  startPythonServer();
  try {
    await waitForServer(DASHBOARD_URL);
    createWindow();
    sendUpdateState();
    checkForUpdates();
  } catch (err) {
    console.error(err.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  app.quit();
});
