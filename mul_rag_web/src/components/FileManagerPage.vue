<script setup lang="ts">
import { computed, ref, watch } from 'vue'

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

type WellDocument = KbFile & {
  kbId: string
  kbName?: string
  category?: string
  wellId?: string
  wellIds?: string[]
  standardObject?: string
  standardUnit?: string
  hasTables?: boolean
}

type WellCategory = {
  category: string
  documents: WellDocument[]
}

type WellGroup = {
  wellId: string
  aliases?: string[]
  documentCount?: number
  categories: WellCategory[]
}

type StandardGroup = {
  object: string
  documentCount?: number
  documents: WellDocument[]
}

type FileManagerState = {
  wells: WellGroup[]
  standards: WellDocument[]
  standardGroups: StandardGroup[]
  sourceKbId: string
  wellCount: number
  documentCount: number
  busy: boolean
  loaded: boolean
}

type PreviewKind = 'pdf' | 'document' | 'table' | 'image' | 'file'

type PreviewState = {
  content: string
  sheets: Record<string, Array<Record<string, unknown>>>
  selectedSheet: string
  page: number
  busy: boolean
}

type DivisionMode = 'well' | 'standard'

const wellSearchQuery = defineModel<string>('wellSearchQuery', { default: '' })
const standardSearchQuery = defineModel<string>('standardSearchQuery', { default: '' })

const props = defineProps<{
  fileManagerState: FileManagerState
  selectedWell: WellGroup | null
  filteredStandardDocuments: WellDocument[]
  filteredStandardGroups: StandardGroup[]
  wellAliasText: (well: WellGroup) => string
  wellCategoryCount: (category: WellCategory) => number
  documentKey: (doc: WellDocument, index?: number) => string
  documentTypeLabel: (doc?: KbFile | WellDocument | null) => string
  parseMethodLabel: (method?: string, parser?: string) => string
  selectWell: (wellId: string) => void
  loadFileManager: () => void
  openManagedFilePreview: (doc: WellDocument) => void
  activePreviewKbId: string
  selectedPreviewFileId: string
  previewFile?: KbFile | WellDocument
  previewKbLabel: string
  previewKind: PreviewKind
  originalPreviewUrl: string
  pdfPagePreviewUrl: string
  previewState: PreviewState
  previewRows: Array<Record<string, unknown>>
  previewColumns: string[]
  chunkContentHtml: (content: string) => string
  loadPreview: () => void
  changePdfPreviewPage: (offset: number) => void
}>()

const collapsedWellCategoryKeys = ref<Set<string>>(new Set())
const expandedWellIds = ref<Set<string>>(new Set())
const expandedStandardObjects = ref<Set<string>>(new Set())
const selectedWellFilters = ref<string[]>([])
const selectedStandardFilters = ref<string[]>([])
const activeDivision = ref<DivisionMode>('well')

function normalizedText(value: unknown) {
  return String(value || '').trim().toLowerCase()
}

function wellMatchesTerm(well: WellGroup, term: string) {
  const keyword = normalizedText(term)
  if (!keyword) return true

  const wellValues = [well.wellId, ...(well.aliases || [])]
  const documentMatches = well.categories
    .flatMap((category) => category.documents)
    .some((doc) =>
      [doc.fileName, doc.fileId, doc.kbName, doc.category, doc.type].some((value) =>
        normalizedText(value).includes(keyword)
      )
    )

  return wellValues.some((value) => normalizedText(value).includes(keyword)) || documentMatches
}

function standardGroupMatchesTerm(group: StandardGroup, term: string) {
  const keyword = normalizedText(term)
  if (!keyword) return true

  return (
    normalizedText(group.object).includes(keyword) ||
    group.documents.some((doc) =>
      [doc.fileName, doc.fileId, doc.kbName, doc.standardObject, doc.standardUnit, doc.type].some((value) =>
        normalizedText(value).includes(keyword)
      )
    )
  )
}

const displayWells = computed(() => {
  const terms = [...selectedWellFilters.value, wellSearchQuery.value].map((term) => term.trim()).filter(Boolean)
  if (!terms.length) return props.fileManagerState.wells
  return props.fileManagerState.wells.filter((well) => terms.some((term) => wellMatchesTerm(well, term)))
})

const displayStandardGroups = computed(() => {
  const terms = [...selectedStandardFilters.value, standardSearchQuery.value].map((term) => term.trim()).filter(Boolean)
  if (!terms.length) return props.fileManagerState.standardGroups
  return props.fileManagerState.standardGroups.filter((group) => terms.some((term) => standardGroupMatchesTerm(group, term)))
})

function addUniqueFilter(target: typeof selectedWellFilters | typeof selectedStandardFilters, value: string) {
  const cleanValue = value.trim()
  if (!cleanValue) return
  if (target.value.some((item) => item.toLowerCase() === cleanValue.toLowerCase())) return
  target.value = [...target.value, cleanValue]
}

function addWellFilter(value = wellSearchQuery.value) {
  addUniqueFilter(selectedWellFilters, value)
  wellSearchQuery.value = ''
}

function addStandardFilter(value = standardSearchQuery.value) {
  addUniqueFilter(selectedStandardFilters, value)
  standardSearchQuery.value = ''
}

function removeWellFilter(value: string) {
  selectedWellFilters.value = selectedWellFilters.value.filter((item) => item !== value)
}

function removeStandardFilter(value: string) {
  selectedStandardFilters.value = selectedStandardFilters.value.filter((item) => item !== value)
}

function clearWellFilters() {
  selectedWellFilters.value = []
  wellSearchQuery.value = ''
}

function clearStandardFilters() {
  selectedStandardFilters.value = []
  standardSearchQuery.value = ''
}

function onWellFilterInputChange() {
  const exactWell = props.fileManagerState.wells.find((well) =>
    [well.wellId, ...(well.aliases || [])].some((value) => normalizedText(value) === normalizedText(wellSearchQuery.value))
  )
  if (exactWell) addWellFilter(exactWell.wellId)
}

function onStandardFilterInputChange() {
  const exactGroup = props.fileManagerState.standardGroups.find((group) => normalizedText(group.object) === normalizedText(standardSearchQuery.value))
  if (exactGroup) {
    addStandardFilter(exactGroup.object)
    return
  }

  const exactDoc = props.filteredStandardDocuments.find((doc) =>
    [doc.fileName, doc.fileId].some((value) => normalizedText(value) === normalizedText(standardSearchQuery.value))
  )
  if (exactDoc) addStandardFilter(exactDoc.fileName || exactDoc.fileId)
}

function wellCategoryKey(category: WellCategory, wellId = props.selectedWell?.wellId || '未选择井号') {
  return `${wellId}-${category.category}`
}

function isWellCategoryExpanded(category: WellCategory, wellId?: string) {
  return !collapsedWellCategoryKeys.value.has(wellCategoryKey(category, wellId))
}

function toggleWellCategory(category: WellCategory, wellId?: string) {
  const next = new Set(collapsedWellCategoryKeys.value)
  const key = wellCategoryKey(category, wellId)

  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }

  collapsedWellCategoryKeys.value = next
}

function firstDocumentForWell(well: WellGroup) {
  for (const category of well.categories) {
    const firstDoc = category.documents[0]
    if (firstDoc) return firstDoc
  }
  return null
}

function selectWellForPreview(well: WellGroup) {
  props.selectWell(well.wellId)
  const firstDoc = firstDocumentForWell(well)
  if (firstDoc) props.openManagedFilePreview(firstDoc)
}

function isWellExpanded(well: WellGroup) {
  return expandedWellIds.value.has(well.wellId)
}

function toggleWellForPreview(well: WellGroup) {
  const next = new Set(expandedWellIds.value)

  if (next.has(well.wellId)) {
    next.delete(well.wellId)
  } else {
    next.add(well.wellId)
    props.selectWell(well.wellId)
    const firstDoc = firstDocumentForWell(well)
    if (firstDoc) props.openManagedFilePreview(firstDoc)
  }

  expandedWellIds.value = next
}

function isStandardGroupExpanded(group: StandardGroup) {
  return expandedStandardObjects.value.has(group.object)
}

function toggleStandardGroupForPreview(group: StandardGroup) {
  const next = new Set(expandedStandardObjects.value)

  if (next.has(group.object)) {
    next.delete(group.object)
  } else {
    next.add(group.object)
    const firstDoc = group.documents[0]
    if (firstDoc) props.openManagedFilePreview(firstDoc)
  }

  expandedStandardObjects.value = next
}

function isPreviewDocument(doc: WellDocument) {
  return props.activePreviewKbId === doc.kbId && props.selectedPreviewFileId === doc.fileId
}

const previewDocumentTitle = computed(() => props.previewFile?.fileName || props.previewFile?.fileId || '文件预览')
const previewDocumentMeta = computed(() => {
  const file = props.previewFile
  if (!file) return '未选择文档'
  return `${props.previewKbLabel || '当前知识库'} · ${props.documentTypeLabel(file)} · ${props.parseMethodLabel(file.parseMethod, file.parser)}`
})
const previewPageCount = computed(() => Math.max(0, Number(props.previewFile?.pageCount || 0)))

watch(displayStandardGroups, (groups) => {
  const availableObjects = new Set(groups.map((group) => group.object))
  expandedStandardObjects.value = new Set(
    [...expandedStandardObjects.value].filter((object) => availableObjects.has(object))
  )
})

watch(
  () => props.selectedWell?.wellId,
  (wellId) => {
    collapsedWellCategoryKeys.value = new Set()
    if (!wellId) return
    const next = new Set(expandedWellIds.value)
    next.add(wellId)
    expandedWellIds.value = next
  },
  { immediate: true }
)

watch(displayWells, (wells) => {
  const availableWellIds = new Set(wells.map((well) => well.wellId))
  expandedWellIds.value = new Set(
    [...expandedWellIds.value].filter((wellId) => availableWellIds.has(wellId))
  )
})
</script>

<template>
  <section class="module-page file-manager-page">
    <div class="module-title">
      <h2>文件管理</h2>
    </div>

    <div class="well-stat-grid">
      <div class="stat">
        <strong>{{ fileManagerState.wellCount }}</strong>
        <span>井号</span>
      </div>
      <div class="stat">
        <strong>{{ fileManagerState.documentCount }}</strong>
        <span>关联文档</span>
      </div>
      <div class="stat">
        <strong>{{ fileManagerState.standards.length }}</strong>
        <span>规范文档</span>
      </div>
      <div class="stat">
        <strong>{{ fileManagerState.sourceKbId || '钻井设计资料' }}</strong>
        <span>井号来源</span>
      </div>
    </div>

    <div class="file-manager-grid">
      <aside class="panel file-manager-nav">
        <div class="panel-head nav-panel-head">
          <div>
            <h3>层级管理</h3>
          </div>

          <div class="nav-head-actions">
            <label class="inline-field nav-division-select">
              <select v-model="activeDivision" aria-label="选择划分方式">
                <option value="well">井号划分</option>
                <option value="standard">规范类划分</option>
              </select>
            </label>

            <button class="ghost" type="button" @click="loadFileManager" :disabled="fileManagerState.busy">
              刷新
            </button>
          </div>
        </div>

        <div v-if="fileManagerState.busy && !fileManagerState.loaded" class="empty">
          正在加载文件管理数据...
        </div>

        <div v-else class="file-manager-nav-scroll">
          <section v-if="activeDivision === 'well'" class="nav-block division-block wells-division">
            <div class="nav-fixed-area">
              <div class="nav-block-head">
                <strong>井号划分-知识库划分</strong>
                <small>{{ displayWells.length }} 口井</small>
              </div>

              <div class="multi-search">
                <label class="inline-field search-field">
                  <span>搜索井号</span>
                  <div class="search-input-row">
                    <input
                      v-model="wellSearchQuery"
                      list="well-search-options"
                      placeholder="输入或下拉选择井号"
                      @change="onWellFilterInputChange"
                      @keydown.enter.prevent="addWellFilter()"
                    />
                    <button type="button" class="ghost" @click="addWellFilter()">添加</button>
                  </div>
                  <datalist id="well-search-options">
                    <option
                      v-for="well in fileManagerState.wells"
                      :key="well.wellId"
                      :value="well.wellId"
                    >
                      {{ wellAliasText(well) }}
                    </option>
                  </datalist>
                </label>

                <div v-if="selectedWellFilters.length" class="filter-chip-row">
                  <button
                    v-for="term in selectedWellFilters"
                    :key="term"
                    type="button"
                    class="filter-chip"
                    @click="removeWellFilter(term)"
                  >
                    {{ term }} ×
                  </button>
                  <button type="button" class="filter-clear" @click="clearWellFilters">清空</button>
                </div>
              </div>
            </div>

            <div class="well-nav-list nav-list-scroll">
              <section
                v-for="well in displayWells"
                :key="well.wellId"
                :class="['well-nav-group', { active: selectedWell?.wellId === well.wellId, expanded: isWellExpanded(well) }]"
              >
                <button
                  type="button"
                  class="well-nav-button"
                  :aria-expanded="isWellExpanded(well)"
                  @click="toggleWellForPreview(well)"
                >
                  <span>
                    <strong>
                      <b :class="['category-arrow well-arrow', { expanded: isWellExpanded(well) }]">›</b>
                      {{ well.wellId }}
                    </strong>
                    <small>{{ wellAliasText(well) || '丰页 / DXFY' }}</small>
                  </span>
                  <b class="nav-count">{{ well.documentCount || 0 }}</b>
                </button>

                <div v-if="isWellExpanded(well)" class="well-nav-doc-groups">
                  <section
                    v-for="category in well.categories"
                    :key="`${well.wellId}-${category.category}`"
                    class="nav-category"
                  >
                    <button
                      type="button"
                      class="nav-category-head"
                      :aria-expanded="isWellCategoryExpanded(category, well.wellId)"
                      @click="toggleWellCategory(category, well.wellId)"
                    >
                      <span>
                        <b :class="['category-arrow', { expanded: isWellCategoryExpanded(category, well.wellId) }]">›</b>
                        {{ category.category }}
                      </span>
                      <small>{{ wellCategoryCount(category) }}</small>
                    </button>

                    <div v-show="isWellCategoryExpanded(category, well.wellId)" class="nav-doc-list">
                      <button
                        v-for="(doc, index) in category.documents"
                        :key="documentKey(doc, index)"
                        type="button"
                        :class="['nav-doc-button', { active: isPreviewDocument(doc) }]"
                        @click="openManagedFilePreview(doc)"
                      >
                        <strong>{{ doc.fileName || doc.fileId }}</strong>
                        <small>{{ doc.kbName || doc.kbId }} · {{ documentTypeLabel(doc) }}</small>
                      </button>
                    </div>
                  </section>
                </div>
              </section>

              <p v-if="!displayWells.length" class="empty">
                没有匹配的井号。
              </p>
            </div>
          </section>

          <section v-if="activeDivision === 'standard'" class="nav-block division-block standards-nav-block">
            <div class="nav-fixed-area">
              <div class="nav-block-head">
                <strong>规范类划分</strong>
                <small>{{ fileManagerState.standards.length }} 份</small>
              </div>

              <div class="multi-search">
                <label class="inline-field search-field compact">
                  <span>搜索规范</span>
                  <div class="search-input-row">
                    <input
                      v-model="standardSearchQuery"
                      list="standard-search-options"
                      placeholder="输入或下拉选择规范"
                      @change="onStandardFilterInputChange"
                      @keydown.enter.prevent="addStandardFilter()"
                    />
                    <button type="button" class="ghost" @click="addStandardFilter()">添加</button>
                  </div>
                  <datalist id="standard-search-options">
                    <option
                      v-for="group in fileManagerState.standardGroups"
                      :key="`group-${group.object}`"
                      :value="group.object"
                    >
                      {{ group.documentCount || group.documents.length }} 份
                    </option>
                    <option
                      v-for="doc in filteredStandardDocuments"
                      :key="`doc-${doc.kbId}-${doc.fileId}`"
                      :value="doc.fileName || doc.fileId"
                    >
                      {{ doc.standardUnit || doc.kbName || doc.kbId }}
                    </option>
                  </datalist>
                </label>

                <div v-if="selectedStandardFilters.length" class="filter-chip-row">
                  <button
                    v-for="term in selectedStandardFilters"
                    :key="term"
                    type="button"
                    class="filter-chip"
                    @click="removeStandardFilter(term)"
                  >
                    {{ term }} ×
                  </button>
                  <button type="button" class="filter-clear" @click="clearStandardFilters">清空</button>
                </div>
              </div>
            </div>

            <div class="standard-object-list nav-list-scroll">
              <section
                v-for="group in displayStandardGroups"
                :key="group.object"
                :class="['standard-nav-group', { expanded: isStandardGroupExpanded(group) }]"
              >
                <button
                  type="button"
                  :class="['standard-object-button', { active: isStandardGroupExpanded(group) }]"
                  :aria-expanded="isStandardGroupExpanded(group)"
                  @click="toggleStandardGroupForPreview(group)"
                >
                  <span>
                    <b :class="['category-arrow', { expanded: isStandardGroupExpanded(group) }]">›</b>
                    {{ group.object }}
                  </span>
                  <small>{{ group.documentCount || group.documents.length }}</small>
                </button>

                <div v-if="isStandardGroupExpanded(group)" class="nav-doc-list standard-nav-doc-list">
                  <button
                    v-for="(doc, index) in group.documents"
                    :key="documentKey(doc, index)"
                    type="button"
                    :class="['nav-doc-button', { active: isPreviewDocument(doc) }]"
                    @click="openManagedFilePreview(doc)"
                  >
                    <strong>{{ doc.fileName || doc.fileId }}</strong>
                    <small>{{ doc.standardUnit || group.object }} · {{ documentTypeLabel(doc) }}</small>
                  </button>
                </div>
              </section>

              <p v-if="!displayStandardGroups.length" class="empty">
                没有匹配的规范类文档。
              </p>
            </div>
          </section>
        </div>
      </aside>

      <section class="panel file-preview-panel">
        <div class="panel-head preview-panel-head">
          <div>
            <h3>{{ previewDocumentTitle }}</h3>
            <small>{{ previewDocumentMeta }}</small>
          </div>
          <button class="ghost" type="button" @click="loadPreview" :disabled="!previewFile || previewState.busy">
            刷新预览
          </button>
        </div>

        <div v-if="!previewFile" class="file-preview-empty">
          <p class="empty">请选择左侧文档。</p>
        </div>

        <div v-else class="inline-preview">
          <div v-if="previewKind === 'pdf'" class="inline-pdf-view">
            <template v-if="previewPageCount > 0">
              <div class="toolbar pdf-page-toolbar">
                <button class="ghost" type="button" :disabled="previewState.page <= 1" @click="changePdfPreviewPage(-1)">
                  上一页
                </button>
                <span>第 {{ previewState.page }} / {{ previewPageCount }} 页</span>
                <button
                  class="ghost"
                  type="button"
                  :disabled="previewState.page >= previewPageCount"
                  @click="changePdfPreviewPage(1)"
                >
                  下一页
                </button>
              </div>
              <div class="inline-pdf-page">
                <img :src="pdfPagePreviewUrl" :alt="`${previewDocumentTitle} 第 ${previewState.page} 页`" />
              </div>
            </template>
            <div
              v-else-if="previewState.content"
              class="rendered-markdown document-rendered pdf-text-fallback"
              v-html="chunkContentHtml(previewState.content)"
            ></div>
            <div v-else class="empty">当前 PDF 尚未生成页面预览，请先解析文档。</div>
          </div>

          <div v-else-if="previewKind === 'document'" class="inline-document-view">
            <div v-if="previewState.busy" class="empty">加载文档内容中...</div>
            <div
              v-else-if="previewState.content"
              class="rendered-markdown document-rendered"
              v-html="chunkContentHtml(previewState.content)"
            ></div>
            <div v-else class="empty">当前文档尚无可预览内容，请先解析文档。</div>
          </div>

          <div v-else-if="previewKind === 'table'" class="inline-table-preview">
            <div class="toolbar sheet-toolbar" v-if="Object.keys(previewState.sheets).length">
              <label class="inline-field small">
                <span>表页</span>
                <select v-model="previewState.selectedSheet">
                  <option v-for="(_, sheet) in previewState.sheets" :key="sheet" :value="sheet">
                    {{ sheet }}
                  </option>
                </select>
              </label>
              <span class="sheet-summary">{{ previewRows.length ? `共 ${previewRows.length} 行` : '暂无行数据' }}</span>
            </div>
            <div v-if="previewState.busy" class="empty">加载表格中...</div>
            <div v-else-if="previewRows.length" class="data-table inline-preview-table">
              <table>
                <thead>
                  <tr>
                    <th v-for="col in previewColumns" :key="col">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in previewRows.slice(0, 300)" :key="index">
                    <td v-for="col in previewColumns" :key="col">{{ row[col] }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="empty">当前表格没有可显示的数据。</div>
          </div>

          <div v-else-if="previewKind === 'image'" class="inline-image-view">
            <img :src="originalPreviewUrl" :alt="previewFile?.fileName || '图片预览'" />
            <div v-if="previewState.content" class="markdown-view image-description-view">
              <h4>图片描述</h4>
              <pre>{{ previewState.content }}</pre>
            </div>
          </div>

          <div v-else class="inline-document-view unsupported-file-view">
            <div
              v-if="previewState.content"
              class="rendered-markdown document-rendered"
              v-html="chunkContentHtml(previewState.content)"
            ></div>
            <div v-else class="empty">
              <p>该文件格式不能在浏览器中直接预览。</p>
              <a class="button-link" :href="originalPreviewUrl" target="_blank" rel="noopener">下载原文件</a>
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.file-manager-page {
  display: grid;
  gap: 14px;
  align-content: start;
}

.file-manager-page .module-title {
  display: grid;
  gap: 6px;
  margin-bottom: 2px;
  padding-top: 2px;
}

.file-manager-page .module-title h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 800;
  line-height: 1.18;
}

.file-manager-page .module-title span {
  color: #64748b;
  font-size: 14px;
}

.well-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 10px;
}

.well-stat-grid .stat strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat {
  display: grid;
  gap: 2px;
  padding: 10px;
  border: 1px solid #e7ebf0;
  border-radius: 8px;
  background: #fff;
}

.stat strong {
  color: #111827;
  font-size: 18px;
  font-weight: 800;
}

.stat span {
  color: #6b7280;
  font-size: 12px;
}

.file-manager-grid {
  display: grid;
  grid-template-columns: minmax(340px, 420px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  min-height: calc(100vh - 214px);
}

.panel {
  min-width: 0;
  padding: 18px;
  background: #fff;
  border: 1px solid #e1eaed;
  border-radius: 8px;
  box-shadow: 0 14px 40px rgba(25, 54, 65, 0.08);
}

.panel-head,
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.panel-head > div {
  display: grid;
  gap: 2px;
  align-content: center;
}

.panel-head h3,
.module-title h2 {
  margin: 0;
  font-weight: 800;
  line-height: 1.28;
}

.panel-head small,
.module-title span,
.well-search-hint,
.managed-doc-title small,
.well-category-head span {
  color: #64748b;
}

.panel-head small,
.well-search-hint,
.managed-doc-title small,
.well-category-head span {
  font-size: 12px;
}

.nav-panel-head {
  align-items: center;
}

.nav-head-actions {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  flex: 1;
  max-width: 240px;
}

.nav-division-select {
  min-width: 0;
}

.nav-division-select select {
  min-height: 36px;
  padding: 6px 10px;
  font-size: 13px;
}

.file-manager-nav,
.file-preview-panel,
.well-sidebar,
.well-document-panel,
.standards-panel {
  display: grid;
  gap: 14px;
}

.file-manager-nav,
.file-preview-panel {
  height: calc(100vh - 214px);
  min-height: 620px;
  overflow: hidden;
}

.file-manager-nav {
  grid-template-rows: auto minmax(0, 1fr);
  position: sticky;
  top: 82px;
}

.file-preview-panel {
  grid-template-rows: auto minmax(0, 1fr);
}

.file-manager-nav-scroll {
  display: grid;
  gap: 14px;
  align-content: stretch;
  min-height: 0;
  overflow: hidden;
  padding-right: 0;
}

.wells-division,
.standards-nav-block {
  min-height: 0;
  height: 100%;
  grid-template-rows: auto minmax(0, 1fr);
}

.nav-fixed-area {
  display: grid;
  gap: 10px;
  align-content: start;
}

.nav-list-scroll {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
}

.multi-search {
  display: grid;
  gap: 8px;
}

.search-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.filter-chip-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-chip,
.filter-clear {
  min-height: 28px;
  padding: 4px 8px;
  font-size: 12px;
}

.filter-chip {
  border-color: #f0c2c2;
  background: #fff5f5;
  color: #a72626;
}

.filter-clear {
  border-color: #dbe5e8;
  background: #f8fbfc;
  color: #526a74;
}

.nav-block {
  display: grid;
  gap: 10px;
}

.division-block {
  border: 1px solid #e4ebef;
  border-radius: 8px;
  padding: 12px;
  background: #fbfdfe;
}

.nav-block-head,
.well-nav-button,
.nav-category-head,
.standard-object-button {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.nav-block-head {
  color: #1f2937;
}

.nav-block-head small,
.well-nav-button small,
.nav-category-head small,
.standard-object-button small,
.nav-doc-button small {
  color: #64748b;
  font-size: 12px;
}

.well-nav-list,
.well-nav-doc-groups,
.nav-doc-list,
.standard-object-list {
  display: grid;
  gap: 8px;
}

.well-nav-group,
.nav-category,
.standard-nav-group {
  display: grid;
  gap: 6px;
}

.well-nav-button,
.nav-category-head,
.nav-doc-button,
.standard-object-button {
  width: 100%;
  min-width: 0;
  text-align: left;
}

.well-nav-button {
  min-height: 58px;
}

.well-nav-button span,
.nav-doc-button {
  min-width: 0;
}

.well-nav-button strong,
.nav-doc-button strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.well-nav-button .nav-count {
  display: inline-grid;
  min-width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 999px;
  background: #f3f6f8;
  color: #334155;
  font-size: 12px;
}

.well-nav-group.active > .well-nav-button,
.nav-doc-button.active,
.standard-object-button.active {
  border-color: #efb3b3;
  background: #fff5f5;
  color: #c51616;
}

.well-nav-doc-groups {
  margin-left: 10px;
  padding-left: 10px;
  border-left: 2px solid #eef2f6;
}

.nav-category-head {
  min-height: 38px;
  padding: 7px 9px;
}

.nav-category-head span {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-doc-button {
  display: grid;
  gap: 3px;
  min-height: 54px;
  padding: 9px 10px;
}

.standards-nav-block {
  align-content: start;
}

.standard-object-list {
  max-height: none;
  overflow: visible;
  padding-right: 0;
}

.standard-object-list.nav-list-scroll {
  overflow-y: auto;
  padding-right: 4px;
}

.standard-object-button {
  min-height: 36px;
  padding: 7px 9px;
}

.standard-nav-doc-list {
  margin-left: 10px;
  padding-left: 10px;
  border-left: 2px solid #eef2f6;
}

.preview-panel-head {
  min-width: 0;
}

.preview-panel-head > div {
  min-width: 0;
}

.preview-panel-head h3,
.preview-panel-head small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-preview,
.file-preview-empty {
  min-height: 0;
  overflow: hidden;
  border: 1px solid #e1eaed;
  border-radius: 8px;
  background: #f8fbfc;
}

.file-preview-empty {
  display: grid;
  place-items: center;
}

.inline-preview-frame,
.inline-pdf-view,
.inline-document-view,
.inline-table-preview,
.inline-image-view {
  width: 100%;
  height: 100%;
  min-height: 560px;
}

.inline-preview-frame {
  border: 0;
  background: #fff;
}

.inline-pdf-view {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
}

.pdf-page-toolbar {
  justify-content: center;
  padding: 10px 12px;
  border-bottom: 1px solid #e1eaed;
}

.inline-pdf-page {
  min-height: 0;
  overflow: auto;
  padding: 14px;
  text-align: center;
  background: #eef2f6;
}

.inline-pdf-page img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  box-shadow: 0 3px 18px rgb(15 23 42 / 14%);
}

.pdf-text-fallback {
  overflow: auto;
  padding: 18px;
}

.unsupported-file-view .empty {
  display: grid;
  place-items: center;
  align-content: center;
  gap: 12px;
  min-height: 260px;
}

.unsupported-file-view .empty p {
  margin: 0;
}

.button-link {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 14px;
  border-radius: 8px;
  color: #fff;
  text-decoration: none;
  background: #df1717;
}

.inline-document-view,
.inline-table-preview,
.inline-image-view {
  overflow: auto;
  padding: 14px;
}

.inline-document-view .document-rendered {
  min-height: 100%;
  border: 0;
  background: #fff;
}

.inline-preview-table {
  max-height: calc(100vh - 330px);
  margin-top: 12px;
  overflow: auto;
  border: 1px solid #dbe5e8;
  border-radius: 8px;
  background: #fff;
}

.inline-preview-table table {
  width: 100%;
  min-width: max-content;
  border-collapse: collapse;
  background: #fff;
  font-size: 13px;
}

.inline-preview-table th,
.inline-preview-table td {
  max-width: 280px;
  border: 1px solid #e1eaed;
  padding: 8px 10px;
  color: #1f2937;
  text-align: left;
  vertical-align: top;
  white-space: pre-wrap;
  word-break: break-word;
}

.inline-preview-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #edf4f6;
  color: #253942;
  font-weight: 800;
}

.sheet-toolbar {
  justify-content: flex-start;
  flex-wrap: wrap;
  align-items: end;
}

.sheet-summary {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.inline-image-view {
  display: grid;
  gap: 12px;
  place-items: center;
}

.inline-image-view img {
  max-width: 100%;
  max-height: 68vh;
  object-fit: contain;
  border-radius: 8px;
  background: #fff;
}

.well-sidebar {
  position: sticky;
  top: 82px;
  max-height: calc(100vh - 118px);
}

.well-document-panel {
  grid-template-rows: auto minmax(0, 1fr);
  align-content: stretch;
  min-height: 0;
  height: calc(100vh - 118px);
  overflow: hidden;
}

.well-document-panel > .panel-head {
  min-height: 40px;
  flex-shrink: 0;
}

.well-document-body {
  height: 100%;
  min-height: 0;
  max-height: 100%;
  overflow-y: auto;
  display: grid;
  gap: 14px;
  align-content: start;
  padding-right: 4px;
  overscroll-behavior: contain;
}

.standards-list,
.managed-doc-list {
  display: grid;
  gap: 10px;
}

.standards-manager-grid {
  display: grid;
  grid-template-columns: minmax(230px, 280px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.standard-object-sidebar,
.standard-document-panel {
  min-height: 0;
  border: 1px solid #e4ebef;
  border-radius: 8px;
  background: #f8fbfc;
}

.standard-object-sidebar {
  display: grid;
  gap: 12px;
  padding: 12px;
  align-content: start;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  box-sizing: border-box;
}

.standard-object-head,
.standard-document-head {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.standard-object-head {
  min-width: 0;
  max-width: 100%;
}

.standard-object-head > div {
  min-width: 0;
  max-width: 100%;
}

.standard-object-head strong,
.standard-document-head h3 {
  margin: 0;
  color: #1f2937;
  font-weight: 800;
}

.standard-object-head strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.standard-object-head small,
.standard-document-head small {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.standard-object-head small {
  flex-shrink: 0;
  white-space: nowrap;
}

.standard-object-search-field {
  display: grid;
  gap: 8px;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}

.standard-object-search-field span {
  min-width: 0;
  max-width: 100%;
  color: #526a74;
  font-size: 12px;
  font-weight: 700;
}

.standard-object-search-field input {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  font-size: 14px;
  box-sizing: border-box;
}

.standard-object-hint {
  min-width: 0;
  max-width: 100%;
  line-height: 1.6;
}

.standard-object-hint p {
  margin: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.standard-document-panel {
  display: grid;
  gap: 12px;
  padding: 12px;
}

.standards-list {
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  align-content: start;
  height: min(48vh, 540px);
  min-height: 260px;
  overflow: auto;
  padding-right: 4px;
}

.standards-list .empty {
  grid-column: 1 / -1;
}

.well-search-hint {
  line-height: 1.6;
}

.well-category-section {
  display: grid;
  min-height: 0;
  overflow: hidden;
  border: 1px solid #e4ebef;
  border-radius: 8px;
  background: #fbfdfe;
}

.well-category-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 48px;
  padding: 12px 14px;
  border: 0;
  border-radius: 0;
  background: #f8fbfc;
  color: #1f2937;
  text-align: left;
}

.well-category-head:hover {
  background: #fff6f6;
  color: #b91c1c;
}

.category-title {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.category-arrow {
  display: inline-grid;
  width: 18px;
  height: 18px;
  place-items: center;
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 18px;
  font-weight: 900;
  line-height: 1;
  transition: transform 0.18s ease;
}

.category-arrow.expanded {
  transform: rotate(90deg);
}

.well-category-head h3 {
  margin: 0;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-summary {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.category-summary small {
  color: #b91c1c;
  font-size: 12px;
  font-weight: 800;
}

.well-category-doc-list {
  max-height: min(34vh, 380px);
  min-height: 92px;
  overflow: auto;
  padding: 10px;
  border-top: 1px solid #e4ebef;
  background: #fff;
}

.managed-doc-card {
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.managed-doc-card {
  align-items: flex-start;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e4ebef;
  background: #fff;
}

.managed-doc-title {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.managed-doc-title strong {
  color: #1f2937;
  font-weight: 800;
}

.managed-doc-title strong,
.managed-doc-title small {
  overflow-wrap: anywhere;
}

.managed-doc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f3f6f8;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
}

.badge.ok {
  background: #ecfdf3;
  color: #047857;
}

.badge.warn {
  background: #fff7ed;
  color: #c2410c;
}

button {
  border: 1px solid #dbe5e8;
  background: #fff;
  color: #1f2937;
  border-radius: 8px;
  padding: 8px 12px;
  font-weight: 600;
  cursor: pointer;
}

button:hover {
  border-color: #efb3b3;
  color: #c51616;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

button.ghost {
  background: #fff;
}

.inline-field,
.field {
  display: grid;
  gap: 6px;
}

.inline-field span,
.field span {
  color: #526a74;
  font-size: 12px;
  font-weight: 700;
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

input,
select,
textarea {
  width: 100%;
  min-height: 38px;
  border: 1px solid #c9d6da;
  border-radius: 8px;
  padding: 8px 10px;
  background: #fff;
  color: #111827;
  box-sizing: border-box;
}

.empty {
  margin: 0;
  color: #94a3b8;
  font-size: 12px;
}

@media (max-width: 1180px) {
  .file-manager-grid,
  .standards-manager-grid {
    grid-template-columns: 1fr;
  }

  .file-manager-nav,
  .file-preview-panel {
    position: static;
    height: auto;
    min-height: 0;
  }

  .file-manager-nav-scroll {
    height: 520px;
    max-height: 520px;
  }

  .inline-preview-frame,
  .inline-pdf-view,
  .inline-document-view,
  .inline-table-preview,
  .inline-image-view {
    min-height: 520px;
  }

  .well-sidebar {
    position: static;
    max-height: none;
  }

  .well-document-panel {
    height: min(76vh, 720px);
    min-height: min(420px, 76vh);
  }
}
</style>
