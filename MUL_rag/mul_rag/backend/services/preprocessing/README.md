# 数据预处理规范模块

这个模块用于把异构结构化数据统一成可索引、可审计的标准 CSV。

## 能力边界

- 冗余剔除：重复列重命名、同义列合并、重复行删除、空行删除。
- 异常纠错：字段类型转换、数值上下限裁剪/置空/删行、枚举值近似纠错。
- 缺失补全：常量、0、均值、中位数、众数、前向/后向填充、插值。
- 格式统一：列名别名映射、必填列补齐、数据类型标准化、单位换算。
- 兼容处理：CSV、Excel 多 sheet、JSON/JSONL 统一输出为 `standardized.csv`。
- 审计追踪：生成 `report.json`，记录每一步处理数量、输出路径和警告。

## 配置示例

```json
{
  "standardVersion": "1.0",
  "datasetType": "drilling_realtime",
  "primaryKeys": ["well_name", "timestamp", "depth_m"],
  "columnSpecs": {
    "well_name": {
      "aliases": ["井名", "井号", "well"],
      "dtype": "string",
      "required": true,
      "fill": {"strategy": "constant", "value": "未知井"}
    },
    "timestamp": {
      "aliases": ["时间", "采集时间", "date_time"],
      "dtype": "datetime",
      "required": true
    },
    "depth_m": {
      "aliases": ["井深", "深度", "depth"],
      "dtype": "number",
      "unit": "m",
      "required": true,
      "anomaly": {"min": 0, "max": 12000, "action": "null"},
      "fill": {"strategy": "ffill"}
    },
    "rop_m_h": {
      "aliases": ["机械钻速", "ROP"],
      "dtype": "number",
      "unit": "m/h",
      "anomaly": {"min": 0, "max": 500, "action": "clip"},
      "fill": {"strategy": "median"}
    }
  },
  "dedupe": {"enabled": true, "subset": ["well_name", "timestamp", "depth_m"]}
}
```

## API

- `POST /api/v1/preprocess/run`
- `GET /api/v1/preprocess/report`

`run` 接口会在文件目录下写入：

- `preprocessed/standardized.csv`
- `preprocessed/report.json`
