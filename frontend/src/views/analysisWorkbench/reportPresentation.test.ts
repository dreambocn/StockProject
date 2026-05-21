import { describe, expect, it } from 'vitest'

import {
  buildFallbackSourceItems,
  buildHistoryDiffHints,
  buildReportRuntimeMeta,
  buildUnifiedSourceItems,
} from './reportPresentation'

describe('analysisWorkbench reportPresentation', () => {
  it('builds runtime metadata with session id for traceability', () => {
    const meta = buildReportRuntimeMeta({
      id: 'report-1',
      status: 'ready',
      summary: '摘要',
      risk_points: [],
      factor_breakdown: [],
      generated_at: '2026-05-20T10:00:00Z',
      used_web_search: false,
      session_id: 'session-1',
      prompt_version: 'evidence-first',
      model_name: 'gpt-test',
      reasoning_effort: 'high',
      token_usage_input: 10,
      token_usage_output: 20,
      failure_type: null,
    })

    expect(meta).toContain('提示词 evidence-first')
    expect(meta).toContain('会话 session-1')
  })

  it('keeps history diff rendering as a pure presentation rule', () => {
    const hints = buildHistoryDiffHints(
      {
        id: 'report-new',
        status: 'ready',
        summary: '新摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-05-21T10:00:00Z',
        used_web_search: false,
        evidence_event_count: 4,
        selected_hypothesis: '政策改善',
        decision_confidence: 'high',
      },
      {
        id: 'report-old',
        status: 'ready',
        summary: '旧摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-05-20T10:00:00Z',
        used_web_search: false,
        evidence_event_count: 2,
        selected_hypothesis: '订单改善',
        decision_confidence: 'medium',
      },
      (value) => value || '--',
    )

    expect(hints).toEqual([
      '生成时间：2026-05-20T10:00:00Z → 2026-05-21T10:00:00Z',
      '事件数：2 → 4',
      '采纳假设：订单改善 → 政策改善',
      '置信度：medium → high',
    ])
  })

  it('sorts explicit source items ahead of fallback details by quality and kind', () => {
    const fallbackItems = buildFallbackSourceItems(
      [
        {
          event_id: 'evt-1',
          scope: 'policy',
          title: '政策原文',
          published_at: '2026-05-20T10:00:00Z',
          source: 'gov_cn',
          macro_topic: null,
          event_type: 'policy',
          event_tags: ['policy'],
          sentiment_label: null,
          sentiment_score: null,
          anchor_trade_date: null,
          window_return_pct: null,
          window_volatility: null,
          abnormal_volume_ratio: null,
          correlation_score: null,
          confidence: null,
          link_status: 'linked',
        },
      ],
      [],
      '暂无数据',
    )

    const items = buildUnifiedSourceItems(
      {
        id: 'report-1',
        status: 'ready',
        summary: '摘要',
        risk_points: [],
        factor_breakdown: [],
        generated_at: '2026-05-20T10:00:00Z',
        used_web_search: false,
        source_items: [
          {
            id: 'web-1',
            source_kind: 'web_reference',
            title: '网页引用',
            quality_status: 'domain_inferred',
          },
          {
            id: 'policy-1',
            source_kind: 'policy_document',
            title: '政策来源',
            quality_status: 'verified',
          },
        ],
      },
      fallbackItems,
    )

    expect(items.map((item) => item.id)).toEqual(['policy-1', 'web-1'])
  })
})
