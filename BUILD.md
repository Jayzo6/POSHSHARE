# Building Poshmark Sharing Bot for distribution

This lets you create a **single exe** (browser included) or a **folder** (exe + browser) that runs on any Windows PC without installing Python.

## 1. Install build tools

```bash
pip install pyinstaller playwright requests
playwright install chromium
```

## 2. Build the exe

### Option A: Single exe with browser included (recommended)

One exe file; no separate `browsers` folder. The exe will be large (~300–400 MB).

1. **Install Chromium into the project folder** (one-time, from the project root):

   **PowerShell:**
   ```powershell
   cd path\to\poshshare
   $env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\bundled_browsers"
   playwright install chromium
   ```

   **CMD:**
   ```bat
   cd path\to\poshshare
   set PLAYWRIGHT_BROWSERS_PATH=%CD%\bundled_browsers
   playwright install chromium
   ```

2. **Build:**
   ```bash
   pyinstaller main.spec
   ```

3. **Ship** `dist/PoshmarkSharingBot.exe`. No zip of a folder needed; the exe is self-contained.

### Option B: Exe only, then add browser folder

If you skip the step above, you get a smaller exe that expects a `browsers` folder next to it (see Option C below).

```bash
pyinstaller main.spec
```

Output: `dist/PoshmarkSharingBot.exe` (one file).

## 3. Make it run on any PC (if you didn’t bundle the browser)

The exe needs Chromium. You can either ship it with the browser or ask users to install it once.

### Option C: Ship exe + browser folder (no setup on their PC)

1. Create a folder, e.g. `PoshmarkSharingBot`.
2. Copy `dist/PoshmarkSharingBot.exe` into that folder.
3. In that **same folder**, run (so Chromium installs next to the exe):

   ```bash
   set PLAYWRIGHT_BROWSERS_PATH=%CD%\browsers
   playwright install chromium
   ```

   Or in PowerShell:

   ```powershell
   $env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\browsers"
   playwright install chromium
   ```

4. You should now have:

   ```
   PoshmarkSharingBot/
   ├── PoshmarkSharingBot.exe
   └── browsers/
       └── chromium-xxxx/   (Playwright’s Chromium)
   ```

5. Zip `PoshmarkSharingBot` and give that zip to anyone. They unzip, run `PoshmarkSharingBot.exe`, and it works. No Python or browser install needed on their PC.

### Option D: User installs browser once

- Give users only `PoshmarkSharingBot.exe`.
- On each PC, they must run **once** (requires Python):

  ```bash
  pip install playwright
  playwright install chromium
  ```

  Then they can run the exe. The exe will use the Chromium installed by Playwright for that user.

## 4. Where the app stores data

- **When run as exe:** credentials and closets list are stored in:
  - `%LOCALAPPDATA%\PoshmarkSharingBot\`
  - e.g. `C:\Users\<username>\AppData\Local\PoshmarkSharingBot\`
- So each Windows user gets their own data, and the exe can live anywhere (Desktop, USB, etc.).

## 5. Summary

| Goal | Steps |
|------|--------|
| **Single exe (browser inside)** | 1) `PLAYWRIGHT_BROWSERS_PATH=.\bundled_browsers` and `playwright install chromium` in project folder. 2) `pyinstaller main.spec`. Ship `dist/PoshmarkSharingBot.exe`. |
| **Exe + folder** | Build exe, copy to a folder, install browser into that folder, zip folder. User unzips and runs exe. |
| **End user** | Run `PoshmarkSharingBot.exe` (no Python or browser install if you used Option A or C). |
