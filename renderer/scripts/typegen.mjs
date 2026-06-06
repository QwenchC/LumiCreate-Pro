/**
 * C1: 从 FastAPI 的 OpenAPI schema 生成前端 TS 类型。
 *
 * 使用：
 *   npm run typegen          # 用 backend/openapi.snapshot.json（离线）
 *   npm run typegen:live     # 从运行中的 backend 拉最新 schema
 *
 * 流程：
 *   1) 选源：LUMI_OPENAPI_URL > backend/openapi.snapshot.json
 *   2) 调 openapi-typescript 生成 paths + components 类型
 *   3) 写入 src/types/generated/api.ts
 */
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '..', '..')
const OUT_PATH  = resolve(__dirname, '..', 'src', 'types', 'generated', 'api.ts')
const SNAPSHOT  = resolve(REPO_ROOT, 'backend', 'openapi.snapshot.json')

const SOURCE_URL = process.env.LUMI_OPENAPI_URL || ''

async function loadSchema() {
  if (SOURCE_URL) {
    console.log(`[typegen] fetching live OpenAPI: ${SOURCE_URL}`)
    try {
      const res = await fetch(SOURCE_URL)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      return json
    } catch (e) {
      console.error(`[typegen] live fetch failed: ${e.message}`)
      if (!existsSync(SNAPSHOT)) {
        process.exit(1)
      }
      console.warn(`[typegen] falling back to snapshot at ${SNAPSHOT}`)
    }
  }
  if (!existsSync(SNAPSHOT)) {
    console.error(
      `[typegen] no snapshot at ${SNAPSHOT}. ` +
      `Run "python -c \\"from app import create_app, json; ...\\"" to dump one, ` +
      `or set LUMI_OPENAPI_URL.`
    )
    process.exit(1)
  }
  console.log(`[typegen] using snapshot: ${SNAPSHOT}`)
  return JSON.parse(readFileSync(SNAPSHOT, 'utf-8'))
}

async function main() {
  const schema = await loadSchema()
  const ast = await openapiTS(schema, {
    exportType: true,
    additionalProperties: false,
  })
  const code = astToString(ast)

  const header = [
    '/* ──────────────────────────────────────────────────────────────────────',
    ' *  AUTO-GENERATED — do not edit by hand.',
    ' *  Source: backend/openapi.snapshot.json (or running backend if --live)',
    ' *  Regenerate: cd renderer && npm run typegen[:live]',
    ' * ──────────────────────────────────────────────────────────────────────',
    ' */',
    '/* eslint-disable */',
    '',
  ].join('\n')

  mkdirSync(dirname(OUT_PATH), { recursive: true })
  writeFileSync(OUT_PATH, header + code, 'utf-8')
  console.log(`[typegen] wrote ${OUT_PATH} (${code.length} bytes)`)
}

main().catch(e => {
  console.error('[typegen] fatal:', e)
  process.exit(1)
})
