const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const http = require("http");
const net = require("net");
const { autoUpdater } = require("electron-updater");

const DEFAULT_PORT = 8000;
let pyProc = null;
let mainWindow = null;
let backendStderr = "";
let backendPort = DEFAULT_PORT;
let updateState = {
  status: "idle",
  message: "No update activity yet.",
  currentVersion: app.getVersion(),
  latestVersion: null,
  percent: 0,
  error: null
};

function getDashboardUrl() {
  return `http://127.0.0.1:${backendPort}`;
}

function probePort(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.on("error", () => resolve(false));
    server.listen({ port, host: "127.0.0.1" }, () => {
      server.close(() => resolve(true));
    });
  });
}

async function pickBackendPort(startPort = DEFAULT_PORT, maxAttempts = 25) {
  for (let i = 0; i < maxAttempts; i++) {
    const candidate = startPort + i;
    // eslint-disable-next-line no-await-in-loop
    const open = await probePort(candidate);
    if (open) return candidate;
  }
  throw new Error(`No open backend port found from ${startPort} to ${startPort + maxAttempts - 1}`);
}

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

function getBackendRoot() {
  return app.isPackaged ? path.join(process.resourcesPath, "backend") : __dirname;
}

function getBundledBackendExecutable() {
  const backendRoot = getBackendRoot();
  if (process.platform === "win32") {
    return path.join(backendRoot, "poshshare-backend.exe");
  }
  return path.join(backendRoot, "poshshare-backend");
}

function getPythonCandidates() {
  if (process.platform === "win32") {
    return ["py", "python", "python3"];
  }
  return ["python3", "python"];
}

function spawnPythonServer(command, serverPath, cwd) {
  return new Promise((resolve, reject) => {
    const args = serverPath ? [serverPath] : [];
    const child = spawn(command, args, {
      cwd,
      env: {
        ...process.env,
        POSHSHARE_PORT: String(backendPort)
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });

    let settled = false;
    const onReady = () => {
      if (settled) return;
      settled = true;
      resolve(child);
    };

    const timer = setTimeout(onReady, 250);

    child.once("error", (err) => {
      clearTimeout(timer);
      if (settled) return;
      settled = true;
      reject(err);
    });

    child.once("spawn", onReady);
  });
}

async function startPythonServer() {
  const projectRoot = getBackendRoot();
  const serverPath = path.join(projectRoot, "server.py");
  const candidates = getPythonCandidates();
  let lastErr = null;

  for (const cmd of candidates) {
    try {
      pyProc = await spawnPythonServer(cmd, serverPath, projectRoot);
      console.log(`Started backend with command: ${cmd}`);
      break;
    } catch (err) {
      lastErr = err;
      if (err && err.code !== "ENOENT") {
        throw err;
      }
    }
  }

  if (!pyProc) {
    const errMsg = "Python runtime not found. Install Python 3 and reopen the app.";
    dialog.showErrorBox("Poshshare startup error", errMsg);
    throw lastErr || new Error(errMsg);
  }
}

async function startBackendServer() {
  if (app.isPackaged) {
    const backendExe = getBundledBackendExecutable();
    pyProc = await spawnPythonServer(backendExe, "", path.dirname(backendExe)).catch((err) => {
      const reason = err?.message ? `\n\nDetails:\n${err.message}` : "";
      dialog.showErrorBox(
        "Poshshare startup error",
        `Bundled backend executable not found or failed to start:\n${backendExe}${reason}`
      );
      throw err;
    });
    console.log(`Started bundled backend: ${backendExe}`);
  } else {
    await startPythonServer();
  }

  pyProc.stdout.on("data", (buf) => {
    process.stdout.write(`[python] ${buf}`);
  });

  pyProc.stderr.on("data", (buf) => {
    const chunk = String(buf);
    backendStderr += chunk;
    if (backendStderr.length > 6000) {
      backendStderr = backendStderr.slice(-6000);
    }
    process.stderr.write(`[python] ${chunk}`);
  });

  pyProc.on("exit", (code) => {
    console.log(`Python server exited with code ${code}`);
    pyProc = null;
    if (!app.isQuitting) {
      const reason = backendStderr.trim()
        ? `\n\nDetails:\n${backendStderr.trim()}`
        : "";
      dialog.showErrorBox(
        "Poshshare backend failed to start",
        `The local backend process exited (code ${code ?? "unknown"}).` + reason
      );
      app.quit();
    }
  });
}

function createWindow() {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, "assets", "icon.png")
    : path.join(__dirname, "assets", "icon.png");
  mainWindow = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: "#0d0d0f",
    autoHideMenuBar: true,
    icon: iconPath,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js")
    }
  });

  mainWindow.loadURL(getDashboardUrl());
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
  try {
    backendPort = await pickBackendPort();
    await startBackendServer();
    await waitForServer(getDashboardUrl());
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
