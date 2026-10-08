import type { PreprocessMethod, QueryMode } from '@/types/app'

export const tabs = [
  { id: 'search', label: '多模态检索', icon: 'chat' },
  { id: 'preprocess', label: '数据预处理', icon: 'sigma' },
  { id: 'extract', label: '知识提取', icon: 'share' },
  { id: 'database', label: '结构化数据库', icon: 'database' },
  { id: 'preview', label: '知识库', icon: 'book' },
  { id: 'file-manager', label: '文件管理', icon: 'folder' },
] as const

export const queryModes: Array<{ id: QueryMode; label: string }> = [
  { id: 'vector', label: '向量检索' },
  { id: 'sql', label: '文本转数据库查询' },
  { id: 'hybrid', label: '两者都用' },
  { id: 'agent', label: '智能自动判断' },
]

export const extractionTemplates: Record<string, string> = {
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

export const preprocessMethods: PreprocessMethod[] = [
  {
    id: 'format_standardize',
    name: '格式归一化',
    description: '统一表格、数据文件和测井文件的格式、字段命名与基础类型。',
    defaultAlgorithm: 'regex_rules',
    algorithms: [
      { id: 'regex_rules', name: '正则表达式', description: '按现有规则统一表头、空白、空值与基础类型。' },
      { id: 'header_mapping', name: '表头映射与字段归一', description: '清理并映射字段名称，保留原始数据类型。' },
      { id: 'datetime_normalize', name: '时间格式统一', description: '识别日期时间字段并统一为标准时间类型。' },
    ],
  },
  {
    id: 'las_to_excel',
    name: '测井曲线转表格',
    description: '解析测井曲线、井信息和空值标记，并输出标准表格文件。',
    defaultAlgorithm: 'lasio_parse',
    algorithms: [
      { id: 'lasio_parse', name: 'LAS 读写解析', description: '解析 LAS 井信息、曲线和空值标记。' },
      { id: 'welly_align', name: '曲线管理与深度对齐', description: '按深度索引对齐多条测井曲线。' },
      { id: 'depth_resample', name: '深度等距重采样', description: '按统一深度间隔重采样曲线数据。' },
    ],
  },
  {
    id: 'dedupe',
    name: '冗余数据剔除',
    description: '识别重复行、空行和冗余记录，保留有效样本。',
    defaultAlgorithm: 'exact_duplicate',
    algorithms: [
      { id: 'exact_duplicate', name: '完全重复删除', description: '删除完全一致的重复记录和空行。' },
      { id: 'minhash_approx', name: 'MinHash 近似去重', description: '按文本分片签名识别近似重复记录。' },
      { id: 'record_linkage', name: '记录链接去重', description: '按归一化记录相似度合并重复项。' },
    ],
  },
  {
    id: 'missing_fill',
    name: '缺失补全',
    description: '按字段类型自动选择前向填充、中位数、众数或默认值补全。',
    defaultAlgorithm: 'statistical_fill',
    algorithms: [
      { id: 'statistical_fill', name: '统计量填充', description: '数值列用中位数，文本列用众数补全。' },
      { id: 'linear_interpolation', name: '线性插值', description: '按记录顺序对数值缺口执行线性插值。' },
      { id: 'knn_imputation', name: 'KNN 插补', description: '利用相似样本的邻域信息补全数值缺失。' },
    ],
  },
  {
    id: 'anomaly_correct',
    name: '异常纠错',
    description: '对数值异常、空白噪声和不规范值进行纠正或标记。',
    defaultAlgorithm: 'iqr',
    algorithms: [
      { id: 'iqr', name: '箱线图 IQR', description: '按四分位距识别并裁剪异常值。' },
      { id: 'three_sigma', name: '3σ 拉依达法则', description: '按均值正负三倍标准差识别异常值。' },
      { id: 'mad', name: 'MAD 中位数绝对偏差', description: '使用稳健统计量识别尖峰和离群点。' },
    ],
  },
  {
    id: 'unit_dimension_check',
    name: '单位统一与量纲校验',
    description: '按测试规则统一钻压、扭矩、立管压力、流量和温度单位。',
    defaultAlgorithm: 'combined_unit_rules',
    algorithms: [
      { id: 'combined_unit_rules', name: '组合单位规则', description: '综合列名、单位列和值内单位完成换算。' },
      { id: 'label_unit_mapping', name: '表头单位映射', description: '根据字段名中的单位标记执行换算。' },
      { id: 'cell_unit_parsing', name: '单元格单位解析', description: '解析数值后的单位文本并统一量纲。' },
    ],
  },
  {
    id: 'engineering_constraint_check',
    name: '工程范围/物理约束校验',
    description: '按测试阈值校验井深、钻压、扭矩、立管压力、流量、温度和转速。',
    defaultAlgorithm: 'boundary_clip',
    algorithms: [
      { id: 'boundary_clip', name: '工程边界裁剪', description: '将越界值裁剪到工程允许范围。' },
      { id: 'invalid_to_missing', name: '越界值置空', description: '将违反工程约束的数值标记为缺失。' },
      { id: 'constraint_flag', name: '物理约束标记', description: '保留原值并新增约束校验结果列。' },
    ],
  },
  {
    id: 'schema_standardize',
    name: '维度标准化',
    description: '统一列顺序、数据维度与标准化输出结构，增强异构兼容。',
    defaultAlgorithm: 'schema_mapping',
    algorithms: [
      { id: 'schema_mapping', name: '字段维度统一', description: '统一字段命名与输出结构。' },
      { id: 'min_max', name: 'Min-Max 归一化', description: '将数值字段缩放到 0 到 1 区间。' },
      { id: 'z_score', name: 'Z-Score 标准化', description: '按均值和标准差标准化数值字段。' },
    ],
  },
]

export const tableSuffixes = new Set(['csv', 'xlsx', 'xls', 'json', 'jsonl', 'las'])
export const imageSuffixes = new Set(['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'tif', 'tiff'])
