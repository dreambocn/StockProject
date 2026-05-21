import type { ComputedRef, Ref } from 'vue'

import { analysisApi, type AnalysisReportResponse } from '../../api/analysis'
import { ApiError } from '../../api/http'

type ReportActionsOptions = {
  selectedReport: ComputedRef<AnalysisReportResponse | null>
  activeSummaryMarkdown: ComputedRef<string>
  tsCode: ComputedRef<string>
  exportLoading: Ref<boolean>
  copySummaryMessage: Ref<string>
  errorMessage: Ref<string>
}

const formatApiErrorMessage = (error: unknown, fallback: string) => {
  if (error instanceof ApiError && error.requestId) {
    return `${error.message || fallback}（请求 ${error.requestId}）`
  }
  return error instanceof Error && error.message ? error.message : fallback
}

const triggerReportDownload = (content: string, fileName: string, mimeType: string) => {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return
  }
  const normalizedContent = mimeType.includes('text/markdown') ? `\uFEFF${content}` : content
  const blob = new Blob([normalizedContent], { type: mimeType })
  const objectUrl = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = fileName
  try {
    document.body.appendChild(anchor)
  } catch {
    // 测试环境中的锚点桩对象不是原生节点时，允许跳过真实挂载。
  }
  anchor.click()
  try {
    document.body.removeChild(anchor)
  } catch {
    // 同上：测试桩对象可能无法作为真实节点移除。
  }
  window.setTimeout(() => {
    window.URL.revokeObjectURL(objectUrl)
  }, 0)
}

export const useReportActions = ({
  selectedReport,
  activeSummaryMarkdown,
  tsCode,
  exportLoading,
  copySummaryMessage,
  errorMessage,
}: ReportActionsOptions) => {
  const exportSelectedReport = async (format: 'markdown' | 'html' | 'package') => {
    if (!selectedReport.value?.id) {
      return
    }
    exportLoading.value = true
    try {
      const content = await analysisApi.exportReport(selectedReport.value.id, format)
      if (!content.trim()) {
        throw new Error('导出内容为空')
      }
      const suffix = format === 'html' || format === 'package' ? 'html' : 'md'
      const fileStem = format === 'package'
        ? `${tsCode.value || 'analysis-report'}-${selectedReport.value.id}-research-package`
        : `${tsCode.value || 'analysis-report'}-${selectedReport.value.id}`
      triggerReportDownload(
        content,
        `${fileStem}.${suffix}`,
        format === 'markdown' ? 'text/markdown;charset=utf-8' : 'text/html;charset=utf-8',
      )
    } catch (error) {
      errorMessage.value = formatApiErrorMessage(error, '导出报告失败，请稍后重试')
    } finally {
      exportLoading.value = false
    }
  }

  const copySelectedReportSummary = async () => {
    const content = activeSummaryMarkdown.value.trim()
    if (!content) {
      return
    }
    try {
      await navigator.clipboard?.writeText(content)
      copySummaryMessage.value = '摘要已复制'
    } catch {
      copySummaryMessage.value = '复制摘要失败'
    }
  }

  return {
    exportSelectedReport,
    copySelectedReportSummary,
  }
}
