/**
 * 类型安全的 API 客户端（C1）。
 *
 * 用法：
 *   import { api } from '@/api/client'
 *
 *   const { data } = await api.get('/api/projects/{project_id}/status', {
 *     params: { path: { project_id: 'p1' } }
 *   })
 *   // data 自动推断为 OpenAPI 返回类型；params/body 在改 schema 后编译期报错
 *
 * 渐进式：
 *   - 新代码用 api.get/post/put/delete
 *   - 老 fetch(...) 不强制改；时间到再迁
 */
import type { paths } from '@/types/generated/api'

const BASE = 'http://127.0.0.1:18520'

type HTTPMethod = 'get' | 'post' | 'put' | 'delete' | 'patch'

type PathsOf<M extends HTTPMethod> = {
  [P in keyof paths]: paths[P] extends Record<M, unknown> ? P : never
}[keyof paths]

type Op<M extends HTTPMethod, P extends keyof paths> = paths[P] extends Record<M, infer O> ? O : never

type Params<O> = O extends { parameters: infer P } ? P : never
type RespOk<O> =
  O extends { responses: { 200: { content: { 'application/json': infer T } } } } ? T :
  O extends { responses: { 201: { content: { 'application/json': infer T } } } } ? T :
  O extends { responses: { 200: any } } ? unknown :
  unknown

type Body<O> =
  O extends { requestBody: { content: { 'application/json': infer B } } } ? B :
  never

// 把 OpenAPI 的 path 模板（如 "/api/projects/{project_id}"）填实参数
function fillPath(template: string, pathParams?: Record<string, string | number>): string {
  if (!pathParams) return template
  return template.replace(/\{(\w+)\}/g, (_m, key) => {
    const v = pathParams[key]
    if (v === undefined || v === null) {
      throw new Error(`Missing path param "${key}" for ${template}`)
    }
    return encodeURIComponent(String(v))
  })
}

function buildUrl(path: string, params?: any): string {
  const tpl = fillPath(path, params?.path)
  const url = new URL(tpl, BASE)
  const query = params?.query as Record<string, string | number | boolean | undefined> | undefined
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue
      url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

export interface RequestInit2<P, B> {
  params?: P
  body?:   B
  signal?: AbortSignal
}

async function doRequest<R>(method: string, url: string, body?: any, signal?: AbortSignal): Promise<R> {
  const init: RequestInit = { method, signal }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail: any
    try { detail = await res.json() } catch { detail = await res.text() }
    throw new ApiError(res.status, detail, url)
  }
  if (res.status === 204) return undefined as R
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return (await res.json()) as R
  return undefined as R
}

export class ApiError extends Error {
  constructor(public status: number, public detail: any, public url: string) {
    super(`HTTP ${status}: ${typeof detail === 'string' ? detail : detail?.detail || JSON.stringify(detail)}`)
    this.name = 'ApiError'
  }
}

export const api = {
  async get<P extends PathsOf<'get'>>(
    path: P,
    init?: RequestInit2<Params<Op<'get', P>>, never>,
  ): Promise<RespOk<Op<'get', P>>> {
    return doRequest('GET', buildUrl(path as string, init?.params), undefined, init?.signal)
  },

  async post<P extends PathsOf<'post'>>(
    path: P,
    init?: RequestInit2<Params<Op<'post', P>>, Body<Op<'post', P>>>,
  ): Promise<RespOk<Op<'post', P>>> {
    return doRequest('POST', buildUrl(path as string, init?.params), init?.body, init?.signal)
  },

  async put<P extends PathsOf<'put'>>(
    path: P,
    init?: RequestInit2<Params<Op<'put', P>>, Body<Op<'put', P>>>,
  ): Promise<RespOk<Op<'put', P>>> {
    return doRequest('PUT', buildUrl(path as string, init?.params), init?.body, init?.signal)
  },

  async delete<P extends PathsOf<'delete'>>(
    path: P,
    init?: RequestInit2<Params<Op<'delete', P>>, never>,
  ): Promise<RespOk<Op<'delete', P>>> {
    return doRequest('DELETE', buildUrl(path as string, init?.params), undefined, init?.signal)
  },
}

/** 留给需要拿原始 URL（例如做 SSE）的调用方使用。 */
export function apiUrl<P extends keyof paths>(
  path: P,
  pathParams?: Record<string, string | number>,
  query?: Record<string, string | number | boolean | undefined>,
): string {
  return buildUrl(path as string, { path: pathParams, query })
}
