import type { SearchResult } from '@/types/app'

type ApiUrl = (path: string, params?: Record<string, string | number | boolean | undefined>) => string

type MarkdownRendererContext = {
  apiUrl: ApiUrl
  getSelectedKbId: () => string
}

export function createMarkdownRenderer({ apiUrl, getSelectedKbId }: MarkdownRendererContext) {
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

  function decodeHtmlEntities(value: string) {
    const text = String(value || '')
    if (!text.includes('&')) return text

    if (typeof document !== 'undefined') {
      const textarea = document.createElement('textarea')
      textarea.innerHTML = text
      return textarea.value
    }

    return text
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&amp;/g, '&')
  }

  function searchResultImageUrl(item: SearchResult, rawUrl: string) {
    const url = rawUrl.trim().replace(/^<|>$/g, '')
    if (/^(https?:|blob:|data:image\/)/i.test(url)) return url
    if (/^javascript:/i.test(url)) return '#'

    const cleanPath = url.split('?')[0] || ''
    const lastSegment = cleanPath.split(/[\\/]/).filter(Boolean).pop() || cleanPath
    const imageName = decodeURIComponent(lastSegment)
    const fileId = searchResultFileId(item)
    const kbId = getSelectedKbId()
    if (!kbId || !fileId || !imageName) return url
    return apiUrl('/pdf/images', { kbId, fileId, imagePath: imageName })
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

  function looksLikeMarkdownTableBlock(markdown: string) {
    const lines = String(markdown || '')
      .replace(/\r\n/g, '\n')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)

    if (lines.length < 2) return false
    for (let index = 0; index < lines.length - 1; index += 1) {
      const line = lines[index] || ''
      if (line.includes('|') && isMarkdownTableSeparator(lines[index + 1] || '')) return true
    }
    return false
  }

  function looksLikeLoosePipeTableStart(lines: string[], index: number) {
    const current = lines[index] || ''
    const next = lines[index + 1] || ''
    if (isMarkdownTableSeparator(next)) return false
    const pipeCount = (line: string) => (line.match(/\|/g) || []).length
    return pipeCount(current) >= 2 && pipeCount(next) >= 2
  }

  function renderLoosePipeTable(tableLines: string[], item: SearchResult) {
    const rows = tableLines
      .map(splitMarkdownTableRow)
      .filter((cells) => cells.length > 1 && cells.some((cell) => cell.trim()))
    if (!rows.length) return ''

    const width = Math.max(...rows.map((cells) => cells.length))
    const normalizedRows = rows.map((cells) => Array.from({ length: width }, (_, index) => cells[index] || ''))
    const headerCells = normalizedRows[0] || []
    const bodyRows = normalizedRows.slice(1)
    const head = headerCells.map((cell) => `<th>${renderMarkdownInline(cell, item)}</th>`).join('')
    const body = bodyRows
      .map((cells) => `<tr>${cells.map((cell) => `<td>${renderMarkdownInline(cell, item)}</td>`).join('')}</tr>`)
      .join('')
    return `<div class="md-table-wrap md-loose-table"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
  }

  function parseFieldValueLine(line: string) {
    const cleaned = String(line || '').replace(/^\s*\[\d+\]\s*/, '')
    const match = cleaned.match(/^\s*([^:\n：]{1,80})\s*[:：]\s*(.*?)\s*$/)
    if (!match) return null
    const key = (match[1] || '').trim()
    const value = (match[2] || '').trim()
    if (!key || key.startsWith('[')) return null
    return { key, value }
  }

  function normalizeTableKey(value: unknown) {
    return String(value || '').toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]+/g, '')
  }

  function tableKeyMatchScore(key: string, query: string) {
    const normalizedKey = normalizeTableKey(key)
    const normalizedQuery = normalizeTableKey(query)
    if (normalizedKey.length < 2 || !normalizedQuery) return 0
    if (normalizedQuery.includes(normalizedKey)) return 100 + normalizedKey.length
    if (normalizedKey.includes(normalizedQuery) && normalizedQuery.length >= 2) return 80 + normalizedQuery.length
    let bestSuffixScore = 0
    for (let start = 1; start < normalizedKey.length - 1; start += 1) {
      const suffix = normalizedKey.slice(start)
      if (suffix.length >= 2 && normalizedQuery.includes(suffix)) bestSuffixScore = Math.max(bestSuffixScore, 10 + suffix.length)
    }
    return bestSuffixScore
  }

  function fieldRowsFromText(value: string) {
    const blocks = String(value || '').replace(/\r\n/g, '\n').split(/\n\s*\n/)
    return blocks
      .map((block) => {
        const row: Record<string, string> = {}
        block.split('\n').forEach((line) => {
          const parsed = parseFieldValueLine(line)
          if (parsed?.key) row[parsed.key] = parsed.value
        })
        return row
      })
      .filter((row) => Object.entries(row).filter(([key, value]) => key !== '来源文件' && value).length >= 3)
  }

  function directFieldResultHtml(item: SearchResult, query: string) {
    const rows = fieldRowsFromText(searchResultText(item))
    if (!rows.length || !query.trim()) return ''
    const metadataKeys = new Set(['工作表', '行号', '来源文件'])
    const candidateFields: Array<{ key: string; score: number }> = []

    rows.forEach((row) => {
      Object.entries(row).forEach(([key, value]) => {
        if (metadataKeys.has(key) || !value) return
        const score = tableKeyMatchScore(key, query)
        if (score) candidateFields.push({ key, score })
      })
    })

    if (!candidateFields.length) return ''
    candidateFields.sort((a, b) => b.score - a.score)
    const targetField = candidateFields[0]?.key || ''
    if (!targetField) return ''

    const normalizedQuery = normalizeTableKey(query)
    const rowScore = (row: Record<string, string>) => Object.entries(row).reduce((score, [key, value]) => {
      if (key === targetField || key === '来源文件') return score
      const normalizedValue = normalizeTableKey(value)
      const normalizedKey = normalizeTableKey(key)
      let next = score
      if (normalizedValue.length >= 2 && normalizedQuery.includes(normalizedValue)) next += 3
      if (normalizedKey.length >= 2 && normalizedQuery.includes(normalizedKey)) next += 1
      return next
    }, 0)

    const sortedRows = rows
      .filter((row) => row[targetField])
      .sort((a, b) => rowScore(b) - rowScore(a))
    const row = sortedRows[0]
    if (!row) return ''

    const sourceParts = [
      row['工作表'] ? `工作表 ${row['工作表']}` : '',
      row['行号'] ? `第 ${row['行号']} 行` : '',
      row['来源文件'] || '',
    ].filter(Boolean)
    const source = sourceParts.length ? `<p class="md-field-source">来源：${sourceParts.map(escapeHtml).join('，')}</p>` : ''
    const value = row[targetField] || ''
    const compact = `<div class="md-direct-field"><strong>${escapeHtml(targetField)}</strong><span>${renderMarkdownInline(value, item)}</span></div>${source}`
    const details = renderFieldValueTable(Object.entries(row).map(([key, rowValue]) => `${key}: ${rowValue}`), item)
    return `${compact}<details class="md-field-details"><summary>查看命中行</summary>${details}</details>`
  }

  function looksLikeFieldValueTableStart(lines: string[], index: number) {
    let count = 0
    for (let cursor = index; cursor < Math.min(lines.length, index + 8); cursor += 1) {
      const line = lines[cursor] || ''
      if (!line.trim()) break
      if (parseFieldValueLine(line)) count += 1
    }
    return count >= 3
  }

  function renderFieldValueTable(tableLines: string[], item: SearchResult) {
    const rows = tableLines
      .map(parseFieldValueLine)
      .filter((row): row is { key: string; value: string } => Boolean(row))
    if (!rows.length) return ''
    const body = rows
      .map((row) => `<tr><th>${renderMarkdownInline(row.key, item)}</th><td>${renderMarkdownInline(row.value, item)}</td></tr>`)
      .join('')
    return `<div class="md-table-wrap md-field-table"><table><tbody>${body}</tbody></table></div>`
  }

  function renderHtmlTableBlock(tableHtml: string) {
    try {
      const doc = new DOMParser().parseFromString(tableHtml, 'text/html')
      const table = doc.querySelector('table')
      if (!table) return `<pre class="md-code"><code>${escapeHtml(tableHtml)}</code></pre>`

      const allowedTags = new Set(['TABLE', 'THEAD', 'TBODY', 'TFOOT', 'TR', 'TH', 'TD', 'CAPTION', 'COLGROUP', 'COL', 'BR'])
      const allowedAttrs = new Set(['rowspan', 'colspan', 'scope'])

      const renderNode = (node: Node): string => {
        if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent || '')
        if (!(node instanceof Element)) return ''

        const tag = node.tagName.toUpperCase()
        if (!allowedTags.has(tag)) return escapeHtml(node.textContent || '')

        if (tag === 'BR') return '<br>'

        const attrs = Array.from(node.attributes)
          .filter((attr) => allowedAttrs.has(attr.name.toLowerCase()))
          .map((attr) => ` ${attr.name}="${escapeHtml(attr.value)}"`)
          .join('')
        const children = Array.from(node.childNodes).map(renderNode).join('')
        return `<${tag.toLowerCase()}${attrs}>${children}</${tag.toLowerCase()}>`
      }

      if (!table.querySelector('th') && !table.querySelector('thead')) {
        const firstRow = table.querySelector('tr')
        if (firstRow) {
          Array.from(firstRow.children).forEach((cell) => {
            if (cell.tagName.toUpperCase() !== 'TD') return
            const th = doc.createElement('th')
            Array.from(cell.attributes).forEach((attr) => th.setAttribute(attr.name, attr.value))
            th.innerHTML = cell.innerHTML
            cell.replaceWith(th)
          })
        }
      }

      return `<div class="md-table-wrap md-html-table">${renderNode(table)}</div>`
    } catch {
      return `<pre class="md-code"><code>${escapeHtml(tableHtml)}</code></pre>`
    }
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
      /<table\b/i.test(line) ||
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
    const markdown = decodeHtmlEntities(String(value || '').replace(/\r\n/g, '\n').replace(/^\uFEFF/, ''))
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
        const fenceLanguage = String(fence[1] || '').toLowerCase()
        index += 1
        while (index < lines.length && !/^\s*```/.test(lines[index] || '')) {
          codeLines.push(lines[index] || '')
          index += 1
        }
        if (index < lines.length) index += 1

        const codeText = codeLines.join('\n')
        if (/<table\b/i.test(codeText)) {
          html.push(renderHtmlTableBlock(codeText))
        } else if (['md', 'markdown', 'table'].includes(fenceLanguage) || looksLikeMarkdownTableBlock(codeText)) {
          html.push(`<div class="md-fenced-markdown">${renderMarkdown(codeText, item)}</div>`)
        } else {
          html.push(`<pre class="md-code"><code>${escapeHtml(codeText)}</code></pre>`)
        }
        continue
      }

      if (/^<table\b/i.test(trimmed) || /<table\b/i.test(line)) {
        const tableLines = [line]
        index += 1
        while (index < lines.length && !/<\/table>/i.test(lines[index] || '')) {
          tableLines.push(lines[index] || '')
          index += 1
        }
        if (index < lines.length) {
          tableLines.push(lines[index] || '')
          index += 1
        }
        html.push(renderHtmlTableBlock(tableLines.join('\n')))
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

      if (looksLikeLoosePipeTableStart(lines, index)) {
        const tableLines = [line]
        index += 1
        while (
          index < lines.length &&
          (lines[index] || '').trim() &&
          (lines[index] || '').includes('|') &&
          !isMarkdownTableSeparator(lines[index] || '')
        ) {
          tableLines.push(lines[index] || '')
          index += 1
        }
        html.push(renderLoosePipeTable(tableLines, item))
        continue
      }

      if (looksLikeFieldValueTableStart(lines, index)) {
        const tableLines = [line]
        index += 1
        while (index < lines.length && (lines[index] || '').trim() && parseFieldValueLine(lines[index] || '')) {
          tableLines.push(lines[index] || '')
          index += 1
        }
        html.push(renderFieldValueTable(tableLines, item))
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

  function searchResultHtml(item: SearchResult, query = '') {
    return directFieldResultHtml(item, query) || renderMarkdown(searchResultText(item), item)
  }

  function chunkContentHtml(content: string) {
    return renderMarkdown(content, { content } as SearchResult)
  }

  function citationAsSearchResult(item: Record<string, unknown>): SearchResult {
    return {
      chunk_text: sourceStringValue(item.snippet),
      fileId: sourceStringValue(item.fileId),
      page: Number(item.page || 0) || undefined,
      score: Number(item.score || 0) || undefined,
      metadata: {
        page: item.page,
        previewUrl: item.previewUrl,
      },
    }
  }

  function citationHtml(item: Record<string, unknown>) {
    return renderMarkdown(sourceStringValue(item.snippet), citationAsSearchResult(item))
  }

  function sqlCellValue(row: Record<string, unknown>, column: string) {
    return sourceStringValue(row[column])
  }


  return {
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
  }
}
