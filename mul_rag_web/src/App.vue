<script setup lang="ts">
import FileManagerPage from './components/FileManagerPage.vue'
import { useAppController } from './composables/useAppController'

const {
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
  kbSearchQuery,
  createKbExpanded,
  kbUploadExpanded,
  selectedFileSearchText,
  selectedImageSearchText,
  selectedStructuredSearchText,
  searchFileId,
  selectedPreviewFileId,
  selectedChunkFileId,
  kbSubTab,
  wellSearchQuery,
  standardSearchQuery,
  previewModalOpen,
  toast,
  newKb,
  uploadState,
  uploadInputRef,
  preprocessInputRef,
  extractInputRef,
  searchState,
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
  selectedKb,
  selectedFile,
  previewFile,
  activePreviewKbId,
  previewKbLabel,
  originalPreviewUrl,
  pdfPagePreviewUrl,
  previewKind,
  filteredKbs,
  filteredFiles,
  selectedWell,
  filteredStandardDocuments,
  filteredStandardGroups,
  allFilesSelected,
  structuredFiles,
  previewRows,
  previewColumns,
  preprocessRowsColumns,
  preprocessSelectedMethodCards,
  preprocessAlgorithmDialogMethod,
  remainingPreprocessMethods,
  preprocessProgressRows,
  preprocessSelectedJob,
  preprocessDoneJobs,
  preprocessReportSummary,
  preprocessPreviewKind,
  preprocessPreviewUrl,
  preprocessJobCards,
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
  searchResultSourceRows,
  searchResultHtml,
  chunkContentHtml,
  queryAnswerHtml,
  citationHtml,
  sqlCellValue,
  documentKey,
  documentTypeLabel,
  parseMethodLabel,
  selectWell,
  wellCategoryCount,
  wellAliasText,
  enterKb,
  goHome,
  openFilePreview,
  openManagedFilePreview,
  onFileSearchChange,
  onImageSearchChange,
  onStructuredSearchChange,
  onSelectAllFilesChange,
  onDbTypeChange,
  loadDbConnections,
  connectStructuredDb,
  disconnectStructuredDb,
  loadDbSchema,
  onDbConnectionChange,
  onDbSchemaChange,
  loadDbTablePreview,
  changeDbPreviewPage,
  loadKbs,
  loadFileManager,
  createKb,
  deleteKb,
  onUploadChange,
  clearUploadSelection,
  removeUploadFile,
  hasFileTask,
  fileTaskBadgeClass,
  fileTaskMessage,
  fileTaskProgress,
  uploadFiles,
  buildIndex,
  parseSelectedFiles,
  deleteSelectedFiles,
  closePreviewModal,
  runSearch,
  loadPreview,
  changePdfPreviewPage,
  loadImages,
  chunkTypeLabel,
  chunkPreview,
  chunkMetadataRows,
  chunkImageSrc,
  openChunkSource,
  loadChunks,
  refreshChunks,
  resetChunkFilters,
  changeChunkPage,
  imageSrc,
  saveImage,
  onExtractFileChange,
  clearExtractSelection,
  extractionCellValue,
  resetExtractionDraft,
  onExtractionCellInput,
  loadExtractionContent,
  saveExtractionResult,
  resetExtractionState,
  startExtraction,
  onPreprocessSourceChange,
  triggerPreprocessFilePicker,
  removePreprocessSourceFile,
  openPreprocessAlgorithmDialog,
  closePreprocessAlgorithmDialog,
  savePreprocessAlgorithm,
  startPreprocessAlgorithmDialogDrag,
  movePreprocessAlgorithmDialog,
  stopPreprocessAlgorithmDialogDrag,
  addPreprocessMethod,
  togglePreprocessMethodMenu,
  removePreprocessMethod,
  uploadPreprocessSource,
  runPreprocess,
  savePreprocessedToKb,
  downloadPreprocessExcel,
  clearPreprocessSelection,
  onPreprocessPreviewSelectChange
} = useAppController()
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">
        <div>
          <h1>非常规油气多模态知识库平台</h1>
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
          <h2>多模态检索</h2>
        </div>

        <div class="panel">
          <div class="form-grid search-form">
            <label class="field search-form-query">
              <span>问题</span>
              <input v-model="searchState.query" placeholder="请输入关键词或问题" />
            </label>
            <label class="field search-form-mode">
              <span>检索模式</span>
              <select v-model="searchState.mode">
                <option v-for="mode in queryModes" :key="mode.id" :value="mode.id">{{ mode.label }}</option>
              </select>
            </label>
            <label v-if="searchUsesVector" class="field search-form-kb">
              <span>{{ searchState.mode === 'agent' ? '选择检索知识库（可选）' : '选择检索知识库' }}</span>
              <select v-model="selectedKbId">
                <option value="">请选择知识库</option>
                <option v-for="kb in kbs" :key="kb.kbId" :value="kb.kbId">{{ kb.kbName }}</option>
              </select>
            </label>
            <label v-if="searchUsesVector" class="field search-form-topk">
              <span>召回数量</span>
              <input v-model.number="searchState.k" type="number" min="1" max="10" />
            </label>
            <label v-if="searchUsesVector" class="field search-form-range">
              <span>选择搜索范围</span>
              <select v-model="searchFileId">
                <option value="">当前知识库（全部文件）</option>
                <option v-for="file in files" :key="file.fileId" :value="file.fileId">{{ file.fileName || file.fileId }}</option>
              </select>
            </label>
            <label v-if="searchUsesSql" class="field search-form-db">
              <span>{{ searchState.mode === 'agent' ? '数据库连接（可选）' : '数据库连接' }}</span>
              <select v-model="dbState.connectionId">
                <option value="">请选择数据库连接</option>
                <option v-for="conn in dbState.connections" :key="conn.connectionId" :value="conn.connectionId">
                  {{ conn.name }} · {{ conn.type }}
                </option>
              </select>
            </label>
            <label v-if="searchUsesSql" class="field search-form-limit">
              <span>数据库返回行数</span>
              <input v-model.number="searchState.sqlLimit" type="number" min="1" max="500" />
            </label>
            <div class="search-form-actions">
              <button v-if="searchUsesSql" class="ghost" type="button" @click="loadDbConnections">刷新数据库连接</button>
              <button class="primary-red" type="button" @click="runSearch" :disabled="searchState.busy">搜索</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h3>搜索结果</h3>
            </div>
          </div>
          <details v-if="searchState.answer" class="query-answer">
            <summary class="query-answer-summary">
              <div class="result-meta">
                <span>答案</span>
                <span v-if="searchState.usedRetrieval">使用文档检索</span>
                <span v-if="searchState.usedSql">使用数据库查询</span>
              </div>
              <span class="query-answer-hint">点击展开查看证据</span>
            </summary>
            <div class="query-answer-body">
              <div class="rendered-markdown result-content" v-html="queryAnswerHtml()"></div>
            </div>
          </details>

          <div v-if="searchState.sqlResult" class="sql-result-card">
            <div class="result-meta">
              <span>数据库查询</span>
              <span v-if="searchState.sqlResult.elapsedMs">{{ searchState.sqlResult.elapsedMs }} 毫秒</span>
              <span v-if="searchState.sqlResult.truncated">结果已按上限截断</span>
            </div>
            <pre v-if="searchState.sqlResult.sql" class="sql-code"><code>{{ searchState.sqlResult.sql }}</code></pre>
            <p v-if="!searchState.sqlResult.ok" class="empty">{{ searchState.sqlResult.message || searchState.sqlResult.error || '数据库查询失败' }}</p>
            <div v-else-if="sqlResultRows.length" class="data-table sql-result-table">
              <table>
                <thead><tr><th v-for="col in sqlResultColumns" :key="col">{{ col }}</th></tr></thead>
                <tbody>
                  <tr v-for="(row, rowIndex) in sqlResultRows" :key="rowIndex">
                    <td v-for="col in sqlResultColumns" :key="col">{{ sqlCellValue(row, col) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else-if="searchState.sqlResult.ok" class="empty">数据库查询已执行，未返回数据行。</p>
          </div>

          <div v-if="searchState.citations.length" class="result-list citation-list">
            <article v-for="(item, index) in searchState.citations" :key="`${item.citation_id || index}`" class="result-item">
              <details class="result-expander" :open="index === 0">
                <summary class="result-summary">
                  <div class="result-meta">
                    <span>引用 {{ index + 1 }}</span>
                    <span v-if="item.fileId">文件：{{ item.fileId }}</span>
                    <span v-if="item.page">页码：{{ item.page }}</span>
                    <span v-if="item.contentType">类型：{{ item.contentType === 'table' ? '表格' : (item.contentType === 'table_row' ? '表格行' : item.contentType) }}</span>
                    <span v-if="item.score">得分：{{ Number(item.score || 0).toFixed(4) }}</span>
                  </div>
                  <span class="result-toggle-text">展开/收起</span>
                </summary>
                <div class="result-expander-body">
                  <div class="rendered-markdown result-content" v-html="citationHtml(item)"></div>
                </div>
              </details>
            </article>
          </div>

          <div class="result-list">
            <article v-for="(item, index) in searchState.results" :key="index" class="result-item">
              <details class="result-expander" :open="index === 0">
                <summary class="result-summary">
                  <div class="result-meta">
                    <span>结果 {{ index + 1 }}</span>
                    <span>得分：{{ Number(item.score || 0).toFixed(4) }}</span>
                  </div>
                  <span class="result-toggle-text">展开/收起</span>
                </summary>
                <div class="result-expander-body">
                  <div class="rendered-markdown result-content" v-html="searchResultHtml(item, searchState.query)"></div>
                  <footer class="result-source">
                    <strong>出处</strong>
                    <div class="source-row-grid">
                      <span v-for="row in searchResultSourceRows(item)" :key="`${row.label}-${row.value}`">
                        <b>{{ row.label }}</b>{{ row.value }}
                      </span>
                    </div>
                  </footer>
                </div>
              </details>
            </article>
            <p v-if="!searchState.results.length && !searchState.answer && !searchState.sqlResult && !searchState.citations.length" class="empty">
              输入问题并点击搜索后，结果会显示在这里。
            </p>
          </div>
        </div>
      </section>

      <section v-if="!isKbDetailPage && activeTab === 'extract'" class="module-page">
        <div class="module-title">
          <h2>知识提取</h2>
        </div>

        <div class="panel-grid two extraction-grid">
          <div class="panel">
            <div class="panel-head">
              <div>
                <h3>文件与配置</h3>
              </div>
              <button v-if="extractState.jobId" class="ghost" type="button" @click="resetExtractionState()">重置状态</button>
            </div>
            <div class="form-grid">
              <label class="field">
                <span>上传待提取的文档、表格、文本或图片</span>
                <input ref="extractInputRef" type="file" accept=".pdf,.doc,.docx,.xlsx,.xls,.csv,.txt,.md,image/*,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tif,.tiff" @change="onExtractFileChange" />
              </label>
              <div v-if="extractState.file" class="upload-file-grid extract-upload-grid">
                <article class="upload-file-card extract-upload-card">
                  <button type="button" class="upload-file-remove" @click="clearExtractSelection" aria-label="移除文件">×</button>
                  <strong>{{ extractState.file.name }}</strong>
                  <small>{{ (extractState.file.size / 1024 / 1024).toFixed(2) }} 兆字节</small>
                </article>
              </div>
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
                <span>提取指令</span>
                <textarea v-model="extractState.instruction" rows="9" placeholder="例如：请提取文档中的所有发票信息，包含发票代码、号码、金额、日期。"></textarea>
              </label>
              <div class="form-grid two-cols">
                <label class="field">
                  <span>输出格式</span>
                  <select v-model="extractState.outputFormat">
                    <option value="excel">excel</option>
                    <option value="csv">csv</option>
                  </select>
                </label>
                <label class="field">
                  <span>解析模型</span>
                  <select v-model="extractState.parseMethod">
                    <option value="original">基础解析（结构化文字识别，适合文本/表格）</option>
                    <option value="olmocr">多模态大模型（视觉增强，适合复杂排版）</option>
                    <option value="mineru">MinerU（文档解析/表格增强）</option>
                  </select>
                </label>
              </div>
              <label class="field">
                <span>保存文件名 (可选)</span>
                <input v-model="extractState.customFilename" placeholder="留空则自动生成提取结果文件名" />
              </label>
            </div>
          </div>

          <div class="panel">
            <div class="panel-head">
              <div>
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
              <p v-if="!extractState.jobId" class="empty">提取结果、原文内容和可编辑区域会在任务完成后显示在这里。</p>

              <div v-else class="extraction-results-stack">
                <details class="preprocess-collapsible extraction-collapsible" open>
                  <summary class="preprocess-collapsible-summary">
                    <div>
                      <h3>{{ extractState.sourceFragmentTitle || '相关片段（前 3 个文本块）' }}</h3>
                      <small class="extraction-page-line">仅展示前 3 个文本块</small>
                    </div>
                    <small>{{ extractState.sourceContentLoading ? '加载中...' : (extractState.sourceContent ? '已定位到提取部分' : '暂无相关片段内容') }}</small>
                  </summary>
                  <div class="extraction-scroll">
                    <pre class="json-view">{{ extractState.sourceContent || '相关片段内容会显示在这里，仅展示前 3 个文本块。' }}</pre>
                  </div>
                </details>

                <details class="preprocess-collapsible extraction-collapsible" open>
                  <summary class="preprocess-collapsible-summary">
                    <div>
                      <h3>提取结果（可编辑）</h3>
                    </div>
                    <small>{{ extractionColumns.length }} 列 · {{ extractState.extractedRows.length }} 行{{ extractState.resultDirty ? ' · 已修改' : '' }}</small>
                  </summary>
                  <div class="extraction-result-toolbar toolbar">
                    <button class="ghost" type="button" @click="loadExtractionContent(extractState.jobId)">重新加载原文</button>
                    <button class="ghost" type="button" @click="resetExtractionDraft()">重置修改</button>
                    <button class="primary-red" type="button" @click="saveExtractionResult" :disabled="extractState.saving || !extractState.extractedRows.length">
                      {{ extractState.saving ? '保存中...' : '保存修改并覆盖提取内容' }}
                    </button>
                  </div>
                  <div v-if="extractionColumns.length && extractState.extractedRows.length" class="data-table extraction-table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th class="extraction-row-index">#</th>
                          <th v-for="column in extractionColumns" :key="column">{{ column }}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, rowIndex) in extractState.extractedRows" :key="`extract-row-${rowIndex}`">
                          <td class="extraction-row-index">{{ rowIndex + 1 }}</td>
                          <td v-for="column in extractionColumns" :key="column">
                            <input
                              class="extraction-cell-input"
                              :value="extractionCellValue(row[column])"
                              @input="onExtractionCellInput(rowIndex, column, $event)"
                            />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <p v-else class="empty">暂无可编辑的提取结果。</p>
                </details>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section v-if="!isKbDetailPage && activeTab === 'database'" class="module-page">
        <div class="module-title">
          <h2>结构化数据库</h2>
        </div>

        <div class="database-layout">
          <div class="panel database-connect-panel">
            <div class="panel-head">
              <div>
                <h3>连接外部数据库</h3>
              </div>
              <button class="ghost" type="button" @click="loadDbConnections">刷新连接</button>
            </div>

            <div class="form-grid">
              <label class="field">
                <span>连接名称</span>
                <input v-model="dbState.form.name" placeholder="例如: 生产库只读连接" />
              </label>
              <div class="form-grid two-cols">
                <label class="field">
                  <span>数据库类型</span>
                  <select v-model="dbState.form.type" @change="onDbTypeChange">
                    <option value="mysql">MySQL</option>
                    <option value="postgresql">PostgreSQL</option>
                    <option value="sqlite">SQLite</option>
                  </select>
                </label>
                <label v-if="dbState.form.type !== 'sqlite'" class="field">
                  <span>端口</span>
                  <input v-model.number="dbState.form.port" type="number" min="1" />
                </label>
              </div>

              <details v-if="dbState.form.type === 'mysql'" class="db-preparation" open>
                <summary>MySQL 前期准备</summary>
                <div class="db-connect-guide">
                  <p>在本地电脑保持反向 SSH 隧道：</p>
                  <code>ssh -p 3333 -N -R 13307:127.0.0.1:3306 lrn@10.16.33.2</code>
                  <p>本页面填写主机 <b>127.0.0.1</b>、端口 <b>13307</b>，并填写本地 MySQL 的数据库名、用户名和密码。</p>
                </div>
              </details>

              <details v-else-if="dbState.form.type === 'postgresql'" class="db-preparation">
                <summary>PostgreSQL 前期准备</summary>
                <div class="db-connect-guide">
                  <p>确认 PostgreSQL 服务已启动，并准备好主机、端口（默认 5432）、数据库名、用户名和密码。</p>
                  <p>如果通过 SSH 隧道访问，请将隧道映射后的服务器端口填写到本页面的端口字段。</p>
                </div>
              </details>

              <details v-else class="db-preparation">
                <summary>SQLite 前期准备</summary>
                <div class="db-connect-guide">
                  <p>SQLite 不需要启动服务或 SSH 隧道。</p>
                  <p>请填写后端运行机器上的数据库文件绝对路径，例如 <code>/data/example.db</code>。</p>
                </div>
              </details>

              <label v-if="dbState.form.type === 'sqlite'" class="field">
                <span>数据库文件路径</span>
                <input v-model="dbState.form.sqlitePath" placeholder="请输入数据库文件路径" />
              </label>

              <template v-else>
                <label class="field">
                  <span>主机地址</span>
                  <input v-model="dbState.form.host" placeholder="127.0.0.1" />
                </label>
                <label class="field">
                  <span>数据库名</span>
                  <input v-model="dbState.form.database" placeholder="数据库名称" />
                </label>
                <div class="form-grid two-cols">
                  <label class="field">
                    <span>用户名</span>
                    <input v-model="dbState.form.username" autocomplete="username" />
                  </label>
                  <label class="field">
                    <span>密码</span>
                    <input v-model="dbState.form.password" type="password" autocomplete="current-password" />
                  </label>
                </div>
              </template>

              <button type="button" @click="connectStructuredDb" :disabled="dbState.connecting">
                {{ dbState.connecting ? '连接中...' : '连接数据库' }}
              </button>
            </div>

            <div class="db-connection-list-head">
              <strong>已建立的数据库连接</strong>
              <small>{{ dbState.connections.length }} 个连接</small>
            </div>

            <div class="db-connection-list">
              <article v-for="conn in dbState.connections" :key="conn.connectionId" :class="{ active: dbState.connectionId === conn.connectionId }">
                <button type="button" class="db-connection-item" @click="dbState.connectionId = conn.connectionId; onDbConnectionChange()">
                  <strong>{{ conn.name }}</strong>
                  <small>{{ conn.type }} · {{ conn.config?.database || conn.config?.host || conn.connectionId }}</small>
                </button>
              </article>
              <p v-if="!dbState.connections.length" class="empty">还没有活动数据库连接。</p>
            </div>
          </div>

          <div class="panel database-browser-panel">
            <div class="panel-head">
              <div>
                <h3>表结构与数据预览</h3>
              </div>
              <div class="toolbar">
                <button type="button" @click="loadDbSchema" :disabled="!dbState.connectionId || dbState.schemaBusy">刷新结构</button>
                <button class="danger ghost" type="button" @click="disconnectStructuredDb" :disabled="!dbState.connectionId">断开连接</button>
              </div>
            </div>

            <div v-if="currentDbConnection" class="db-current-line">
              <span>{{ currentDbConnection.name }}</span>
              <small>{{ currentDbConnection.type }} · {{ currentDbConnection.config?.database || currentDbConnection.config?.host }}</small>
            </div>

            <div class="toolbar db-browser-toolbar">
              <label class="inline-field">
                <span>模式</span>
                <select v-model="dbState.selectedSchema" :disabled="!dbState.schemas.length" @change="onDbSchemaChange">
                  <option v-for="schema in dbState.schemas" :key="schema.name || 'default'" :value="schema.name">{{ schema.name || '默认' }}</option>
                </select>
              </label>
              <label class="inline-field">
                <span>表 / 视图</span>
                <select v-model="dbState.selectedTable" :disabled="!dbSchemaTables.length" @change="loadDbTablePreview(true)">
                  <option v-for="table in dbSchemaTables" :key="`${table.schema || 'default'}-${table.name}`" :value="table.name">
                    {{ table.name }} · {{ table.type }}
                  </option>
                </select>
              </label>
              <label class="inline-field small">
                <span>每页</span>
                <select v-model.number="dbState.limit" @change="loadDbTablePreview(true)">
                  <option :value="50">50</option>
                  <option :value="100">100</option>
                  <option :value="200">200</option>
                  <option :value="500">500</option>
                </select>
              </label>
            </div>

            <div v-if="selectedDbTableInfo?.columns?.length" class="db-column-strip-scroll">
              <div class="db-column-strip">
                <span v-for="column in selectedDbTableInfo.columns" :key="column.name">
                  <b>{{ column.name }}</b>{{ column.type }}
                </span>
              </div>
            </div>

            
              <div v-if="dbState.tableBusy || dbState.rows.length" class="data-table db-preview-table">
              <table>
                <thead>
                  <tr>
                    <th v-for="col in dbState.columns" :key="col">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, rowIndex) in dbState.rows" :key="rowIndex">
                    <td v-for="col in dbState.columns" :key="col">{{ row[col] }}</td>
                  </tr>
                </tbody>
              </table>
              </div>

              <p v-else class="empty">
                {{ dbState.schemaBusy ? '正在读取数据库结构...' : '连接数据库后选择表，即可只读预览数据。' }}
              </p>

              <div class="toolbar db-pagination">
              <small>显示 {{ dbPreviewStart }}-{{ dbPreviewEnd }} / {{ dbState.totalRows }} 行</small>
              <div class="row-actions">
                <button class="ghost" type="button" :disabled="dbState.offset <= 0 || dbState.tableBusy" @click="changeDbPreviewPage(-1)">上一页</button>
                <b>{{ dbPreviewPage }} / {{ dbPreviewPages }}</b>
                <button class="ghost" type="button" :disabled="dbState.offset + dbState.limit >= dbState.totalRows || dbState.tableBusy" @click="changeDbPreviewPage(1)">下一页</button>
              </div>
              </div>
          
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'preview' || isKbDetailPage" class="module-page">
        <div class="module-title">
          <h2>{{ isKbDetailPage ? '知识库详情' : '知识库管理' }}</h2>
          <span v-if="!isKbDetailPage">选择一个知识库进入管理，或创建新的知识库。</span>
          <span v-else>当前知识库：{{ selectedKb?.kbName || detailKbId }}</span>
        </div>

        <template v-if="!isKbDetailPage">
          <div class="panel preview-create-panel">
            <div class="panel-head">
              <div>
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
                <h3>搜索知识库</h3>
              </div>
            </div>
            <label class="field">
              <span>按知识库名称搜索</span>
              <input v-model="kbSearchQuery" placeholder="输入知识库名称、标识或向量模型关键字" />
            </label>
          </div>

          <div class="panel preview-list-panel">
            <div class="panel-head">
              <div>
                <h3>已有知识库</h3>
              </div>
              <small>{{ filteredKbs.length }} / {{ kbs.length }} 个</small>
            </div>
            <div class="kb-card-scroll">
              <div class="kb-card-grid">
                <article v-for="kb in filteredKbs" :key="kb.kbId" :class="{ active: selectedKbId === kb.kbId }" @click="enterKb(kb.kbId)">
                  <div>
                    <strong>{{ kb.kbName }}</strong>
                    <small>ID：{{ kb.kbId }}</small>
                  </div>
                  <div class="metric-row">
                    <span>文件数 {{ kb.fileCount || 0 }}</span>
                    <span>{{ kb.vectorStoreType || 'faiss' }}</span>
                  </div>
                  <div class="toolbar">
                    <button type="button" @click.stop="enterKb(kb.kbId)">进入知识库</button>
                    <button
                      class="danger ghost icon-button delete-kb-button"
                      type="button"
                      :title="`删除知识库 ${kb.kbName}`"
                      :aria-label="`删除知识库 ${kb.kbName}`"
                      @click.stop="deleteKb(kb.kbId)"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24" focusable="false">
                        <path d="M3 6h18" />
                        <path d="M8 6V4h8v2" />
                        <path d="M19 6l-1 14H6L5 6" />
                        <path d="M10 11v5" />
                        <path d="M14 11v5" />
                      </svg>
                    </button>
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
              <h3>知识库：{{ selectedKb.kbName }}</h3>
            </div>
            <div class="toolbar">
              <div class="stat-grid compact">
                <div v-for="item in stats" :key="item.label" class="stat"><strong>{{ item.value }}</strong><span>{{ item.label }}</span></div>
              </div>
              <button class="ghost" type="button" @click="kbUploadExpanded = !kbUploadExpanded">{{ kbUploadExpanded ? '收起上传区' : '展开上传区' }}</button>
            </div>
          </div>
          <div v-if="kbUploadExpanded" class="upload-box inline-upload">
            <input ref="uploadInputRef" type="file" multiple accept=".pdf,.doc,.docx,.xlsx,.xls,.csv,.txt,.md,.json,.jsonl,image/*,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tif,.tiff" @change="onUploadChange" />
            <div v-if="uploadState.files.length" class="upload-file-grid kb-upload-grid">
              <article v-for="(file, index) in uploadState.files" :key="`${file.name}-${file.size}-${index}`" class="upload-file-card">
                <button type="button" class="upload-file-remove" @click="removeUploadFile(index)" :disabled="uploadState.busy" aria-label="移除文件">×</button>
                <strong>{{ file.name }}</strong>
                <small>{{ (file.size / 1024 / 1024).toFixed(2) }} 兆字节</small>
              </article>
            </div>
            <button type="button" class="ghost" @click="clearUploadSelection" :disabled="uploadState.busy">清空已选文件</button>
            <select v-model="uploadState.parseMethod">
              <option value="original">基础解析（快，传统文字识别）</option>
              <option value="olmocr">增强解析（慢，多模态大模型）</option>
              <option value="mineru">MinerU（文档解析/表格增强）</option>
            </select>
            <button type="button" @click="uploadFiles" :disabled="uploadState.busy">上传并入库</button>
            <small>{{ uploadState.message }}</small>
          </div>
        </div>

        <div v-if="isKbDetailPage && selectedKb" class="sub-tabs">
          <button type="button" :class="{ active: kbSubTab === 'files' }" @click="kbSubTab = 'files'">文件库管理</button>
          <button type="button" :class="{ active: kbSubTab === 'chunks' }" @click="kbSubTab = 'chunks'; refreshChunks()">知识块视图</button>
          <button type="button" :class="{ active: kbSubTab === 'images' }" @click="kbSubTab = 'images'; loadImages()">图像管理</button>
          <button type="button" :class="{ active: kbSubTab === 'numbers' }" @click="kbSubTab = 'numbers'">数值管理</button>
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'files'" class="panel files-workbench">
          <div class="panel-head">
            <div>
              <h3>文件列表与预览</h3>
            </div>
            <div class="inline-field search-field">
              <input
                v-model="selectedFileSearchText"
                list="file-search-options"
                placeholder="搜索文件名或标识"
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
            <div class="file-table-body">
              <div v-for="file in filteredFiles" :key="file.fileId" :class="['file-row', { active: selectedFileId === file.fileId }]" @click="openFilePreview(file.fileId)">
                <span><input v-model="selectedFileIds" :value="file.fileId" type="checkbox" @click.stop /></span>
                <span class="file-name">{{ file.fileName || file.fileId }}</span>
                <span>{{ documentTypeLabel(file) }}</span>
                <span>{{ parseMethodLabel(file.parseMethod, file.parser || (file.type === 'excel' ? 'pandas' : '')) }}</span>
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
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'chunks'" class="panel chunks-workbench">
          <div class="panel-head">
            <div>
              <h3>知识块视图</h3>
            </div>
            <div class="toolbar">
              <button type="button" @click="refreshChunks()">刷新知识块</button>
              <button class="ghost" type="button" @click="resetChunkFilters">清空筛选</button>
            </div>
          </div>

          <div class="chunk-stat-grid">
            <div class="stat"><strong>{{ chunkState.stats.total }}</strong><span>知识块总数</span></div>
            <div class="stat"><strong>{{ chunkState.stats.text }}</strong><span>文本块</span></div>
            <div class="stat"><strong>{{ chunkState.stats.image }}</strong><span>图像块</span></div>
            <div class="stat"><strong>{{ chunkState.stats.files }}</strong><span>索引文件数</span></div>
          </div>

          <div class="toolbar chunk-toolbar">
            <label class="inline-field">
              <span>来源文件</span>
              <select v-model="selectedChunkFileId" @change="loadChunks(true)">
                <option value="">全部文件</option>
                <option v-for="file in files" :key="file.fileId" :value="file.fileId">{{ file.fileName || file.fileId }}</option>
              </select>
            </label>
            <label class="inline-field search-field chunk-search-field">
              <span>搜索知识块</span>
              <input v-model="chunkState.query" placeholder="搜索块内容、文件标识或元数据" @keyup.enter="loadChunks(true)" />
            </label>
            <label class="inline-field small">
              <span>每页</span>
              <select v-model.number="chunkState.limit" @change="loadChunks(true)">
                <option :value="25">25</option>
                <option :value="50">50</option>
                <option :value="100">100</option>
                <option :value="200">200</option>
              </select>
            </label>
            <button type="button" @click="loadChunks(true)">查询</button>
          </div>

          <div v-if="chunkState.busy" class="empty">正在加载知识块...</div>
          <div v-else-if="chunkState.chunks.length" class="chunk-list">
            <article v-for="chunk in chunkState.chunks" :key="chunk.id" class="chunk-card">
              <div class="chunk-card-head">
                <div class="chunk-title">
                  <div class="chunk-title-line">
                    <b>#{{ chunk.ordinal }}</b>
                    <strong>{{ chunk.headerPath || chunk.source || '未命名知识块' }}</strong>
                  </div>
                  <small>
                    {{ chunk.fileName || chunk.fileId }}
                    <template v-if="chunk.page"> · 第 {{ chunk.page }} 页</template>
                  </small>
                </div>
                <div class="chunk-badges">
                  <b :class="['badge', chunk.type === 'image' ? 'busy' : 'ok']">{{ chunkTypeLabel(chunk.type) }}</b>
                  <b class="badge warn">{{ chunk.charCount || 0 }} 字符</b>
                </div>
              </div>

              <div v-if="chunk.imagePath" class="chunk-image-preview">
                <img :src="chunkImageSrc(chunk)" :alt="chunk.imagePath" />
              </div>

              <div class="rendered-markdown chunk-content chunk-rendered" v-html="chunkContentHtml(chunkPreview(chunk.content))"></div>

              <div v-if="chunkMetadataRows(chunk).length" class="chunk-meta-grid">
                <span v-for="row in chunkMetadataRows(chunk)" :key="`${chunk.id}-${row.label}`"><b>{{ row.label }}</b>{{ row.value }}</span>
              </div>

              <details class="chunk-detail">
                <summary>查看完整知识块</summary>
                <div class="rendered-markdown chunk-content chunk-rendered full" v-html="chunkContentHtml(chunk.content)"></div>
              </details>

              <div class="toolbar chunk-actions">
                <button class="ghost" type="button" @click="openChunkSource(chunk)">查看来源文件</button>
              </div>
            </article>
          </div>
          <p v-else class="empty">当前筛选条件下没有知识块。请先构建索引，或调整文件和关键词筛选。</p>

          <div class="toolbar chunk-pagination">
            <small>显示 {{ chunkPageStart }}-{{ chunkPageEnd }} / {{ chunkState.total }} 个知识块</small>
            <div class="row-actions">
              <button class="ghost" type="button" :disabled="chunkState.offset <= 0 || chunkState.busy" @click="changeChunkPage(-1)">上一页</button>
              <b>{{ chunkCurrentPage }} / {{ chunkTotalPages }}</b>
              <button class="ghost" type="button" :disabled="chunkState.offset + chunkState.limit >= chunkState.total || chunkState.busy" @click="changeChunkPage(1)">下一页</button>
            </div>
          </div>
        </div>

        <div v-if="isKbDetailPage && selectedKb && kbSubTab === 'images'" class="panel images-workbench">
          <div class="panel-head">
            <div><h3>图像管理</h3></div>
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
            <article v-for="item in imageState.images" :key="`${item.fileId}-${item.old_img_name || item.base_img_path || item.imagePath || item.img_name}`" class="image-card">
              <img :src="imageSrc(item)" alt="已提取图片" />
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

      <FileManagerPage
        v-if="!isKbDetailPage && activeTab === 'file-manager'"
        v-model:wellSearchQuery="wellSearchQuery"
        v-model:standardSearchQuery="standardSearchQuery"
        :file-manager-state="fileManagerState"
        :selected-well="selectedWell"
        :filtered-standard-documents="filteredStandardDocuments"
        :filtered-standard-groups="filteredStandardGroups"
        :well-alias-text="wellAliasText"
        :well-category-count="wellCategoryCount"
        :document-key="documentKey"
        :document-type-label="documentTypeLabel"
        :parse-method-label="parseMethodLabel"
        :select-well="selectWell"
        :load-file-manager="loadFileManager"
        :open-managed-file-preview="openManagedFilePreview"
        :active-preview-kb-id="activePreviewKbId"
        :selected-preview-file-id="selectedPreviewFileId"
        :preview-file="previewFile"
        :preview-kb-label="previewKbLabel"
        :preview-kind="previewKind"
        :original-preview-url="originalPreviewUrl"
        :pdf-page-preview-url="pdfPagePreviewUrl"
        :preview-state="previewState"
        :preview-rows="previewRows"
        :preview-columns="previewColumns"
        :chunk-content-html="chunkContentHtml"
        :load-preview="loadPreview"
        :change-pdf-preview-page="changePdfPreviewPage"
      />

      <section v-if="!isKbDetailPage && activeTab === 'preprocess'" class="module-page">
        <div class="module-title">
          <h2>数据预处理</h2>
          <span>上传表格、数据文件或测井文件，选择多个预处理方法，生成标准化结果后再保存到知识库。</span>
        </div>

        <div class="preprocess-grid">
          <div class="panel preprocess-flow">
            <div class="preprocess-step">
              <div class="panel-head"><div><h3>上传文件</h3></div></div>
              <div class="form-grid">
                <label class="field">
                  <span>选择一个或多个结构化文件或测井文件</span>
                  <input ref="preprocessInputRef" type="file" multiple accept=".csv,.xlsx,.xls,.json,.jsonl,.las" @change="onPreprocessSourceChange" />
                </label>
                <div v-if="preprocessState.sourceFiles.length || preprocessState.jobs.length" class="upload-file-grid preprocess-upload-grid">
                  <article v-for="(file, index) in preprocessState.sourceFiles" :key="`${file.name}-${file.size}-${index}`" class="upload-file-card preprocess-upload-card">
                    <button type="button" class="upload-file-remove" @click="removePreprocessSourceFile(index)" :disabled="preprocessState.uploading" aria-label="移除文件">×</button>
                    <strong>{{ file.name }}</strong>
                    <small>{{ (file.size / 1024 / 1024).toFixed(2) }} 兆字节</small>
                    <small :class="preprocessPendingSourceFiles.includes(file) ? 'pending' : 'done'">
                      {{ preprocessPendingSourceFiles.includes(file) ? '待上传' : '已上传到工作台' }}
                    </small>
                    <!-- {{ file.type || '未知类型' }}</small>-->  
                  </article>
                  <button class="upload-file-card preprocess-upload-add-card" type="button" @click="triggerPreprocessFilePicker" :disabled="preprocessState.uploading">
                    <span>+</span>
                    <strong>继续添加文件</strong>
                  </button>
                </div>
                <div class="toolbar preprocess-upload-toolbar">
                  <button class="ghost" type="button" @click="clearPreprocessSelection" :disabled="preprocessState.uploading">清空工作台</button>
                  <button class="primary-red" type="button" @click="uploadPreprocessSource" :disabled="!preprocessPendingSourceFiles.length || preprocessState.uploading">
                    {{ preprocessState.uploading ? '上传中...' : `上传 ${preprocessPendingSourceFiles.length} 个文件到预处理工作台` }}
                  </button>
                </div>
                <small v-if="preprocessState.sourceFiles.length">已选择 {{ preprocessState.sourceFiles.length }} 个文件，其中 {{ preprocessPendingSourceFiles.length }} 个待上传。</small>
                <small v-if="preprocessState.jobs.length" class="status-line">工作台已有 {{ preprocessState.jobs.length }} 个任务，继续上传不会清空已有任务。</small>
              </div>
            </div>

            <div class="preprocess-step">
              <div class="panel-head"><div><h3>选择预处理方法</h3></div></div>
              <div class="preprocess-method-strip">
                <article v-for="method in preprocessSelectedMethodCards" :key="method.id" class="preprocess-method-card">
                  <button class="method-remove" type="button" @click="removePreprocessMethod(method.id)">×</button>
                  <span class="method-index">{{ method.index }}</span>
                  <strong>{{ method.name }}</strong>
                  <p>{{ method.description }}</p>
                  <div v-if="method.algorithms?.length" class="preprocess-method-card-footer">
                    <span>目前已选：<b>{{ method.selectedAlgorithmName }}</b></span>
                    <button class="method-algorithm-change" type="button" @click="openPreprocessAlgorithmDialog(method.id)">选择其他</button>
                  </div>
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
              <Teleport to="body">
                <div
                  v-if="preprocessAlgorithmDialog.open && preprocessAlgorithmDialogMethod"
                  class="preprocess-algorithm-dialog"
                  role="dialog"
                  aria-modal="false"
                  :aria-label="`${preprocessAlgorithmDialogMethod.name}算法选择`"
                  :style="{ left: `${preprocessAlgorithmDialog.left}px`, top: `${preprocessAlgorithmDialog.top}px` }"
                  @pointermove="movePreprocessAlgorithmDialog"
                  @pointerup="stopPreprocessAlgorithmDialogDrag"
                  @pointercancel="stopPreprocessAlgorithmDialogDrag"
                >
                  <div class="preprocess-algorithm-dialog-head" @pointerdown="startPreprocessAlgorithmDialogDrag">
                    <div>
                      <strong>{{ preprocessAlgorithmDialogMethod.name }}</strong>
                      <small>选择一种算法</small>
                    </div>
                    <button type="button" aria-label="关闭算法选择" @pointerdown.stop @click="closePreprocessAlgorithmDialog">×</button>
                  </div>
                  <div class="preprocess-algorithm-options">
                    <button
                      v-for="algorithm in preprocessAlgorithmDialogMethod.algorithms"
                      :key="algorithm.id"
                      type="button"
                      :class="{ active: preprocessAlgorithmDialog.draftAlgorithmId === algorithm.id }"
                      @click="preprocessAlgorithmDialog.draftAlgorithmId = algorithm.id"
                    >
                      <strong>{{ algorithm.name }}</strong>
                      <span>{{ algorithm.description }}</span>
                    </button>
                  </div>
                  <div class="preprocess-algorithm-dialog-actions">
                    <button class="primary-red" type="button" :disabled="!preprocessAlgorithmDialog.draftAlgorithmId" @click="savePreprocessAlgorithm">保存</button>
                  </div>
                </div>
              </Teleport>
            </div>

            <div class="preprocess-step">
              <div class="panel-head"><div><h3>开始预处理</h3></div></div>
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
                  <h3>流程产物预览</h3>
                </div>
                <!--<small v-if="preprocessSelectedJob">当前任务：{{ preprocessSelectedJob.fileName || preprocessSelectedJob.jobId }}</small>-->
              </summary>
              <label class="field preprocess-preview-search">
                <span>选择已处理文件</span>
                <div class="preprocess-preview-controls">
                  <select :value="preprocessState.previewJobId" @change="onPreprocessPreviewSelectChange">
                    <option value="" disabled>从流程产物文件中选择</option>
                    <option v-for="job in preprocessJobCards" :key="`preprocess-preview-select-${job.jobId || job.fileName}`" :value="job.jobId || ''">
                      {{ job.fileName || job.jobId }} · {{ job.status === 'done' ? '已完成' : job.status === 'running' ? '处理中' : job.status === 'failed' ? '失败' : '已上传' }}
                    </option>
                  </select>
                </div>
              </label>
              <div class="preprocess-preview-current">
                <div class="preprocess-preview-current-head">
                  <strong>{{ preprocessSelectedJob?.fileName || preprocessSelectedJob?.jobId || '当前文件' }}</strong>
                  <button v-if="preprocessSelectedJob?.status === 'done'" class="ghost" type="button" @click="downloadPreprocessExcel">下载文件</button>
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
                <div v-if="preprocessPreviewKind === 'table'" class="data-table preprocess-data-table">
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
                <div v-else-if="preprocessPreviewKind === 'image'" class="preprocess-file-preview preprocess-image-preview">
                  <img :src="preprocessPreviewUrl" :alt="preprocessSelectedJob?.fileName || '预处理产物图片'" />
                </div>
                <div v-else-if="preprocessPreviewKind === 'markdown'" class="preprocess-file-preview preprocess-text-preview">
                  <div v-if="preprocessState.previewLoading" class="empty">加载预览中...</div>
                  <div v-else-if="preprocessState.previewText" class="rendered-markdown" v-html="chunkContentHtml(preprocessState.previewText)"></div>
                  <p v-else-if="preprocessState.previewError" class="empty">{{ preprocessState.previewError }}</p>
                  <p v-else class="empty">当前 Markdown 产物暂无可显示内容。</p>
                </div>
                <div v-else-if="preprocessPreviewKind === 'json' || preprocessPreviewKind === 'text'" class="preprocess-file-preview preprocess-text-preview">
                  <div v-if="preprocessState.previewLoading" class="empty">加载预览中...</div>
                  <pre v-else-if="preprocessState.previewText">{{ preprocessState.previewText }}</pre>
                  <p v-else-if="preprocessState.previewError" class="empty">{{ preprocessState.previewError }}</p>
                  <p v-else class="empty">当前文本产物暂无可显示内容。</p>
                </div>
                <iframe v-else-if="preprocessPreviewKind === 'frame'" class="preprocess-file-frame" :src="preprocessPreviewUrl" title="预处理产物预览"></iframe>
                <p v-else class="empty">当前产物暂不支持在线预览，可直接下载或保存到知识库。</p>
              </div>
            </details>

            <div class="preprocess-step">
              <div class="panel-head"><div><h3>保存到知识库</h3></div></div>
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
              <button type="button" @click="savePreprocessedToKb" :disabled="preprocessState.saving || !preprocessDoneJobs.length">
                {{ preprocessState.saving ? '保存中...' : `保存 ${preprocessDoneJobs.length} 个预处理文件到知识库` }}
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
            <h3>{{ previewFile?.fileName || previewFile?.fileId || '文件预览' }}</h3>
            <small>{{ previewKbLabel || '当前知识库' }} · {{ documentTypeLabel(previewFile) }} · {{ parseMethodLabel(previewFile?.parseMethod, previewFile?.parser) }}</small>
          </div>
          <button type="button" class="ghost" @click="closePreviewModal">关闭</button>
        </div>
        <div class="original-preview">
          <iframe v-if="previewKind === 'pdf'" class="original-preview-frame" :src="originalPreviewUrl" title="文件预览"></iframe>
          <div v-else-if="previewKind === 'document'" class="document-view modal-document-view">
            <div v-if="previewState.busy" class="empty">加载文档内容中...</div>
            <div
              v-else-if="previewState.content"
              class="rendered-markdown document-rendered"
              v-html="chunkContentHtml(previewState.content)"
            ></div>
            <div v-else class="empty">当前文档尚无可预览内容，请先解析文档。</div>
          </div>
          <div v-else-if="previewKind === 'table'" class="table-preview modal-table-preview">
            <div class="toolbar sheet-toolbar" v-if="Object.keys(previewState.sheets).length">
              <label class="inline-field small">
                <span>表页</span>
                <select v-model="previewState.selectedSheet"><option v-for="(_, sheet) in previewState.sheets" :key="sheet" :value="sheet">{{ sheet }}</option></select>
              </label>
              <span class="sheet-summary">{{ previewRows.length ? `共 ${previewRows.length} 行` : '暂无行数据' }}</span>
            </div>
            <div v-if="previewState.busy" class="empty">加载表格中...</div>
            <div v-else-if="previewRows.length" class="data-table">
              <table>
                <thead><tr><th v-for="col in previewColumns" :key="col">{{ col }}</th></tr></thead>
                <tbody><tr v-for="(row, index) in previewRows.slice(0, 200)" :key="index"><td v-for="col in previewColumns" :key="col">{{ row[col] }}</td></tr></tbody>
              </table>
            </div>
            <div v-else class="empty">当前表格没有可显示的数据。</div>
          </div>
          <div v-else-if="previewKind === 'image'" class="document-view modal-image-view">
            <img :src="originalPreviewUrl" :alt="previewFile?.fileName || '图片预览'" />
            <div v-if="previewState.content" class="markdown-view image-description-view">
              <h4>图片描述</h4>
              <pre>{{ previewState.content }}</pre>
            </div>
          </div>
          <div v-else class="document-view modal-file-view">
            <iframe class="original-preview-frame" :src="originalPreviewUrl" title="文件预览"></iframe>
          </div>
        </div>
      </div>
    </div>

    <div v-if="toast" :class="['toast', toast.type]">{{ toast.text }}</div>
  </div>
</template>

<style scoped src="./assets/app.css"></style>
