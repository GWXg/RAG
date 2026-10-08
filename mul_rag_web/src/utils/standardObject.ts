const STANDARD_OBJECT_KEYWORDS = [
  '陆上石油天然气',
  '海上石油天然气',
  '非常规油气',
  '已开发油田',
  '油气层',
  '页岩气',
  '煤层气',
  '致密油气',
  '陆上丛式同台井',
  '海上钻井',
  '海上固井',
  '套管侧钻井',
  '浅层大位移井',
  '大位移井',
  '小井眼',
  '水平井',
  '定向井',
  '直井',
  '固井',
  '钻井液',
  '钻井设备',
  '钻井队',
  '钻机',
  '钻头',
  '井控',
  '井场设备',
  '井场',
  '取心',
  '岩石',
  '个体防护装备',
  '个体防护',
  'HSE',
  '钻井现场',
  '钻井质量',
  '钻井工程设计',
]

const GENERIC_STANDARD_OBJECTS = new Set(['', '规范类文档', '规范文档', '标准规范', '其他规范对象'])
const STANDARD_UNIT_FALLBACK = '未明确油田/采油厂'
const STANDARD_UNIT_ALIASES = [
  ['胜利', '胜利油田'],
  ['中原', '中原油田'],
  ['江汉', '江汉油田'],
  ['河南', '河南油田'],
  ['华北', '华北油田'],
  ['华东', '华东油田'],
  ['西北', '西北油田'],
  ['西南', '西南油气田'],
  ['东北', '东北油田'],
  ['塔河', '塔河油田'],
  ['普光', '普光气田'],
  ['川东北', '川东北地区'],
] as const
const STANDARD_PLANT_ALIASES = [
  ['胜采', '胜利采油厂'],
  ['现河', '现河采油厂'],
  ['滨南', '滨南采油厂'],
  ['东辛', '东辛采油厂'],
  ['河口', '河口采油厂'],
  ['孤东', '孤东采油厂'],
  ['孤岛', '孤岛采油厂'],
  ['纯梁', '纯梁采油厂'],
  ['桩西', '桩西采油厂'],
  ['临盘', '临盘采油厂'],
  ['鲁明', '鲁明采油厂'],
  ['乐安', '乐安采油厂'],
] as const

type StandardDocumentLike = {
  fileId?: string
  fileName?: string
  standardObject?: string
  standardUnit?: string
}

export type BuiltStandardGroup<T extends StandardDocumentLike> = {
  object: string
  documentCount: number
  documents: T[]
}

function normalizeStandardObject(value?: string | null) {
  const object = (String(value || '')
    .replace(/[\s"'“”‘’`]+/g, '')
    .split(/[，,;；/、]/)[0] || '')
    .replace(/[：:。.!！?？\-_]+$/g, '')
    .trim()
  if (!object || GENERIC_STANDARD_OBJECTS.has(object) || object.length > 24) return ''
  return object
}

function normalizeStandardUnit(value?: string | null) {
  const unit = (String(value || '')
    .replace(/[\s"'“”‘’`]+/g, '')
    .split(/[，,;；/、]/)[0] || '')
    .replace(/^第\d+部分/g, '')
    .replace(/[：:。.!！?？\-_]+$/g, '')
    .trim()
  if (!unit || ['规范类文档', '标准规范', STANDARD_UNIT_FALLBACK].includes(unit) || unit.length > 24) return ''
  return unit
}

function cleanStandardTitle(value?: string | null) {
  const fileName = String(value || '')
    .split(/[\\/]/)
    .pop() || ''
  return fileName
    .replace(/\.[^.]+$/g, '')
    .replace(/[_+]+/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/^(?:QSH|Q\/SH|SY\/T|SY|GB\/T|GB|AQ)\s*[0-9A-Za-z_. -]+-?\d{4}\s*/i, '')
    .replace(/^\d{8}-\d+\s*/, '')
    .replace(/[（(]带水印[）)]/g, '')
    .trim()
    .replace(/^[-_：:\s]+|[-_：:\s]+$/g, '')
}

export function isGenericStandardObject(value?: string | null) {
  return !normalizeStandardObject(value)
}

export function isGenericStandardUnit(value?: string | null) {
  return !normalizeStandardUnit(value)
}

export function inferStandardObjectFromName(value?: string | null) {
  const title = cleanStandardTitle(value)
  const compactTitle = title.replace(/\s+/g, '')
  for (const keyword of STANDARD_OBJECT_KEYWORDS) {
    if (compactTitle.includes(keyword)) return keyword
  }

  const partMatch = title.match(/第\s*\d+\s*部分[：:]\s*([^：:，,。\s]{2,24})/)
  const partObject = normalizeStandardObject(partMatch?.[1])
  if (partObject) return partObject

  const nounMatch = compactTitle.match(
    /([\u4e00-\u9fffA-Za-z0-9]{2,24}?)(?:技术要求|工艺技术|推荐作法|作业规程|操作规程|设计与施工|配套标准|设置|条件|方法|要求)/,
  )
  const nounObject = normalizeStandardObject(nounMatch?.[1])
  if (nounObject) return nounObject

  return '其他规范对象'
}

export function standardDocumentObject(doc: StandardDocumentLike) {
  const explicit = normalizeStandardObject(doc.standardObject)
  if (explicit) return explicit
  return inferStandardObjectFromName(doc.fileName || doc.fileId || '')
}

export function inferStandardUnitFromName(value?: string | null) {
  const title = cleanStandardTitle(value)
  const compactTitle = title.replace(/\s+/g, '')

  if (compactTitle.includes('油田企业')) return '油田企业通用'
  if (compactTitle.includes('已开发油田')) return '已开发油田'
  if (compactTitle.includes('非常规油气田')) return '非常规油气田'
  if (compactTitle.includes('非常规油气')) return '非常规油气'

  for (const [alias, unit] of STANDARD_PLANT_ALIASES) {
    if (compactTitle.includes(alias)) return unit
  }

  const plantMatch = compactTitle.match(/([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:采油厂|采气厂|采油气厂|采油管理区|采气管理区|作业区))/)
  const plantUnit = normalizeStandardUnit(plantMatch?.[1])
  if (plantUnit) return plantUnit

  const fieldMatch = compactTitle.match(/([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:油气田|油田|气田))/)
  const fieldUnit = normalizeStandardUnit(fieldMatch?.[1])
  if (fieldUnit) return fieldUnit

  const regionMatch = compactTitle.match(/([\u4e00-\u9fffA-Za-z0-9]{2,18}?(?:地区|区块|油区))/)
  const regionUnit = normalizeStandardUnit(regionMatch?.[1])
  if (regionUnit) return regionUnit

  for (const [alias, unit] of STANDARD_UNIT_ALIASES) {
    if (compactTitle.includes(alias)) return unit
  }

  return STANDARD_UNIT_FALLBACK
}

export function standardDocumentUnit(doc: StandardDocumentLike) {
  const explicit = normalizeStandardUnit(doc.standardUnit)
  if (explicit) return explicit
  return inferStandardUnitFromName(doc.fileName || doc.fileId || '')
}

export function buildStandardGroupsFromDocuments<T extends StandardDocumentLike>(documents: T[]): BuiltStandardGroup<T>[] {
  const groupMap = new Map<string, BuiltStandardGroup<T>>()
  documents.forEach((doc) => {
    const object = standardDocumentUnit(doc)
    const group = groupMap.get(object) || { object, documentCount: 0, documents: [] }
    group.documents.push({ ...doc, standardUnit: object })
    group.documentCount = group.documents.length
    groupMap.set(object, group)
  })
  return Array.from(groupMap.values()).sort((a, b) => {
    if (a.object === STANDARD_UNIT_FALLBACK) return 1
    if (b.object === STANDARD_UNIT_FALLBACK) return -1
    return a.object.localeCompare(b.object, 'zh-CN')
  })
}
