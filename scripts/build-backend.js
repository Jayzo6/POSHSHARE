const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist_backend");
const backendExe = path.join(distDir, process.platform === "win32" ? "poshshare-backend.exe" : "poshshare-backend");

if (!fs.existsSync(path.join(root, "server.spec"))) {
  console.error("Missing server.spec file.");
  process.exit(1);
}

if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

const pythonCandidates = process.platform === "win32" ? ["py", "python", "python3"] : ["python3", "python"];
let built = false;
let lastError = null;

for (const cmd of pythonCandidates) {
  const result = spawnSync(
    cmd,
    ["-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist_backend", "--workpath", "build/backend", "server.spec"],
    { cwd: root, stdio: "inherit" }
  );
  if (result.status === 0) {
    built = true;
    break;
  }
  lastError = new Error(`Command "${cmd}" failed with exit code ${result.status}`);
}

if (!built || !fs.existsSync(backendExe)) {
  console.error("Failed to build bundled backend executable.");
  console.error("Install PyInstaller first: py -m pip install pyinstaller");
  if (lastError) console.error(lastError.message);
  process.exit(1);
}

console.log(`Bundled backend ready: ${backendExe}`);
