import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { extractionTemplates, imageSuffixes, preprocessMethods, queryModes, tableSuffixes, tabs } from '@/constants/app'
import { createMarkdownRenderer } from '@/utils/markdown'
import { asFiniteNumber, directPreprocessChange, formatTime, objectEntryCount, summarizePreprocessReport, sumNumericValues } from '@/utils/preprocessReport'
import { buildStandardGroupsFromDocuments, standardDocumentObject, standardDocumentUnit } from '@/utils/standardObject'
import type { Kb, KbFile, WellDocument, WellCategory, WellGroup, StandardGroup, FileTaskState, SearchResult, QueryMode, SqlQueryResult, UnifiedQueryResponse, ExtractionRow, ExtractionStatus, ExtractionContentResponse, ExtractionFilenameCheckResponse, PreprocessMethod, PreprocessJob, PreprocessMethodReport, PreprocessReport, PreprocessJobState, PreprocessArtifact, ImageItem, KnowledgeChunk, ChunkStats, StructuredDbConnection, StructuredDbTable, StructuredDbSchema, ChatMessage, Toast } from '@/types/app'

export function useAppController() {
  const PARSE_POLL_INTERVAL_MS = 1500
  const PARSE_POLL_MAX_ATTEMPTS = Number(import.meta.env.VITE_PARSE_POLL_MAX_ATTEMPTS || 9600)
  const PARSE_STATUS_RETRY_LIMIT = Number(import.meta.env.VITE_PARSE_STATUS_RETRY_LIMIT || 5)

  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8002/api/v1'
  const route = useRoute()
  const router = useRouter()
  const detailKbId = computed(() => (typeof route.params.kbId === 'string' ? route.params.kbId : ''))
  const isKbDetailPage = computed(() => route.name === 'kb-detail')

  const activeTab = ref<(typeof tabs)[number]['id']>('preview')
  const kbs = ref<Kb[]>([])
  const files = ref<KbFile[]>([])
  const availablePreprocessMethods = ref<PreprocessMethod[]>([...preprocessMethods])
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
  const selectedChunkFileId = ref('')
  const kbSubTab = ref<'files' | 'images' | 'numbers' | 'chunks'>('files')
  const previewKbId = ref('')
  const managedPreviewDocument = ref<WellDocument | null>(null)
  const wellSearchQuery = ref('')
  const standardSearchQuery = ref('')
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
  const preprocessInputRef = ref<HTMLInputElement | null>(null)
  const extractInputRef = ref<HTMLInputElement | null>(null)

  const searchState = reactive({
    mode: 'vector' as QueryMode,
    query: '',
    k: 5,
    sqlLimit: 100,
    results: [] as SearchResult[],
    answer: '',
    citations: [] as Array<Record<string, unknown>>,
    sqlResult: null as SqlQueryResult | null,
    agentTrace: [] as string[],
    usedRetrieval: false,
    usedSql: false,
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

  const chunkState = reactive({
    chunks: [] as KnowledgeChunk[],
    stats: { total: 0, text: 0, image: 0, files: 0 } as ChunkStats,
    query: '',
    limit: 50,
    offset: 0,
    total: 0,
    busy: false,
  })

  const fileManagerState = reactive({
    wells: [] as WellGroup[],
    standards: [] as WellDocument[],
    standardGroups: [] as StandardGroup[],
    unmatched: [] as WellDocument[],
    sourceKbId: '',
    standardsKbId: '',
    wellCount: 0,
    documentCount: 0,
    selectedWellId: '',
    busy: false,
    loaded: false,
  })

  function normalizeStandardGroups(groups: StandardGroup[] | undefined, documents: WellDocument[]): StandardGroup[] {
    if (documents.length) {
      return buildStandardGroupsFromDocuments(documents)
    }

    const availableGroups = Array.isArray(groups)
      ? groups.filter((group) => Array.isArray(group.documents) && group.documents.length)
      : []
    return availableGroups.map((group) => {
      const object = standardDocumentUnit({ standardUnit: group.object, fileName: group.documents[0]?.fileName, fileId: group.documents[0]?.fileId })
      const normalizedDocuments = group.documents.map((doc) => ({
        ...doc,
        standardUnit: standardDocumentUnit(doc),
      }))
      return {
        ...group,
        object,
        documentCount: Number(group.documentCount || normalizedDocuments.length),
        documents: normalizedDocuments,
      }
    })
  }

  const dbState = reactive({
    connections: [] as StructuredDbConnection[],
    connectionId: '',
    schemas: [] as StructuredDbSchema[],
    selectedSchema: '',
    selectedTable: '',
    columns: [] as string[],
    rows: [] as Array<Record<string, unknown>>,
    totalRows: 0,
    limit: 100,
    offset: 0,
    connecting: false,
    schemaBusy: false,
    tableBusy: false,
    form: {
      name: '',
      type: 'mysql',
      host: '127.0.0.1',
      port: 13307,
      database: '',
      username: '',
      password: '',
      sqlitePath: '',
    },
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
    result: null as ExtractionStatus | null,
    extractedRows: [] as ExtractionRow[],
    sourceContent: '',
    sourcePages: [] as Array<number | string>,
    sourceScope: '',
    sourceFragmentTitle: '',
    sourceContentLoading: false,
    resultDirty: false,
    saving: false,
    busy: false,
  })

  const preprocessState = reactive({
    sourceFiles: [] as File[],
    jobs: [] as PreprocessJobState[],
    job: null as PreprocessJobState | null,
    previewJobId: '' as string,
    selectedMethods: [] as string[],
    selectedAlgorithms: {} as Record<string, string>,
    saveMode: 'existing' as 'existing' | 'new',
    targetKbId: '',
    newKbName: '',
    rebuildIndex: false,
    report: null as PreprocessReport | null,
    rows: [] as Array<Record<string, unknown>>,
    previewText: '',
    previewLoading: false,
    previewError: '',
    methodProgress: {} as Record<string, number>,
    methodStatus: {} as Record<string, string>,
    jobDetailOpenStates: {} as Record<string, boolean>,
    uploadedSourceFileKeys: [] as string[],
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
  const preprocessAlgorithmDialog = reactive({
    open: false,
    methodId: '',
    draftAlgorithmId: '',
    left: 0,
    top: 0,
    dragging: false,
    dragOffsetX: 0,
    dragOffsetY: 0,
  })

  const selectedKb = computed(() => kbs.value.find((kb) => kb.kbId === selectedKbId.value))
  const selectedFile = computed(() => files.value.find((file) => file.fileId === selectedFileId.value))
  const activePreviewKbId = computed(() => previewKbId.value || selectedKbId.value)
  const previewFile = computed<KbFile | WellDocument | undefined>(() => {
    if (managedPreviewDocument.value?.fileId === selectedPreviewFileId.value) return managedPreviewDocument.value
    return files.value.find((file) => file.fileId === selectedPreviewFileId.value)
  })
  const previewKbLabel = computed(() => {
    if (managedPreviewDocument.value?.fileId === selectedPreviewFileId.value) return managedPreviewDocument.value.kbName || managedPreviewDocument.value.kbId
    return kbs.value.find((kb) => kb.kbId === activePreviewKbId.value)?.kbName || activePreviewKbId.value
  })
  const selectedImageFile = computed(() => files.value.find((file) => file.fileId === selectedImageFileId.value))
  const originalPreviewUrl = computed(() =>
    activePreviewKbId.value && selectedPreviewFileId.value
      ? apiUrl('/kb/file/original', { kbId: activePreviewKbId.value, fileId: selectedPreviewFileId.value })
      : '',
  )
  const pdfPagePreviewUrl = computed(() =>
    activePreviewKbId.value && selectedPreviewFileId.value
      ? apiUrl('/pdf/page', {
          kbId: activePreviewKbId.value,
          fileId: selectedPreviewFileId.value,
          page: previewState.page,
          type: 'original',
        })
      : '',
  )
  const previewKind = computed<'pdf' | 'document' | 'table' | 'image' | 'file'>(() => {
    const file = previewFile.value
    const suffix = fileSuffix(file)
    if (file?.type === 'pdf' || suffix === 'pdf') return 'pdf'
    if (file?.type === 'word' || suffix === 'doc' || suffix === 'docx') return 'document'
    if (file?.type === 'image' || imageSuffixes.has(suffix)) return 'image'
    if (file?.type === 'excel' || file?.type === 'las' || tableSuffixes.has(suffix)) return 'table'
    return 'file'
  })
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
  const filteredWells = computed(() => {
    const query = wellSearchQuery.value.trim().toLowerCase()
    if (!query) return fileManagerState.wells
    return fileManagerState.wells.filter((well) => {
      const documentText = well.categories
        .flatMap((category) => category.documents)
        .some((doc) => [doc.fileName, doc.fileId, doc.kbName, doc.category].some((value) => String(value || '').toLowerCase().includes(query)))
      return [well.wellId, ...(well.aliases || [])].some((value) => String(value || '').toLowerCase().includes(query)) || documentText
    })
  })
  const selectedWell = computed(() => {
    if (!filteredWells.value.length) return null
    return filteredWells.value.find((well) => well.wellId === fileManagerState.selectedWellId) || filteredWells.value[0] || null
  })
  const filteredStandardDocuments = computed(() => {
    const query = standardSearchQuery.value.trim().toLowerCase()
    if (!query) return fileManagerState.standards
    return fileManagerState.standards.filter((doc) =>
      [doc.fileName, doc.fileId, doc.kbName, doc.category, doc.standardUnit, standardDocumentUnit(doc), doc.standardObject, standardDocumentObject(doc), doc.type].some((value) =>
        String(value || '').toLowerCase().includes(query),
      ),
    )
  })
  const filteredStandardGroups = computed(() => {
    const sourceGroups = fileManagerState.standardGroups.length
      ? fileManagerState.standardGroups
      : buildStandardGroupsFromDocuments(fileManagerState.standards)
    const query = standardSearchQuery.value.trim().toLowerCase()
    if (!query) return sourceGroups
    return sourceGroups
      .map((group) => {
        const objectMatched = String(group.object || '').toLowerCase().includes(query)
        const documents = objectMatched
          ? group.documents
          : group.documents.filter((doc) =>
              [doc.fileName, doc.fileId, doc.kbName, doc.category, doc.standardUnit, standardDocumentUnit(doc), doc.standardObject, standardDocumentObject(doc), doc.type].some((value) =>
                String(value || '').toLowerCase().includes(query),
              ),
            )
        return { ...group, documents, documentCount: documents.length }
      })
      .filter((group) => group.documents.length)
  })
  const selectedActionFileIds = computed(() => {
    const ids = selectedFileIds.value.length ? selectedFileIds.value : selectedFileId.value ? [selectedFileId.value] : []
    return Array.from(new Set(ids)).filter(Boolean)
  })
  const allFilesSelected = computed(
    () => filteredFiles.value.length > 0 && filteredFiles.value.every((file) => selectedFileIds.value.includes(file.fileId)),
  )
  const structuredFiles = computed(() =>
    files.value.filter((file) => Number(file.tableCount || 0) > 0 || ['excel', 'las', 'unknown'].includes(file.type || '') || /\.(csv|xlsx|xls|json|jsonl|las)$/i.test(file.fileName || '')),
  )
  const previewRows = computed(() => previewState.sheets[previewState.selectedSheet] || [])
  const previewColumns = computed(() => Object.keys(previewRows.value[0] || {}))
  const preprocessRowsColumns = computed(() => Object.keys(preprocessState.rows[0] || {}))
  const preprocessMethodById = computed(
    () => Object.fromEntries(availablePreprocessMethods.value.map((method) => [method.id, method])) as Record<string, PreprocessMethod>,
  )
  const preprocessGroupedMethod = computed(
    () =>
      preprocessState.selectedMethods
        .map((methodId) => preprocessMethodById.value[methodId])
        .find((method) => String(method?.metadata?.inputMode || '') === 'grouped_files') || null,
  )
  const preprocessSelectedMethodCards = computed(() =>
    preprocessState.selectedMethods.map((methodId, index) => {
      const method: PreprocessMethod = preprocessMethodById.value[methodId] || { id: methodId, name: methodId, description: '' }
      const selectedAlgorithmId = preprocessState.selectedAlgorithms[methodId] || method.defaultAlgorithm || method.algorithms?.[0]?.id || ''
      const selectedAlgorithm = method.algorithms?.find((algorithm) => algorithm.id === selectedAlgorithmId)
      return {
        ...method,
        index: index + 1,
        selectedAlgorithmId,
        selectedAlgorithmName: selectedAlgorithm?.name || selectedAlgorithmId || '默认算法',
      }
    }),
  )
  const preprocessAlgorithmDialogMethod = computed(() => preprocessMethodById.value[preprocessAlgorithmDialog.methodId] || null)
  const remainingPreprocessMethods = computed(() =>
    availablePreprocessMethods.value.filter((method) => !preprocessState.selectedMethods.includes(method.id)),
  )
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
  const preprocessHasGroupedOutputJobs = computed(() => preprocessState.jobs.some((job) => Boolean(job.groupedOutput)))
  const preprocessDoneJobs = computed(() =>
    preprocessState.jobs.filter((job) => job.status === 'done' && String(job.jobId || '') && (!preprocessHasGroupedOutputJobs.value || Boolean(job.groupedOutput))),
  )
  const preprocessReportSource = computed(() => preprocessState.report || preprocessSelectedJob.value?.report || null)
  const preprocessReportSummary = computed(() => summarizePreprocessReport(preprocessReportSource.value))
  const preprocessSelectedJobSuffix = computed(() => preprocessOutputSuffix(preprocessSelectedJob.value))
  const preprocessPreviewKind = computed(() => {
    const suffix = preprocessSelectedJobSuffix.value
    if (preprocessState.rows.length) return 'table'
    if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff'].includes(suffix)) return 'image'
    if (['md', 'markdown'].includes(suffix)) return 'markdown'
    if (suffix === 'json') return 'json'
    if (['txt', 'log', 'csv', 'jsonl', 'yaml', 'yml'].includes(suffix)) return 'text'
    if (suffix === 'pdf') return 'frame'
    return 'unsupported'
  })
  const preprocessPreviewUrl = computed(() => {
    const jobId = String(preprocessSelectedJob.value?.jobId || '')
    return jobId ? apiUrl('/preprocess/workbench/download', { jobId, format: 'csv' }) : ''
  })
  const preprocessJobCards = computed(() =>
    preprocessState.jobs
      .filter((job) => !preprocessHasGroupedOutputJobs.value || Boolean(job.groupedOutput))
      .map((job) => ({
        ...job,
        summary: summarizePreprocessReport(job.report || null),
        active: preprocessSelectedJob.value?.jobId === job.jobId,
      })),
  )
  const preprocessArtifacts = computed(() => collectPreprocessArtifacts(preprocessReportSource.value))
  const preprocessPendingSourceFiles = computed(() =>
    preprocessState.sourceFiles.filter((file) => !preprocessState.uploadedSourceFileKeys.includes(preprocessSourceFileKey(file))),
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
  const chunkCurrentPage = computed(() => Math.floor(chunkState.offset / chunkState.limit) + 1)
  const chunkTotalPages = computed(() => Math.max(1, Math.ceil(chunkState.total / chunkState.limit)))
  const chunkPageStart = computed(() => (chunkState.total ? chunkState.offset + 1 : 0))
  const chunkPageEnd = computed(() => Math.min(chunkState.offset + chunkState.chunks.length, chunkState.total))
  const currentDbConnection = computed(() => dbState.connections.find((item) => item.connectionId === dbState.connectionId))
  const dbSchemaTables = computed(() => dbState.schemas.find((schema) => schema.name === dbState.selectedSchema)?.tables || [])
  const selectedDbTableInfo = computed(() => dbSchemaTables.value.find((table) => table.name === dbState.selectedTable))
  const dbPreviewPage = computed(() => Math.floor(dbState.offset / dbState.limit) + 1)
  const dbPreviewPages = computed(() => Math.max(1, Math.ceil(dbState.totalRows / dbState.limit)))
  const dbPreviewStart = computed(() => (dbState.totalRows ? dbState.offset + 1 : 0))
  const dbPreviewEnd = computed(() => Math.min(dbState.offset + dbState.rows.length, dbState.totalRows))
  const searchUsesVector = computed(() => searchState.mode === 'vector' || searchState.mode === 'hybrid' || searchState.mode === 'agent')
  const searchUsesSql = computed(() => searchState.mode === 'sql' || searchState.mode === 'hybrid' || searchState.mode === 'agent')
  const sqlResultRows = computed(() => searchState.sqlResult?.rows || [])
  const sqlResultColumns = computed(() => searchState.sqlResult?.columns || [])
  const extractionColumns = computed(() => {
    const columns: string[] = []
    const seen = new Set<string>()

    extractState.extractedRows.forEach((row) => {
      Object.keys(row || {}).forEach((column) => {
        if (seen.has(column)) return
        seen.add(column)
        columns.push(column)
      })
    })

    return columns
  })

  if (detailKbId.value) selectedKbId.value = detailKbId.value

  const {
    searchResultText,
    searchResultSourceObject,
    sourceStringValue,
    isNonEmptyString,
    searchResultFileId,
    searchResultFile,
    searchResultSourceRows,
    escapeHtml,
    decodeHtmlEntities,
    searchResultImageUrl,
    safeLinkUrl,
    renderMarkdownInline,
    isMarkdownTableSeparator,
    splitMarkdownTableRow,
    looksLikeMarkdownTableBlock,
    renderHtmlTableBlock,
    isMarkdownBlockStart,
    renderMarkdownTable,
    renderMarkdown,
    searchResultHtml,
    chunkContentHtml,
    citationAsSearchResult,
    citationHtml,
    sqlCellValue
  } = createMarkdownRenderer({
    apiUrl,
    getSelectedKbId: () => selectedKbId.value,
  })

  function queryAnswerHtml() {
    return renderMarkdown(searchState.answer, { content: searchState.answer })
  }

  function fileDisplayName(file?: KbFile | null) {
    return file?.fileName || file?.fileId || ''
  }

  function fileSuffix(file?: KbFile | null) {
    const name = file?.fileName || file?.fileId || ''
    const match = String(name).toLowerCase().match(/\.([a-z0-9]+)$/)
    return match?.[1] || ''
  }

  function documentKey(doc: WellDocument, index = 0) {
    return `${doc.kbId}-${doc.fileId}-${index}`
  }

  function documentTypeLabel(doc?: KbFile | WellDocument | null) {
    const suffix = fileSuffix(doc)
    if (suffix) return suffix
    return String(doc?.type || '').trim() || 'unknown'
  }

  function parseMethodLabel(method?: string, parser?: string) {
    const normalized = String(method || '').toLowerCase()
    if (normalized === 'original') return '基础解析'
    if (normalized === 'olmocr') return '增强解析'
    if (normalized === 'mineru') return 'MinerU'
    if (normalized === 'pandas') return 'pandas'
    if (normalized === 'las') return 'las'
    if (normalized === 'extraction') return 'KnowledgeExtraction'
    if (normalized === 'preprocess') return 'DataPreprocess'
    return parser || method || '未记录'
  }

  function selectWell(wellId: string) {
    fileManagerState.selectedWellId = wellId
  }

  function firstDocumentForWell(well?: WellGroup | null) {
    if (!well) return null
    for (const category of well.categories) {
      const firstDoc = category.documents[0]
      if (firstDoc) return firstDoc
    }
    return null
  }

  function wellCategoryCount(category: WellCategory) {
    return category.documents.length
  }

  function wellAliasText(well: WellGroup) {
    return (well.aliases || []).filter((alias) => alias !== well.wellId).join(' / ')
  }

  function findWellByQuery(query: string) {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return null
    return (
      fileManagerState.wells.find((well) => [well.wellId, ...(well.aliases || [])].some((value) => String(value || '').toLowerCase() === normalized)) ||
      fileManagerState.wells.find((well) => [well.wellId, ...(well.aliases || [])].some((value) => String(value || '').toLowerCase().includes(normalized))) ||
      null
    )
  }

  function onWellSearchChange() {
    const matchedWell = findWellByQuery(wellSearchQuery.value)
    if (matchedWell) {
      selectWell(matchedWell.wellId)
      const firstDoc = firstDocumentForWell(matchedWell)
      if (firstDoc) openManagedFilePreview(firstDoc)
    }
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
    previewKbId.value = selectedKbId.value
    managedPreviewDocument.value = null
    selectedFileId.value = fileId
    selectedPreviewFileId.value = fileId
    previewModalOpen.value = true
    loadPreview()
  }

  function selectFile(fileId: string) {
    previewKbId.value = selectedKbId.value
    managedPreviewDocument.value = null
    selectedFileId.value = fileId
    selectedPreviewFileId.value = fileId
  }

  function openManagedFilePreview(doc: WellDocument) {
    previewKbId.value = doc.kbId
    managedPreviewDocument.value = doc
    selectedPreviewFileId.value = doc.fileId
    selectedFileId.value = doc.kbId === selectedKbId.value ? doc.fileId : ''
    previewModalOpen.value = false
    loadPreview()
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

  async function loadPreprocessMethods() {
    try {
      const data = await requestJson<{ methods?: PreprocessMethod[] }>('/preprocess/methods')
      const methods = Array.isArray(data.methods)
        ? data.methods
            .filter((method) => method && method.id)
            .map((method) => ({
              id: String(method.id),
              name: String(method.name || method.id),
              description: String(method.description || ''),
              category: method.category,
              type: method.type,
              algorithms: Array.isArray(method.algorithms)
                ? method.algorithms
                    .filter((algorithm) => algorithm && algorithm.id)
                    .map((algorithm) => ({
                      id: String(algorithm.id),
                      name: String(algorithm.name || algorithm.id),
                      description: String(algorithm.description || ''),
                    }))
                : [],
              defaultAlgorithm: method.defaultAlgorithm ? String(method.defaultAlgorithm) : undefined,
              metadata: method.metadata,
            }))
        : []
      if (methods.length) {
        const serverById = Object.fromEntries(methods.map((method) => [method.id, method])) as Record<string, PreprocessMethod>
        const originalIds = new Set(preprocessMethods.map((method) => method.id))
        availablePreprocessMethods.value = [
          ...preprocessMethods.map((method) => {
            const serverMethod = serverById[method.id]
            return {
              ...serverMethod,
              ...method,
              algorithms: serverMethod?.algorithms?.length ? serverMethod.algorithms : method.algorithms,
              defaultAlgorithm: serverMethod?.defaultAlgorithm || method.defaultAlgorithm,
            }
          }),
          ...methods.filter((method) => !originalIds.has(method.id)),
        ]
      }
    } catch {
      availablePreprocessMethods.value = [...preprocessMethods]
    }
  }

  function collectPreprocessArtifacts(report: PreprocessReport | null): PreprocessArtifact[] {
    const artifacts: PreprocessArtifact[] = []
    const allowedSuffixes = new Set(['csv', 'xlsx', 'xls', 'json', 'png', 'jpg', 'jpeg', 'txt', 'md'])

    const visit = (value: unknown, prefix: string, methodName: string) => {
      if (!value) return
      if (Array.isArray(value)) {
        value.forEach((item, index) => visit(item, `${prefix} ${index + 1}`.trim(), methodName))
        return
      }
      if (typeof value === 'object') {
        Object.entries(value as Record<string, unknown>).forEach(([key, item]) => {
          visit(item, prefix ? `${prefix} / ${key}` : key, methodName)
        })
        return
      }
      if (typeof value !== 'string') return
      const path = value.trim()
      const name = path.split(/[\\/]/).filter(Boolean).pop() || path
      const suffix = (name.split('.').pop() || '').toLowerCase()
      if (!path || !allowedSuffixes.has(suffix)) return
      artifacts.push({
        method: methodName,
        label: prefix || name,
        path,
        name,
        suffix,
      })
    }

    ;(report?.methodReports || []).forEach((stage) => {
      const methodName = String(stage.name || stage.method || '预处理方法')
      const operations = stage.operations || {}
      visit(operations.artifacts, '产物', methodName)
      visit(operations.originalProgramArtifacts, '原程序产物', methodName)
    })
    return artifacts
  }

  function onDbTypeChange() {
    if (dbState.form.type === 'mysql') dbState.form.port = 13307
    else if (dbState.form.type === 'postgresql') dbState.form.port = 5432
  }

  function resetDbPreview() {
    dbState.schemas = []
    dbState.selectedSchema = ''
    dbState.selectedTable = ''
    dbState.columns = []
    dbState.rows = []
    dbState.totalRows = 0
    dbState.offset = 0
  }

  async function loadDbConnections() {
    try {
      const data = await requestJson<{ connections?: StructuredDbConnection[] }>('/structured-db/connections')
      dbState.connections = data.connections || []
      if (dbState.connectionId && !dbState.connections.some((item) => item.connectionId === dbState.connectionId)) {
        dbState.connectionId = ''
        resetDbPreview()
      }
      if (!dbState.connectionId && dbState.connections[0]) dbState.connectionId = dbState.connections[0].connectionId
    } catch (error) {
      notify(`数据库连接列表加载失败：${(error as Error).message}`, 'error')
    }
  }

  async function connectStructuredDb() {
    dbState.connecting = true
    try {
      const payload = { ...dbState.form }
      if (payload.type === 'sqlite') {
        payload.host = ''
        payload.username = ''
        payload.password = ''
        payload.database = payload.sqlitePath
      }
      const data = await requestJson<{ connection?: StructuredDbConnection }>('/structured-db/connect', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (data.connection?.connectionId) dbState.connectionId = data.connection.connectionId
      dbState.form.password = ''
      await loadDbConnections()
      await loadDbSchema()
      notify('数据库连接成功', 'success')
    } catch (error) {
      notify(`数据库连接失败：${(error as Error).message}`, 'error')
    } finally {
      dbState.connecting = false
    }
  }

  async function disconnectStructuredDb() {
    if (!dbState.connectionId) return
    try {
      await requestJson('/structured-db/disconnect', {
        method: 'POST',
        body: JSON.stringify({ connectionId: dbState.connectionId }),
      })
      dbState.connectionId = ''
      resetDbPreview()
      await loadDbConnections()
      notify('数据库连接已断开', 'success')
    } catch (error) {
      notify(`断开连接失败：${(error as Error).message}`, 'error')
    }
  }

  async function loadDbSchema() {
    if (!dbState.connectionId) return
    dbState.schemaBusy = true
    resetDbPreview()
    try {
      const data = await requestJson<{ schemas?: StructuredDbSchema[] }>(`/structured-db/schema?connectionId=${encodeURIComponent(dbState.connectionId)}`)
      dbState.schemas = data.schemas || []
      const firstSchema = dbState.schemas.find((schema) => schema.tables?.length) || dbState.schemas[0]
      dbState.selectedSchema = firstSchema?.name || ''
      dbState.selectedTable = firstSchema?.tables?.[0]?.name || ''
      if (dbState.selectedTable) await loadDbTablePreview(true)
    } catch (error) {
      notify(`数据库结构加载失败：${(error as Error).message}`, 'error')
    } finally {
      dbState.schemaBusy = false
    }
  }

  async function onDbConnectionChange() {
    await loadDbSchema()
  }

  async function onDbSchemaChange() {
    dbState.selectedTable = dbSchemaTables.value[0]?.name || ''
    await loadDbTablePreview(true)
  }

  async function loadDbTablePreview(reset = false) {
    if (!dbState.connectionId || !dbState.selectedTable) return
    if (reset) dbState.offset = 0
    dbState.tableBusy = true
    try {
      const params = new URLSearchParams({
        connectionId: dbState.connectionId,
        table: dbState.selectedTable,
        schema: dbState.selectedSchema,
        limit: String(dbState.limit),
        offset: String(dbState.offset),
      })
      const data = await requestJson<{ columns?: string[]; rows?: Array<Record<string, unknown>>; total?: number; limit?: number; offset?: number }>(
        `/structured-db/table?${params.toString()}`,
      )
      dbState.columns = data.columns || []
      dbState.rows = data.rows || []
      dbState.totalRows = Number(data.total || 0)
      dbState.limit = Number(data.limit || dbState.limit)
      dbState.offset = Number(data.offset || 0)
    } catch (error) {
      notify(`表数据预览失败：${(error as Error).message}`, 'error')
    } finally {
      dbState.tableBusy = false
    }
  }

  function changeDbPreviewPage(direction: number) {
    const nextOffset = dbState.offset + direction * dbState.limit
    dbState.offset = Math.max(0, Math.min(nextOffset, Math.max(0, dbState.totalRows - 1)))
    loadDbTablePreview(false)
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
      if (selectedChunkFileId.value && !files.value.some((file) => file.fileId === selectedChunkFileId.value)) selectedChunkFileId.value = ''
      if (!firstFile) {
        selectedPreviewFileId.value = ''
        previewModalOpen.value = false
      }
      syncSearchTexts()
    } catch (error) {
      notify(`文件列表加载失败：${(error as Error).message}`, 'error')
    }
  }

  async function loadFileManager() {
    fileManagerState.busy = true
    try {
      const data = await requestJson<{
        sourceKbId?: string
        standardsKbId?: string
        wellCount?: number
        documentCount?: number
        wells?: WellGroup[]
        standards?: { documents?: WellDocument[]; groups?: StandardGroup[]; documentCount?: number }
        unmatched?: WellDocument[]
      }>('/file-manager/wells')
      fileManagerState.wells = data.wells || []
      fileManagerState.standards = data.standards?.documents || []
      fileManagerState.standardGroups = normalizeStandardGroups(data.standards?.groups, fileManagerState.standards)
      fileManagerState.unmatched = data.unmatched || []
      fileManagerState.sourceKbId = data.sourceKbId || '钻井设计资料'
      fileManagerState.standardsKbId = data.standardsKbId || ''
      fileManagerState.wellCount = Number(data.wellCount || fileManagerState.wells.length || 0)
      fileManagerState.documentCount = Number(
        data.documentCount || fileManagerState.wells.reduce((sum, well) => sum + Number(well.documentCount || 0), 0),
      )
      if (!fileManagerState.wells.some((well) => well.wellId === fileManagerState.selectedWellId)) {
        fileManagerState.selectedWellId = fileManagerState.wells[0]?.wellId || ''
      }
      const managedDocs = fileManagerState.wells.flatMap((well) => well.categories.flatMap((category) => category.documents))
      const allManagerDocs = [...managedDocs, ...fileManagerState.standards]
      const currentManagedDocExists = allManagerDocs.some((doc) => doc.kbId === activePreviewKbId.value && doc.fileId === selectedPreviewFileId.value)
      if (!currentManagedDocExists) {
        const selectedWellDocs =
          fileManagerState.wells
            .find((well) => well.wellId === fileManagerState.selectedWellId)
            ?.categories.flatMap((category) => category.documents) || []
        const firstDoc = selectedWellDocs[0] || managedDocs[0] || fileManagerState.standards[0]
        if (firstDoc) openManagedFilePreview(firstDoc)
      }
      fileManagerState.loaded = true
    } catch (error) {
      notify(`文件管理数据加载失败：${(error as Error).message}`, 'error')
    } finally {
      fileManagerState.busy = false
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

  function filenameKey(name?: string) {
    return String(name || '').trim().toLowerCase()
  }

  function uploadDuplicateMessage() {
    const selectedNames = new Map<string, string>()
    const repeatedNames: string[] = []
    const repeatedKeys = new Set<string>()
    for (const file of uploadState.files) {
      const key = filenameKey(file.name)
      if (!key) continue
      if (selectedNames.has(key) && !repeatedKeys.has(key)) {
        repeatedKeys.add(key)
        repeatedNames.push(file.name)
      } else {
        selectedNames.set(key, file.name)
      }
    }
    if (repeatedNames.length) {
      return `本次选择中包含重复文件名：${repeatedNames.join('、')}。已取消上传，请保留一个后再试。`
    }

    const existingNames = new Set(files.value.map((file) => filenameKey(file.fileName)).filter(Boolean))
    const conflicts: string[] = []
    const conflictKeys = new Set<string>()
    for (const file of uploadState.files) {
      const key = filenameKey(file.name)
      if (key && existingNames.has(key) && !conflictKeys.has(key)) {
        conflictKeys.add(key)
        conflicts.push(file.name)
      }
    }
    if (conflicts.length) {
      return `知识库中已存在同名文件：${conflicts.join('、')}。已取消上传，请重命名后再试。`
    }
    return ''
  }

  async function uploadFiles() {
    if (!selectedKbId.value || !uploadState.files.length) {
      notify('请选择知识库和待上传文件', 'error')
      return
    }
    const duplicateMessage = uploadDuplicateMessage()
    if (duplicateMessage) {
      uploadState.message = duplicateMessage
      notify(duplicateMessage, 'error')
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
      if (parseResult.failed.length) {
        const detail = parseResult.failed.slice(0, 3).map((fileId) => `${fileId}: ${parseResult.errors[fileId] || '解析失败'}`).join('；')
        throw new Error(`${parseResult.failed.length} 个文件解析失败${detail ? `：${detail}` : ''}`)
      }
      if (parseResult.pending.length) {
        await loadFiles()
        uploadState.message = `仍有 ${parseResult.pending.length} 个文件在后台解析，完成后可在文件列表中重新触发索引`
        notify(uploadState.message, 'info')
        return
      }
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
    const errors: Record<string, string> = {}
    const retryCounts: Record<string, number> = {}
    const maxAttempts = Number.isFinite(PARSE_POLL_MAX_ATTEMPTS) && PARSE_POLL_MAX_ATTEMPTS > 0 ? PARSE_POLL_MAX_ATTEMPTS : 9600
    const retryLimit = Number.isFinite(PARSE_STATUS_RETRY_LIMIT) && PARSE_STATUS_RETRY_LIMIT > 0 ? PARSE_STATUS_RETRY_LIMIT : 5
    for (let i = 0; i < maxAttempts && pending.size; i += 1) {
      await Promise.all(
        Array.from(pending).map(async (fileId) => {
          try {
            const res = await fetch(apiUrl('/pdf/status', { kbId: selectedKbId.value, fileId }))
            if (!res.ok) throw new Error(`状态接口异常：${res.status}`)
            const data = await res.json()
            retryCounts[fileId] = 0
            const progress = Math.max(0, Math.min(100, Number(data.progress || 0)))
            if (data.status === 'ready') {
              ready.add(fileId)
              pending.delete(fileId)
              setFileTask(fileId, { phase: 'parse', status: 'done', message: '解析完成', progress: 100 })
            } else if (data.status === 'error') {
              failed.add(fileId)
              pending.delete(fileId)
              const errorMessage = String(data.error || '解析失败')
              errors[fileId] = errorMessage
              setFileTask(fileId, { phase: 'parse', status: 'failed', message: errorMessage, progress })
            } else if (data.status === 'parsing') {
              setFileTask(fileId, { phase: 'parse', status: 'running', message: '正在解析', progress })
            } else {
              setFileTask(fileId, { phase: 'parse', status: 'queued', message: '等待解析', progress })
            }
          } catch (error) {
            retryCounts[fileId] = (retryCounts[fileId] || 0) + 1
            const message = (error as Error).message || '状态获取失败'
            if (retryCounts[fileId] >= retryLimit) {
              failed.add(fileId)
              pending.delete(fileId)
              errors[fileId] = message
              setFileTask(fileId, { phase: 'parse', status: 'failed', message, progress: 0 })
            } else {
              const progress = fileTaskProgress(fileId) ?? 0
              setFileTask(fileId, {
                phase: 'parse',
                status: 'running',
                message: `状态暂时不可用，正在重试 ${retryCounts[fileId]}/${retryLimit}`,
                progress,
              })
            }
          }
        }),
      )
      if (pending.size) await new Promise((resolve) => window.setTimeout(resolve, PARSE_POLL_INTERVAL_MS))
    }
    pending.forEach((fileId) => {
      errors[fileId] = '等待窗口已结束，后台可能仍在继续解析，请稍后刷新状态'
      setFileTask(fileId, {
        phase: 'parse',
        status: 'running',
        message: errors[fileId],
        progress: fileTaskProgress(fileId) ?? 0,
      })
    })
    return { ready: Array.from(ready), failed: Array.from(failed), pending: Array.from(pending), errors }
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
        const detail = parseResult.failed.slice(0, 3).map((fileId) => `${fileId}: ${parseResult.errors[fileId] || '解析失败'}`).join('；')
        notify(`重新解析完成 ${parseResult.ready.length}/${targetFileIds.length}，失败 ${parseResult.failed.length} 个${detail ? `，${detail}` : ''}`, 'error')
      } else if (parseResult.pending.length) {
        notify(`已完成 ${parseResult.ready.length}/${targetFileIds.length}，仍有 ${parseResult.pending.length} 个文件在后台解析`, 'info')
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
    const kbId = activePreviewKbId.value
    if (!kbId || !selectedPreviewFileId.value) return
    try {
      const response = await fetch(
        apiUrl('/pdf/page', {
          kbId,
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
    const question = searchState.query.trim()
    if (!question) {
      notify('请输入检索问题', 'error')
      return
    }
    if ((searchState.mode === 'vector' || searchState.mode === 'hybrid') && !selectedKbId.value) {
      notify('请选择知识库', 'error')
      return
    }
    if ((searchState.mode === 'sql' || searchState.mode === 'hybrid') && !dbState.connectionId) {
      notify('请选择数据库连接', 'error')
      return
    }
    if (searchState.mode === 'agent' && !selectedKbId.value && !dbState.connectionId) {
      notify('请至少选择知识库或数据库连接', 'error')
      return
    }

    searchState.busy = true
    searchState.results = []
    searchState.answer = ''
    searchState.citations = []
    searchState.sqlResult = null
    searchState.agentTrace = []
    searchState.usedRetrieval = false
    searchState.usedSql = false
    try {
      if (searchState.mode === 'vector') {
        const data = await requestJson<{ results?: SearchResult[]; data?: SearchResult[] }>('/index/search', {
          method: 'POST',
          body: JSON.stringify({
            kbId: selectedKbId.value,
            fileId: searchFileId.value || undefined,
            query: question,
            k: searchState.k,
          }),
        })
        searchState.results = data.results || data.data || []
      } else {
        const data = await requestJson<UnifiedQueryResponse>('/query', {
          method: 'POST',
          body: JSON.stringify({
            mode: searchState.mode,
            message: question,
            kbId: selectedKbId.value || undefined,
            fileId: searchFileId.value || undefined,
            connectionId: dbState.connectionId || undefined,
            sqlLimit: searchState.sqlLimit,
          }),
        })
        searchState.answer = data.answer || ''
        searchState.citations = data.citations || []
        searchState.sqlResult = data.sqlResult || null
        searchState.agentTrace = data.agentTrace || []
        searchState.usedRetrieval = Boolean(data.usedRetrieval)
        searchState.usedSql = Boolean(data.usedSql)
      }
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
    const kbId = activePreviewKbId.value
    if (!kbId || !selectedPreviewFileId.value) return
    previewState.busy = true
    previewState.content = ''
    previewState.sheets = {}
    try {
      const file = previewFile.value

      const contentRes = await fetch(apiUrl('/kb/file/content', { kbId, fileId: selectedPreviewFileId.value }))
      if (contentRes.ok) {
        const contentData = await contentRes.json()
        previewState.content = String(contentData.content || '')
      }

      if (file?.type === 'image') {
        return
      }

      const table = await fetch(apiUrl('/kb/file/dataframe', { kbId, fileId: selectedPreviewFileId.value }))
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

  function changePdfPreviewPage(offset: number) {
    const lastPage = Math.max(1, Number(previewFile.value?.pageCount || 1))
    previewState.page = Math.min(lastPage, Math.max(1, previewState.page + offset))
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
        old_img_name: item.old_img_name || item.base_img_path || item.imagePath || item.img_name,
        base_img_path: item.base_img_path || item.imagePath || item.img_name,
        imagePath: item.imagePath || item.img_name,
      }))
      selectedImageSearchText.value = fileDisplayName(files.value.find((file) => file.fileId === selectedImageFileId.value))
    } catch (error) {
      notify(`图片列表加载失败：${(error as Error).message}`, 'error')
    } finally {
      imageState.busy = false
    }
  }

  function chunkTypeLabel(type?: string) {
    const normalized = String(type || '').toLowerCase()
    if (normalized === 'image') return '图像片段'
    if (normalized === 'table') return '表格片段'
    return '文本片段'
  }

  function chunkPreview(content: string) {
    const text = String(content || '').trim()
    return text.length > 520 ? `${text.slice(0, 520)}...` : text
  }

  function chunkMetadataRows(item: KnowledgeChunk) {
    return Object.entries(item.metadata || {})
      .filter(([, value]) => value !== undefined && value !== null && value !== '')
      .slice(0, 8)
      .map(([label, value]) => ({ label, value: sourceStringValue(value) }))
  }

  function chunkImageSrc(item: KnowledgeChunk) {
    if (!item.imagePath) return ''
    return apiUrl('/pdf/images', { kbId: selectedKbId.value, fileId: item.fileId, imagePath: item.imagePath })
  }

  function openChunkSource(item: KnowledgeChunk) {
    if (!item.fileId) return
    openFilePreview(item.fileId)
  }

  async function loadChunkStats() {
    if (!selectedKbId.value) {
      chunkState.stats = { total: 0, text: 0, image: 0, files: 0 }
      return
    }
    try {
      const data = await requestJson<ChunkStats>(`/index/chunks/stats?kbId=${encodeURIComponent(selectedKbId.value)}`)
      chunkState.stats = {
        total: Number(data.total || 0),
        text: Number(data.text || 0),
        image: Number(data.image || 0),
        files: Number(data.files || 0),
        byFile: data.byFile || [],
      }
    } catch (error) {
      notify(`知识块统计加载失败：${(error as Error).message}`, 'error')
    }
  }

  async function loadChunks(reset = false) {
    if (!selectedKbId.value) {
      chunkState.chunks = []
      chunkState.total = 0
      return
    }
    if (reset) chunkState.offset = 0
    chunkState.busy = true
    try {
      const query = new URLSearchParams({
        kbId: selectedKbId.value,
        limit: String(chunkState.limit),
        offset: String(chunkState.offset),
      })
      if (selectedChunkFileId.value) query.set('fileId', selectedChunkFileId.value)
      if (chunkState.query.trim()) query.set('q', chunkState.query.trim())
      const data = await requestJson<{ chunks?: KnowledgeChunk[]; total?: number; limit?: number; offset?: number }>(`/index/chunks?${query.toString()}`)
      chunkState.chunks = data.chunks || []
      chunkState.total = Number(data.total || 0)
      chunkState.limit = Number(data.limit || chunkState.limit)
      chunkState.offset = Number(data.offset || 0)
    } catch (error) {
      notify(`知识块加载失败：${(error as Error).message}`, 'error')
    } finally {
      chunkState.busy = false
    }
  }

  async function refreshChunks(reset = true) {
    await Promise.all([loadChunkStats(), loadChunks(reset)])
  }

  function resetChunkFilters() {
    selectedChunkFileId.value = ''
    chunkState.query = ''
    refreshChunks(true)
  }

  function changeChunkPage(direction: number) {
    const nextOffset = chunkState.offset + direction * chunkState.limit
    chunkState.offset = Math.max(0, Math.min(nextOffset, Math.max(0, chunkState.total - 1)))
    loadChunks(false)
  }

  function imageSrc(item: ImageItem) {
    const img = item.old_img_name || item.base_img_path || item.imagePath || item.img_name || ''
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
          old_img_name: item.old_img_name || item.base_img_path || item.imagePath || item.img_name,
          img_name: item.img_name || item.imagePath,
          summary: item.summary || '',
        }),
      })
      notify('图片名称/描述已保存并重建索引', 'success')
      await loadImages()
    } catch (error) {
      notify(`保存失败：${(error as Error).message}`, 'error')
    } finally {
      imageState.saving = false
    }
  }

  function onExtractFileChange(event: Event) {
    extractState.file = ((event.target as HTMLInputElement).files || [])[0] || null
  }

  function clearExtractSelection() {
    extractState.file = null
    if (extractInputRef.value) extractInputRef.value.value = ''
  }

  function applyExtractionTemplate() {
    if (extractState.mode === '预置模板 (油气领域)') {
      extractState.instruction = extractionTemplates[extractState.templateKey] || extractState.instruction
    }
  }

  function cloneExtractionRows(rows: ExtractionRow[]) {
    return rows.map((row) => ({ ...row }))
  }

  function normalizeExtractionRows(rows: unknown) {
    if (!Array.isArray(rows)) return [] as ExtractionRow[]
    return rows
      .filter((row): row is ExtractionRow => Boolean(row) && typeof row === 'object' && !Array.isArray(row))
      .map((row) => ({ ...row }))
  }

  function extractionCellValue(value: unknown) {
    if (value === undefined || value === null) return ''
    if (typeof value === 'string') return value
    if (typeof value === 'number' || typeof value === 'boolean') return String(value)
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }

  function sanitizeExtractionFilename(name: string) {
    return String(name || '')
      .replace(/[\\/:*?"<>|]/g, '')
      .trim()
  }

  function buildExtractionOutputFilename() {
    const ext = extractState.outputFormat === 'csv' ? 'csv' : extractState.outputFormat === 'excel' ? 'xlsx' : 'txt'
    const customName = sanitizeExtractionFilename(extractState.customFilename)
    if (customName) {
      return customName.toLowerCase().endsWith(`.${ext}`) ? customName : `${customName}.${ext}`
    }
    return `extracted_${Math.floor(Date.now() / 1000)}.${ext}`
  }

  function extractionFilenameVariant(filename: string, index: number) {
    const cleanName = sanitizeExtractionFilename(filename)
    const dotIndex = cleanName.lastIndexOf('.')
    if (dotIndex > 0) {
      return `${cleanName.slice(0, dotIndex)}_${index}${cleanName.slice(dotIndex)}`
    }
    return `${cleanName}_${index}`
  }

  async function checkExtractionFilenameConflict(filename: string) {
    return requestJson<ExtractionFilenameCheckResponse>(
      `/extraction/check_filename?kbId=${encodeURIComponent(selectedKbId.value)}&filename=${encodeURIComponent(filename)}`,
    )
  }

  async function resolveUniqueExtractionFilename(filename: string) {
    let candidate = filename
    for (let index = 1; index <= 20; index += 1) {
      const response = await checkExtractionFilenameConflict(candidate)
      if (!response.exists) return candidate
      candidate = extractionFilenameVariant(filename, index)
    }
    return `${filename}_${Date.now()}`
  }

  function resetExtractionDraft() {
    extractState.extractedRows = cloneExtractionRows(normalizeExtractionRows(extractState.result?.data))
    extractState.resultDirty = false
  }

  function onExtractionCellInput(rowIndex: number, column: string, event: Event) {
    const row = extractState.extractedRows[rowIndex]
    if (!row) return
    row[column] = extractionCellValue((event.target as HTMLInputElement).value)
    extractState.resultDirty = true
  }

  async function loadExtractionContent(jobId: string) {
    if (!jobId) return
    const requestedJobId = jobId
    extractState.sourceContentLoading = true
    try {
      const data = await requestJson<ExtractionContentResponse>(`/extraction/content?jobId=${encodeURIComponent(jobId)}`)
      if (extractState.jobId !== requestedJobId) return
      extractState.sourceContent = String(data.content || '')
      extractState.sourcePages = Array.isArray(data.pages) ? data.pages : []
      extractState.sourceScope = String(data.scope || '')
      extractState.sourceFragmentTitle = String(data.fragmentTitle || '')
    } catch (error) {
      if (extractState.jobId !== requestedJobId) return
      extractState.sourceContent = `原文内容加载失败：${error instanceof Error ? error.message : '未知错误'}`
      extractState.sourcePages = []
      extractState.sourceScope = ''
      extractState.sourceFragmentTitle = ''
    } finally {
      if (extractState.jobId !== requestedJobId) return
      extractState.sourceContentLoading = false
    }
  }

  function syncExtractionResult(data: ExtractionStatus) {
    extractState.result = data
    extractState.extractedRows = cloneExtractionRows(normalizeExtractionRows(data.data))
    extractState.resultDirty = false
  }

  async function saveExtractionResult() {
    if (!extractState.jobId) {
      notify('没有可保存的提取任务', 'error')
      return
    }
    if (!extractState.extractedRows.length) {
      notify('当前没有可保存的提取内容', 'error')
      return
    }

    extractState.saving = true
    try {
      const response = await requestJson<{ ok?: boolean; updated_path?: string }>('/extraction/update_result', {
        method: 'POST',
        body: JSON.stringify({ jobId: extractState.jobId, data: extractState.extractedRows }),
      })
      extractState.resultDirty = false
      extractState.result = extractState.result ? { ...extractState.result, data: cloneExtractionRows(extractState.extractedRows) } : null
      notify(`提取内容已更新${response.updated_path ? `：${response.updated_path}` : ''}`, 'success')
    } catch (error) {
      notify(`保存失败：${(error as Error).message}`, 'error')
    } finally {
      extractState.saving = false
    }
  }

  function resetExtractionState() {
    extractState.jobId = ''
    extractState.status = ''
    extractState.progress = 0
    extractState.result = null
    extractState.extractedRows = []
    extractState.sourceContent = ''
    extractState.sourcePages = []
    extractState.sourceScope = ''
    extractState.sourceFragmentTitle = ''
    extractState.sourceContentLoading = false
    extractState.resultDirty = false
    extractState.saving = false
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

    const outputFilename = buildExtractionOutputFilename()
    let overwriteExisting = false
    let finalFilename = outputFilename
    try {
      const conflictCheck = await checkExtractionFilenameConflict(outputFilename)
      if (conflictCheck.exists) {
        const conflictNames = (conflictCheck.conflicts || []).map((item) => item.fileName || '').filter(Boolean).join('、') || outputFilename
        const shouldOverwrite = window.confirm(`知识库中已存在同名文件：${conflictNames}。点击“确定”将替换已有文件，点击“取消”将自动修改文件名并停止本次提取。`)
        if (shouldOverwrite) {
          overwriteExisting = true
        } else {
          finalFilename = await resolveUniqueExtractionFilename(outputFilename)
          extractState.customFilename = finalFilename
          notify(`已自动修改文件名为：${finalFilename}，请再次点击开始提取`, 'info')
          return
        }
      }
    } catch (error) {
      notify(`文件名检查失败：${(error as Error).message}`, 'error')
      return
    }

    extractState.busy = true
    extractState.result = null
    extractState.extractedRows = []
    extractState.sourceContent = ''
    extractState.sourcePages = []
    extractState.sourceScope = ''
    extractState.sourceFragmentTitle = ''
    extractState.resultDirty = false
    try {
      const form = new FormData()
      form.append('file', extractState.file)
      form.append('instruction', extractState.instruction)
      form.append('kb_id', selectedKbId.value || '')
      form.append('output_format', extractState.outputFormat)
      form.append('custom_filename', finalFilename)
      form.append('parse_method', extractState.parseMethod)
      form.append('overwrite_existing', String(overwriteExisting))
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
    const existing = new Set(preprocessState.sourceFiles.map((file) => preprocessSourceFileKey(file)))
    const appended = selectedFiles.filter((file) => !existing.has(preprocessSourceFileKey(file)))
    preprocessState.sourceFiles = [...preprocessState.sourceFiles, ...appended]
    preprocessState.methodProgress = {}
    preprocessState.methodStatus = {}
    if (preprocessInputRef.value) preprocessInputRef.value.value = ''
  }

  function preprocessSourceFileKey(file: File) {
    return `${file.name}:${file.size}:${file.lastModified}`
  }

  function triggerPreprocessFilePicker() {
    if (preprocessState.uploading) return
    preprocessInputRef.value?.click()
  }

  function removePreprocessSourceFile(index: number) {
    if (preprocessState.uploading) return
    const removed = preprocessState.sourceFiles[index]
    preprocessState.sourceFiles = preprocessState.sourceFiles.filter((_, currentIndex) => currentIndex !== index)
    if (removed) {
      const removedKey = preprocessSourceFileKey(removed)
      preprocessState.uploadedSourceFileKeys = preprocessState.uploadedSourceFileKeys.filter((key) => key !== removedKey)
    }
    if (preprocessInputRef.value) preprocessInputRef.value.value = ''
  }

  function preprocessMethodName(methodId: string) {
    return preprocessMethodById.value[methodId]?.name || methodId
  }

  function preprocessOutputSuffix(job: PreprocessJobState | null | undefined) {
    const outputFile = job?.report?.outputFile && typeof job.report.outputFile === 'object' ? (job.report.outputFile as Record<string, unknown>) : {}
    const explicit = String(job?.suffix || outputFile.suffix || '').trim().toLowerCase()
    if (explicit) return explicit.replace(/^\./, '')
    const name = String(job?.fileName || job?.report?.sourceFileName || '')
    const match = name.match(/\.([^.]+)$/)
    return match?.[1] ? match[1].toLowerCase() : ''
  }

  function openPreprocessAlgorithmDialog(methodId: string) {
    const method = preprocessMethodById.value[methodId]
    if (!method?.algorithms?.length) return
    const dialogWidth = 380
    const dialogHeight = 330
    preprocessAlgorithmDialog.methodId = methodId
    preprocessAlgorithmDialog.draftAlgorithmId =
      preprocessState.selectedAlgorithms[methodId] || method.defaultAlgorithm || method.algorithms[0]?.id || ''
    preprocessAlgorithmDialog.left = Math.max(12, Math.round((window.innerWidth - dialogWidth) / 2))
    preprocessAlgorithmDialog.top = Math.max(12, Math.round((window.innerHeight - dialogHeight) / 2))
    preprocessAlgorithmDialog.open = true
  }

  function closePreprocessAlgorithmDialog() {
    preprocessAlgorithmDialog.open = false
    preprocessAlgorithmDialog.dragging = false
  }

  function savePreprocessAlgorithm() {
    const method = preprocessAlgorithmDialogMethod.value
    const algorithmId = preprocessAlgorithmDialog.draftAlgorithmId
    if (!method?.algorithms?.some((algorithm) => algorithm.id === algorithmId)) return
    preprocessState.selectedAlgorithms[method.id] = algorithmId
    closePreprocessAlgorithmDialog()
  }

  function startPreprocessAlgorithmDialogDrag(event: PointerEvent) {
    if (event.button !== 0) return
    preprocessAlgorithmDialog.dragging = true
    preprocessAlgorithmDialog.dragOffsetX = event.clientX - preprocessAlgorithmDialog.left
    preprocessAlgorithmDialog.dragOffsetY = event.clientY - preprocessAlgorithmDialog.top
    const dragHandle = event.currentTarget as HTMLElement | null
    dragHandle?.setPointerCapture?.(event.pointerId)
  }

  function movePreprocessAlgorithmDialog(event: PointerEvent) {
    if (!preprocessAlgorithmDialog.dragging) return
    const dialogWidth = Math.min(380, window.innerWidth - 16)
    const dialogHeight = Math.min(330, window.innerHeight - 16)
    preprocessAlgorithmDialog.left = Math.max(8, Math.min(window.innerWidth - dialogWidth - 8, event.clientX - preprocessAlgorithmDialog.dragOffsetX))
    preprocessAlgorithmDialog.top = Math.max(8, Math.min(window.innerHeight - dialogHeight - 8, event.clientY - preprocessAlgorithmDialog.dragOffsetY))
  }

  function stopPreprocessAlgorithmDialogDrag() {
    preprocessAlgorithmDialog.dragging = false
  }

  function addPreprocessMethod(methodId: string) {
    if (!methodId || preprocessState.selectedMethods.includes(methodId)) return
    const method = preprocessMethodById.value[methodId]
    const isGrouped = String(method?.metadata?.inputMode || '') === 'grouped_files'
    if (isGrouped) {
      preprocessState.selectedMethods = [methodId]
    } else if (preprocessGroupedMethod.value) {
      preprocessState.selectedMethods = [methodId]
    } else {
      preprocessState.selectedMethods.push(methodId)
    }
    preprocessState.methodProgress[methodId] = 0
    preprocessState.methodStatus[methodId] = '等待处理'
    if (method?.algorithms?.length) {
      preprocessState.selectedAlgorithms[methodId] = method.defaultAlgorithm || method.algorithms[0]?.id || ''
    }
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
    delete preprocessState.selectedAlgorithms[methodId]
    if (preprocessAlgorithmDialog.methodId === methodId) closePreprocessAlgorithmDialog()
  }

  function onPreprocessPreviewToggle(event: Event) {
    preprocessState.previewOpen = Boolean((event.target as HTMLDetailsElement).open)
  }

  async function uploadPreprocessSource() {
    const filesToUpload = preprocessPendingSourceFiles.value
    if (!preprocessState.sourceFiles.length) {
      notify('请选择至少一个需要上传的结构化文件', 'error')
      return
    }
    if (!filesToUpload.length) {
      notify('当前选择列表中的文件都已上传，可点击 + 继续添加新文件', 'error')
      return
    }
    preprocessState.uploading = true
    try {
      const uploadResults = await Promise.all(
        filesToUpload.map(async (file) => {
          try {
            const form = new FormData()
            form.append('file', file)
            const data = await requestJson<PreprocessJob>('/preprocess/upload', { method: 'POST', body: form })
            return {
              ok: true as const,
              sourceKey: preprocessSourceFileKey(file),
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
      const successfulUploads = uploadResults.filter(
        (result): result is { ok: true; sourceKey: string; job: PreprocessJobState } => result.ok,
      )
      const uploadedJobs = successfulUploads.map((result) => result.job)
      const uploadedSourceKeys = successfulUploads.map((result) => result.sourceKey)
      const failedMessages = uploadResults.filter((result): result is { ok: false; message: string } => !result.ok).map((result) => result.message)

      const existingJobIds = new Set(preprocessState.jobs.map((job) => String(job.jobId || '')).filter(Boolean))
      const appendedJobs = uploadedJobs.filter((job) => !existingJobIds.has(String(job.jobId || '')))
      preprocessState.jobs = [...preprocessState.jobs, ...appendedJobs]
      const firstUploadedJob = uploadedJobs[0]
      if (firstUploadedJob) selectPreprocessJob(firstUploadedJob.jobId || '')
      preprocessState.uploadedSourceFileKeys = Array.from(new Set([...preprocessState.uploadedSourceFileKeys, ...uploadedSourceKeys]))

      if (failedMessages.length && uploadedJobs.length) {
        notify(`已上传 ${uploadedJobs.length} 个文件，${failedMessages.length} 个文件上传失败`, 'error')
      } else if (uploadedJobs.length) {
        notify(`已上传 ${uploadedJobs.length} 个文件到预处理工作台`, 'success')
      } else {
        throw new Error(failedMessages[0] || '上传失败')
      }

      if (preprocessInputRef.value) preprocessInputRef.value.value = ''
    } catch (error) {
      notify(`上传失败：${(error as Error).message}`, 'error')
    } finally {
      preprocessState.uploading = false
    }
  }

  async function pollExtraction() {
    for (let i = 0; i < 240 && extractState.jobId; i += 1) {
      const data = await requestJson<ExtractionStatus>(`/extraction/status?jobId=${encodeURIComponent(extractState.jobId)}`)
      extractState.status = String(data.status || '')
      extractState.progress = Number(data.progress || 0)
      if (['done', 'completed', 'error', 'failed'].includes(extractState.status)) {
        syncExtractionResult(data)
        if (['error', 'failed'].includes(extractState.status)) notify(String(data.error || '提取任务失败'), 'error')
        else {
          await loadExtractionContent(extractState.jobId)
          await loadFiles()
          notify('知识提取完成，原文和提取结果已加载，可直接编辑后保存', 'success')
        }
        return
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
    }
    extractState.status = 'timeout'
    notify('知识提取等待超时（前端已停止轮询，后台可能仍在继续执行），请稍后刷新状态', 'error')
  }

  async function runPreprocess() {
    const jobsToRun = preprocessState.jobs.filter((job) => job.status !== 'done' && String(job.jobId || ''))
    if (!preprocessState.jobs.length) {
      notify('请先上传至少一个文件到预处理工作台', 'error')
      return
    }
    if (!jobsToRun.length) {
      notify('当前没有待处理文件；如需重新处理，请先重新上传文件', 'error')
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
      const runningJobIds = new Set(jobsToRun.map((job) => String(job.jobId || '')))
      preprocessState.jobs = preprocessState.jobs.map((job) =>
        runningJobIds.has(String(job.jobId || ''))
          ? {
              ...job,
              status: 'running',
              error: '',
            }
          : job,
      )
      preprocessState.selectedMethods.forEach((methodId) => {
        preprocessState.methodProgress[methodId] = 0
        preprocessState.methodStatus[methodId] = '等待处理'
      })
      preprocessState.selectedMethods.forEach((methodId) => {
        preprocessState.methodProgress[methodId] = 12
        preprocessState.methodStatus[methodId] = '处理中'
      })

      const groupedMethod = preprocessGroupedMethod.value
      if (groupedMethod) {
        const inputJobs = preprocessState.jobs.filter((job) => String(job.jobId || '') && !Boolean(job.groupedOutput))
        const inputJobIds = new Set(inputJobs.map((job) => String(job.jobId || '')))
        if (!inputJobs.length) throw new Error('请先上传该方法需要的输入文件')
        const report = await requestJson<PreprocessReport>('/preprocess/workbench/grouped/run', {
          method: 'POST',
          body: JSON.stringify({
            method: groupedMethod.id,
            jobs: inputJobs.map((job) => ({
              jobId: String(job.jobId || ''),
              role: typeof job.role === 'string' ? job.role : '',
            })),
            config: {},
          }),
        })
        const outputJobsPayload = Array.isArray(report.outputJobs) ? (report.outputJobs as PreprocessJob[]) : []
        const outputJobs = await Promise.all(
          outputJobsPayload.map(async (outputJob) => {
            const outputJobId = String(outputJob.jobId || '')
            let rows: Array<Record<string, unknown>> = []
            if (outputJobId) {
              try {
                const data = await requestJson<{ rows: Array<Record<string, unknown>>; previewUnsupported?: boolean }>(
                  `/preprocess/workbench/dataframe?jobId=${encodeURIComponent(outputJobId)}&limit=100`,
                )
                rows = data.rows || []
              } catch {
                rows = []
              }
            }
            return {
              ...outputJob,
              jobId: outputJobId,
              fileName: String(outputJob.fileName || '流程产物'),
              status: 'done' as const,
              report: {
                ...report,
                jobId: outputJobId,
                sourceFileName: outputJob.fileName,
                outputFile: outputJob,
                groupedOutput: true,
              },
              rows,
              groupedOutput: true,
            } satisfies PreprocessJobState
          }),
        )
        if (!outputJobs.length) throw new Error('预处理完成，但没有发现可展示的流程产物文件')
        preprocessState.jobs = [
          ...preprocessState.jobs
            .filter((job) => !Boolean(job.groupedOutput))
            .map((job) =>
              inputJobIds.has(String(job.jobId || ''))
                ? {
                    ...job,
                    status: 'uploaded' as const,
                    error: '',
                  }
                : job,
            ),
          ...outputJobs,
        ]
        const activeOutput = outputJobs.find((job) => job.rows?.length) || outputJobs[0]
        if (!activeOutput) throw new Error('预处理完成，但没有发现可展示的流程产物文件')
        preprocessState.report = activeOutput.report || report
        preprocessState.rows = activeOutput.rows || []
        preprocessState.previewOpen = true
        selectPreprocessJob(String(activeOutput.jobId || ''))
        preprocessState.selectedMethods.forEach((methodId) => {
          preprocessState.methodProgress[methodId] = 100
          preprocessState.methodStatus[methodId] = '完成'
        })
        notify(`${groupedMethod.name || '组合预处理'}完成，已生成 ${outputJobs.length} 个流程产物文件`, 'success')
        return
      }

      const results = await Promise.all(
        jobsToRun.map(async (job) => {
          try {
            const jobId = String(job.jobId || '')
            const report = await requestJson<PreprocessReport>('/preprocess/workbench/run', {
              method: 'POST',
              body: JSON.stringify({
                jobId,
                methods: preprocessState.selectedMethods,
                algorithmSelections: preprocessState.selectedAlgorithms,
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

      const resultByJobId = Object.fromEntries(jobsToRun.map((job, index) => [String(job.jobId || ''), results[index]]))
      const nextJobs = preprocessState.jobs.map((job) => {
        const result = resultByJobId[String(job.jobId || '')]
        if (!result) return job
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
    const jobsToSave = preprocessDoneJobs.value
    if (!jobsToSave.length) {
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
      let destinationKbId = preprocessState.saveMode === 'existing' ? preprocessState.targetKbId : ''
      const savedByJobId: Record<string, Record<string, unknown>> = {}

      for (const job of jobsToSave) {
        const jobId = String(job.jobId || '')
        const payload: Record<string, unknown> = {
          jobId,
          rebuildIndex: preprocessState.rebuildIndex,
        }
        if (destinationKbId) {
          payload.targetKbId = destinationKbId
        } else {
          payload.newKbName = preprocessState.newKbName
        }

        const saved = await requestJson<Record<string, unknown>>('/preprocess/workbench/store', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        savedByJobId[jobId] = saved
        destinationKbId = String(saved.kbId || destinationKbId)
      }

      preprocessState.jobs = preprocessState.jobs.map((job) => {
        const saved = savedByJobId[String(job.jobId || '')]
        if (!saved) return job
        return {
          ...job,
          report: {
            ...(job.report || {}),
            savedToKb: saved,
          },
        }
      })
      const activeJob = preprocessState.jobs.find((job) => job.jobId === preprocessState.previewJobId) || preprocessState.job
      preprocessState.job = activeJob || null
      preprocessState.report = activeJob?.report || preprocessState.report

      await loadKbs()
      if (destinationKbId) selectedKbId.value = destinationKbId
      await loadFiles()
      notify(`预处理文件已保存到知识库：${Object.keys(savedByJobId).length}/${jobsToSave.length} 个`, 'success')
    } catch (error) {
      notify(`保存失败：${(error as Error).message}`, 'error')
    } finally {
      preprocessState.saving = false
    }
  }

  async function downloadPreprocessExcel() {
    const jobId = String(preprocessSelectedJob.value?.jobId || preprocessState.report?.jobId || preprocessState.job?.jobId || '')
    if (!jobId) {
      notify('请先完成预处理', 'error')
      return
    }
    try {
      const response = await fetch(apiUrl('/preprocess/workbench/download', { jobId, format: 'xlsx' }))
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data?.error?.message || '下载失败')
      }
      const blob = await response.blob()
      const contentDisposition = response.headers.get('content-disposition') || ''
      const filenameMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/i)
      const encodedFilename = filenameMatch?.[1] || filenameMatch?.[2] || ''
      const filename = encodedFilename ? decodeURIComponent(encodedFilename) : 'preprocessed.xlsx'
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      notify(`下载失败：${(error as Error).message}`, 'error')
    }
  }

  async function downloadPreprocessArtifact(artifact: PreprocessArtifact) {
    const jobId = String(preprocessSelectedJob.value?.jobId || preprocessState.report?.jobId || preprocessState.job?.jobId || '')
    if (!jobId || !artifact.path) {
      notify('请先选择一个已完成的预处理文件', 'error')
      return
    }
    try {
      const response = await fetch(apiUrl('/preprocess/workbench/artifact/download', { jobId, path: artifact.path }))
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data?.error?.message || '下载失败')
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = artifact.name || 'preprocess-artifact'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (error) {
      notify(`下载失败：${(error as Error).message}`, 'error')
    }
  }

  async function loadPreprocessFilePreview(job: PreprocessJobState | null) {
    preprocessState.previewText = ''
    preprocessState.previewError = ''
    preprocessState.previewLoading = false
    if (!job?.jobId) return
    const suffix = preprocessOutputSuffix(job)
    const shouldLoadText = ['md', 'markdown', 'json', 'txt', 'log', 'jsonl', 'yaml', 'yml'].includes(suffix)
    if (!shouldLoadText) return
    preprocessState.previewLoading = true
    try {
      const response = await fetch(apiUrl('/preprocess/workbench/download', { jobId: String(job.jobId), format: 'csv' }))
      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data?.error?.message || '预览加载失败')
      }
      const text = await response.text()
      if (suffix === 'json') {
        try {
          preprocessState.previewText = JSON.stringify(JSON.parse(text), null, 2)
        } catch {
          preprocessState.previewText = text
        }
      } else {
        preprocessState.previewText = text
      }
    } catch (error) {
      preprocessState.previewError = error instanceof Error ? error.message : '预览加载失败'
    } finally {
      preprocessState.previewLoading = false
    }
  }

  function selectPreprocessJob(jobId: string) {
    const matchedJob = preprocessState.jobs.find((job) => job.jobId === jobId)
    if (!matchedJob) return
    preprocessState.previewJobId = jobId
    preprocessState.job = matchedJob
    preprocessState.report = matchedJob.report || null
    preprocessState.rows = matchedJob.rows || []
    loadPreprocessFilePreview(matchedJob)
    preprocessState.previewOpen = true
  }

  function clearPreprocessSelection() {
    preprocessState.sourceFiles = []
    preprocessState.uploadedSourceFileKeys = []
    preprocessState.jobs = []
    preprocessState.job = null
    preprocessState.previewJobId = ''
    preprocessState.report = null
    preprocessState.rows = []
    preprocessState.previewText = ''
    preprocessState.previewLoading = false
    preprocessState.previewError = ''
    preprocessState.previewOpen = false
    preprocessState.jobDetailOpenStates = {}
    preprocessState.selectedAlgorithms = {}
    closePreprocessAlgorithmDialog()
    if (preprocessInputRef.value) preprocessInputRef.value.value = ''
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
    if (kbSubTab.value === 'chunks') await refreshChunks()
  })

  watch(
    detailKbId,
    (kbId) => {
      if (kbId && selectedKbId.value !== kbId) selectedKbId.value = kbId
    },
    { immediate: true },
  )

  watch(selectedPreviewFileId, () => {
    previewState.page = 1
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
      previewKbId.value = selectedKbId.value
      managedPreviewDocument.value = null
      if (!files.value.some((file) => file.fileId === selectedPreviewFileId.value)) {
        selectedPreviewFileId.value = files.value[0]?.fileId || ''
      }
      loadPreview()
      loadImages()
    } else if (tab === 'file-manager') {
      loadFileManager()
    } else if (tab === 'database') {
      loadDbConnections()
      if (dbState.connectionId && !dbState.schemas.length) loadDbSchema()
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
    } else if (tab === 'chunks') {
      refreshChunks()
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
    await loadPreprocessMethods()
    await loadKbs()
    await loadFiles()
    await loadDbConnections()
  })

  return {
    PARSE_POLL_INTERVAL_MS,
    PARSE_POLL_MAX_ATTEMPTS,
    PARSE_STATUS_RETRY_LIMIT,
    API_BASE,
    route,
    router,
    detailKbId,
    isKbDetailPage,
    tabs,
    queryModes,
    activeTab,
    kbs,
    files,
    selectedKbId,
    selectedFileId,
    selectedFileIds,
    fileTaskStates,
    kbSearchQuery,
    createKbExpanded,
    kbUploadExpanded,
    selectedFileSearchText,
    selectedImageSearchText,
    selectedStructuredSearchText,
    searchFileId,
    selectedPreviewFileId,
    selectedImageFileId,
    selectedChunkFileId,
    kbSubTab,
    previewKbId,
    managedPreviewDocument,
    wellSearchQuery,
    standardSearchQuery,
    previewModalOpen,
    previewTab,
    pagePreviewUrl,
    loading,
    toast,
    newKb,
    uploadState,
    uploadInputRef,
    preprocessInputRef,
    extractInputRef,
    searchState,
    chatState,
    previewState,
    imageState,
    chunkState,
    fileManagerState,
    dbState,
    extractState,
    preprocessState,
    preprocessMethodMenuOpen,
    preprocessMethodMenuStyle,
    preprocessAlgorithmDialog,
    extractionTemplates,
    preprocessMethods: availablePreprocessMethods,
    tableSuffixes,
    imageSuffixes,
    selectedKb,
    selectedFile,
    activePreviewKbId,
    previewFile,
    previewKbLabel,
    selectedImageFile,
    originalPreviewUrl,
    pdfPagePreviewUrl,
    previewKind,
    filteredKbs,
    filteredFiles,
    filteredWells,
    selectedWell,
    filteredStandardDocuments,
    filteredStandardGroups,
    selectedActionFileIds,
    allFilesSelected,
    structuredFiles,
    previewRows,
    previewColumns,
    preprocessRowsColumns,
    preprocessMethodById,
    preprocessSelectedMethodCards,
    preprocessAlgorithmDialogMethod,
    remainingPreprocessMethods,
    preprocessProgressRows,
    preprocessSelectedJob,
    preprocessDoneJobs,
    preprocessReportSource,
    preprocessReportSummary,
    preprocessSelectedJobSuffix,
    preprocessPreviewKind,
    preprocessPreviewUrl,
    preprocessJobCards,
    preprocessArtifacts,
    preprocessPendingSourceFiles,
    stats,
    chunkCurrentPage,
    chunkTotalPages,
    chunkPageStart,
    chunkPageEnd,
    currentDbConnection,
    dbSchemaTables,
    selectedDbTableInfo,
    dbPreviewPage,
    dbPreviewPages,
    dbPreviewStart,
    dbPreviewEnd,
    searchUsesVector,
    searchUsesSql,
    sqlResultRows,
    sqlResultColumns,
    extractionColumns,
    searchResultText,
    searchResultSourceObject,
    sourceStringValue,
    isNonEmptyString,
    searchResultFileId,
    searchResultFile,
    searchResultSourceRows,
    escapeHtml,
    decodeHtmlEntities,
    searchResultImageUrl,
    safeLinkUrl,
    renderMarkdownInline,
    isMarkdownTableSeparator,
    splitMarkdownTableRow,
    looksLikeMarkdownTableBlock,
    renderHtmlTableBlock,
    isMarkdownBlockStart,
    renderMarkdownTable,
    renderMarkdown,
    searchResultHtml,
    chunkContentHtml,
    queryAnswerHtml,
    citationAsSearchResult,
    citationHtml,
    sqlCellValue,
    fileDisplayName,
    fileSuffix,
    documentKey,
    documentTypeLabel,
    parseMethodLabel,
    selectWell,
    wellCategoryCount,
    wellAliasText,
    findWellByQuery,
    onWellSearchChange,
    findFileByQuery,
    syncSearchTexts,
    enterKb,
    goHome,
    openFilePreview,
    selectFile,
    openManagedFilePreview,
    selectPreviewFile,
    onStructuredFileChange,
    selectFileByQuery,
    selectImageFileByQuery,
    selectStructuredFileByQuery,
    onFileSearchChange,
    onImageSearchChange,
    onStructuredSearchChange,
    onSelectAllFilesChange,
    parseFile,
    deleteFile,
    notify,
    apiUrl,
    requestJson,
    onDbTypeChange,
    resetDbPreview,
    loadDbConnections,
    connectStructuredDb,
    disconnectStructuredDb,
    loadDbSchema,
    onDbConnectionChange,
    onDbSchemaChange,
    loadDbTablePreview,
    changeDbPreviewPage,
    loadKbs,
    loadFiles,
    loadFileManager,
    createKb,
    deleteKb,
    onUploadChange,
    clearUploadSelection,
    removeUploadFile,
    deleteUploadedFiles,
    setFileTask,
    clearFileTask,
    taskBadgeClass,
    hasFileTask,
    fileTaskBadgeClass,
    fileTaskMessage,
    fileTaskProgress,
    filenameKey,
    uploadDuplicateMessage,
    uploadFiles,
    pollParse,
    buildIndex,
    parseFiles,
    parseSelectedFiles,
    deleteFiles,
    deleteSelectedFiles,
    closePreviewModal,
    loadPagePreview,
    runSearch,
    sendChat,
    handleSseEvent,
    clearChat,
    loadPreview,
    changePdfPreviewPage,
    loadImages,
    chunkTypeLabel,
    chunkPreview,
    chunkMetadataRows,
    chunkImageSrc,
    openChunkSource,
    loadChunkStats,
    loadChunks,
    refreshChunks,
    resetChunkFilters,
    changeChunkPage,
    imageSrc,
    saveImage,
    onExtractFileChange,
    clearExtractSelection,
    applyExtractionTemplate,
    cloneExtractionRows,
    normalizeExtractionRows,
    extractionCellValue,
    sanitizeExtractionFilename,
    buildExtractionOutputFilename,
    extractionFilenameVariant,
    checkExtractionFilenameConflict,
    resolveUniqueExtractionFilename,
    resetExtractionDraft,
    onExtractionCellInput,
    loadExtractionContent,
    syncExtractionResult,
    saveExtractionResult,
    resetExtractionState,
    startExtraction,
    onPreprocessSourceChange,
    triggerPreprocessFilePicker,
    removePreprocessSourceFile,
    preprocessMethodName,
    openPreprocessAlgorithmDialog,
    closePreprocessAlgorithmDialog,
    savePreprocessAlgorithm,
    startPreprocessAlgorithmDialogDrag,
    movePreprocessAlgorithmDialog,
    stopPreprocessAlgorithmDialogDrag,
    addPreprocessMethod,
    togglePreprocessMethodMenu,
    removePreprocessMethod,
    onPreprocessPreviewToggle,
    uploadPreprocessSource,
    pollExtraction,
    runPreprocess,
    savePreprocessedToKb,
    downloadPreprocessExcel,
    downloadPreprocessArtifact,
    formatTime,
    asFiniteNumber,
    sumNumericValues,
    objectEntryCount,
    directPreprocessChange,
    summarizePreprocessReport,
    selectPreprocessJob,
    clearPreprocessSelection,
    onPreprocessPreviewSelectChange,
    onPreprocessJobDetailToggle
  }
}
