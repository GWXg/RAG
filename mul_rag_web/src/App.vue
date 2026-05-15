<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

type Kb = {
  kbId: string
  kbName: string
  vectorStoreType?: string
  embedModel?: string
  fileCount?: number
  createdAt?: number
}

type KbFile = {
  fileId: string
  fileName?: string
  type?: string
  hasParsed?: boolean
  isIndexed?: boolean
  pageCount?: number
  tableCount?: number
  parseMethod?: string
  parser?: string
}

type FileTaskState = {
  phase: 'parse' | 'index'
  status: 'queued' | 'running' | 'done' | 'failed'
  message: string
  progress?: number
}

type SearchResult = {
  text?: string
  content?: string
  chunk_text?: string
  fileId?: string
  fileName?: string
  entity_key?: string
  source?: string
  page?: number
  score?: number
  metadata?: Record<string, unknown>
}

type PreprocessMethod = {
  id: string
  name: string
  description: string
}

type PreprocessJob = {
  jobId?: string
  fileName?: string
  [key: string]: unknown
}

type PreprocessMethodReport = {
  method?: string
  name?: string
  status?: string
  progress?: number
  rowsIn?: number
  rowsOut?: number
  columnsIn?: number
  columnsOut?: number
  missingBefore?: number
  missingAfter?: number
  operations?: Record<string, unknown>
}

type PreprocessReport = Record<string, unknown> & {
  ok?: boolean
  jobId?: string
  sourceFileName?: string
  rowsIn?: number
  rowsOut?: number
  columnsIn?: string[]
  columnsOut?: string[]
  selectedMethods?: string[]
  methodReports?: PreprocessMethodReport[]
  operations?: Record<string, unknown>
  savedToKb?: Record<string, unknown>
}

type PreprocessJobState = PreprocessJob & {
  status?: 'uploaded' | 'running' | 'done' | 'failed'
  error?: string
  report?: PreprocessReport | null
  rows?: Array<Record<string, unknown>>
}

type ImageItem = {
  fileId: string
  kbId?: string
  fileName?: string
  img_name?: string
  imagePath?: string
  summary?: string
  page_num?: number
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  citations?: Array<Record<string, unknown>>
}

type Toast = {
  type: 'success' | 'error' | 'info'
  text: string
}

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8002/api/v1'
const route = useRoute()
const router = useRouter()
const detailKbId = computed(() => (typeof route.params.kbId === 'string' ? route.params.kbId : ''))
const isKbDetailPage = computed(() => route.name === 'kb-detail')

const tabs = [
  { id: 'search', label: '多模态检索', icon: 'chat' },
  { id: 'extract', label: '知识提取', icon: 'share' },
  { id: 'preview', label: '知识库', icon: 'book' },
  { id: 'preprocess', label: '数据预处理', icon: 'sigma' },
] as const

const activeTab = ref<(typeof tabs)[number]['id']>('preview')
const kbs = ref<Kb[]>([])
const files = ref<KbFile[]>([])
const selectedKbId = ref('')
const selectedFileId = ref('')
const selectedFileIds = ref<string[]>([])
const fileTaskStates = reactive<Record<string, FileTaskState>>({})
const kbSearchQuery = ref('')
const createKbExpanded = ref(true)
const kbUploadExpanded = ref(true)
const selectedFileSearchText = ref('')
const selectedImageSearchText = ref('')
const selectedStructuredSearchText = ref('')
const searchFileId = ref('')
const selectedPreviewFileId = ref('')
const selectedImageFileId = ref('')
const kbSubTab = ref<'files' | 'images' | 'numbers'>('files')
const previewModalOpen = ref(false)
const previewTab = ref<'markdown' | 'page'>('markdown')
const pagePreviewUrl = ref('')
const loading = ref(false)
const toast = ref<Toast | null>(null)
const newKb = reactive({
  kbName: '',
  vectorStoreType: 'faiss',
  embedModel: 'bge-m3:latest',
})

const uploadState = reactive({
  files: [] as File[],
  parseMethod: 'original',
  busy: false,
  message: '',
})

const uploadInputRef = ref<HTMLInputElement | null>(null)

const searchState = reactive({
  query: '',
  k: 5,
  results: [] as SearchResult[],
  busy: false,
})

const chatState = reactive({
  input: '',
  busy: false,
  sessionId: `vue_${Date.now()}`,
  messages: [] as ChatMessage[],
})

const previewState = reactive({
  content: '',
  sheets: {} as Record<string, Array<Record<string, unknown>>>,
  selectedSheet: '',
  page: 1,
  mode: 'original',
  busy: false,
})

const imageState = reactive({
  images: [] as ImageItem[],
  busy: false,
  saving: false,
})

const extractState = reactive({
  file: null as File | null,
  instruction: '请从文件中提取关键结构化信息，保留字段名称、数值、单位和页码依据。',
  outputFormat: 'excel',
  parseMethod: 'original',
  customFilename: '',
  mode: '自定义输入',
  templateKey: '地层压力和温度',
  kbMode: '现有知识库',
  jobId: '',
  status: '',
  progress: 0,
  result: null as Record<string, unknown> | null,
  busy: false,
})

const preprocessState = reactive({
  sourceFiles: [] as File[],
  jobs: [] as PreprocessJobState[],
  job: null as PreprocessJobState | null,
  previewJobId: '' as string,
  selectedMethods: [] as string[],
  saveMode: 'existing' as 'existing' | 'new',
  targetKbId: '',
  newKbName: '',
  rebuildIndex: false,
  report: null as PreprocessReport | null,
  rows: [] as Array<Record<string, unknown>>,
  methodProgress: {} as Record<string, number>,
  methodStatus: {} as Record<string, string>,
  jobDetailOpenStates: {} as Record<string, boolean>,
  busy: false,
  uploading: false,
  saving: false,
  previewOpen: false,
})

const preprocessMethodMenuOpen = ref(false)
const preprocessMethodMenuStyle = reactive({
  left: '0px',
  bottom: '0px',
  maxHeight: '320px',
})

const extractionTemplates: Record<string, string> = {
  地层压力和温度:
    "请提取'地层压力和温度'表格。该表通常包含多级表头。\n目标列(JSON Key)：\n- 序号\n- 井号\n- 原始_饱和压力_MPa\n- 原始_地层压力_MPa\n- 原始_压力系数\n- 原始_油层温度_℃\n- 原始_地温梯度_℃/100m\n- 结论_温度\n- 结论_压力\n- 备注\n注意：请处理'原始'和'结论'下的合并单元格结构，将子列的数据准确提取到对应字段。",
  油水关系及油藏类型:
    "请提取'油水关系及油藏类型'表格。\n目标列(JSON Key)：\n- 序号\n- 层位\n- 油藏类型\n- 油藏类型细分\n- 边底水\n- 气顶\n- 油水界面_m\n- 备注\n注意：若存在合并行，请将合并内容填充到每一行。",
  油分析:
    "请提取'原油分析'或'油分析'表格。\n目标列(JSON Key)：\n- 序号\n- 层位\n- 取样_取样井号\n- 取样_取样井段_m\n- 取样_取样时间\n- 油分析_测粘温度_℃\n- 油分析_地面密度_g/cm3\n- 油分析_地面粘度_mPa.s\n- 油分析_凝固点_℃\n- 油分析_含硫_%\n- 油分析_含蜡_%\n- 油分析_H2S 含量_%\n- 结论\n注意：若存在合并行，请将合并内容填充到每一行。",
  水分析:
    "请提取'地层水分析'或'水分析'表格。\n目标列(JSON Key)：\n- 序号\n- 层位\n- 取样_取样井号\n- 取样_取样井段_m\n- 取样_取样时间\n- 水分析_Na+_mg/l\n- 水分析_Mg+_mg/l\n- 水分析_Ca+_mg/l\n- 水分析_Cl-_mg/l\n- 水分析_SO4-_mg/l\n- 水分析_CO3-_mg/l\n- 水分析_总矿化度_mg/l\n- 结论\n注意：若存在合并行，请将合并内容填充到每一行。",
  气分析:
    "请提取'天然气分析'或'气分析'表格。\n目标列(JSON Key)：\n- 序号\n- 层位\n- 取样_取样井号\n- 取样_取样井段_m\n- 取样_取样时间\n- 气分析_氦\n- 气分析_氢\n- 气分析_氧\n- 气分析_氮\n- 气分析_二氧化碳\n- 气分析_乙烷\n- 气分析_丙烷\n- 气分析_异丁烷\n- 气分析_正丁烷\n- 气分析_新戊烷\n- 气分析_异戊烷\n- 气分析_正戊烷\n- 气分析_己烷\n- 气分析_庚烷和更重组分\n- 气分析_一氧化碳\n- 气分析_硫化氢\n- 气分析_二氧化硫\n注意：若存在合并行，请将合并内容填充到每一行。",
}

const preprocessMethods: PreprocessMethod[] = [
  {
    id: 'format_standardize',
    name: '格式归一化',
    description: '统一 CSV、Excel、JSON、JSONL 的表格格式、字段命名与基础类型。',
  },
  {
    id: 'dedupe',
    name: '冗余数据剔除',
    description: '识别重复行、空行和冗余记录，保留有效样本。',
  },
  {
    id: 'missing_fill',
    name: '缺失补全',
    description: '按字段类型自动选择前向填充、中位数、众数或默认值补全。',
  },
  {
    id: 'anomaly_correct',
    name: '异常纠错',
    description: '对数值异常、空白噪声和不规范值进行纠正或标记。',
  },
  {
    id: 'unit_dimension_check',
    name: '单位统一与量纲校验',
    description: '按测试规则统一 WOB、扭矩、立管压力、流量和温度单位。',
  },
  {
    id: 'engineering_constraint_check',
    name: '工程范围/物理约束校验',
    description: '按测试阈值校验 depth_m、wob_kN、torque_kNm、standpipe_pressure_MPa、flow_rate_Ls、temperature_C 和 rpm。',
  },
  {
    id: 'schema_standardize',
    name: '维度标准化',
    description: '统一列顺序、数据维度与标准化输出结构，增强异构兼容。',
  },
]

const selectedKb = computed(() => kbs.value.find((kb) => kb.kbId === selectedKbId.value))
const selectedFile = computed(() => files.value.find((file) => file.fileId === selectedFileId.value))
const previewFile = computed(() => files.value.find((file) => file.fileId === selectedPreviewFileId.value))
const selectedImageFile = computed(() => files.value.find((file) => file.fileId === selectedImageFileId.value))
const filteredKbs = computed(() => {
  const query = kbSearchQuery.value.trim().toLowerCase()
  if (!query) return kbs.value
  return kbs.value.filter((kb) => [kb.kbName, kb.kbId, kb.vectorStoreType, kb.embedModel].some((value) => String(value || '').toLowerCase().includes(query)))
})
const filteredFiles = computed(() => {
  const query = selectedFileSearchText.value.trim().toLowerCase()
  if (!query) return files.value
  return files.value.filter((file) =>
    [file.fileName, file.fileId, file.type, file.parseMethod, file.parser].some((value) => String(value || '').toLowerCase().includes(query)),
  )
})
const selectedActionFileIds = computed(() => {
  const ids = selectedFileIds.value.length ? selectedFileIds.value : selectedFileId.value ? [selectedFileId.value] : []
  return Array.from(new Set(ids)).filter(Boolean)
})
const allFilesSelected = computed(
  () => filteredFiles.value.length > 0 && filteredFiles.value.every((file) => selectedFileIds.value.includes(file.fileId)),
)
const structuredFiles = computed(() =>
  files.value.filter((file) => Number(file.tableCount || 0) > 0 || ['excel', 'unknown'].includes(file.type || '') || /\.(csv|xlsx|xls|json|jsonl)$/i.test(file.fileName || '')),
)
const previewRows = computed(() => previewState.sheets[previewState.selectedSheet] || [])
const previewColumns = computed(() => Object.keys(previewRows.value[0] || {}))
const preprocessRowsColumns = computed(() => Object.keys(preprocessState.rows[0] || {}))
const preprocessMethodById = computed(
  () => Object.fromEntries(preprocessMethods.map((method) => [method.id, method])) as Record<string, PreprocessMethod>,
)
const preprocessSelectedMethodCards = computed(() =>
  preprocessState.selectedMethods.map((methodId, index) => ({
    ...(preprocessMethodById.value[methodId] || { id: methodId, name: methodId, description: '' }),
    index: index + 1,
  })),
)
const remainingPreprocessMethods = computed(() => preprocessMethods.filter((method) => !preprocessState.selectedMethods.includes(method.id)))
const preprocessProgressRows = computed(() =>
  preprocessState.selectedMethods.map((methodId) => ({
    id: methodId,
    name: preprocessMethodName(methodId),
    progress: preprocessState.methodProgress[methodId] ?? 0,
    status: preprocessState.methodStatus[methodId] || (preprocessState.busy ? '处理中' : '等待处理'),
  })),
)
const preprocessSelectedJob = computed(
  () => preprocessState.jobs.find((job) => job.jobId === preprocessState.previewJobId) || preprocessState.job,
)
const preprocessReportSource = computed(() => preprocessState.report || preprocessSelectedJob.value?.report || null)
const preprocessReportSummary = computed(() => summarizePreprocessReport(preprocessReportSource.value))
const preprocessJobCards = computed(() =>
  preprocessState.jobs.map((job) => ({
    ...job,
    summary: summarizePreprocessReport(job.report || null),
    active: preprocessSelectedJob.value?.jobId === job.jobId,
  })),
)
const stats = computed(() => {
  const indexed = files.value.filter((file) => file.isIndexed).length
  const parsed = files.value.filter((file) => file.hasParsed).length
  return [
    { label: '知识库总数', value: kbs.value.length },
    { label: '当前文件总数', value: files.value.length },
    { label: '已解析文件总数', value: parsed },
    { label: '已索引文件总数', value: indexed },
  ]
})

if (detailKbId.value) selectedKbId.value = detailKbId.value

function searchResultText(item: SearchResult) {
  return item.chunk_text || item.text || item.content || JSON.stringify(item.metadata || item)
}

function searchResultSourceObject(item: SearchResult) {
  const source: Record<string, unknown> = {}
  if (item.metadata && typeof item.metadata === 'object') Object.assign(source, item.metadata)
  if (item.source) {
    try {
      const parsed = JSON.parse(item.source)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) Object.assign(source, parsed)
      else source.source = item.source
    } catch {
      source.source = item.source
    }
  }
  return source
}

function sourceStringValue(value: unknown) {
  if (value === undefined || value === null || value === '') return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function searchResultFileId(item: SearchResult) {
  const source = searchResultSourceObject(item)
  return item.fileId || item.entity_key || sourceStringValue(source.file_id) || sourceStringValue(source.fileId)
}

function searchResultFile(item: SearchResult) {
  return item.fileName || searchResultFileId(item) || 'Unknown'
}

function searchResultSourceRows(item: SearchResult) {
  const source = searchResultSourceObject(item)
  const rows: Array<{ label: string; value: string }> = []
  const file = searchResultFile(item)
  const page = sourceStringValue(item.page ?? source.page ?? source.page_num ?? source.source_page_num)
  const type = sourceStringValue(source.type)
  const headers = ['Header 1', 'Header 2', 'Header 3']
    .map((key) => sourceStringValue(source[key]))
    .filter(Boolean)
    .join(' / ')
  const imagePath = sourceStringValue(source.image_path || source.img_name || source.imagePath)
  const rawSource = source.source ? sourceStringValue(source.source) : ''

  if (file) rows.push({ label: '文件', value: file })
  if (page) rows.push({ label: '页码', value: page })
  if (type) rows.push({ label: '类型', value: type === 'image' ? '图像片段' : type })
  if (headers) rows.push({ label: '章节层级', value: headers })
  if (imagePath) rows.push({ label: '图片', value: imagePath })
  if (rawSource) rows.push({ label: '元数据', value: rawSource })
  if (!rows.length && item.source) rows.push({ label: '元数据', value: item.source })
  return rows
}

function escapeHtml(value: unknown) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function searchResultImageUrl(item: SearchResult, rawUrl: string) {
  const url = rawUrl.trim().replace(/^<|>$/g, '')
  if (/^(https?:|blob:|data:image\/)/i.test(url)) return url
  if (/^javascript:/i.test(url)) return '#'

  const cleanPath = url.split('?')[0] || ''
  const lastSegment = cleanPath.split(/[\\/]/).filter(Boolean).pop() || cleanPath
  const imageName = decodeURIComponent(lastSegment)
  const fileId = searchResultFileId(item)
  if (!selectedKbId.value || !fileId || !imageName) return url
  return apiUrl('/pdf/images', { kbId: selectedKbId.value, fileId, imagePath: imageName })
}

function safeLinkUrl(rawUrl: string) {
  const url = rawUrl.trim().replace(/^<|>$/g, '')
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('#')) return url
  return '#'
}

function renderMarkdownInline(value: string, item: SearchResult) {
  const placeholders: string[] = []
  const token = (html: string) => {
    const key = `@@MD_TOKEN_${placeholders.length}@@`
    placeholders.push(html)
    return key
  }

  let text = value.replace(/!\[([^\]]*)\]\((.*?\.(?:png|jpe?g|gif|webp|bmp|svg))\)/gi, (_, alt: string, url: string) => {
    const src = searchResultImageUrl(item, url)
    const safeAlt = escapeHtml(alt || '检索图片')
    return token(`<figure class="md-image-figure"><img src="${escapeHtml(src)}" alt="${safeAlt}" loading="lazy" /><figcaption>${safeAlt}</figcaption></figure>`)
  })

  text = text.replace(/(?<!!)\[([^\]]+)\]\(([^)]+)\)/g, (_, label: string, url: string) => {
    const href = safeLinkUrl(url)
    return token(`<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`)
  })

  text = escapeHtml(text)
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  placeholders.forEach((html, index) => {
    text = text.replaceAll(`@@MD_TOKEN_${index}@@`, html)
  })
  return text
}

function isMarkdownTableSeparator(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
}

function splitMarkdownTableRow(line: string) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
}

function isMarkdownBlockStart(lines: string[], index: number) {
  const line = lines[index] || ''
  const next = lines[index + 1] || ''
  return (
    /^\s*```/.test(line) ||
    /^\s{0,3}#{1,6}\s+/.test(line) ||
    /^\s*([-*+])\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    (line.includes('|') && isMarkdownTableSeparator(next))
  )
}

function renderMarkdownTable(tableLines: string[], item: SearchResult) {
  const headerCells = splitMarkdownTableRow(tableLines[0] || '')
  const bodyLines = tableLines.slice(2)
  const head = headerCells.map((cell) => `<th>${renderMarkdownInline(cell, item)}</th>`).join('')
  const body = bodyLines
    .map((line) => {
      const cells = splitMarkdownTableRow(line)
      return `<tr>${headerCells.map((_, index) => `<td>${renderMarkdownInline(cells[index] || '', item)}</td>`).join('')}</tr>`
    })
    .join('')
  return `<div class="md-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
}

function renderMarkdown(value: string, item: SearchResult) {
  const markdown = String(value || '').replace(/\r\n/g, '\n')
  if (!markdown.trim()) return '<p class="md-empty">暂无检索内容</p>'

  const lines = markdown.split('\n')
  const html: string[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index] || ''
    const trimmed = line.trim()
    if (!trimmed) {
      index += 1
      continue
    }

    const fence = line.match(/^\s*```(\w+)?/)
    if (fence) {
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !/^\s*```/.test(lines[index] || '')) {
        codeLines.push(lines[index] || '')
        index += 1
      }
      if (index < lines.length) index += 1
      html.push(`<pre class="md-code"><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`)
      continue
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/)
    if (heading) {
      const level = (heading[1] || '#').length
      html.push(`<h${level}>${renderMarkdownInline(heading[2] || '', item)}</h${level}>`)
      index += 1
      continue
    }

    if (line.includes('|') && isMarkdownTableSeparator(lines[index + 1] || '')) {
      const tableLines = [line, lines[index + 1] || '']
      index += 2
      while (index < lines.length && (lines[index] || '').includes('|') && (lines[index] || '').trim()) {
        tableLines.push(lines[index] || '')
        index += 1
      }
      html.push(renderMarkdownTable(tableLines, item))
      continue
    }

    const unordered = line.match(/^\s*([-*+])\s+(.+)$/)
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      const tag = ordered ? 'ol' : 'ul'
      const items: string[] = []
      while (index < lines.length) {
        const current = lines[index] || ''
        const match = tag === 'ol' ? current.match(/^\s*\d+[.)]\s+(.+)$/) : current.match(/^\s*[-*+]\s+(.+)$/)
        if (!match) break
        items.push(`<li>${renderMarkdownInline(match[1] || '', item)}</li>`)
        index += 1
      }
      html.push(`<${tag}>${items.join('')}</${tag}>`)
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index] || '')) {
        quoteLines.push((lines[index] || '').replace(/^\s*>\s?/, ''))
        index += 1
      }
      html.push(`<blockquote>${renderMarkdownInline(quoteLines.join('\n'), item).replace(/\n/g, '<br>')}</blockquote>`)
      continue
    }

    const paragraphLines = [line]
    index += 1
    while (index < lines.length && (lines[index] || '').trim() && !isMarkdownBlockStart(lines, index)) {
      paragraphLines.push(lines[index] || '')
      index += 1
    }
    html.push(`<p>${renderMarkdownInline(paragraphLines.join('\n'), item).replace(/\n/g, '<br>')}</p>`)
  }

  return html.join('')
}

function searchResultHtml(item: SearchResult) {
  return renderMarkdown(searchResultText(item), item)
}

function fileDisplayName(file?: KbFile | null) {
  return file?.fileName || file?.fileId || ''
}

function findFileByQuery(query: string, sourceFiles: KbFile[]) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return null
  return (
    sourceFiles.find((file) => [file.fileId, file.fileName].some((value) => String(value || '').toLowerCase() === normalized)) ||
    sourceFiles.find((file) => [file.fileId, file.fileName].some((value) => String(value || '').toLowerCase().includes(normalized))) ||
    null
  )
}

function syncSearchTexts() {
  selectedImageSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedImageFileId.value))
  selectedStructuredSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedPreviewFileId.value))
}

function enterKb(kbId: string) {
  selectedKbId.value = kbId
  activeTab.value = 'preview'
  router.push({ name: 'kb-detail', params: { kbId } })
}

function goHome() {
  router.push({ name: 'home' })
}

function openFilePreview(fileId: string) {
  selectedFileId.value = fileId
  selectedPreviewFileId.value = fileId
  previewModalOpen.value = true
  previewTab.value = 'markdown'
  loadPreview()
}

function selectFile(fileId: string) {
  selectedFileId.value = fileId
  selectedPreviewFileId.value = fileId
}

function selectPreviewFile(fileId: string) {
  selectFile(fileId)
}

function onStructuredFileChange(event: Event) {
  const target = event.target as HTMLSelectElement | null
  if (target?.value) selectPreviewFile(target.value)
}

function selectFileByQuery(query: string) {
  const matchedFile = findFileByQuery(query, files.value)
  if (!matchedFile) return
  selectedFileId.value = matchedFile.fileId
  selectedPreviewFileId.value = matchedFile.fileId
  loadPreview()
}

function selectImageFileByQuery(query: string) {
  if (!query.trim()) {
    selectedImageFileId.value = ''
    selectedImageSearchText.value = ''
    loadImages()
    return
  }
  const matchedFile = findFileByQuery(query, files.value)
  if (!matchedFile) return
  selectedImageFileId.value = matchedFile.fileId
  selectedImageSearchText.value = fileDisplayName(matchedFile)
  loadImages()
}

function selectStructuredFileByQuery(query: string) {
  const sourceFiles = structuredFiles.value.length ? structuredFiles.value : files.value
  const matchedFile = findFileByQuery(query, sourceFiles)
  if (!matchedFile) return
  selectedPreviewFileId.value = matchedFile.fileId
  selectedStructuredSearchText.value = fileDisplayName(matchedFile)
  loadPreview()
}

function onFileSearchChange() {
  selectFileByQuery(selectedFileSearchText.value)
}

function onImageSearchChange() {
  selectImageFileByQuery(selectedImageSearchText.value)
}

function onStructuredSearchChange() {
  selectStructuredFileByQuery(selectedStructuredSearchText.value)
}

function onSelectAllFilesChange(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  selectedFileIds.value = checked ? filteredFiles.value.map((file) => file.fileId) : []
}

async function parseFile(fileId: string) {
  selectFile(fileId)
  await parseFiles([fileId])
}

async function deleteFile(fileId: string, deleteFileContent: boolean) {
  selectFile(fileId)
  await deleteFiles([fileId], deleteFileContent)
}

function notify(text: string, type: Toast['type'] = 'info') {
  toast.value = { text, type }
  window.setTimeout(() => {
    if (toast.value?.text === text) toast.value = null
  }, 3200)
}

function apiUrl(path: string, params?: Record<string, string | number | boolean | undefined>) {
  const url = new URL(`${API_BASE}${path}`)
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== '') url.searchParams.set(key, String(value))
  })
  return url.toString()
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(options.headers || {}),
    },
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = data?.error?.message || data?.detail || response.statusText
    throw new Error(message)
  }
  return data as T
}

async function loadKbs() {
  loading.value = true
  try {
    const data = await requestJson<{ kbs: Kb[] }>('/kb/list')
    kbs.value = data.kbs || []
    if (!selectedKbId.value && kbs.value.length) selectedKbId.value = kbs.value[0]?.kbId || ''
    if (!preprocessState.targetKbId && kbs.value.length) preprocessState.targetKbId = selectedKbId.value || kbs.value[0]?.kbId || ''
  } catch (error) {
    notify(`知识库列表加载失败：${(error as Error).message}`, 'error')
  } finally {
    loading.value = false
  }
}

async function loadFiles() {
  if (!selectedKbId.value) {
    files.value = []
    selectedFileIds.value = []
    selectedFileSearchText.value = ''
    selectedStructuredSearchText.value = ''
    return
  }
  try {
    const data = await requestJson<{ files: KbFile[] }>(`/kb/files?kbId=${encodeURIComponent(selectedKbId.value)}`)
    files.value = data.files || []
    const firstFile = files.value[0]?.fileId || ''
    const existingIds = new Set(files.value.map((file) => file.fileId))
    selectedFileIds.value = selectedFileIds.value.filter((fileId) => existingIds.has(fileId))
    Object.keys(fileTaskStates).forEach((fileId) => {
      if (!existingIds.has(fileId)) delete fileTaskStates[fileId]
    })
    if (!files.value.some((file) => file.fileId === selectedFileId.value)) selectedFileId.value = firstFile
    if (searchFileId.value && !files.value.some((file) => file.fileId === searchFileId.value)) searchFileId.value = ''
    if (!files.value.some((file) => file.fileId === selectedPreviewFileId.value)) selectedPreviewFileId.value = firstFile
    if (!firstFile) {
      selectedPreviewFileId.value = ''
      previewModalOpen.value = false
    }
    syncSearchTexts()
  } catch (error) {
    notify(`文件列表加载失败：${(error as Error).message}`, 'error')
  }
}

async function createKb() {
  if (!newKb.kbName.trim()) {
    notify('请输入知识库名称', 'error')
    return
  }
  try {
    const data = await requestJson<Kb>('/kb/create', {
      method: 'POST',
      body: JSON.stringify(newKb),
    })
    newKb.kbName = ''
    selectedKbId.value = data.kbId
    await loadKbs()
    notify('知识库创建成功', 'success')
  } catch (error) {
    notify(`创建失败：${(error as Error).message}`, 'error')
  }
}

async function deleteKb(kbId: string) {
  if (!window.confirm('确认删除该知识库？此操作会删除其中的文件和索引。')) return
  try {
    await requestJson('/kb/delete', {
      method: 'POST',
      body: JSON.stringify({ kbId }),
    })
    if (selectedKbId.value === kbId) selectedKbId.value = ''
    await loadKbs()
    notify('知识库已删除', 'success')
  } catch (error) {
    notify(`删除失败：${(error as Error).message}`, 'error')
  }
}

function onUploadChange(event: Event) {
  const input = event.target as HTMLInputElement
  uploadState.files = Array.from(input.files || [])
}

function clearUploadSelection() {
  uploadState.files = []
  uploadState.message = ''
  if (uploadInputRef.value) uploadInputRef.value.value = ''
}

function removeUploadFile(index: number) {
  if (uploadState.busy) return
  uploadState.files = uploadState.files.filter((_, currentIndex) => currentIndex !== index)
  if (uploadInputRef.value) uploadInputRef.value.value = ''
  uploadState.message = uploadState.files.length ? `已选择 ${uploadState.files.length} 个文件` : ''
}

async function deleteUploadedFiles(fileIds: string[]) {
  if (!selectedKbId.value || !fileIds.length) return
  for (const fileId of fileIds) {
    await requestJson('/kb/file/delete', {
      method: 'POST',
      body: JSON.stringify({ kbId: selectedKbId.value, fileId, deleteIndex: true, deleteFile: true }),
    })
  }
}

function setFileTask(fileId: string, state: FileTaskState) {
  fileTaskStates[fileId] = state
}

function clearFileTask(fileId: string) {
  delete fileTaskStates[fileId]
}

function taskBadgeClass(state?: FileTaskState) {
  if (!state) return ''
  if (state.status === 'failed') return 'error'
  if (state.status === 'done') return 'ok'
  if (state.status === 'queued') return 'warn'
  return 'busy'
}

function hasFileTask(fileId: string) {
  return Boolean(fileTaskStates[fileId])
}

function fileTaskBadgeClass(fileId: string) {
  return taskBadgeClass(fileTaskStates[fileId])
}

function fileTaskMessage(fileId: string) {
  return fileTaskStates[fileId]?.message || ''
}

function fileTaskProgress(fileId: string) {
  return fileTaskStates[fileId]?.progress
}

async function uploadFiles() {
  if (!selectedKbId.value || !uploadState.files.length) {
    notify('请选择知识库和待上传文件', 'error')
    return
  }
  uploadState.busy = true
  uploadState.message = uploadState.files.length > 1 ? `正在上传 ${uploadState.files.length} 个文件...` : '正在上传文件...'
  try {
    const form = new FormData()
    form.append('kbId', selectedKbId.value)
    form.append('replace', 'true')
    for (const file of uploadState.files) {
      form.append('files', file)
    }
    const response = await fetch(apiUrl('/pdf/upload'), { method: 'POST', body: form })
    const data = await response.json()
    if (!response.ok) throw new Error(data?.error?.message || '上传失败')
    const uploadedIds: string[] = Array.isArray(data.fileIds)
      ? data.fileIds.filter(isNonEmptyString)
      : data.fileId
        ? [String(data.fileId)]
        : Array.isArray(data.files)
          ? data.files.map((item: { fileId?: string }) => item.fileId).filter(isNonEmptyString)
          : []
    if (!uploadedIds.length) throw new Error('上传接口未返回文件ID')
    uploadState.message = '文件已上传，等待确认是否继续解析入库...'
    const confirmText = uploadedIds.length > 1
      ? `已上传 ${uploadedIds.length} 个文件。是否继续解析并入库？取消将删除这些已上传文件。`
      : '文件已上传。是否继续解析并入库？取消将删除这个已上传文件。'
    if (!window.confirm(confirmText)) {
      uploadState.message = '正在取消并删除已上传文件...'
      await deleteUploadedFiles(uploadedIds)
      clearUploadSelection()
      notify('已取消本次上传，已删除未入库文件', 'info')
      return
    }
    uploadState.message = '上传完成，正在解析...'
    uploadedIds.forEach((fileId) => setFileTask(fileId, { phase: 'parse', status: 'queued', message: '等待解析', progress: 0 }))
    await requestJson('/pdf/parse', {
      method: 'POST',
      body: JSON.stringify({ kbId: selectedKbId.value, fileIds: uploadedIds, method: uploadState.parseMethod }),
    })
    const parseResult = await pollParse(uploadedIds)
    if (parseResult.failed.length) throw new Error(`${parseResult.failed.length} 个文件解析失败`)
    uploadState.message = '解析完成，正在构建索引...'
    await buildIndex(parseResult.ready, false)
    await loadFiles()
    uploadedIds.forEach(clearFileTask)
    uploadState.message = '上传、解析与索引已完成'
    notify('文件已入库并完成索引', 'success')
    clearUploadSelection()
  } catch (error) {
    notify(`上传流程失败：${(error as Error).message}`, 'error')
  } finally {
    uploadState.busy = false
  }
}

async function pollParse(fileIds: string[]) {
  const pending = new Set(fileIds)
  const ready = new Set<string>()
  const failed = new Set<string>()
  for (let i = 0; i < 240 && pending.size; i += 1) {
    await Promise.all(
      Array.from(pending).map(async (fileId) => {
        try {
          const res = await fetch(apiUrl('/pdf/status', { kbId: selectedKbId.value, fileId }))
          const data = await res.json()
          const progress = Math.max(0, Math.min(100, Number(data.progress || 0)))
          if (data.status === 'ready') {
            ready.add(fileId)
            pending.delete(fileId)
            setFileTask(fileId, { phase: 'parse', status: 'done', message: '解析完成', progress: 100 })
          } else if (data.status === 'error') {
            failed.add(fileId)
            pending.delete(fileId)
            setFileTask(fileId, { phase: 'parse', status: 'failed', message: '解析失败', progress })
          } else if (data.status === 'parsing') {
            setFileTask(fileId, { phase: 'parse', status: 'running', message: '正在解析', progress })
          } else {
            setFileTask(fileId, { phase: 'parse', status: 'queued', message: '等待解析', progress })
          }
        } catch {
          failed.add(fileId)
          pending.delete(fileId)
          setFileTask(fileId, { phase: 'parse', status: 'failed', message: '状态获取失败', progress: 0 })
        }
      }),
    )
    if (pending.size) await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
  pending.forEach((fileId) => {
    failed.add(fileId)
    setFileTask(fileId, { phase: 'parse', status: 'failed', message: '解析超时', progress: 0 })
  })
  return { ready: Array.from(ready), failed: Array.from(failed), pending: Array.from(pending) }
}

async function buildIndex(fileIds = selectedActionFileIds.value, showToast = true) {
  const targetFileIds = Array.from(new Set(fileIds)).filter(Boolean)
  if (!selectedKbId.value || !targetFileIds.length) return
  let totalChunks = 0
  let successCount = 0
  const failedMessages: string[] = []
  for (const fileId of targetFileIds) {
    setFileTask(fileId, { phase: 'index', status: 'running', message: '正在索引', progress: 5 })
    try {
      const data = await requestJson<{ chunks?: number; results?: Array<{ fileId?: string; chunks?: number; ok?: boolean; error?: string }> }>(
        '/index/build',
        {
          method: 'POST',
          body: JSON.stringify({ kbId: selectedKbId.value, fileId }),
        },
      )
      const result = data.results?.find((item) => item.fileId === fileId)
      if (result && result.ok === false) throw new Error(result.error || '索引构建失败')
      const chunks = Number(result?.chunks ?? data.chunks ?? 0)
      totalChunks += chunks
      successCount += 1
      setFileTask(fileId, { phase: 'index', status: 'done', message: `索引完成 ${chunks} 片段`, progress: 100 })
    } catch (error) {
      const message = (error as Error).message
      failedMessages.push(`${fileId}: ${message}`)
      setFileTask(fileId, { phase: 'index', status: 'failed', message: '索引失败', progress: 0 })
    }
  }
  await loadFiles()
  targetFileIds.forEach((fileId) => {
    if (fileTaskStates[fileId]?.status === 'done') clearFileTask(fileId)
  })
  if (showToast) {
    if (failedMessages.length) {
      notify(`索引构建完成 ${successCount}/${targetFileIds.length}，失败 ${failedMessages.length} 个`, 'error')
    } else {
      notify(`索引构建完成：${totalChunks} 个片段`, 'success')
    }
  }
}

async function parseFiles(fileIds: string[] = selectedActionFileIds.value) {
  const targetFileIds = Array.from(new Set(fileIds)).filter(Boolean)
  if (!selectedKbId.value || !targetFileIds.length) return
  try {
    targetFileIds.forEach((fileId) => setFileTask(fileId, { phase: 'parse', status: 'queued', message: '等待解析', progress: 0 }))
    await requestJson('/pdf/parse', {
      method: 'POST',
      body: JSON.stringify({ kbId: selectedKbId.value, fileIds: targetFileIds, method: uploadState.parseMethod }),
    })
    const parseResult = await pollParse(targetFileIds)
    await loadFiles()
    parseResult.ready.forEach(clearFileTask)
    if (parseResult.failed.length) {
      notify(`重新解析完成 ${parseResult.ready.length}/${targetFileIds.length}，失败 ${parseResult.failed.length} 个`, 'error')
    } else {
      notify(targetFileIds.length > 1 ? `已完成 ${targetFileIds.length} 个文件的重新解析` : '重新解析完成', 'success')
    }
  } catch (error) {
    targetFileIds.forEach((fileId) => setFileTask(fileId, { phase: 'parse', status: 'failed', message: '解析失败', progress: 0 }))
    notify(`解析失败：${(error as Error).message}`, 'error')
  }
}

async function parseSelectedFiles() {
  await parseFiles()
}

async function deleteFiles(fileIds: string[] = selectedActionFileIds.value, deleteFile: boolean) {
  const targetFileIds = Array.from(new Set(fileIds)).filter(Boolean)
  if (!selectedKbId.value || !targetFileIds.length) return
  const action = deleteFile ? '删除文件及索引' : '删除索引'
  const confirmText = targetFileIds.length > 1 ? `确认${action}这 ${targetFileIds.length} 个文件？` : `确认${action}？`
  if (!window.confirm(confirmText)) return
  try {
    for (const fileId of targetFileIds) {
      await requestJson('/kb/file/delete', {
        method: 'POST',
        body: JSON.stringify({ kbId: selectedKbId.value, fileId, deleteIndex: true, deleteFile }),
      })
    }
    await loadFiles()
    notify(targetFileIds.length > 1 ? `${action}完成：${targetFileIds.length} 个文件` : `${action}完成`, 'success')
  } catch (error) {
    notify(`${action}失败：${(error as Error).message}`, 'error')
  }
}

async function deleteSelectedFiles(deleteFile: boolean) {
  await deleteFiles(selectedActionFileIds.value, deleteFile)
}

function closePreviewModal() {
  previewModalOpen.value = false
  previewTab.value = 'markdown'
  if (pagePreviewUrl.value) {
    URL.revokeObjectURL(pagePreviewUrl.value)
    pagePreviewUrl.value = ''
  }
}

async function loadPagePreview() {
  if (!selectedKbId.value || !selectedPreviewFileId.value) return
  try {
    const response = await fetch(
      apiUrl('/pdf/page', {
        kbId: selectedKbId.value,
        fileId: selectedPreviewFileId.value,
        page: previewState.page,
        type: previewState.mode,
      }),
    )
    if (!response.ok) throw new Error(`页面预览加载失败：${response.statusText}`)
    const blob = await response.blob()
    if (pagePreviewUrl.value) URL.revokeObjectURL(pagePreviewUrl.value)
    pagePreviewUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    if (pagePreviewUrl.value) URL.revokeObjectURL(pagePreviewUrl.value)
    pagePreviewUrl.value = ''
    notify((error as Error).message, 'error')
  }
}

async function runSearch() {
  if (!selectedKbId.value || !searchState.query.trim()) {
    notify('请选择知识库并输入检索问题', 'error')
    return
  }
  searchState.busy = true
  try {
    const data = await requestJson<{ results?: SearchResult[]; data?: SearchResult[] }>('/index/search', {
      method: 'POST',
      body: JSON.stringify({
        kbId: selectedKbId.value,
        fileId: searchFileId.value || undefined,
        query: searchState.query,
        k: searchState.k,
      }),
    })
    searchState.results = data.results || data.data || []
  } catch (error) {
    notify(`检索失败：${(error as Error).message}`, 'error')
  } finally {
    searchState.busy = false
  }
}

async function sendChat() {
  if (!selectedKbId.value || !chatState.input.trim() || chatState.busy) return
  const prompt = chatState.input.trim()
  chatState.messages.push({ role: 'user', content: prompt })
  const assistant: ChatMessage = { role: 'assistant', content: '', citations: [] }
  chatState.messages.push(assistant)
  chatState.input = ''
  chatState.busy = true
  try {
    const response = await fetch(apiUrl('/chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: prompt,
        sessionId: chatState.sessionId,
        kbId: selectedKbId.value,
        fileId: selectedFileId.value || undefined,
      }),
    })
    if (!response.ok || !response.body) throw new Error(response.statusText)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const raw of events) handleSseEvent(raw, assistant)
    }
  } catch (error) {
    assistant.content += `\n[回答失败：${(error as Error).message}]`
  } finally {
    chatState.busy = false
  }
}

function handleSseEvent(raw: string, message: ChatMessage) {
  const event = raw.split('\n').find((line) => line.startsWith('event:'))?.replace('event:', '').trim()
  const dataLine = raw.split('\n').find((line) => line.startsWith('data:'))?.replace('data:', '').trim()
  if (!event || !dataLine) return
  const data = JSON.parse(dataLine)
  if (event === 'token') message.content += data.text || ''
  if (event === 'citation') message.citations?.push(data)
  if (event === 'error') message.content += `\n[${data.message || '生成失败'}]`
}

async function clearChat() {
  await requestJson('/chat/clear', {
    method: 'POST',
    body: JSON.stringify({ sessionId: chatState.sessionId }),
  }).catch(() => undefined)
  chatState.messages = []
}

async function loadPreview() {
  if (!selectedKbId.value || !selectedPreviewFileId.value) return
  previewState.busy = true
  previewState.content = ''
  previewState.sheets = {}
  try {
    const content = await fetch(apiUrl('/kb/file/content', { kbId: selectedKbId.value, fileId: selectedPreviewFileId.value }))
    if (content.ok) previewState.content = (await content.json()).content || ''
    const table = await fetch(apiUrl('/kb/file/dataframe', { kbId: selectedKbId.value, fileId: selectedPreviewFileId.value }))
    if (table.ok) {
      const data = await table.json()
      previewState.sheets = data.sheets || {}
      previewState.selectedSheet = Object.keys(previewState.sheets)[0] || ''
    }
  } catch (error) {
    notify(`预览加载失败：${(error as Error).message}`, 'error')
  } finally {
    previewState.busy = false
  }
}

async function loadImages() {
  if (!selectedKbId.value) return
  imageState.busy = true
  try {
    const path = selectedImageFileId.value ? '/pdf/image_summaries' : '/kb/images/all'
    const data = await requestJson<{ images?: ImageItem[]; summaries?: ImageItem[] }>(
      `${path}?kbId=${encodeURIComponent(selectedKbId.value)}${selectedImageFileId.value ? `&fileId=${encodeURIComponent(selectedImageFileId.value)}` : ''}`,
    )
    imageState.images = (data.images || data.summaries || []).map((item) => ({
      ...item,
      fileId: item.fileId || selectedImageFileId.value,
    }))
    selectedImageSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedImageFileId.value))
  } catch (error) {
    notify(`图片列表加载失败：${(error as Error).message}`, 'error')
  } finally {
    imageState.busy = false
  }
}

function imageSrc(item: ImageItem) {
  const img = item.img_name || item.imagePath || ''
  return apiUrl('/pdf/images', { kbId: selectedKbId.value, fileId: item.fileId, imagePath: img })
}

async function saveImage(item: ImageItem) {
  imageState.saving = true
  try {
    await requestJson('/kb/image/update', {
      method: 'POST',
      body: JSON.stringify({
        kbId: selectedKbId.value,
        fileId: item.fileId,
        img_name: item.img_name || item.imagePath,
        summary: item.summary || '',
      }),
    })
    notify('图片摘要已保存并重建索引', 'success')
  } catch (error) {
    notify(`保存失败：${(error as Error).message}`, 'error')
  } finally {
    imageState.saving = false
  }
}

function onExtractFileChange(event: Event) {
  extractState.file = ((event.target as HTMLInputElement).files || [])[0] || null
}

function applyExtractionTemplate() {
  if (extractState.mode === '预置模板 (油气领域)') {
    extractState.instruction = extractionTemplates[extractState.templateKey] || extractState.instruction
  }
}

async function startExtraction() {
  if (!extractState.file) {
    notify('请选择待提取文件', 'error')
    return
  }
  if (!selectedKbId.value) {
    notify('请选择目标知识库，提取结果会自动入库', 'error')
    return
  }
  extractState.busy = true
  extractState.result = null
  try {
    const form = new FormData()
    form.append('file', extractState.file)
    form.append('instruction', extractState.instruction)
    form.append('kb_id', selectedKbId.value || '')
    form.append('output_format', extractState.outputFormat)
    form.append('custom_filename', extractState.customFilename)
    form.append('parse_method', extractState.parseMethod)
    const response = await fetch(apiUrl('/extraction/extract'), { method: 'POST', body: form })
    const data = await response.json()
    if (!response.ok) throw new Error(data?.error?.message || '任务创建失败')
    extractState.jobId = data.jobId
    await pollExtraction()
  } catch (error) {
    notify(`提取失败：${(error as Error).message}`, 'error')
  } finally {
    extractState.busy = false
  }
}

function onPreprocessSourceChange(event: Event) {
  const selectedFiles = Array.from((event.target as HTMLInputElement).files || [])
  clearPreprocessSelection()
  preprocessState.sourceFiles = selectedFiles
  preprocessState.methodProgress = {}
  preprocessState.methodStatus = {}
}

function removePreprocessSourceFile(index: number) {
  if (preprocessState.uploading) return
  preprocessState.sourceFiles = preprocessState.sourceFiles.filter((_, currentIndex) => currentIndex !== index)
  if (uploadInputRef.value) uploadInputRef.value.value = ''
}

function preprocessMethodName(methodId: string) {
  return preprocessMethodById.value[methodId]?.name || methodId
}

function addPreprocessMethod(methodId: string) {
  if (!methodId || preprocessState.selectedMethods.includes(methodId)) return
  preprocessState.selectedMethods.push(methodId)
  preprocessState.methodProgress[methodId] = 0
  preprocessState.methodStatus[methodId] = '等待处理'
  preprocessMethodMenuOpen.value = false
}

function togglePreprocessMethodMenu(event: MouseEvent) {
  if (preprocessMethodMenuOpen.value) {
    preprocessMethodMenuOpen.value = false
    return
  }
  const trigger = event.currentTarget as HTMLButtonElement | null
  if (!trigger) {
    preprocessMethodMenuOpen.value = !preprocessMethodMenuOpen.value
    return
  }

  const rect = trigger.getBoundingClientRect()
  const menuWidth = 250
  const viewportPadding = 12
  const availableAbove = Math.max(160, rect.top - viewportPadding)

  preprocessMethodMenuStyle.left = `${Math.max(viewportPadding, Math.min(rect.left, window.innerWidth - menuWidth - viewportPadding))}px`
  preprocessMethodMenuStyle.bottom = `${Math.max(viewportPadding, window.innerHeight - rect.top + 8)}px`
  preprocessMethodMenuStyle.maxHeight = `${Math.min(320, availableAbove)}px`
  preprocessMethodMenuOpen.value = true
}

function removePreprocessMethod(methodId: string) {
  preprocessState.selectedMethods = preprocessState.selectedMethods.filter((id) => id !== methodId)
  delete preprocessState.methodProgress[methodId]
  delete preprocessState.methodStatus[methodId]
}

function onPreprocessPreviewToggle(event: Event) {
  preprocessState.previewOpen = Boolean((event.target as HTMLDetailsElement).open)
}

async function uploadPreprocessSource() {
  if (!preprocessState.sourceFiles.length) {
    notify('请选择至少一个需要上传的结构化文件', 'error')
    return
  }
  preprocessState.uploading = true
  try {
    const uploadResults = await Promise.all(
      preprocessState.sourceFiles.map(async (file) => {
        try {
          const form = new FormData()
          form.append('file', file)
          const data = await requestJson<PreprocessJob>('/preprocess/upload', { method: 'POST', body: form })
          return {
            ok: true as const,
            job: {
              ...data,
              status: 'uploaded' as const,
              report: null,
              rows: [],
            } as PreprocessJobState,
          }
        } catch (error) {
          return {
            ok: false as const,
            message: error instanceof Error ? error.message : '上传失败',
          }
        }
      }),
    )
    const uploadedJobs = uploadResults.filter((result): result is { ok: true; job: PreprocessJobState } => result.ok).map((result) => result.job)
    const failedMessages = uploadResults.filter((result): result is { ok: false; message: string } => !result.ok).map((result) => result.message)

    preprocessState.jobs = uploadedJobs
    const firstUploadedJob = uploadedJobs[0]
    if (firstUploadedJob) selectPreprocessJob(firstUploadedJob.jobId || '')

    if (failedMessages.length && uploadedJobs.length) {
      notify(`已上传 ${uploadedJobs.length} 个文件，${failedMessages.length} 个文件上传失败`, 'error')
    } else if (uploadedJobs.length) {
      notify(`已上传 ${uploadedJobs.length} 个文件到预处理工作台`, 'success')
    } else {
      throw new Error(failedMessages[0] || '上传失败')
    }

    if (uploadInputRef.value) uploadInputRef.value.value = ''
  } catch (error) {
    notify(`上传失败：${(error as Error).message}`, 'error')
  } finally {
    preprocessState.uploading = false
  }
}

async function pollExtraction() {
  for (let i = 0; i < 240 && extractState.jobId; i += 1) {
    const data = await requestJson<Record<string, unknown>>(`/extraction/status?jobId=${encodeURIComponent(extractState.jobId)}`)
    extractState.status = String(data.status || '')
    extractState.progress = Number(data.progress || 0)
    if (['done', 'completed', 'error', 'failed'].includes(extractState.status)) {
      extractState.result = data
      if (['error', 'failed'].includes(extractState.status)) notify(String(data.error || '提取任务失败'), 'error')
      else {
        await loadFiles()
        notify('知识提取完成，结果已写入知识库', 'success')
      }
      return
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1500))
  }
}

async function runPreprocess() {
  const jobIds = preprocessState.jobs.map((job) => String(job.jobId || '')).filter(Boolean)
  if (!jobIds.length) {
    notify('请先上传至少一个文件到预处理工作台', 'error')
    return
  }
  if (!preprocessState.selectedMethods.length) {
    notify('请至少选择一个预处理方法', 'error')
    return
  }
  preprocessState.busy = true
  try {
    preprocessState.report = null
    preprocessState.rows = []
    preprocessState.previewOpen = false
    preprocessState.jobs = preprocessState.jobs.map((job) => ({
      ...job,
      status: 'running',
      error: '',
    }))
    preprocessState.selectedMethods.forEach((methodId) => {
      preprocessState.methodProgress[methodId] = 0
      preprocessState.methodStatus[methodId] = '等待处理'
    })
    preprocessState.selectedMethods.forEach((methodId) => {
      preprocessState.methodProgress[methodId] = 12
      preprocessState.methodStatus[methodId] = '处理中'
    })

    const results = await Promise.all(
      preprocessState.jobs.map(async (job) => {
        try {
          const jobId = String(job.jobId || '')
          const report = await requestJson<PreprocessReport>('/preprocess/workbench/run', {
            method: 'POST',
            body: JSON.stringify({
              jobId,
              methods: preprocessState.selectedMethods,
              saveToKb: false,
            }),
          })
          const data = await requestJson<{ rows: Array<Record<string, unknown>> }>(
            `/preprocess/workbench/dataframe?jobId=${encodeURIComponent(jobId)}&limit=100`,
          )
          return { ok: true as const, jobId, report, rows: data.rows || [] }
        } catch (error) {
          return { ok: false as const, message: error instanceof Error ? error.message : '预处理失败' }
        }
      }),
    )

    const nextJobs = preprocessState.jobs.map((job, index) => {
      const result = results[index]
      if (!result || !result.ok) {
        const message = result && !result.ok ? result.message : '预处理失败'
        return {
          ...job,
          status: 'failed' as const,
          error: message,
        }
      }
      const nextJob: PreprocessJobState = {
        ...job,
        status: 'done',
        report: result.report,
        rows: result.rows,
        error: '',
      }
      const methodReports: PreprocessMethodReport[] = Array.isArray(result.report.methodReports) ? result.report.methodReports || [] : []
      methodReports.forEach((stage: PreprocessMethodReport) => {
        const methodId = String(stage.method || '')
        if (!methodId) return
        preprocessState.methodProgress[methodId] = Number(stage.progress || 100)
        preprocessState.methodStatus[methodId] = '完成'
      })
      return nextJob
    })

    preprocessState.jobs = nextJobs
    const activeJob = nextJobs.find((job) => job.status === 'done') || nextJobs[0]
    if (activeJob) selectPreprocessJob(String(activeJob.jobId || ''))
    const doneCount = nextJobs.filter((job) => job.status === 'done').length
    if (doneCount) {
      notify(`数据预处理完成：${doneCount}/${nextJobs.length} 个文件`, 'success')
    } else {
      throw new Error('所有文件的预处理都失败了')
    }
  } catch (error) {
    preprocessState.selectedMethods.forEach((methodId) => {
      if ((preprocessState.methodProgress[methodId] ?? 0) < 100) preprocessState.methodStatus[methodId] = '未完成'
    })
    notify(`预处理失败：${(error as Error).message}`, 'error')
  } finally {
    preprocessState.busy = false
  }
}

async function savePreprocessedToKb() {
  const jobId = String(preprocessState.report?.jobId || preprocessState.job?.jobId || '')
  if (!jobId) {
    notify('请先完成预处理', 'error')
    return
  }
  if (preprocessState.saveMode === 'existing' && !preprocessState.targetKbId) {
    notify('请选择目标知识库', 'error')
    return
  }
  if (preprocessState.saveMode === 'new' && !preprocessState.newKbName.trim()) {
    notify('请输入新知识库名称', 'error')
    return
  }
  preprocessState.saving = true
  try {
    const saved = await requestJson<Record<string, unknown>>('/preprocess/workbench/store', {
      method: 'POST',
      body: JSON.stringify({
        jobId,
        targetKbId: preprocessState.saveMode === 'existing' ? preprocessState.targetKbId : undefined,
        newKbName: preprocessState.saveMode === 'new' ? preprocessState.newKbName : undefined,
        rebuildIndex: preprocessState.rebuildIndex,
      }),
    })
    preprocessState.report = {
      ...(preprocessState.report || {}),
      savedToKb: saved,
    }
    const savedKbId = String(saved.kbId || '')
    await loadKbs()
    if (savedKbId) selectedKbId.value = savedKbId
    await loadFiles()
    notify('预处理文件已保存到知识库', 'success')
  } catch (error) {
    notify(`保存失败：${(error as Error).message}`, 'error')
  } finally {
    preprocessState.saving = false
  }
}

function formatTime(ts?: number) {
  if (!ts) return '未知'
  return new Date(ts * 1000).toLocaleString()
}

function asFiniteNumber(value: unknown, fallback = 0) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : fallback
}

function sumNumericValues(value: unknown): number {
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

function objectEntryCount(value: unknown): number {
  return value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value as Record<string, unknown>).length : 0
}

function directPreprocessChange(item: PreprocessMethodReport) {
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

  if (rowsIn !== rowsOut) return `行数 ${rowsIn} → ${rowsOut}`
  if (missingBefore !== missingAfter) return `缺失值 ${missingBefore} → ${missingAfter}`
  if (columnsIn !== columnsOut) return `列数 ${columnsIn} → ${columnsOut}`
  return '无直接变动'
}

function summarizePreprocessReport(report?: PreprocessReport | null) {
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

function selectPreprocessJob(jobId: string) {
  const matchedJob = preprocessState.jobs.find((job) => job.jobId === jobId)
  if (!matchedJob) return
  preprocessState.previewJobId = jobId
  preprocessState.job = matchedJob
  preprocessState.report = matchedJob.report || null
  preprocessState.rows = matchedJob.rows || []
  preprocessState.previewOpen = true
}

function clearPreprocessSelection() {
  preprocessState.sourceFiles = []
  preprocessState.jobs = []
  preprocessState.job = null
  preprocessState.previewJobId = ''
  preprocessState.report = null
  preprocessState.rows = []
  preprocessState.previewOpen = false
  preprocessState.jobDetailOpenStates = {}
  if (uploadInputRef.value) uploadInputRef.value.value = ''
}

function onPreprocessPreviewSelectChange(event: Event) {
  const jobId = (event.target as HTMLSelectElement).value
  if (jobId) selectPreprocessJob(jobId)
}

function onPreprocessJobDetailToggle(jobId: string, event: Event) {
  preprocessState.jobDetailOpenStates[jobId] = Boolean((event.target as HTMLDetailsElement).open)
  if (preprocessState.jobDetailOpenStates[jobId]) selectPreprocessJob(jobId)
}

watch(selectedKbId, async () => {
  await loadFiles()
  await loadImages()
})

watch(
  detailKbId,
  (kbId) => {
    if (kbId && selectedKbId.value !== kbId) selectedKbId.value = kbId
  },
  { immediate: true },
)

watch(selectedPreviewFileId, () => {
  if (activeTab.value === 'preview') loadPreview()
  if (pagePreviewUrl.value) {
    URL.revokeObjectURL(pagePreviewUrl.value)
    pagePreviewUrl.value = ''
  }
  selectedStructuredSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedPreviewFileId.value))
})

watch(selectedImageFileId, () => {
  selectedImageSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedImageFileId.value))
})

watch([previewTab, selectedPreviewFileId, () => previewState.page, () => previewState.mode], () => {
  if (previewModalOpen.value && previewTab.value === 'page') loadPagePreview()
})

watch(activeTab, (tab) => {
  if (tab === 'preview') {
    loadPreview()
    loadImages()
  }
})

watch(kbSubTab, (tab) => {
  if (tab === 'numbers') {
    const firstPreviewableFile = structuredFiles.value[0]?.fileId || files.value[0]?.fileId || ''
    if (firstPreviewableFile && selectedPreviewFileId.value !== firstPreviewableFile) {
      selectPreviewFile(firstPreviewableFile)
    } else if (selectedPreviewFileId.value) {
      loadPreview()
    }
  }
})

onBeforeUnmount(() => {
  if (pagePreviewUrl.value) URL.revokeObjectURL(pagePreviewUrl.value)
})

watch(
  () => extractState.templateKey,
  () => applyExtractionTemplate(),
)

watch(
  () => extractState.mode,
  () => applyExtractionTemplate(),
)

onMounted(async () => {
  await loadKbs()
  await loadFiles()
})
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <div>
          <h1>非常规油气多模态知识库平台</h1>
          <p>Petro Knowledge Platform</p>
        </div>
      </div>

      <nav v-if="!isKbDetailPage" class="top-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <span :class="['nav-icon', tab.icon]"></span>
          {{ tab.label }}
        </button>
      </nav>

      <div v-else class="detail-actions">
        <button class="ghost" type="button" @click="goHome">返回总览</button>
      </div>
    </header>

    <main class="workspace">
      <section v-if="!isKbDetailPage && activeTab === 'search'" class="module-page">
        <div class="module-title">
          <p class="eyebrow">Vector Index Search</p>
          <h2>向量索引搜索</h2>
        </div>

        <div class="panel">
          <div class="form-grid search-form">
            <label class="field">
              <span>选择检索知识库</span>
              <select v-model="selectedKbId">
                <option value="">请选择知识库</option>
                <option v-for="kb in kbs" :key="kb.kbId" :value="kb.kbId">{{ kb.kbName }}</option>
              </select>
            </label>
            <label class="field">
              <span>搜索关键词</span>
              <input v-model="searchState.query" placeholder="请输入关键词或问题" />
            </label>
            <label class="field">
              <span>Top K</span>
              <input v-model.number="searchState.k" type="number" min="1" max="10" />
            </label>
            <label class="field">
              <span>选择搜索范围</span>
              <select v-model="searchFileId">
                <option value="">当前知识库 (All files)</option>
                <option v-for="file in files" :key="file.fileId" :value="file.fileId">{{ file.fileName || file.fileId }}</option>
              </select>
            </label>
            <button class="primary-red" type="button" @click="runSearch" :disabled="searchState.busy">搜索</button>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Results</p>
              <h3>搜索结果</h3>
            </div>
          </div>
          <div class="result-list">
            <article v-for="(item, index) in searchState.results" :key="index" class="result-item">
              <div class="result-meta">
                <span>Result {{ index + 1 }}</span>
                <span>Score: {{ Number(item.score || 0).toFixed(4) }}</span>
              </div>
              <div class="rendered-markdown result-content" v-html="searchResultHtml(item)"></div>
              <footer class="result-source">
                <strong>出处</strong>
                <div class="source-row-grid">
                  <span v-for="row in searchResultSourceRows(item)" :key="`${row.label}-${row.value}`">
                    <b>{{ row.label }}</b>{{ row.value }}
                  </span>
                </div>
              </footer>
            </article>
            <p v-if="!searchState.results.length" class="empty">输入关键词并点击搜索后，结果会显示在这里。</p>
          </div>
        </div>
      </section>

      <section v-if="!isKbDetailPage && activeTab === 'extract'" class="module-page">
        <div class="module-title">
          <p class="eyebrow">Knowledge Extraction</p>
          <h2>知识提取</h2>
        </div>

        <div class="panel-grid two">
          <div class="panel">
            <div class="panel-head">
              <div>
                <p class="eyebrow">Step 1</p>
                <h3>文件与配置</h3>
              </div>
              <button v-if="extractState.jobId" class="ghost" type="button" @click="extractState.jobId = ''">重置状态</button>
            </div>
            <div class="form-grid">
              <label class="field">
                <span>上传待提取的文件 (PDF, Word, Excel, CSV, TXT)</span>
                <input type="file" accept=".pdf,.doc,.docx,.xlsx,.xls,.csv,.txt,.md" @change="onExtractFileChange" />
              </label>
              <div class="segmented">
                <button type="button" :class="{ active: extractState.mode === '自定义输入' }" @click="extractState.mode = '自定义输入'">自定义输入</button>
                <button type="button" :class="{ active: extractState.mode === '预置模板 (油气领域)' }" @click="extractState.mode = '预置模板 (油气领域)'">预置模板 (油气领域)</button>
              </div>
              <label v-if="extractState.mode === '预置模板 (油气领域)'" class="field">
                <span>选择提取模板</span>
                <select v-model="extractState.templateKey">
                  <option v-for="(_, key) in extractionTemplates" :key="key" :value="key">{{ key }}</option>
                </select>
              </label>
              <label class="field">
                <span>提取指令 (Prompt)</span>
                <textarea v-model="extractState.instruction" rows="9" placeholder="例如：请提取文档中的所有发票信息，包含发票代码、号码、金额、日期。"></textarea>
              </label>
              <div class="form-grid two-cols">
                <label class="field">
                  <span>输出格式</span>
                  <select v-model="extractState.outputFormat">
                    <option value="excel">Excel</option>
                    <option value="csv">CSV</option>
                  </select>
                </label>
                <label class="field">
                  <span>解析模型</span>
                  <select v-model="extractState.parseMethod">
                    <option value="original">基础解析 (结构化OCR, 适合文本/表格)</option>
                    <option value="olmocr">多模态大模型 (视觉增强, 适合复杂排版)</option>
                    <option value="mineru">MinerU (文档解析/表格增强)</option>
                  </select>
                </label>
              </div>
              <label class="field">
                <span>保存文件名 (可选)</span>
                <input v-model="extractState.customFilename" placeholder="留空则自动生成: extracted_{timestamp}" />
              </label>
            </div>
          </div>

          <div class="panel">
            <div class="panel-head">
              <div>
                <p class="eyebrow">Step 2</p>
                <h3>目标知识库</h3>
              </div>
            </div>
            <div class="form-grid">
              <div class="segmented">
                <button type="button" :class="{ active: extractState.kbMode === '现有知识库' }" @click="extractState.kbMode = '现有知识库'">现有知识库</button>
                <button type="button" :class="{ active: extractState.kbMode === '新建知识库' }" @click="extractState.kbMode = '新建知识库'">新建知识库</button>
              </div>
              <label v-if="extractState.kbMode === '现有知识库'" class="field">
                <span>选择目标知识库</span>
                <select v-model="selectedKbId">
                  <option value="">请选择知识库</option>
                  <option v-for="kb in kbs" :key="kb.kbId" :value="kb.kbId">{{ kb.kbName }} ({{ kb.kbId }})</option>
                </select>
              </label>
              <div v-else class="nested-box">
                <label class="field"><span>知识库名称</span><input v-model="newKb.kbName" placeholder="请输入名称..." /></label>
                <label class="field"><span>向量模型</span><input v-model="newKb.embedModel" /></label>
                <button type="button" @click="createKb">立即创建</button>
              </div>
              <button class="primary-red" type="button" @click="startExtraction" :disabled="extractState.busy || !!extractState.jobId">开始提取</button>
            </div>

            <div class="job-box">
              <div class="progress">
                <span :style="{ width: `${extractState.progress}%` }"></span>
              </div>
              <p>{{ extractState.status || '等待任务启动' }} · {{ extractState.progress }}%</p>
              <pre class="json-view">{{ extractState.result ? JSON.stringify(extractState.result, null, 2) : '提取结果、定位上下文和入库信息会显示在这里。' }}</pre>
            </div>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'preview' || isKbDetailPage" class="module-page">
        <div class="module-title">
          <p class="eyebrow">Knowledge Base</p>
          <h2>{{ isKbDetailPage ? '知识库详情' : '知识库管理' }}</h2>
          <span v-if="!isKbDetailPage">选择一个知识库进入管理，或创建新的知识库。</span>
          <span v-else>当前知识库：{{ selectedKb?.kbName || detailKbId }}</span>
        </div>

        <template v-if="!isKbDetailPage">
          <div class="panel preview-create-panel">
            <div class="panel-head">
              <div>
                <p class="eyebrow">Create</p>
                <h3>新建知识库</h3>
              </div>
              <div class="toolbar">
                <button class="ghost" type="button" @click="loadKbs">刷新列表</button>
                <button class="ghost" type="button" @click="createKbExpanded = !createKbExpanded">{{ createKbExpanded ? '收起' : '展开' }}</button>
              </div>
            </div>
            <div v-show="createKbExpanded" class="form-grid">
              <label class="field"><span>知识库名称</span><input v-model="newKb.kbName" placeholder="例如: 公司财报2023" /></label>
              <div class="form-grid two-cols">
                <label class="field"><span>向量库类型</span><select v-model="newKb.vectorStoreType"><option value="faiss">faiss</option><option value="milvus">milvus</option><option value="es">es</option></select></label>
                <label class="field"><span>向量模型</span><input v-model="newKb.embedModel" /></label>
              </div>
              <button type="button" @click="createKb">立即创建</button>
            </div>
          </div>

          <div class="panel preview-search-panel">
            <div class="panel-head">
              <div>
                <p class="eyebrow">Search</p>
                <h3>搜索知识库</h3>
              </div>
            </div>
            <label class="field">
              <span>按知识库名称搜索</span>
              <input v-model="kbSearchQuery" placeholder="输入知识库名称、ID 或向量模型关键字" />
            </label>
          </div>

          <div class="panel preview-list-panel">
            <div class="panel-head">
              <div>
                <p class="eyebrow">Inventory</p>
                <h3>已有知识库</h3>
              </div>
              <small>{{ filteredKbs.length }} / {{ kbs.length }} 个</small>
            </div>
            <div class="kb-card-scroll">
              <div class="kb-card-grid">
                <article v-for="kb in filteredKbs" :key="kb.kbId" :class="{ active: selectedKbId === kb.kbId }" @click="enterKb(kb.kbId)">
                  <div>
                    <strong>{{ kb.kbName }}</strong>
                    <small>ID: {{ kb.kbId }}</small>
                  </div>
                  <div class="metric-row">
                    <span>文件数 {{ kb.fileCount || 0 }}</span>
                    <span>{{ kb.vectorStoreType || 'faiss' }}</span>
                  </div>
                  <div class="toolbar">
                    <button type="button" @click.stop="enterKb(kb.kbId)">进入知识库</button>
                    <button class="danger ghost" type="button" @click.stop="deleteKb(kb.kbId)">删除</button>
                  </div>
                </article>
                <p v-if="!filteredKbs.length" class="empty">没有匹配的知识库。</p>
              </div>
            </div>
          </div>
        </template>

        <div v-if="isKbDetailPage && selectedKb" class="panel">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Current KB</p>
              <h3>知识库: {{ selectedKb.kbName }}</h3>
            </div>
            <div class="toolbar">
              <div class="stat-grid compact">
                <div v-for="item in stats" :key="item.label" class="stat"><strong>{{ item.value }}</strong><span>{{ item.label }}</span></div>
              </div>
              <button class="ghost" type="button" @click="kbUploadExpanded = !kbUploadExpanded">{{ kbUploadExpanded ? '收起上传区' : '展开上传区' }}</button>
            </div>
          </div>
          <div v-if="kbUploadExpanded" class="upload-box inline-upload">
            <input ref="uploadInputRef" type="file" multiple accept=".pdf,.doc,.docx,.xlsx,.xls,.csv,.txt,.md,.json,.jsonl" @change="onUploadChange" />
            <div v-if="uploadState.files.length" class="upload-file-grid">
              <article v-for="(file, index) in uploadState.files" :key="`${file.name}-${file.size}-${index}`" class="upload-file-card">
                <button type="button" class="upload-file-remove" @click="removeUploadFile(index)" :disabled="uploadState.busy" aria-label="移除文件">×</button>
                <strong>{{ file.name }}</strong>
                <small>{{ (file.size / 1024 / 1024).toFixed(2) }} MB · {{ file.type || '未知类型' }}</small>
              </article>
            </div>
            <button type="button" class="ghost" @click="clearUploadSelection" :disabled="uploadState.busy">清空已选文件</button>
            <select v-model="uploadState.parseMethod">
              <option value="original">基础解析 (快, 传统OCR)</option>
              <option value="olmocr">增强解析 (慢, 多模态大模型)</option>
              <option value="mineru">MinerU (文档解析/表格增强)</option>
            </select>
            <button type="button" @click="uploadFiles" :disabled="uploadState.busy">上传并入库</button>
            <small>{{ uploadState.message }}</small>
          </div>
        </div>

        <div v-if="isKbDetailPage && selectedKb" class="sub-tabs">
          <button type="button" :class="{ active: kbSubTab === 'files' }" @click="kbSubTab = 'files'">文件库管理</button>
          <button type="button" :class="{ active: kbSubTab === 'images' }" @click="kbSubTab = 'images'; loadImages()">图像管理</button>
          <button type="button" :class="{ active: kbSubTab === 'numbers' }" @click="kbSubTab = 'numbers'">数值管理</button>
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'files'" class="panel files-workbench">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Files</p>
              <h3>文件列表与预览</h3>
            </div>
            <div class="inline-field search-field">
              <input
                v-model="selectedFileSearchText"
                list="file-search-options"
                placeholder="搜索文件名或ID"
                aria-label="搜索文件"
                @change="onFileSearchChange"
              />
              <datalist id="file-search-options">
                <option v-for="file in files" :key="file.fileId" :value="file.fileName || file.fileId">{{ file.fileId }}</option>
              </datalist>
            </div>
          </div>
          <div class="toolbar">
            <button type="button" @click="parseSelectedFiles">重新解析勾选文件</button>
            <button type="button" @click="buildIndex()">重建索引</button>
            <button class="ghost" type="button" @click="deleteSelectedFiles(false)">删除勾选文件索引</button>
            <button class="danger" type="button" @click="deleteSelectedFiles(true)">删除勾选文件</button>
            <small>{{ selectedFileIds.length ? `已勾选 ${selectedFileIds.length} 个文件` : '可通过复选框进行单选或多选' }}</small>
          </div>
          <div class="file-table">
            <div class="file-row head"><span><label class="check-field head-check"><input :checked="allFilesSelected" type="checkbox" @change="onSelectAllFilesChange" /> 全选</label></span><span>文件名 (点击预览)</span><span>类型</span><span>解析模型</span><span>向量化模型</span><span>状态</span></div>
            <div v-for="file in filteredFiles" :key="file.fileId" :class="['file-row', { active: selectedFileId === file.fileId }]" @click="openFilePreview(file.fileId)">
              <span><input v-model="selectedFileIds" :value="file.fileId" type="checkbox" @click.stop /></span>
              <span class="file-name">{{ file.fileName || file.fileId }}</span>
              <span>{{ (file.type || 'unknown').toUpperCase() }}</span>
              <span>{{ file.parseMethod || file.parser || (file.type === 'excel' ? 'pandas' : '未记录') }}</span>
              <span>{{ selectedKb?.embedModel || 'bge-m3' }}</span>
              <span class="file-status-cell">
                <b :class="['badge', file.hasParsed ? 'ok' : 'warn']">{{ file.hasParsed ? '解析完成' : '未解析' }}</b>
                <b :class="['badge', file.isIndexed ? 'ok' : 'warn']">{{ file.isIndexed ? '已索引' : '未索引' }}</b>
                <b v-if="hasFileTask(file.fileId)" :class="['badge', fileTaskBadgeClass(file.fileId)]">
                  {{ fileTaskMessage(file.fileId) }}
                  <template v-if="fileTaskProgress(file.fileId) !== undefined"> · {{ fileTaskProgress(file.fileId) }}%</template>
                </b>
              </span>
            </div>
            <p v-if="!filteredFiles.length" class="empty">没有匹配的文件。</p>
          </div>
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'images'" class="panel images-workbench">
          <div class="panel-head">
            <div><p class="eyebrow">Images</p><h3>图像管理</h3></div>
            <div class="toolbar">
              <div class="inline-field search-field compact">
                <input
                  v-model="selectedImageSearchText"
                  list="image-search-options"
                  placeholder="搜索图片来源文件"
                  aria-label="搜索图片来源文件"
                  @change="onImageSearchChange"
                />
                <datalist id="image-search-options">
                  <option v-for="file in files" :key="file.fileId" :value="file.fileName || file.fileId">{{ file.fileId }}</option>
                </datalist>
              </div>
              <button type="button" @click="loadImages">刷新图片列表</button>
            </div>
          </div>
          <div class="image-grid">
            <article v-for="item in imageState.images" :key="`${item.fileId}-${item.img_name || item.imagePath}`" class="image-card">
              <img :src="imageSrc(item)" alt="extracted figure" />
              <label class="field compact">
                <span>图片名</span>
                <input v-model="item.img_name" placeholder="请输入图片名" />
              </label>
              <label class="field compact">
                <span>图片描述</span>
                <textarea v-model="item.summary" rows="4" placeholder="图片描述 (可编辑)"></textarea>
              </label>
              <button type="button" @click="saveImage(item)" :disabled="imageState.saving">保存摘要</button>
            </article>
            <p v-if="!imageState.images.length" class="empty">当前知识库未检测到已解析的图片。</p>
          </div>
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'numbers'" class="panel numbers-workbench">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Structured Data</p>
              <h3>数值管理</h3>
            </div>
            <div class="inline-field search-field">
              <input
                v-model="selectedStructuredSearchText"
                list="structured-search-options"
                placeholder="搜索结构化文件"
                aria-label="搜索结构化文件"
                @change="onStructuredSearchChange"
              />
              <datalist id="structured-search-options">
                <option v-for="file in structuredFiles" :key="file.fileId" :value="file.fileName || file.fileId">{{ file.fileId }}</option>
              </datalist>
            </div>
          </div>

          <div class="structured-panel">
            <div class="toolbar">
              <button type="button" @click="loadPreview">刷新结构化数据</button>
              <small v-if="selectedPreviewFileId">当前文件：{{ selectedFile?.fileName || selectedPreviewFileId }}</small>
              <small v-else>请选择一个已提取表格的文件</small>
            </div>

            <div class="table-preview structured-table-preview" v-if="previewState.busy || Object.keys(previewState.sheets).length">
              <div class="toolbar sheet-toolbar">
                <label class="inline-field small">
                  <span>表页</span>
                  <select v-model="previewState.selectedSheet"><option v-for="(_, sheet) in previewState.sheets" :key="sheet" :value="sheet">{{ sheet }}</option></select>
                </label>
                <span class="sheet-summary">{{ previewRows.length ? `共 ${previewRows.length} 行` : '暂无行数据' }}</span>
              </div>
              <div v-if="previewState.busy" class="empty">加载结构化数据中...</div>
              <div v-else class="data-table">
                <table>
                  <thead><tr><th v-for="col in previewColumns" :key="col">{{ col }}</th></tr></thead>
                  <tbody><tr v-for="(row, index) in previewRows.slice(0, 80)" :key="index"><td v-for="col in previewColumns" :key="col">{{ row[col] }}</td></tr></tbody>
                </table>
              </div>
            </div>

            <p v-else class="empty">当前文件没有可显示的结构化表格数据，请先选择已提取表格的文件。</p>
          </div>
        </div>
      </section>

      <section v-if="!isKbDetailPage && activeTab === 'preprocess'" class="module-page">
        <div class="module-title">
          <p class="eyebrow">Data Preprocess</p>
          <h2>数据预处理</h2>
          <span>上传 CSV、Excel、JSON 或 JSONL 文件，选择多个预处理方法，生成标准化结果后再保存到知识库。</span>
        </div>

        <div class="preprocess-grid">
          <div class="panel preprocess-flow">
            <div class="preprocess-step">
              <div class="panel-head"><div><p class="eyebrow">Step 1</p><h3>上传文件</h3></div></div>
              <div class="form-grid">
                <label class="field">
                  <span>选择一个或多个结构化文件</span>
                  <input ref="uploadInputRef" type="file" multiple accept=".csv,.xlsx,.xls,.json,.jsonl" @change="onPreprocessSourceChange" />
                </label>
                <div v-if="preprocessState.sourceFiles.length" class="upload-file-grid preprocess-upload-grid">
                  <article v-for="(file, index) in preprocessState.sourceFiles" :key="`${file.name}-${file.size}-${index}`" class="upload-file-card preprocess-upload-card">
                    <button type="button" class="upload-file-remove" @click="removePreprocessSourceFile(index)" :disabled="preprocessState.uploading" aria-label="移除文件">×</button>
                    <strong>{{ file.name }}</strong>
                    <small>{{ (file.size / 1024 / 1024).toFixed(2) }} MB</small>
                    <!-- {{ file.type || '未知类型' }}</small>-->  
                  </article>
                </div>
                <div class="toolbar preprocess-upload-toolbar">
                  <button class="ghost" type="button" @click="clearPreprocessSelection" :disabled="preprocessState.uploading">清空选择</button>
                  <button class="primary-red" type="button" @click="uploadPreprocessSource" :disabled="!preprocessState.sourceFiles.length || preprocessState.uploading">
                    {{ preprocessState.uploading ? '上传中...' : '上传到预处理工作台' }}
                  </button>
                </div>
                <small v-if="preprocessState.sourceFiles.length">已选择 {{ preprocessState.sourceFiles.length }} 个文件，上传后会自动生成独立任务。</small>
                <!-- <small v-if="preprocessState.jobs.length" class="status-line">已上传 {{ preprocessState.jobs.length }} 个任务，点击下方结果卡可切换查看。</small> -->
              </div>
            </div>

            <div class="preprocess-step">
              <div class="panel-head"><div><p class="eyebrow">Step 2</p><h3>选择预处理方法</h3></div></div>
              <div class="preprocess-method-strip">
                <article v-for="method in preprocessSelectedMethodCards" :key="method.id" class="preprocess-method-card">
                  <button class="method-remove" type="button" @click="removePreprocessMethod(method.id)">×</button>
                  <span class="method-index">{{ method.index }}</span>
                  <strong>{{ method.name }}</strong>
                  <p>{{ method.description }}</p>
                </article>
                <div v-if="!preprocessSelectedMethodCards.length" class="preprocess-method-empty">尚未选择预处理方法</div>
                <div class="method-add-wrap">
                  <button class="method-add-circle" type="button" @click="togglePreprocessMethodMenu">+</button>
                  <div v-if="preprocessMethodMenuOpen" class="method-menu" :style="preprocessMethodMenuStyle">
                    <button v-for="method in remainingPreprocessMethods" :key="method.id" class="method-menu-item" type="button" @click="addPreprocessMethod(method.id)">
                      <strong>{{ method.name }}</strong>
                      <span>{{ method.description }}</span>
                    </button>
                    <span v-if="!remainingPreprocessMethods.length" class="empty">所有方法都已选择</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="preprocess-step">
              <div class="panel-head"><div><p class="eyebrow">Step 3</p><h3>开始预处理</h3></div></div>
              <button class="primary-red" type="button" @click="runPreprocess" :disabled="preprocessState.busy || !preprocessState.jobs.length || !preprocessState.selectedMethods.length">
                {{ preprocessState.busy ? '预处理中...' : '开始预处理' }}
              </button>
              <div v-if="preprocessProgressRows.length" class="method-progress-list">
                <div v-for="item in preprocessProgressRows" :key="item.id" class="method-progress-row">
                  <span>{{ item.name }}</span>
                  <div class="progress"><span :style="{ width: `${item.progress}%` }"></span></div>
                  <small>{{ item.status }}</small>
                </div>
              </div>
            </div>

            <details v-if="preprocessState.report || preprocessState.rows.length" class="panel full preprocess-preview-panel preprocess-collapsible" open>
              <summary class="preprocess-collapsible-summary">
                <div>
                  <p class="eyebrow">Preview</p>
                  <h3>标准化结果预览</h3>
                </div>
                <!--<small v-if="preprocessSelectedJob">当前任务：{{ preprocessSelectedJob.fileName || preprocessSelectedJob.jobId }}</small>-->
              </summary>
              <label class="field preprocess-preview-search">
                <span>选择已处理文件</span>
                <div class="preprocess-preview-controls">
                  <select :value="preprocessState.previewJobId" @change="onPreprocessPreviewSelectChange">
                    <option value="" disabled>从全部预处理文件中选择</option>
                    <option v-for="job in preprocessJobCards" :key="`preprocess-preview-select-${job.jobId || job.fileName}`" :value="job.jobId || ''">
                      {{ job.fileName || job.jobId }} · {{ job.status === 'done' ? '已完成' : job.status === 'running' ? '处理中' : job.status === 'failed' ? '失败' : '已上传' }}
                    </option>
                  </select>
                </div>
              </label>
              <div class="preprocess-preview-current">
                <div class="preprocess-preview-current-head">
                  <strong>{{ preprocessSelectedJob?.fileName || preprocessSelectedJob?.jobId || '当前文件' }}</strong>
                  <!--<small v-if="preprocessSelectedJob">Job {{ preprocessSelectedJob.jobId }}</small>-->
                </div>
              </div>
              <div class="preprocess-preview-scroll">
                <div class="preprocess-operation-strip">
                  <span class="preprocess-method-count">方法数 {{ preprocessReportSummary.methodCount }}</span>
                  <div v-for="method in preprocessReportSummary.methodHighlights" :key="method.id" class="preprocess-method-diff-row">
                    <strong>{{ method.name }}</strong>
                    <span>{{ method.directText }}</span>
                  </div>
                </div>
                <div v-if="preprocessState.rows.length" class="data-table preprocess-data-table">
                  <table>
                    <thead>
                      <tr>
                        <th v-for="col in preprocessRowsColumns" :key="col">{{ col }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, index) in preprocessState.rows" :key="index">
                        <td v-for="col in preprocessRowsColumns" :key="col">{{ row[col] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="empty">请选择一个已处理文件后查看标准化结果预览。</p>
              </div>
            </details>

            <div class="preprocess-step">
              <div class="panel-head"><div><p class="eyebrow">Step 4</p><h3>保存到知识库</h3></div></div>
              <div class="radio-row">
                <label><input v-model="preprocessState.saveMode" type="radio" value="existing" /> 选择已存在的知识库</label>
                <label><input v-model="preprocessState.saveMode" type="radio" value="new" /> 新建知识库</label>
              </div>
              <label v-if="preprocessState.saveMode === 'existing'" class="field">
                <span>目标知识库</span>
                <select v-model="preprocessState.targetKbId"><option value="">请选择知识库</option><option v-for="kb in kbs" :key="kb.kbId" :value="kb.kbId">{{ kb.kbName || kb.kbId }}</option></select>
              </label>
              <label v-else class="field">
                <span>新知识库名称</span>
                <input v-model="preprocessState.newKbName" type="text" placeholder="例如：标准化录井数据" />
              </label>
              <label class="check-field"><input v-model="preprocessState.rebuildIndex" type="checkbox" /> 存入后立即构建索引</label>
              <button type="button" @click="savePreprocessedToKb" :disabled="preprocessState.saving || !preprocessReportSource">
                {{ preprocessState.saving ? '保存中...' : '保存预处理文件到知识库' }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>

    <div v-if="previewModalOpen" class="preview-modal-backdrop" @click.self="closePreviewModal">
      <div class="preview-modal-panel">
        <div class="panel-head modal-head">
          <div>
            <p class="eyebrow">File Preview</p>
            <h3>{{ previewFile?.fileName || previewFile?.fileId || '文件预览' }}</h3>
            <small>{{ previewFile?.type || 'unknown' }} · {{ previewFile?.parseMethod || previewFile?.parser || '未记录' }}</small>
          </div>
          <button type="button" class="ghost" @click="closePreviewModal">关闭</button>
        </div>
        <div class="preview-tabs">
          <button type="button" :class="{ active: previewTab === 'markdown' }" @click="previewTab = 'markdown'">解析 markdown</button>
          <button type="button" :class="{ active: previewTab === 'page' }" @click="previewTab = 'page'">页面预览</button>
        </div>
        <div v-if="previewTab === 'markdown'" class="markdown-view modal-markdown-view">
          <pre>{{ previewState.busy ? '加载中...' : previewState.content || '暂无解析 markdown 内容，请先选择文件并完成解析。' }}</pre>
        </div>
        <div v-else class="page-preview-wrap">
          <div class="toolbar modal-page-toolbar">
            <label class="inline-field small"><span>页码</span><input v-model.number="previewState.page" type="number" min="1" /></label>
            <select v-model="previewState.mode"><option value="original">原始页面</option><option value="parsed">解析预览</option></select>
            <button type="button" @click="loadPagePreview">加载页面</button>
          </div>
          <div class="document-view modal-page-view">
            <img v-if="pagePreviewUrl" :src="pagePreviewUrl" alt="page preview" />
            <div v-else class="empty">暂无页面预览，请点击“加载页面”。</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="toast" :class="['toast', toast.type]">{{ toast.text }}</div>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 72% 16%, rgba(226, 42, 42, 0.06), transparent 26%),
    linear-gradient(180deg, #fbfcfd 0%, #f5f7fa 52%, #eef2f6 100%);
  color: #111827;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: grid;
  grid-template-columns: minmax(300px, 430px) minmax(420px, 1fr);
  gap: 18px;
  align-items: center;
  height: 58px;
  padding: 0 26px;
  background: rgba(255, 255, 255, 0.92);
  color: #1f2937;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 12px 34px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(18px);
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
}

.brand h1 {
  font-size: 17px;
  line-height: 1.25;
  font-weight: 800;
  color: #df1717;
}

.brand p,
.eyebrow {
  margin: 0;
  color: #66818b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.app-header .eyebrow,
.app-header small,
.app-header .field span {
  color: #6b7280;
}

.app-body {
  min-height: calc(100vh - 58px);
}

.workspace {
  min-width: 0;
  padding: 28px 32px 48px;
  max-width: 1480px;
  margin: 0 auto;
}

.topbar,
.panel-head,
.toolbar,
.topbar-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.topbar {
  margin-bottom: 14px;
}

h2,
h3,
strong {
  font-weight: 800;
}

h2 {
  font-size: 28px;
}

h3 {
  font-size: 18px;
}

.top-tabs {
  display: flex;
  gap: 18px;
  justify-content: flex-start;
  white-space: nowrap;
}

.top-tabs button,
button {
  min-height: 38px;
  border: 0;
  border-radius: 8px;
  padding: 0 14px;
  background: #d71414;
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.top-tabs button {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 38px;
  border: 1px solid transparent;
  background: transparent;
  color: #1f2937;
}

.top-tabs button.active {
  background: #fff;
  border-color: #eef0f4;
  color: #e11919;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.nav-icon::before {
  display: inline-grid;
  width: 18px;
  height: 18px;
  place-items: center;
  color: currentColor;
  font-size: 17px;
  line-height: 1;
}

.nav-icon.chat::before {
  content: '▣';
}

.nav-icon.share::before {
  content: '◇';
}

.nav-icon.book::before {
  content: '▱';
}

.nav-icon.sigma::before {
  content: '∑';
  font-weight: 900;
}

.ghost {
  border: 1px solid #c9d6da;
  background: #fff;
  color: #24404a;
}

.danger {
  background: #d71414;
}

.danger.ghost {
  border-color: #efc4c4;
  color: #a83939;
}

.panel-grid {
  display: grid;
  gap: 16px;
}

.module-page {
  display: grid;
  gap: 18px;
}

.module-title {
  display: grid;
  gap: 4px;
  margin-bottom: 2px;
}

.module-title h2 {
  font-size: 28px;
}

.module-title span {
  color: #64748b;
}

.search-form {
  grid-template-columns: minmax(220px, 0.9fr) minmax(320px, 1.4fr) 110px minmax(220px, 0.9fr) 92px;
  align-items: end;
}

.form-grid.two-cols {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.segmented,
.sub-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.segmented button,
.sub-tabs button {
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
}

.segmented button.active,
.sub-tabs button.active {
  border-color: #f3b7b7;
  background: #fff2f2;
  color: #d71414;
}

.nested-box,
.job-box {
  display: grid;
  gap: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  background: #f8fbfc;
}

.nested-box p,
.job-box p {
  margin: 0;
  color: #64748b;
}

.kb-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
}

.preview-create-panel,
.preview-search-panel {
  display: grid;
  gap: 14px;
}

.preview-search-panel {
  margin-top: 14px;
}

.preview-list-panel {
  display: grid;
  gap: 14px;
  max-height: min(72vh, 860px);
}

.kb-card-scroll {
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.kb-card-grid article {
  display: grid;
  gap: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 14px;
  background: #f8fbfc;
  cursor: pointer;
}

.kb-card-grid article.active {
  border-color: #e11919;
  background: #fff7f7;
}

.metric-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.metric-row span {
  border-radius: 999px;
  padding: 4px 9px;
  background: #eef2f6;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.preview-create-panel .form-grid {
  transition: max-height 0.25s ease, opacity 0.2s ease, transform 0.2s ease;
}

.preview-search-panel input {
  border-color: #d5dee3;
}

.preview-create-panel .form-grid {
  overflow: hidden;
}

.preview-list-panel .panel-head small {
  color: #6b7280;
  font-weight: 700;
}

.inline-upload {
  grid-template-columns: 1fr;
  align-items: stretch;
}

.search-workbench {
  display: grid;
  gap: 24px;
}

.analysis-stage {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 290px;
  gap: 42px;
  align-items: center;
  max-width: 980px;
  min-height: 350px;
  margin: 0 auto;
}

.analysis-copy {
  display: grid;
  gap: 16px;
}

.module-kicker {
  display: flex;
  gap: 10px;
  align-items: center;
  color: #6b7280;
  font-size: 13px;
  font-weight: 700;
}

.module-kicker b {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #e11919;
  box-shadow: 0 0 0 7px rgba(225, 25, 25, 0.08);
}

.analysis-copy h2 {
  max-width: 640px;
  font-size: 40px;
  line-height: 1.12;
  letter-spacing: 0;
}

.analysis-copy p {
  margin: 0;
  color: #4b5563;
  font-size: 17px;
}

.analysis-copy small {
  color: #9aa3af;
}

.example-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(210px, 1fr));
  gap: 12px;
  max-width: 560px;
}

.example-grid button,
.chip-row button {
  min-height: 38px;
  border: 1px solid #e4e8ef;
  border-radius: 999px;
  background: #fff;
  color: #475569;
  box-shadow: none;
}

.process-card {
  padding: 28px 22px 20px;
  border: 1px solid #e6e9ef;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.08);
}

.radar {
  position: relative;
  width: 190px;
  height: 190px;
  margin: 0 auto 18px;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(225, 25, 25, 0.18) 0 16%, transparent 17%),
    repeating-radial-gradient(circle, transparent 0 28px, rgba(148, 163, 184, 0.25) 29px 30px);
}

.radar-core {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #ffb7b7, #d81f1f 65%);
  transform: translate(-50%, -50%);
  box-shadow: 0 0 0 14px rgba(225, 25, 25, 0.12);
}

.dot {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 3px solid #e11919;
  border-radius: 50%;
  background: #fff;
}

.dot.one {
  top: 54px;
  left: 54px;
}

.dot.two {
  top: 26px;
  right: 58px;
}

.dot.three {
  top: 62px;
  right: 24px;
}

.process-card strong {
  display: block;
  padding-top: 14px;
  border-top: 1px solid #e6e9ef;
  color: #334155;
  font-size: 18px;
}

.process-card p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.prompt-dock {
  display: grid;
  gap: 10px;
  max-width: 900px;
  margin: 0 auto;
  padding: 14px;
  border: 1px solid #e2e7ee;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
}

.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip-row button {
  min-height: 30px;
  padding: 0 12px;
  color: #d71414;
  font-size: 12px;
  font-weight: 800;
}

.prompt-row {
  display: grid;
  grid-template-columns: minmax(160px, 210px) minmax(260px, 1fr) 86px 92px;
  gap: 10px;
  align-items: end;
}

.primary-red {
  background: linear-gradient(180deg, #df1717, #b90808);
}

.module-block {
  margin-bottom: 16px;
}

.panel-grid.two {
  grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr);
}

.panel,
.side-card {
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 14px 40px rgba(25, 54, 65, 0.08);
}

.files-workbench {
  display: grid;
  gap: 14px;
  max-height: min(78vh, 920px);
  overflow: auto;
}

.images-workbench,
.numbers-workbench {
  display: grid;
  gap: 14px;
}

.preprocess-grid {
  display: grid;
  gap: 18px;
}

.preprocess-flow {
  display: grid;
  gap: 14px;
}

.preprocess-step {
  display: grid;
  gap: 12px;
}

.preprocess-upload-grid {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  max-height: min(28vh, 260px);
  overflow: auto;
  padding-right: 4px;
}

.preprocess-upload-card {
  min-height: 78px;
  padding: 10px 12px;
}

.preprocess-upload-toolbar {
  justify-content: flex-start;
}

.preprocess-results-panel,
.preprocess-preview-panel {
  display: grid;
  gap: 14px;
}

.preprocess-collapsible {
  padding-top: 14px;
}

.preprocess-collapsible > summary {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  list-style: none;
}

.preprocess-collapsible > summary::-webkit-details-marker {
  display: none;
}

.preprocess-collapsible-summary h3,
.preprocess-collapsible-summary p {
  margin: 0;
}

.preprocess-collapsible-summary small {
  color: #64748b;
  font-weight: 700;
  white-space: nowrap;
}

.preprocess-results-panel {
  display: flex;
  flex-direction: column;
  max-height: min(58vh, 620px);
  overflow: hidden;
}

.preprocess-preview-panel {
  display: flex;
  flex-direction: column;
  overflow: visible;
}

.preprocess-preview-picker {
  flex: 0 0 auto;
  display: grid;
  gap: 10px;
  max-height: min(22vh, 220px);
  overflow: auto;
  padding-right: 4px;
}

.preprocess-preview-choice {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 10px;
  align-items: start;
  padding: 12px 14px;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  background: #f8fbfc;
  cursor: pointer;
}

.preprocess-preview-choice.active {
  border-color: #e11919;
  background: #fff7f7;
}

.preprocess-preview-choice input {
  margin-top: 3px;
}

.preprocess-preview-choice-content {
  display: grid;
  gap: 8px;
}

.preprocess-preview-current {
  display: grid;
  gap: 8px;
  padding: 4px 2px 0;
}

.preprocess-preview-controls {
  display: grid;
  grid-template-columns: minmax(260px, 520px);
  align-items: center;
}

.preprocess-preview-current-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.preprocess-preview-current-head small {
  color: #64748b;
  font-weight: 700;
}

.preprocess-result-scroll {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 12px;
  overflow: auto;
  padding-right: 4px;
}

.preprocess-result-card {
  display: flex;
  flex-direction: column;
  gap: 0;
  max-height: min(34vh, 320px);
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  background: #f8fbfc;
  overflow: hidden;
}

.preprocess-result-card.active {
  border-color: #e11919;
  background: #fff7f7;
}

.preprocess-result-card > summary {
  flex: 0 0 auto;
  display: grid;
  gap: 12px;
  padding: 14px;
  cursor: pointer;
  list-style: none;
}

.preprocess-result-card > summary::-webkit-details-marker {
  display: none;
}

.preprocess-result-summary .result-card-head {
  align-items: center;
}

.result-stat-grid-compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.preprocess-result-body {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 12px;
  overflow: auto;
  padding: 0 14px 14px;
}

.result-card-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.result-card-head small,
.result-card-head strong {
  display: block;
}

.result-card-head small {
  color: #64748b;
  font-size: 12px;
}

.result-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.result-stat-card {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.result-stat-card span {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.result-stat-card strong {
  color: #1f2937;
  font-size: 16px;
}

.result-stat-card small {
  color: #64748b;
  font-size: 12px;
}

.result-chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.result-chip-row.compact {
  gap: 6px;
}

.result-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: #eef2f6;
  color: #465d67;
  font-size: 12px;
  font-weight: 700;
}

.method-report-list.compact {
  gap: 8px;
}

.method-report-card.compact {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.method-report-card.compact strong {
  color: #1f2937;
  font-size: 14px;
}

.method-report-card.compact small {
  color: #64748b;
  font-size: 12px;
}

.preprocess-operation-strip {
  display: flex;
  gap: 8px;
  align-items: center;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
  white-space: nowrap;
}

.preprocess-method-count,
.preprocess-method-diff-row {
  flex: 0 0 auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fbfc;
  color: #526a74;
  font-size: 12px;
  font-weight: 700;
}

.preprocess-method-count {
  padding: 8px 10px;
  color: #1f2937;
  background: #eef2f6;
}

.preprocess-method-diff-row {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  max-width: 360px;
  padding: 8px 10px;
}

.preprocess-method-diff-row strong {
  color: #1f2937;
  font-size: 13px;
}

.preprocess-method-diff-row span,
.preprocess-method-diff-row strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preprocess-preview-scroll {
  display: grid;
  gap: 14px;
  overflow: visible;
  padding-right: 4px;
}

.status-line {
  color: #18715f;
  font-weight: 700;
}

.preprocess-method-strip {
  display: flex;
  gap: 10px;
  min-height: 124px;
  overflow-x: auto;
  padding: 2px 4px 10px 0;
}

.preprocess-method-card,
.preprocess-method-empty {
  flex: 0 0 198px;
  width: 198px;
  height: 118px;
  box-sizing: border-box;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
  padding: 10px;
}

.preprocess-method-card {
  position: relative;
  display: grid;
  grid-template-rows: 22px auto 1fr;
  gap: 6px;
}

.preprocess-method-card strong {
  color: #1f2937;
  font-size: 14px;
  line-height: 1.35;
}

.preprocess-method-card p {
  margin: 0;
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
  overflow: hidden;
}

.preprocess-method-empty {
  display: flex;
  align-items: center;
  color: #64748b;
  background: #f8fbfc;
}

.method-index {
  width: 20px;
  height: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #eef9f6;
  color: #18715f;
  font-weight: 800;
  font-size: 11px;
}

.method-remove {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 22px;
  min-height: 22px;
  padding: 0;
  border-radius: 999px;
  background: #f2f6f7;
  color: #526a74;
  font-size: 14px;
}

.method-add-wrap {
  position: relative;
  flex: 0 0 56px;
  display: flex;
  align-items: center;
}

.method-add-circle {
  width: 42px;
  min-height: 42px;
  border-radius: 999px;
  padding: 0;
  font-size: 22px;
  line-height: 1;
}

.method-menu {
  position: fixed;
  right: auto;
  z-index: 60;
  display: grid;
  gap: 8px;
  width: 250px;
  max-height: 320px;
  overflow: auto;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  padding: 10px;
  background: #fff;
  box-shadow: 0 18px 46px rgba(25, 54, 65, 0.16);
}

.method-menu-item {
  display: grid;
  gap: 4px;
  min-height: auto;
  padding: 10px;
  border: 1px solid #e2e8f0;
  background: #f8fbfc;
  color: #243942;
  text-align: left;
}

.method-menu-item span {
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
}

.method-progress-list {
  display: grid;
  gap: 10px;
  max-height: min(34vh, 320px);
  overflow-y: auto;
  padding-right: 4px;
}

.method-progress-row {
  display: grid;
  grid-template-columns: 170px minmax(120px, 1fr) 64px;
  gap: 12px;
  align-items: center;
}

.method-progress-row > span {
  color: #24404a;
  font-weight: 800;
}

.method-progress-row small {
  color: #64748b;
  text-align: right;
}

.radio-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.radio-row label {
  display: flex;
  gap: 6px;
  align-items: center;
  color: #526a74;
  font-weight: 700;
}

.radio-row input {
  width: auto;
}

.preview-expander {
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
}

.preview-expander summary {
  cursor: pointer;
  padding: 14px 16px;
  color: #1f2937;
  font-weight: 800;
}

.preview-expander .data-table,
.preview-expander .empty {
  margin: 0;
  padding: 0 16px 16px;
}

.preprocess-data-table {
  min-height: 260px;
  max-height: min(62vh, 640px);
  overflow: auto;
  padding-right: 4px;
  padding-bottom: 8px;
  border: 1px solid #e1eaed;
  border-radius: 8px;
  background: #fff;
}

.panel {
  min-width: 0;
  padding: 18px;
}

.panel.large,
.panel.full {
  grid-column: 1 / -1;
}

.panel-grid.two .panel.large {
  grid-column: auto;
}

.side-card {
  display: grid;
  gap: 6px;
  padding: 14px;
  background: #173640;
  border-color: #2b5966;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.stat-grid.compact {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.stat {
  display: grid;
  gap: 2px;
  padding: 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e7ebf0;
}

.stat strong {
  color: #111827;
  font-size: 18px;
}

.stat span {
  color: #6b7280;
  font-size: 12px;
}

.field,
.inline-field {
  display: grid;
  gap: 6px;
}

.inline-field {
  min-width: 180px;
}

.inline-field.small {
  min-width: 90px;
}

.search-field {
  min-width: 280px;
}

.search-field.compact {
  min-width: 240px;
}

.search-field input {
  min-width: 0;
}

.field span,
.inline-field span {
  color: #526a74;
  font-size: 12px;
  font-weight: 700;
}

input,
select,
textarea {
  width: 100%;
  min-height: 38px;
  border: 1px solid #c9d6da;
  border-radius: 8px;
  padding: 8px 10px;
  background: #fff;
  color: #13202a;
  font: inherit;
}

textarea {
  resize: vertical;
}

.form-grid,
.upload-box {
  display: grid;
  gap: 12px;
}

.upload-file-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}

.upload-file-card {
  position: relative;
  display: grid;
  gap: 6px;
  align-content: start;
  min-height: 92px;
  border: 1px solid #dbe5e8;
  border-radius: 10px;
  padding: 12px 34px 12px 12px;
  background: linear-gradient(180deg, #fff 0%, #f7fafb 100%);
}

.upload-file-card strong {
  font-size: 13px;
  color: #13202a;
  word-break: break-word;
}

.upload-file-card small {
  color: #667985;
  font-size: 12px;
}

.upload-file-remove {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  min-height: 24px;
  border-radius: 999px;
  padding: 0;
  border: 1px solid #d9a3a3;
  background: #fff;
  color: #a52e2e;
  font-size: 16px;
  line-height: 1;
}

.result-list,
.chat-stream,
.kb-list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.result-item,
.message,
.kb-list article,
.image-card {
  border: 1px solid #e0e8eb;
  border-radius: 8px;
  padding: 12px;
  background: #f8fbfc;
}

.result-item {
  display: grid;
  gap: 10px;
}

.result-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: #607780;
  font-size: 12px;
}

.result-content {
  min-width: 0;
  border: 1px solid #e5edf0;
  border-radius: 8px;
  padding: 14px 16px;
  background: #fff;
}

.rendered-markdown {
  color: #1f2937;
  font-size: 14px;
  line-height: 1.75;
}

.rendered-markdown :deep(h1),
.rendered-markdown :deep(h2),
.rendered-markdown :deep(h3),
.rendered-markdown :deep(h4),
.rendered-markdown :deep(h5),
.rendered-markdown :deep(h6) {
  margin: 14px 0 8px;
  color: #111827;
  line-height: 1.32;
}

.rendered-markdown :deep(h1) {
  padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
  font-size: 24px;
}

.rendered-markdown :deep(h2) {
  padding-left: 10px;
  border-left: 4px solid #d71414;
  font-size: 20px;
}

.rendered-markdown :deep(h3) {
  font-size: 17px;
}

.rendered-markdown :deep(h4),
.rendered-markdown :deep(h5),
.rendered-markdown :deep(h6) {
  font-size: 15px;
}

.rendered-markdown :deep(p) {
  margin: 8px 0;
}

.rendered-markdown :deep(ul),
.rendered-markdown :deep(ol) {
  margin: 8px 0 8px 22px;
  padding: 0;
}

.rendered-markdown :deep(li) {
  margin: 3px 0;
}

.rendered-markdown :deep(blockquote) {
  margin: 10px 0;
  border-left: 4px solid #cbd5e1;
  padding: 8px 12px;
  background: #f8fafc;
  color: #475569;
}

.rendered-markdown :deep(code) {
  border-radius: 5px;
  padding: 2px 5px;
  background: #eef2f6;
  color: #9f1239;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

.rendered-markdown :deep(.md-code) {
  overflow: auto;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  padding: 12px;
  background: #f8fbfc;
}

.rendered-markdown :deep(.md-code code) {
  padding: 0;
  background: transparent;
  color: #253942;
}

.rendered-markdown :deep(.md-image-figure) {
  margin: 12px 0;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  padding: 10px;
  background: #f8fbfc;
}

.rendered-markdown :deep(.md-image-figure img) {
  display: block;
  width: min(100%, 860px);
  max-height: 520px;
  object-fit: contain;
  border-radius: 6px;
  background: #fff;
}

.rendered-markdown :deep(.md-image-figure figcaption) {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.rendered-markdown :deep(.md-table-wrap) {
  overflow: auto;
  margin: 10px 0;
  border: 1px solid #e1eaed;
  border-radius: 8px;
}

.rendered-markdown :deep(.md-table-wrap table) {
  min-width: 520px;
}

.result-source {
  display: grid;
  gap: 8px;
  border-top: 1px solid #e1eaed;
  padding-top: 10px;
}

.result-source strong {
  color: #334155;
  font-size: 13px;
}

.source-row-grid {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.source-row-grid span {
  display: inline-flex;
  gap: 6px;
  max-width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  padding: 5px 9px;
  background: #fff;
  color: #526a74;
  font-size: 12px;
  line-height: 1.35;
}

.source-row-grid b {
  color: #1f2937;
}

.chat-panel {
  min-height: 620px;
}

.chat-stream {
  max-height: 500px;
  overflow: auto;
}

.message.user {
  background: #e9f5f1;
}

.message span {
  color: #526a74;
  font-size: 12px;
  font-weight: 800;
}

.chat-input {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-top: 12px;
}

.kb-list article {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.kb-list article.active {
  border-color: #1f8f7c;
  background: #eef9f6;
}

.kb-list small {
  display: block;
  color: #66818b;
}

.file-table,
.data-table {
  margin-top: 14px;
  overflow: auto;
}

.file-row {
  display: grid;
  grid-template-columns: 44px minmax(220px, 1fr) 100px 140px 140px minmax(220px, 0.8fr);
  gap: 10px;
  align-items: center;
  min-height: 42px;
  border-bottom: 1px solid #e7eef0;
}

.file-row:not(.head) {
  cursor: pointer;
}

.file-row.active {
  background: #f1fbf8;
}

.file-row.head {
  color: #526a74;
  font-size: 12px;
  font-weight: 800;
}

.badge {
  width: fit-content;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 12px;
  font-weight: 800;
}

.badge.ok {
  background: #dff4e9;
  color: #13724f;
}

.badge.warn {
  background: #fff0cf;
  color: #8a5d00;
}

.badge.busy {
  background: #dbeafe;
  color: #1d4ed8;
}

.badge.error {
  background: #fee2e2;
  color: #b91c1c;
}

.file-status-cell {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  min-width: 0;
}

.row-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.row-actions button {
  min-height: 30px;
  padding: 0 10px;
  font-size: 12px;
}

.file-name {
  font-weight: 700;
}

.head-check {
  min-height: 0;
  font-size: 12px;
}

.head-check input,
.file-row input[type='checkbox'] {
  width: auto;
  margin: 0;
}

.structured-panel {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.structured-table-preview {
  margin-top: 0;
}

.sheet-toolbar {
  align-items: end;
}

.sheet-summary {
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
}

.preview-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.preview-tabs button {
  border: 1px solid #e2e8f0;
  background: #fff;
  color: #475569;
}

.preview-tabs button.active {
  border-color: #f3b7b7;
  background: #fff2f2;
  color: #d71414;
}

.modal-markdown-view,
.modal-page-view {
  min-height: 520px;
}

.modal-page-toolbar {
  margin-bottom: 12px;
}

.modal-page-view {
  display: grid;
  place-items: center;
  padding: 12px;
}

.page-preview-wrap {
  display: grid;
  gap: 12px;
}

.modal-page-view img {
  width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 8px;
  background: #fff;
}

.preview-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(360px, 1.1fr);
  gap: 14px;
  margin-top: 14px;
}

.document-view,
.markdown-view {
  min-height: 520px;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #f8fbfc;
  overflow: auto;
}

.document-view {
  padding: 12px;
}

.document-view img {
  width: 100%;
  margin-top: 10px;
  border-radius: 6px;
  background: #fff;
}

.preview-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.54);
  backdrop-filter: blur(8px);
}

.preview-modal-panel {
  width: min(1320px, 100%);
  max-height: calc(100vh - 40px);
  overflow: auto;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 18px;
  padding: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbfc 100%);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.28);
}

.modal-head {
  margin-bottom: 14px;
}

.modal-preview-grid {
  margin-top: 0;
}

.modal-table-preview {
  margin-top: 14px;
}

pre,
.json-view {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  color: #253942;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}

.markdown-view pre,
.json-view {
  padding: 14px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  max-width: 260px;
  border: 1px solid #e1eaed;
  padding: 8px;
  text-align: left;
  vertical-align: top;
}

th {
  position: sticky;
  top: 0;
  background: #edf4f6;
  font-weight: 800;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.images-workbench .image-grid {
  max-height: min(72vh, 860px);
  overflow: auto;
  padding-right: 4px;
}

.numbers-workbench .data-table {
  max-height: min(72vh, 860px);
  overflow: auto;
  padding-right: 4px;
}

.image-card {
  display: grid;
  gap: 10px;
}

.image-card img {
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: contain;
  border-radius: 6px;
  background: #edf4f6;
}

.progress {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #dbe5e8;
}

.progress span {
  display: block;
  height: 100%;
  background: #1f8f7c;
}

.api-pill {
  border: 1px solid #dbe5e8;
  border-radius: 999px;
  padding: 7px 10px;
  background: #fff;
  color: #526a74;
  font-size: 12px;
}

.empty {
  color: #66818b;
}

.toast {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 20;
  max-width: 420px;
  border-radius: 8px;
  padding: 12px 14px;
  background: #13202a;
  color: #fff;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.18);
}

.toast.success {
  background: #17765d;
}

.toast.error {
  background: #b64242;
}

.check-field {
  display: flex;
  gap: 8px;
  align-items: center;
}

.check-field input {
  width: auto;
}

@media (max-width: 1100px) {
  .app-header,
  .search-form,
  .form-grid.two-cols,
  .inline-upload,
  .analysis-stage,
  .prompt-row,
  .panel-grid.two,
  .preview-grid {
    grid-template-columns: 1fr;
  }

  .app-header {
    position: relative;
    height: auto;
  }

  .top-tabs {
    justify-content: flex-start;
    overflow-x: auto;
  }

  .file-row {
    grid-template-columns: 34px minmax(180px, 1fr) 80px 80px 80px 70px;
  }

  .method-progress-row {
    grid-template-columns: 1fr;
  }

  .method-progress-row small {
    text-align: left;
  }

  .method-menu {
    left: 0;
    right: auto;
  }
}
</style>
