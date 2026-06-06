/**
 * C1: typed client 烟雾测试。
 * 验证：apiUrl 路径模板填充 / query 序列化 / ApiError 行为。
 * 不发真请求；用 fetch mock 检查传参。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, apiUrl, ApiError } from './client'

describe('apiUrl', () => {
  it('fills path params', () => {
    const u = apiUrl('/api/projects/{project_id}/status', { project_id: 'p1' })
    expect(u).toContain('/api/projects/p1/status')
  })

  it('encodes path param special chars', () => {
    const u = apiUrl('/api/projects/{project_id}/status', { project_id: 'a/b c' })
    expect(u).toContain('/api/projects/a%2Fb%20c/status')
  })

  it('serializes query params', () => {
    const u = apiUrl('/api/projects/{project_id}/events',
                     { project_id: 'p1' },
                     { trace_id: 'abc', limit: 10, level: undefined })
    expect(u).toContain('trace_id=abc')
    expect(u).toContain('limit=10')
    expect(u).not.toContain('level=')   // undefined should be skipped
  })

  it('throws if path param missing', () => {
    expect(() => apiUrl('/api/projects/{project_id}/status' as any, {} as any))
      .toThrow(/Missing path param "project_id"/)
  })
})

describe('api.get', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch')
  })
  afterEach(() => fetchSpy.mockRestore())

  it('returns parsed JSON on 200', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(
      JSON.stringify({ summary: { project_stage: 'drafted' }, scenes: [] }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const data = await api.get('/api/projects/{project_id}/status', {
      params: { path: { project_id: 'p1' } },
    })
    expect((data as any).summary.project_stage).toBe('drafted')
    expect(fetchSpy).toHaveBeenCalledOnce()
    const [calledUrl] = fetchSpy.mock.calls[0]
    expect(String(calledUrl)).toContain('/api/projects/p1/status')
  })

  it('throws ApiError on non-2xx with detail', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: 'not found' }),
      { status: 404, headers: { 'content-type': 'application/json' } },
    ))
    await expect(
      api.get('/api/projects/{project_id}/status', { params: { path: { project_id: 'no' } } })
    ).rejects.toThrow(ApiError)
  })
})

describe('api.post', () => {
  it('sends JSON body and parses response', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(new Response(
      JSON.stringify({ task_id: 'abcd1234', status: 'pending' }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const result = await api.post('/api/tasks', {
      body: {
        project_id: 'p1', type: 'orchestrator',
        request: { stages: ['scenes'] },
      },
    })
    expect((result as any).task_id).toBe('abcd1234')
    const init = fetchSpy.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect((init.headers as any)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string).type).toBe('orchestrator')
    fetchSpy.mockRestore()
  })
})
