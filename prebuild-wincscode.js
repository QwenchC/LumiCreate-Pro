/**
 * prebuild-wincscode.js
 *
 * Pre-populates the electron-builder winCodeSign cache by extracting the archive
 * while EXCLUDING the darwin/ directory (which contains macOS symlinks that
 * require elevated symlink creation privileges on Windows).
 *
 * Without this, electron-builder fails with:
 *   "Cannot create symbolic link : 客户端没有所需的特权"
 * even when code signing is disabled.
 */

const { spawnSync } = require('child_process')
const path = require('path')
const fs   = require('fs')
const os   = require('os')
const https = require('https')

const VERSION       = 'winCodeSign-2.6.0'
const DOWNLOAD_URL  = `https://github.com/electron-userland/electron-builder-binaries/releases/download/${VERSION}/${VERSION}.7z`
const LOCAL_APPDATA = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local')
const CACHE_ROOT    = path.join(LOCAL_APPDATA, 'electron-builder', 'Cache', 'winCodeSign')
const TARGET_DIR    = path.join(CACHE_ROOT, VERSION)
const SEVENZIP      = path.join(__dirname, 'node_modules', '7zip-bin', 'win', 'x64', '7za.exe')

async function main () {
  // Already cached — nothing to do
  if (fs.existsSync(TARGET_DIR)) {
    console.log('[prebuild] winCodeSign cache OK:', TARGET_DIR)
    return
  }

  console.log('[prebuild] winCodeSign cache missing — pre-populating...')
  fs.mkdirSync(CACHE_ROOT, { recursive: true })

  // Re-use any .7z already downloaded by previous failed electron-builder runs
  let archivePath = null
  if (fs.existsSync(CACHE_ROOT)) {
    const existing = fs.readdirSync(CACHE_ROOT).filter(f => f.endsWith('.7z'))
    if (existing.length > 0) {
      archivePath = path.join(CACHE_ROOT, existing[0])
      console.log('[prebuild] Re-using cached archive:', archivePath)
    }
  }

  // Otherwise download fresh
  if (!archivePath) {
    archivePath = path.join(os.tmpdir(), `${VERSION}.7z`)
    console.log('[prebuild] Downloading', DOWNLOAD_URL)
    await download(DOWNLOAD_URL, archivePath)
    console.log('[prebuild] Download complete')
  }

  // Extract, skipping darwin/ (macOS symlinks)
  if (!fs.existsSync(SEVENZIP)) {
    console.error('[prebuild] 7-zip not found at', SEVENZIP)
    console.error('[prebuild] Run: npm install')
    process.exit(1)
  }

  const tmp = path.join(CACHE_ROOT, `_tmp_${Date.now()}`)
  fs.mkdirSync(tmp, { recursive: true })

  console.log('[prebuild] Extracting (excluding darwin/)...')
  const result = spawnSync(
    SEVENZIP,
    ['x', '-bd', archivePath, `-o${tmp}`, '-x!darwin', '-y'],
    { stdio: 'inherit' }
  )

  if (result.status !== 0) {
    console.error('[prebuild] Extraction failed')
    fs.rmSync(tmp, { recursive: true, force: true })
    process.exit(1)
  }

  // Move extracted dir to final cache location
  fs.renameSync(tmp, TARGET_DIR)
  console.log('[prebuild] winCodeSign cache ready:', TARGET_DIR)
}

function download (url, dest) {
  return new Promise((resolve, reject) => {
    const follow = (u) => {
      https.get(u, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          follow(res.headers.location)
          return
        }
        const file = fs.createWriteStream(dest)
        res.pipe(file)
        file.on('finish', () => { file.close(); resolve() })
        file.on('error',  (e) => { fs.unlink(dest, () => {}); reject(e) })
      }).on('error', reject)
    }
    follow(url)
  })
}

main().catch(e => { console.error('[prebuild]', e); process.exit(1) })
