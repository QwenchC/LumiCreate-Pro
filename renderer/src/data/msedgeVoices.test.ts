import { describe, it, expect } from 'vitest'
import { MSEDGE_VOICES, filterVoices, groupByGender } from './msedgeVoices'

describe('msedgeVoices', () => {
  it('includes 14 builtin voices with gender + label', () => {
    expect(MSEDGE_VOICES.length).toBeGreaterThanOrEqual(14)
    for (const v of MSEDGE_VOICES) {
      expect(v.value).toMatch(/^zh-CN-/)
      expect(v.gender).toMatch(/^(female|male|child)$/)
      expect(v.label.length).toBeGreaterThan(0)
    }
  })

  it('filterVoices: empty allow list returns ALL voices (no filtering)', () => {
    expect(filterVoices([], []).length).toEqual(MSEDGE_VOICES.length)
    expect(filterVoices(undefined as any, []).length).toEqual(MSEDGE_VOICES.length)
  })

  it('filterVoices: only allowed voices appear', () => {
    const allowed = ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural']
    const result = filterVoices(allowed, [])
    expect(result.length).toBe(2)
    expect(result.map(v => v.value).sort()).toEqual(allowed.sort())
  })

  it('filterVoices: extraSelected is preserved even if not in allow list', () => {
    const allowed = ['zh-CN-XiaoxiaoNeural']
    const result = filterVoices(allowed, ['zh-CN-YunjianNeural'])
    expect(result.map(v => v.value).sort()).toEqual(
      ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunjianNeural'].sort()
    )
  })

  it('groupByGender: returns at most 3 groups, each non-empty', () => {
    const groups = groupByGender(MSEDGE_VOICES)
    expect(groups.length).toBeLessThanOrEqual(3)
    for (const g of groups) {
      expect(g.items.length).toBeGreaterThan(0)
      expect(['female', 'male', 'child']).toContain(g.gender)
    }
  })

  it('groupByGender: skips empty groups when input is subset', () => {
    const onlyFemale = MSEDGE_VOICES.filter(v => v.gender === 'female').slice(0, 2)
    const groups = groupByGender(onlyFemale)
    expect(groups.length).toBe(1)
    expect(groups[0].gender).toBe('female')
  })
})
