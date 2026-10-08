import type { PreprocessMethodReport, PreprocessReport } from '@/types/app'

export function formatTime(ts?: number) {
  if (!ts) return '未知'
  return new Date(ts * 1000).toLocaleString()
}

export function asFiniteNumber(value: unknown, fallback = 0) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : fallback
}

export function sumNumericValues(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (Array.isArray(value)) return value.reduce((total, item) => total + sumNumericValues(item), 0)
  if (value && typeof value === 'object') {
    return (Object.values(value as Record<string, unknown>) as unknown[]).reduce<number>(
      (total, item) => total + sumNumericValues(item),
      0,
    )
  }
  return 0
}

export function objectEntryCount(value: unknown): number {
  return value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value as Record<string, unknown>).length : 0
}

export function directPreprocessChange(item: PreprocessMethodReport) {
  const method = String(item.method || '')
  const operations = (item.operations || {}) as Record<string, unknown>
  const rowsIn = asFiniteNumber(item.rowsIn)
  const rowsOut = asFiniteNumber(item.rowsOut)
  const columnsIn = asFiniteNumber(item.columnsIn)
  const columnsOut = asFiniteNumber(item.columnsOut)
  const missingBefore = asFiniteNumber(item.missingBefore)
  const missingAfter = asFiniteNumber(item.missingAfter)

  if (method === 'dedupe') return `行数 ${rowsIn} → ${rowsOut}`
  if (method === 'missing_fill') return `缺失值 ${missingBefore} → ${missingAfter}`
  if (method === 'anomaly_correct') return `异常值纠正 ${sumNumericValues(operations.anomaliesCorrected)} 处`
  if (method === 'unit_dimension_check') return `单位统一 ${sumNumericValues(operations.unitConversions)} 处`
  if (method === 'engineering_constraint_check') {
    const corrections = sumNumericValues(operations.constraintCorrections) + sumNumericValues(operations.monotonicCorrections)
    return `工程约束修正 ${corrections} 处`
  }
  if (method === 'schema_standardize') {
    const renamedColumns = objectEntryCount(operations.columnsRenamed)
    return renamedColumns ? `列名标准化 ${renamedColumns} 列` : `列数 ${columnsIn} → ${columnsOut}`
  }
  if (method === 'format_standardize') {
    const renamedColumns = objectEntryCount(operations.columnsRenamed)
    const inferredTypes = objectEntryCount(operations.typesInferred)
    if (inferredTypes) return `类型推断 ${inferredTypes} 项`
    if (renamedColumns) return `列名清理 ${renamedColumns} 列`
    return `缺失值 ${missingBefore} → ${missingAfter}`
  }
  if (method === 'las_to_excel') return `Excel 输出 ${rowsOut} 行`

  if (rowsIn !== rowsOut) return `行数 ${rowsIn} → ${rowsOut}`
  if (missingBefore !== missingAfter) return `缺失值 ${missingBefore} → ${missingAfter}`
  if (columnsIn !== columnsOut) return `列数 ${columnsIn} → ${columnsOut}`
  return '无直接变动'
}

export function summarizePreprocessReport(report?: PreprocessReport | null) {
  const methodReports = Array.isArray(report?.methodReports) ? report?.methodReports || [] : []
  const firstMethod = methodReports[0]
  const lastMethod = methodReports[methodReports.length - 1]
  const columnsIn = Array.isArray(report?.columnsIn) ? report?.columnsIn || [] : []
  const columnsOut = Array.isArray(report?.columnsOut) ? report?.columnsOut || [] : []
  const rowsIn = asFiniteNumber(report?.rowsIn ?? firstMethod?.rowsIn)
  const rowsOut = asFiniteNumber(report?.rowsOut ?? lastMethod?.rowsOut)
  const missingBefore = asFiniteNumber(firstMethod?.missingBefore)
  const missingAfter = asFiniteNumber(lastMethod?.missingAfter)

  return {
    rowsIn,
    rowsOut,
    rowsDelta: rowsOut - rowsIn,
    columnsIn,
    columnsOut,
    missingBefore,
    missingAfter,
    methodHighlights: methodReports.map((item, index) => ({
      id: `${String(item.method || item.name || 'step')}-${index}`,
      name: String(item.name || item.method || '预处理步骤'),
      directText: directPreprocessChange(item),
    })),
    methodCount: methodReports.length,
  }
}
