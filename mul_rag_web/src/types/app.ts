export type Kb = {
  kbId: string
  kbName: string
  vectorStoreType?: string
  embedModel?: string
  fileCount?: number
  createdAt?: number
}

export type KbFile = {
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

export type WellDocument = KbFile & {
  kbId: string
  kbName?: string
  category?: string
  wellId?: string
  wellIds?: string[]
  standardObject?: string
  standardUnit?: string
  hasTables?: boolean
}

export type WellCategory = {
  category: string
  documents: WellDocument[]
}

export type WellGroup = {
  wellId: string
  aliases?: string[]
  documentCount?: number
  categories: WellCategory[]
}

export type StandardGroup = {
  object: string
  documentCount?: number
  documents: WellDocument[]
}

export type FileTaskState = {
  phase: 'parse' | 'index'
  status: 'queued' | 'running' | 'done' | 'failed'
  message: string
  progress?: number
}

export type SearchResult = {
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

export type QueryMode = 'vector' | 'sql' | 'hybrid' | 'agent'

export type SqlQueryResult = {
  ok?: boolean
  sql?: string
  columns?: string[]
  rows?: Array<Record<string, unknown>>
  rowCount?: number
  limit?: number
  truncated?: boolean
  explanation?: string
  confidence?: number
  message?: string
  error?: string
  elapsedMs?: number
}

export type UnifiedQueryResponse = {
  mode?: QueryMode
  answer?: string
  citations?: Array<Record<string, unknown>>
  sqlResult?: SqlQueryResult | null
  usedRetrieval?: boolean
  usedSql?: boolean
  agentTrace?: string[]
}

export type ExtractionRow = Record<string, unknown>

export type ExtractionStatus = Record<string, unknown> & {
  jobId?: string
  status?: string
  progress?: number
  filename?: string
  kb_id?: string
  output_format?: string
  data?: ExtractionRow[]
}

export type ExtractionContentResponse = {
  jobId?: string
  content?: string
  pages?: Array<number | string>
  scope?: string
  fragmentTitle?: string
}

export type ExtractionFilenameCheckResponse = {
  kbId?: string
  filename?: string
  exists?: boolean
  conflicts?: Array<{ fileId?: string; fileName?: string }>
}

export type PreprocessAlgorithm = {
  id: string
  name: string
  description?: string
}

export type PreprocessMethod = {
  id: string
  name: string
  description: string
  category?: string
  type?: string
  algorithms?: PreprocessAlgorithm[]
  defaultAlgorithm?: string
  metadata?: Record<string, unknown>
}

export type PreprocessJob = {
  jobId?: string
  fileName?: string
  [key: string]: unknown
}

export type PreprocessMethodReport = {
  method?: string
  name?: string
  algorithm?: string
  algorithmName?: string
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

export type PreprocessReport = Record<string, unknown> & {
  ok?: boolean
  jobId?: string
  sourceFileName?: string
  rowsIn?: number
  rowsOut?: number
  columnsIn?: string[]
  columnsOut?: string[]
  selectedMethods?: string[]
  algorithmSelections?: Record<string, string>
  methodReports?: PreprocessMethodReport[]
  operations?: Record<string, unknown>
  savedToKb?: Record<string, unknown>
}

export type PreprocessJobState = PreprocessJob & {
  status?: 'uploaded' | 'running' | 'done' | 'failed'
  error?: string
  report?: PreprocessReport | null
  rows?: Array<Record<string, unknown>>
}

export type PreprocessArtifact = {
  method: string
  label: string
  path: string
  name: string
  suffix: string
}

export type ImageItem = {
  fileId: string
  kbId?: string
  fileName?: string
  img_name?: string
  old_img_name?: string
  base_img_path?: string
  imagePath?: string
  summary?: string
  page_num?: number
}

export type KnowledgeChunk = {
  id: number
  ordinal: number
  kbId?: string
  fileId: string
  fileName?: string
  type?: string
  page?: number | string | null
  headers?: string[]
  headerPath?: string
  imagePath?: string
  source?: string
  content: string
  charCount?: number
  metadata?: Record<string, unknown>
}

export type ChunkStats = {
  total: number
  text: number
  image: number
  files: number
  byFile?: Array<{ fileId: string; fileName?: string; total: number; text: number; image: number }>
}

export type StructuredDbConnection = {
  connectionId: string
  name: string
  type: string
  createdAt?: number
  config?: Record<string, unknown>
}

export type StructuredDbTable = {
  name: string
  type: 'table' | 'view' | string
  schema?: string
  columns?: Array<{ name?: string; type?: string; nullable?: boolean; default?: unknown }>
}

export type StructuredDbSchema = {
  name: string
  tables: StructuredDbTable[]
}

export type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  citations?: Array<Record<string, unknown>>
}

export type Toast = {
  type: 'success' | 'error' | 'info'
  text: string
}
