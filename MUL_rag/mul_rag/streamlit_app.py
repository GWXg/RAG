import streamlit as st
import requests
import json
import time
import os
import re
import html
import io
import pandas as pd
import urllib.parse
import base64
from pathlib import Path

PARSE_MONITOR_MAX_RETRIES = int(os.getenv("PARSE_MONITOR_MAX_RETRIES", "9600"))
PARSE_STATUS_TIMEOUT = int(os.getenv("PARSE_STATUS_TIMEOUT", "5"))

# 设置页面配置
st.set_page_config(
    page_title="多模态 RAG 系统 (Python版)",
    page_icon="🤖",
    layout="wide"
)

# --- 自定义 CSS 样式 ---
st.markdown("""
<style>
    /* 全局字体优化 */
    html, body, [class*="css"] {
        font-family: 'PingFang SC', 'Helvetica Neue', Helvetica, 'Microsoft YaHei', Arial, sans-serif;
    }
    
    /* Level 1 Tabs (Top-level tabs: Multimodal Search, KB Preview) */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.8rem;
        font-weight: 700;
        padding-top: 5px;
        padding-bottom: 5px;
    }

    /* Level 2 Tabs (Nested tabs: File Mgmt, Image Mgmt, Numerical Mgmt) */
    /* Target stTabs that are inside a tab-panel (which implies nesting) */
    [data-baseweb="tab-panel"] .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.2rem;
        font-weight: 600;
    }
    
    /* 选中 Tab 的下划线颜色 */
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #FF4B4B;
    }

    /* 侧边栏/Expander 标题字体 */
    .streamlit-expanderHeader {
        font-size: 1.1rem !important;
        font-weight: 500;
        color: #31333F;
    }
    
    /* 按钮样式微调 */
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s;
        justify-content: flex-start !important; /* 文左对齐 */
        padding-left: 10px !important;
    }
    .stButton button:hover {
        border-color: #FF4B4B;
        color: #FF4B4B;
    }

    /* 列表头加粗 */
    .css-164nlkn {
        font-weight: bold;
        font-size: 1.05rem;
    }

    /* 数据表格标题 */
    h3 {
        font-size: 1.5rem !important;
        padding-bottom: 10px;
        border-bottom: 2px solid #f0f2f6;
        margin-bottom: 20px;
    }
    
    /* 分隔线间距 */
    hr {
        margin-top: 1.5rem;
        margin-bottom: 1.5rem;
    }
    
    /* Toast 样式 */
    .stToast {
        background-color: #ffffff;
        border: 1px solid #f0f2f6;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "kb_id" not in st.session_state:
    st.session_state.kb_id = None
if "file_id" not in st.session_state:
    st.session_state.file_id = None
if "session_id" not in st.session_state:
    st.session_state.session_id = f"sess_{int(time.time())}"
if "parsing_status" not in st.session_state:
    st.session_state.parsing_status = "idle"
if "preprocess_last_report" not in st.session_state:
    st.session_state.preprocess_last_report = None
if "preprocess_last_run_dir" not in st.session_state:
    st.session_state.preprocess_last_run_dir = None
if "preprocess_last_source_name" not in st.session_state:
    st.session_state.preprocess_last_source_name = None

# Sidebar 配置
# (Sidebar 已移除，功能移至 Tab 5)
api_base = "http://localhost:8002/api/v1"

# --- 辅助函数：新建知识库处理 ---
def handle_create_kb(key_suffix, existing_kbs, api_base):
    with st.expander("➕ 新建知识库", expanded=True): 
        with st.form(f"create_kb_form_{key_suffix}"):
            col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
            with col_c1:
                new_kb_name = st.text_input("知识库名称 (例如: 公司财报2023)", placeholder="请输入名称...", key=f"kb_name_{key_suffix}")
            with col_c2:
                vector_store_type = st.selectbox(
                    "向量库类型", 
                    options=["faiss", "milvus", "es"], 
                    index=0,
                    help="faiss: 本地索引; milvus/es: 后端需配置连接。",
                    key=f"vs_type_{key_suffix}"
                )
            with col_c3:
                embed_model = st.text_input("向量模型", value="bge-m3:latest", key=f"emb_model_{key_suffix}")
            
            submitted = st.form_submit_button("立即创建")
            if submitted:
                name_to_create = new_kb_name.strip()
                if not name_to_create:
                    st.error("请输入知识库名称")
                    return None
                elif any(k.get('kbName') == name_to_create or k.get('kbId') == name_to_create for k in existing_kbs):
                    st.error(f"知识库名称 '{name_to_create}' 已存在，请使用其他名称。")
                    return None
                else:
                    try:
                        # 构造创建请求
                        payload = {
                            "kbName": name_to_create, 
                            "embedModel": embed_model, 
                            "vectorStoreType": vector_store_type
                        }
                        r = requests.post(f"{api_base}/kb/create", json=payload)
                        
                        if r.status_code == 200:
                            st.success(f"知识库 '{name_to_create}' 创建成功！")
                            time.sleep(1)
                            st.rerun()
                            return r.json().get("kbId")
                        else:
                            st.error(f"创建失败: {r.text}")
                            return None
                    except Exception as e:
                        st.error(f"连接失败: {e}")
                        return None
    return None


def _file_error_text(result):
    if not result:
        return "未知错误"
    error = result.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("code") or str(error)
    return str(error or result.get("detail") or result.get("message") or "未知错误")


PREPROCESS_METHOD_CARDS = [
    {
        "id": "format_standardize",
        "name": "格式标准化",
        "description": "统一表头、空值标记、空白字符和基础类型。",
    },
    {
        "id": "las_to_excel",
        "name": "LAS 转 Excel",
        "description": "解析 LAS 测井曲线、井信息和空值标记，并输出标准 Excel 文件。",
    },
    {
        "id": "dedupe",
        "name": "冗余数据剔除",
        "description": "剔除空行、重复行和重复采集记录。",
    },
    {
        "id": "missing_fill",
        "name": "缺失补全",
        "description": "按列类型自动使用中位数、众数或空串补齐。",
    },
    {
        "id": "anomaly_correct",
        "name": "异常纠错",
        "description": "对数值列按 IQR 范围裁剪异常值。",
    },
    {
        "id": "schema_standardize",
        "name": "维度标准统一",
        "description": "统一字段命名，补齐异构表的输出维度。",
    },
]

PREPROCESS_METHOD_BY_ID = {item["id"]: item for item in PREPROCESS_METHOD_CARDS}


def load_preprocess_method_cards():
    try:
        response = requests.get(f"{api_base}/preprocess/methods", timeout=5)
        if response.status_code == 200:
            methods = response.json().get("methods", [])
            normalized = []
            for method in methods:
                if not isinstance(method, dict) or not method.get("id"):
                    continue
                normalized.append(
                    {
                        "id": str(method.get("id")),
                        "name": str(method.get("name") or method.get("id")),
                        "description": str(method.get("description") or ""),
                    }
                )
            if normalized:
                return normalized
    except Exception:
        pass
    return PREPROCESS_METHOD_CARDS


def collect_preprocess_artifacts(report: dict):
    artifacts = []

    def visit(value, prefix, method_name):
        if isinstance(value, dict):
            for key, item in value.items():
                label = f"{prefix} / {key}" if prefix else str(key)
                visit(item, label, method_name)
            return
        if isinstance(value, list):
            for idx, item in enumerate(value, start=1):
                visit(item, f"{prefix} {idx}", method_name)
            return
        if not isinstance(value, str):
            return

        text = value.strip()
        suffix = Path(text).suffix.lower()
        if not text or suffix not in {".csv", ".xlsx", ".xls", ".json", ".png", ".jpg", ".jpeg", ".txt", ".md"}:
            return
        artifacts.append(
            {
                "method": method_name,
                "label": prefix or Path(text).name,
                "path": text,
                "name": Path(text).name,
                "suffix": suffix.lstrip(".") or "file",
            }
        )

    for stage in report.get("methodReports", []) or []:
        if not isinstance(stage, dict):
            continue
        method_name = stage.get("name") or stage.get("method") or "预处理方法"
        operations = stage.get("operations") or {}
        if not isinstance(operations, dict):
            continue
        visit(operations.get("artifacts"), "产物", method_name)
        visit(operations.get("originalProgramArtifacts"), "原程序产物", method_name)
    return artifacts


def render_artifact_preview(name: str, data: bytes, suffix: str):
    suffix = suffix.lower().lstrip(".")
    try:
        if suffix == "csv":
            df = pd.read_csv(io.BytesIO(data))
            st.dataframe(df.head(300), use_container_width=True, height=260)
            st.caption(f"预览 {min(len(df), 300)} / {len(df)} 行")
        elif suffix in {"xlsx", "xls"}:
            df = pd.read_excel(io.BytesIO(data))
            st.dataframe(df.head(300), use_container_width=True, height=260)
            st.caption(f"预览 {min(len(df), 300)} / {len(df)} 行")
        elif suffix == "json":
            st.json(json.loads(data.decode("utf-8-sig")))
        elif suffix in {"png", "jpg", "jpeg"}:
            st.image(data, caption=name, use_container_width=True)
        elif suffix in {"txt", "md"}:
            st.code(data.decode("utf-8-sig", errors="replace")[:12000])
        else:
            st.caption("该格式暂不支持在线预览，可直接下载。")
    except Exception as exc:
        st.caption(f"该产物暂不可预览: {exc}")


def render_preprocess_artifacts(report: dict):
    artifacts = collect_preprocess_artifacts(report)
    if not artifacts:
        return
    job_id = report.get("jobId")
    st.markdown("### 方法产物")
    if not job_id:
        st.caption("当前报告缺少 Job ID，暂不能下载方法产物。")
        return

    artifact_rows = [
        {
            "方法": item["method"],
            "产物": item["label"],
            "文件名": item["name"],
            "格式": item["suffix"],
        }
        for item in artifacts
    ]
    st.dataframe(pd.DataFrame(artifact_rows), use_container_width=True, hide_index=True)

    for idx, artifact in enumerate(artifacts):
        title = f"{artifact['method']} · {artifact['label']} · {artifact['name']}"
        with st.expander(title, expanded=False):
            try:
                response = requests.get(
                    f"{api_base}/preprocess/workbench/artifact/download",
                    params={"jobId": job_id, "path": artifact["path"]},
                    timeout=120,
                )
                if response.status_code != 200:
                    st.warning(f"产物读取失败: {response.text}")
                    continue
                data = response.content
                render_artifact_preview(artifact["name"], data, artifact["suffix"])
                st.download_button(
                    "下载该产物",
                    data=data,
                    file_name=artifact["name"],
                    mime=response.headers.get("content-type") or "application/octet-stream",
                    use_container_width=True,
                    key=f"preprocess_artifact_download_{idx}",
                )
            except Exception as exc:
                st.error(f"产物读取失败: {exc}")


PREPROCESS_METHOD_PRESETS = {
    "通用表格标准化": {
        "description": "适合 CSV、Excel、JSON、JSONL、LAS 的通用清洗、去重和列名规范化。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
            "dedupe": {"enabled": True, "subset": []},
            "textNormalization": {"strip": True, "collapseWhitespace": True},
            "columnSpecs": {},
        },
    },
    "列名标准化": {
        "description": "适合字段名比较混乱的表格，会优先把常见别名统一成标准列名。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "well_name": {"aliases": ["井名", "井号", "well", "well_name", "井号/井名"], "dtype": "string"},
                "timestamp": {"aliases": ["时间", "采集时间", "记录时间", "timestamp", "date_time", "datetime"], "dtype": "datetime"},
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m", "md", "垂深"], "dtype": "number", "unit": "m"},
                "rop_m_h": {"aliases": ["机械钻速", "钻速", "ROP", "rop", "rate_of_penetration"], "dtype": "number", "unit": "m/h"},
            },
        },
    },
    "缺失值补全": {
        "description": "适合空值较多的文件，会优先对常见字段配置默认补全策略。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "well_name": {"aliases": ["井名", "井号", "well", "well_name"], "dtype": "string", "fill": {"strategy": "constant", "value": "未知井"}},
                "status": {"aliases": ["状态", "工况", "status"], "dtype": "string", "fill": {"strategy": "constant", "value": "未知"}},
                "timestamp": {"aliases": ["时间", "记录时间", "timestamp", "date_time"], "dtype": "datetime", "fill": {"strategy": "ffill"}},
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m"], "dtype": "number", "unit": "m", "fill": {"strategy": "ffill"}},
                "rop_m_h": {"aliases": ["机械钻速", "钻速", "ROP", "rop"], "dtype": "number", "unit": "m/h", "fill": {"strategy": "median"}},
                "pressure_mpa": {"aliases": ["压力", "pressure", "pressure_mpa"], "dtype": "number", "unit": "MPa", "fill": {"strategy": "median"}},
            },
        },
    },
    "类型强制转换": {
        "description": "适合字段都在但类型混乱的文件，会把数字、时间、布尔值转成规范类型。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "well_name": {"aliases": ["井名", "井号", "well", "well_name"], "dtype": "string"},
                "timestamp": {"aliases": ["时间", "记录时间", "timestamp", "date_time", "datetime"], "dtype": "datetime"},
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m"], "dtype": "number", "unit": "m"},
                "rop_m_h": {"aliases": ["机械钻速", "钻速", "ROP", "rop"], "dtype": "number", "unit": "m/h"},
                "is_valid": {"aliases": ["是否有效", "有效", "is_valid", "valid"], "dtype": "boolean"},
            },
        },
    },
    "文本字段清洗": {
        "description": "适合备注、名称、描述类字段，会做空白压缩和字符串规范化。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "textNormalization": {"strip": True, "collapseWhitespace": True},
            "columnSpecs": {
                "well_name": {"aliases": ["井名", "井号", "well", "well_name"], "dtype": "string"},
                "status": {"aliases": ["状态", "工况", "status"], "dtype": "string", "categories": ["正常", "停工", "维护", "测试", "异常"], "categoryCorrection": "closest"},
                "remarks": {"aliases": ["备注", "说明", "remarks", "comment"], "dtype": "string"},
            },
        },
    },
    "时间字段规范化": {
        "description": "适合时间列写法不统一的表格，会把各种日期、时刻字段统一为 datetime。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": ["timestamp"]},
            "columnSpecs": {
                "timestamp": {"aliases": ["时间", "采集时间", "记录时间", "开始时间", "结束时间", "timestamp", "date_time", "datetime"], "dtype": "datetime", "required": True},
                "start_time": {"aliases": ["开始时间", "start_time", "start", "begin_time"], "dtype": "datetime"},
                "end_time": {"aliases": ["结束时间", "end_time", "end", "finish_time"], "dtype": "datetime"},
            },
        },
    },
    "数值异常清洗": {
        "description": "适合深度、钻速、压力、温度等数值字段，会对异常范围做裁剪或置空。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m", "md"], "dtype": "number", "unit": "m", "anomaly": {"min": 0, "max": 12000, "action": "null"}},
                "rop_m_h": {"aliases": ["机械钻速", "钻速", "ROP", "rop"], "dtype": "number", "unit": "m/h", "anomaly": {"min": 0, "max": 500, "action": "clip"}, "fill": {"strategy": "median"}},
                "pressure_mpa": {"aliases": ["压力", "压力值", "pressure", "pressure_mpa", "p_mpa"], "dtype": "number", "unit": "MPa", "anomaly": {"min": 0, "max": 200, "action": "clip"}, "fill": {"strategy": "median"}},
                "temperature_c": {"aliases": ["温度", "temperature", "temp", "temperature_c", "t_c"], "dtype": "number", "unit": "C", "anomaly": {"min": -50, "max": 300, "action": "null"}, "fill": {"strategy": "mean"}},
            },
        },
    },
    "单位换算": {
        "description": "适合英制与公制混用的表格，会把常见字段换算到统一单位。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m", "ft_depth"], "dtype": "number", "sourceUnit": "ft", "unit": "m", "unitFactor": 0.3048},
                "rop_m_h": {"aliases": ["机械钻速", "钻速", "ROP", "rop", "rop_ft_h"], "dtype": "number", "sourceUnit": "ft/h", "unit": "m/h", "unitFactor": 0.3048},
                "pressure_mpa": {"aliases": ["压力", "pressure", "pressure_mpa", "pressure_psi"], "dtype": "number", "sourceUnit": "psi", "unit": "MPa", "unitFactor": 0.00689476},
            },
        },
    },
    "空行剔除": {
        "description": "适合有大量空白行、空表头和导出脏行的表格，会自动去掉全空记录。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
            "dedupe": {"enabled": False, "subset": []},
            "columnSpecs": {},
        },
    },
    "重复行去重": {
        "description": "适合多次导出、重复采集或重复合并的表格，只保留第一条有效记录。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": [], "keep": "first"},
            "columnSpecs": {},
        },
    },
    "钻井实时数据": {
        "description": "适合井名、时间、深度、ROP 等字段齐全的实时/动态数据。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "drilling_realtime",
            "primaryKeys": ["well_name", "timestamp", "depth_m"],
            "columnSpecs": {
                "well_name": {"aliases": ["井名", "井号", "well", "well_name"], "dtype": "string", "required": True, "fill": {"strategy": "constant", "value": "未知井"}},
                "timestamp": {"aliases": ["时间", "采集时间", "date_time", "timestamp"], "dtype": "datetime", "required": True},
                "depth_m": {"aliases": ["井深", "深度", "depth", "depth_m"], "dtype": "number", "unit": "m", "required": True, "anomaly": {"min": 0, "max": 12000, "action": "null"}, "fill": {"strategy": "ffill"}},
                "rop_m_h": {"aliases": ["机械钻速", "ROP", "rop"], "dtype": "number", "unit": "m/h", "anomaly": {"min": 0, "max": 500, "action": "clip"}, "fill": {"strategy": "median"}},
            },
            "dedupe": {"enabled": True, "subset": ["well_name", "timestamp", "depth_m"]},
        },
    },
    "多 sheet 合并": {
        "description": "适合 Excel 多工作表，需要合并后统一输出的场景。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "multi_sheet_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {},
        },
    },
    "枚举值标准化": {
        "description": "适合状态、类别、工况等离散字段，会把接近的写法统一到标准枚举。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {
                "well_status": {"aliases": ["状态", "井状态", "status", "well_status", "工况"], "dtype": "string", "categories": ["正常", "停工", "维护", "测试", "异常"], "categoryCorrection": "closest", "categoryCutoff": 0.75},
                "phase": {"aliases": ["阶段", "工序", "phase", "stage"], "dtype": "string", "categories": ["设计", "施工", "完井", "测试"], "categoryCorrection": "closest", "categoryCutoff": 0.75},
            },
        },
    },
    "严格去重模式": {
        "description": "适合重复记录较多的文件，会优先按整行和主键组合进行去重。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "generic_tabular",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "missingValues": ["", " ", "NA", "N/A", "null", "NULL", "None", "nan", "NaN", "--", "-", "/"],
            "dedupe": {"enabled": True, "subset": [], "keep": "first"},
            "columnSpecs": {},
        },
    },
    "JSON/JSONL 归一化": {
        "description": "适合半结构化 JSON/JSONL 数据，会尽量保留原字段并统一成表格。",
        "config": {
            "standardVersion": "1.0",
            "datasetType": "json_normalized",
            "headerDetection": True,
            "concatSheets": True,
            "addProvenanceColumns": True,
            "keepExtraColumns": True,
            "dedupe": {"enabled": True, "subset": []},
            "columnSpecs": {},
            "jsonMode": "normalize",
        },
    },
}


def preprocess_config_template(template_name: str):
    return PREPROCESS_METHOD_PRESETS.get(template_name, PREPROCESS_METHOD_PRESETS["通用表格标准化"])["config"]


def render_preprocess_result(report: dict):
    if not report:
        return
    ops = report.get("operations", {})
    missing_total = sum(v for v in (ops.get("missingFilled") or {}).values() if isinstance(v, (int, float)))
    anomaly_total = sum(v for v in (ops.get("anomaliesCorrected") or {}).values() if isinstance(v, (int, float)))

    st.divider()
    st.markdown("### 处理结果")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("输入行数", report.get("rowsIn", 0))
    m2.metric("输出行数", report.get("rowsOut", 0))
    m3.metric("剔除重复", ops.get("duplicateRowsRemoved", 0))
    m4.metric("补全/纠错", int(missing_total + anomaly_total))

    op_rows = [
        {"处理项": "同义列重命名", "结果": len(ops.get("columnsRenamed") or {})},
        {"处理项": "同义列合并", "结果": len(ops.get("columnsMerged") or {})},
        {"处理项": "空行剔除", "结果": ops.get("emptyRowsRemoved", 0)},
        {"处理项": "重复行剔除", "结果": ops.get("duplicateRowsRemoved", 0)},
        {"处理项": "缺失补全", "结果": missing_total},
        {"处理项": "异常纠错", "结果": anomaly_total},
        {"处理项": "异常删行", "结果": ops.get("rowsDroppedForAnomalies", 0)},
    ]
    st.dataframe(pd.DataFrame(op_rows), use_container_width=True, hide_index=True)

    saved = report.get("savedToKb") or {}
    if saved.get("stored"):
        st.success(f"标准化文件已存入知识库 `{saved.get('kbId')}`，文件 ID: `{saved.get('fileId')}`")
        if saved.get("indexRebuilt"):
            st.caption(f"已同步构建索引，共 {saved.get('indexedChunks', 0)} 个文本块。")

    excel_output_path = report.get("excelOutputPath")
    if excel_output_path and Path(str(excel_output_path)).exists():
        st.download_button(
            "下载 Excel 结果",
            data=Path(str(excel_output_path)).read_bytes(),
            file_name=f"{Path(report.get('sourceFileName') or 'preprocessed').stem}_preprocessed.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    render_preprocess_artifacts(report)

    with st.expander("查看完整审计报告", expanded=False):
        st.json(report)

    with st.expander("标准化结果预览", expanded=False):
        job_id = report.get("jobId")
        if job_id:
            try:
                r_preview = requests.get(
                    f"{api_base}/preprocess/workbench/dataframe",
                    params={"jobId": job_id, "limit": 500},
                    timeout=60,
                )
                if r_preview.status_code == 200:
                    payload = r_preview.json()
                    df_preview = pd.DataFrame(payload.get("rows", []))
                    total_rows = payload.get("totalRows", len(df_preview))
                else:
                    st.warning(f"标准化结果暂不可预览: {r_preview.text}")
                    return
                st.dataframe(df_preview, use_container_width=True, height=420)
                st.caption(f"预览 {len(df_preview)} / {total_rows} 行")
            except Exception as exc:
                st.error(f"标准化结果读取失败: {exc}")
        else:
            st.caption("当前报告缺少预处理 Job ID，暂不能读取预览。")


def render_data_preprocess_workspace():
    st.caption("上传结构化文件，按顺序选择多个预处理方法，统一开始处理后再按需保存到知识库。支持 LAS 测井数据转 Excel。")
    st.markdown(
        """
        <style>
        .preprocess-method-strip {
            display: flex;
            gap: 12px;
            min-height: 148px;
            overflow-x: auto;
            padding: 4px 0 10px;
        }
        .preprocess-method-card,
        .preprocess-method-empty {
            flex: 0 0 232px;
            width: 232px;
            height: 136px;
            box-sizing: border-box;
            border: 1px solid #dbe5e8;
            border-radius: 8px;
            background: #fff;
            padding: 12px;
        }
        .preprocess-method-card {
            display: grid;
            grid-template-rows: auto auto 1fr;
            gap: 6px;
        }
        .preprocess-method-empty {
            display: flex;
            align-items: center;
            color: #64748b;
            background: #f8fbfc;
        }
        .preprocess-method-index {
            width: 24px;
            height: 24px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #eef9f6;
            color: #18715f;
            font-weight: 800;
            font-size: 12px;
        }
        .preprocess-method-title {
            color: #1f2937;
            font-size: 15px;
            font-weight: 800;
            line-height: 1.35;
        }
        .preprocess-method-desc {
            color: #64748b;
            font-size: 12px;
            line-height: 1.45;
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 1. 上传文件")
    uploaded_files = st.file_uploader(
        "选择结构化文件",
        type=["csv", "xlsx", "xls", "json", "jsonl", "las"],
        accept_multiple_files=True,
        key="standalone_preprocess_uploader",
    )
    uploaded_files = uploaded_files or []

    if "preprocess_job" not in st.session_state:
        st.session_state.preprocess_job = None
    if "preprocess_jobs" not in st.session_state:
        st.session_state.preprocess_jobs = []
    if "preprocess_reports_by_job" not in st.session_state:
        st.session_state.preprocess_reports_by_job = {}
    if "preprocess_uploaded_file_keys" not in st.session_state:
        st.session_state.preprocess_uploaded_file_keys = set()
    if "preprocess_selected_methods" not in st.session_state:
        st.session_state.preprocess_selected_methods = []
    if "preprocess_last_report" not in st.session_state:
        st.session_state.preprocess_last_report = None

    upload_col, upload_info_col = st.columns([1, 2])
    with upload_col:
        upload_clicked = st.button(
            "上传到预处理工作台",
            disabled=not uploaded_files,
            type="primary",
            use_container_width=True,
            key="standalone_preprocess_upload_btn",
        )
    with upload_info_col:
        if uploaded_files:
            st.caption(f"待上传 {len(uploaded_files)} 个文件: " + "、".join(file.name for file in uploaded_files[:4]))
        if st.session_state.preprocess_jobs:
            st.success(f"工作台已有 {len(st.session_state.preprocess_jobs)} 个文件")

    if upload_clicked and uploaded_files:
        uploaded_count = 0
        skipped_count = 0
        for file_item in uploaded_files:
            file_bytes = file_item.getvalue()
            file_key = f"{file_item.name}:{len(file_bytes)}"
            if file_key in st.session_state.preprocess_uploaded_file_keys:
                skipped_count += 1
                continue
            try:
                files = {"file": (file_item.name, file_bytes, "application/octet-stream")}
                r_upload = requests.post(f"{api_base}/preprocess/upload", files=files, timeout=180)
                if r_upload.status_code == 200:
                    job = r_upload.json()
                    st.session_state.preprocess_jobs.append(job)
                    st.session_state.preprocess_job = job
                    st.session_state.preprocess_last_report = st.session_state.preprocess_reports_by_job.get(job.get("jobId"))
                    st.session_state.preprocess_uploaded_file_keys.add(file_key)
                    uploaded_count += 1
                else:
                    st.error(f"{file_item.name} 上传失败: {r_upload.text}")
            except Exception as exc:
                st.error(f"{file_item.name} 上传请求失败: {exc}")
        if uploaded_count:
            st.success(f"已上传 {uploaded_count} 个文件到预处理工作台")
        if skipped_count:
            st.caption(f"已跳过 {skipped_count} 个本次会话中已上传的同名同大小文件。")
        if uploaded_count:
            st.rerun()

    if st.session_state.preprocess_jobs:
        job_options = [job.get("jobId") for job in st.session_state.preprocess_jobs if job.get("jobId")]
        current_job_id = (st.session_state.preprocess_job or {}).get("jobId")
        default_index = job_options.index(current_job_id) if current_job_id in job_options else len(job_options) - 1
        selected_job_id = st.selectbox(
            "当前处理文件",
            options=job_options,
            index=max(default_index, 0),
            format_func=lambda jid: next(
                (
                    f"{job.get('fileName')} · {jid}"
                    for job in st.session_state.preprocess_jobs
                    if job.get("jobId") == jid
                ),
                jid,
            ),
            key="preprocess_current_job_select",
        )
        selected_job = next((job for job in st.session_state.preprocess_jobs if job.get("jobId") == selected_job_id), None)
        if selected_job and selected_job.get("jobId") != current_job_id:
            st.session_state.preprocess_job = selected_job
            st.session_state.preprocess_last_report = st.session_state.preprocess_reports_by_job.get(selected_job_id)
            st.rerun()

    st.markdown("### 2. 选择预处理方法")
    preprocess_method_cards = load_preprocess_method_cards()
    preprocess_method_by_id = {item["id"]: item for item in preprocess_method_cards}
    selected_methods = st.session_state.preprocess_selected_methods
    remaining_methods = [m for m in preprocess_method_cards if m["id"] not in selected_methods]

    method_cards = []
    for idx, method_id in enumerate(selected_methods):
        method = preprocess_method_by_id.get(method_id, {"name": method_id, "description": ""})
        method_cards.append(
            f"""
            <div class="preprocess-method-card">
                <span class="preprocess-method-index">{idx + 1}</span>
                <div class="preprocess-method-title">{html.escape(method["name"])}</div>
                <p class="preprocess-method-desc">{html.escape(method.get("description", ""))}</p>
            </div>
            """
        )
    if not method_cards:
        method_cards.append('<div class="preprocess-method-empty">点击右侧 ⊕ 添加预处理方法。</div>')

    card_col, add_col = st.columns([1, 0.16])
    with card_col:
        st.markdown(f'<div class="preprocess-method-strip">{"".join(method_cards)}</div>', unsafe_allow_html=True)
    with add_col:
        if hasattr(st, "popover"):
            with st.popover("⊕", use_container_width=True):
                if not remaining_methods:
                    st.caption("所有方法都已选择")
                for method in remaining_methods:
                    if st.button(method["name"], key=f"add_preprocess_method_{method['id']}", use_container_width=True):
                        st.session_state.preprocess_selected_methods.append(method["id"])
                        st.rerun()
                    st.caption(method["description"])
        else:
            add_choice = st.selectbox(
                "添加方法",
                options=[""] + [m["id"] for m in remaining_methods],
                format_func=lambda mid: "⊕" if not mid else preprocess_method_by_id[mid]["name"],
                key="fallback_add_preprocess_method",
            )
            if add_choice:
                st.session_state.preprocess_selected_methods.append(add_choice)
                st.rerun()

    if selected_methods:
        remove_col, _ = st.columns([0.35, 0.65])
        with remove_col:
            remove_choice = st.selectbox(
                "移除已选方法",
                options=[""] + selected_methods,
                format_func=lambda mid: "请选择" if not mid else preprocess_method_by_id.get(mid, {"name": mid})["name"],
                key="preprocess_remove_choice",
            )
            if st.button("移除所选方法", disabled=not remove_choice, use_container_width=True, key="preprocess_remove_selected"):
                st.session_state.preprocess_selected_methods = [m for m in selected_methods if m != remove_choice]
                st.rerun()

    st.markdown("### 3. 开始预处理")
    can_run = bool(st.session_state.preprocess_job) and bool(st.session_state.preprocess_selected_methods)
    if st.button("开始预处理", type="primary", use_container_width=True, disabled=not can_run, key="standalone_preprocess_run"):
        progress_placeholders = {}
        for method_id in st.session_state.preprocess_selected_methods:
            method = preprocess_method_by_id.get(method_id, {"name": method_id})
            progress_placeholders[method_id] = st.progress(0, text=f"{method['name']} 等待处理")

        try:
            payload = {
                "jobId": st.session_state.preprocess_job["jobId"],
                "methods": st.session_state.preprocess_selected_methods,
                "saveToKb": False,
            }
            r_run = requests.post(f"{api_base}/preprocess/workbench/run", json=payload, timeout=3600)
            if r_run.status_code == 200:
                report = r_run.json()
                st.session_state.preprocess_last_report = report
                if report.get("jobId"):
                    st.session_state.preprocess_reports_by_job[report["jobId"]] = report
                for stage in report.get("methodReports", []):
                    method_id = stage.get("method")
                    method = preprocess_method_by_id.get(method_id, {"name": stage.get("name", method_id)})
                    if method_id in progress_placeholders:
                        progress_placeholders[method_id].progress(
                            int(stage.get("progress", 100)),
                            text=f"{method['name']} 完成",
                        )
                st.success("预处理完成")
            else:
                for method_id, placeholder in progress_placeholders.items():
                    method = preprocess_method_by_id.get(method_id, {"name": method_id})
                    placeholder.progress(0, text=f"{method['name']} 未完成")
                st.error(f"预处理失败: {r_run.text}")
        except Exception as exc:
            st.error(f"预处理请求失败: {exc}")

    st.markdown("### 4. 保存到知识库")
    try:
        r_kb = requests.get(f"{api_base}/kb/list", timeout=5)
        existing_kbs = r_kb.json().get("kbs", []) if r_kb.status_code == 200 else []
    except Exception:
        existing_kbs = []

    save_mode = st.radio("目标知识库", ["选择已存在的知识库", "新建知识库"], horizontal=True, key="preprocess_save_mode")
    target_kb_id = None
    new_kb_name = None
    if save_mode == "选择已存在的知识库":
        if existing_kbs:
            kb_options = [kb.get("kbId") for kb in existing_kbs]
            kb_label = {kb.get("kbId"): kb.get("kbName") or kb.get("kbId") for kb in existing_kbs}
            target_kb_id = st.selectbox(
                "选择知识库",
                options=kb_options,
                format_func=lambda kid: kb_label.get(kid, kid),
                key="preprocess_target_kb",
            )
        else:
            st.warning("当前没有可选知识库，请选择新建知识库。")
    else:
        new_kb_name = st.text_input("新知识库名称", placeholder="例如：标准化录井数据", key="preprocess_new_kb_name")

    rebuild_index = st.checkbox(
        "存入后立即构建索引",
        value=False,
        help="勾选后会调用向量模型入库，数据量较大时会更久。",
        key="preprocess_rebuild_index",
    )

    can_save = bool(st.session_state.preprocess_last_report and st.session_state.preprocess_last_report.get("jobId"))
    if not can_save:
        st.caption("完成预处理后，可在这里把标准化文件保存到已有知识库或新建知识库。")

    if st.button("保存预处理文件到知识库", use_container_width=True, disabled=not can_save, key="preprocess_store_to_kb"):
        if save_mode == "选择已存在的知识库" and not target_kb_id:
            st.error("请选择目标知识库")
            return
        if save_mode == "新建知识库" and not (new_kb_name or "").strip():
            st.error("请输入新知识库名称")
            return
        try:
            payload = {
                "jobId": st.session_state.preprocess_last_report["jobId"],
                "targetKbId": target_kb_id if save_mode == "选择已存在的知识库" else None,
                "newKbName": new_kb_name if save_mode == "新建知识库" else None,
                "rebuildIndex": rebuild_index,
            }
            r_store = requests.post(f"{api_base}/preprocess/workbench/store", json=payload, timeout=3600)
            if r_store.status_code == 200:
                saved_info = r_store.json()
                st.session_state.preprocess_last_report["savedToKb"] = saved_info
                if st.session_state.preprocess_last_report.get("jobId"):
                    st.session_state.preprocess_reports_by_job[
                        st.session_state.preprocess_last_report["jobId"]
                    ] = st.session_state.preprocess_last_report
                st.success(f"已保存到知识库 `{saved_info.get('kbId')}`，文件 ID: `{saved_info.get('fileId')}`")
            else:
                st.error(f"保存失败: {r_store.text}")
        except Exception as exc:
            st.error(f"保存请求失败: {exc}")

    if st.session_state.preprocess_last_report:
        render_preprocess_result(st.session_state.preprocess_last_report)

# 主界面 Tabs

tab7, tab4, tab5, tab6 = st.tabs(["🧹 数据预处理", "🔍 多模态搜索", "⛏️ 知识提取", "📚 知识库预览"])
#tab1, tab2, tab3, tab4, tab5 = st.tabs(["💬 对话", "📄 文档查看", "🖼️ 提取图片", "🔍 调试搜索", "📚 知识库预览"])
# --- Tab 1: 对话 ---
# with tab1:
#     st.header("多模态 RAG 对话 (全局知识库)")
#     st.caption("当前对话将检索知识库中所有已索引的文件。")
    
#     # 辅助函数：显示引用
#     def render_citations(citations, api_base_url):
#         if not citations:
#             return
#         with st.expander("📚 参考引用 (点击查看原文)"):
#             for c in citations:
#                 page = c.get("page")
#                 score = c.get("score")
#                 text = c.get("snippet", "")
#                 preview_url = c.get("previewUrl", "")
                
#                 # 构建完整 URL
#                 full_url = preview_url
#                 if preview_url.startswith("/"):
#                     # 尝试从 api_base 提取 host
#                     # api_base 如 http://localhost:8000/api/v1
#                     if "/api/v1" in api_base_url:
#                         host = api_base_url.split("/api/v1")[0]
#                         full_url = host + preview_url
#                     else:
#                         # 简单拼接
#                         full_url = api_base_url.rstrip("/") + preview_url

#                 st.markdown(f"**📄 Page {page}** (相似度: {score:.2f})")
#                 st.markdown(f"🔗 [点击查看原文页面]({full_url})")
#                 st.caption(text[:200] + "..." if len(text) > 200 else text)
#                 st.divider()

#     # 显示历史消息
#     for msg in st.session_state.messages:
#         with st.chat_message(msg["role"]):
#             st.markdown(msg["content"])
#             if "citations" in msg and msg["citations"]:
#                 render_citations(msg["citations"], api_base)

#     # 输入框
#     if prompt := st.chat_input("请输入关于文档的问题..."):
#         # 添加用户消息
#         st.session_state.messages.append({"role": "user", "content": prompt})
#         with st.chat_message("user"):
#             st.markdown(prompt)

#         # 请求后端流式响应
#         with st.chat_message("assistant"):
#             message_placeholder = st.empty()
#             full_response = ""
#             citations = []
            
#             try:
#                 payload = {
#                     "message": prompt,
#                     "sessionId": st.session_state.session_id,
#                     "pdfFileId": st.session_state.file_id
#                 }
                
#                 with requests.post(f"{api_base}/chat", json=payload, stream=True) as r:
#                     if r.status_code == 200:
#                         for line in r.iter_lines():
#                             if line:
#                                 decoded_line = line.decode('utf-8')
#                                 if decoded_line.startswith("event:"):
#                                     event_type = decoded_line.split(":", 1)[1].strip()
#                                 elif decoded_line.startswith("data:"):
#                                     data_str = decoded_line.split(":", 1)[1].strip()
#                                     try:
#                                         data_json = json.loads(data_str)
                                        
#                                         if event_type == "token":
#                                             token_text = data_json.get("text", "")
#                                             full_response += token_text
                                            
#                                             # 实时替换图片路径为完整的 API URL
#                                             # 使用正则进行更稳健的替换
#                                             if "/api/v1" in api_base:
#                                                 api_root = api_base.split("/api/v1")[0]
#                                             else:
#                                                 api_root = api_base.rstrip("/")
                                            
#                                             display_response = re.sub(r'\]\(\s*/api/v1/', f']({api_root}/api/v1/', full_response)
#                                             display_response = re.sub(r'src="\s*/api/v1/', f'src="{api_root}/api/v1/', display_response)
                                            
#                                             message_placeholder.markdown(display_response + "▌")
                                            
#                                         elif event_type == "citation":
#                                             citations.append(data_json)
                                            
#                                         elif event_type == "error":
#                                             st.error(f"后端错误: {data_json.get('message')}")
#                                     except json.JSONDecodeError:
#                                         st.error("无法解析后端数据")
#                         # 最终显示也需要替换
#                         if "/api/v1" in api_base:
#                             api_root = api_base.split("/api/v1")[0]
#                         else:
#                             api_root = api_base.rstrip("/")
                            
#                         final_display_response = re.sub(r'\]\(\s*/api/v1/', f']({api_root}/api/v1/', full_response)
#                         final_display_response = re.sub(r'src="\s*/api/v1/', f'src="{api_root}/api/v1/', final_display_response)
                        
#                         # 最终显示也需要替换
#                         if "/api/v1" in api_base:
#                             api_root = api_base.split("/api/v1")[0]
#                         else:
#                             api_root = api_base.rstrip("/")
                            
#                         final_display_response = re.sub(r'\]\(\s*/api/v1/', f']({api_root}/api/v1/', full_response)
#                         final_display_response = re.sub(r'src="\s*/api/v1/', f'src="{api_root}/api/v1/', final_display_response)
                        
#                         message_placeholder.markdown(final_display_response)
#                         # 保存助手回复
#                         st.session_state.messages.append({
#                             "role": "assistant", 
#                             "content": final_display_response, # 保存替换后的内容，以便历史记录正确显示
#                             "citations": citations
#                         })
                        
#                         if citations:
#                             render_citations(citations, api_base)
#                     else:
#                         st.error(f"API 请求失败: {r.status_code}")
#             except Exception as e:
#                 st.error(f"发生异常: {e}")

# # --- Tab 2: 文档查看 ---
# with tab2:
#     st.header("文档可视化")
#     if st.session_state.file_id:
#         col1, col2 = st.columns([1, 3])
#         with col1:
#             page_num = st.number_input("页码", min_value=1, value=1)
        
#         col_orig, col_parsed = st.columns(2)
        
#         with col_orig:
#             st.subheader("原始页面")
#             orig_url = f"{api_base}/pdf/page?fileId={st.session_state.file_id}&page={page_num}&type=original"
#             # 使用 st.image 直接加载 URL (如果后端支持跨域且可访问)
#             # 或者下载后显示
#             try:
#                 st.image(orig_url, use_container_width=True)
#             except:
#                 st.warning("无法加载原始页面")

#         with col_parsed:
#             st.subheader("解析后 (带框)")
#             if st.session_state.parsing_status == "ready":
#                 parsed_url = f"{api_base}/pdf/page?fileId={st.session_state.file_id}&page={page_num}&type=parsed"
#                 try:
#                     st.image(parsed_url, use_container_width=True)
#                 except:
#                     st.warning("无法加载解析页面")
#             else:
#                 st.info("文档尚未解析完成")
#     else:
#         st.info("请先上传文件")

# # --- Tab 3: 提取图片 ---
# with tab3:
#     st.header("提取的图片与表格")
#     if st.session_state.file_id and st.session_state.parsing_status == "ready":
#         if st.button("加载图片列表"):
#             try:
#                 resp = requests.get(f"{api_base}/pdf/images_list", params={"fileId": st.session_state.file_id})
#                 if resp.status_code == 200:
#                     images = resp.json().get("images", [])
#                     if images:
#                         st.success(f"共找到 {len(images)} 张图片/表格截图")
                        
#                         # 使用网格布局显示图片
#                         cols = st.columns(3)
#                         for idx, img_name in enumerate(images):
#                             img_url = f"{api_base}/pdf/images?fileId={st.session_state.file_id}&imagePath={img_name}"
#                             with cols[idx % 3]:
#                                 st.image(img_url, caption=img_name, use_container_width=True)
#                     else:
#                         st.info("未提取到任何图片或表格。")
#                 else:
#                     st.error("获取图片列表失败")
#             except Exception as e:
#                 st.error(f"错误: {e}")
#     elif not st.session_state.file_id:
#         st.info("请先上传文件")
#     else:
#         st.info("请等待解析完成")

# --- Tab 4: 调试搜索 ---
with tab4:
    st.header("向量索引搜索")
    
    # 0. 获取知识库列表
    all_kbs_search = []
    try:
        r_list = requests.get(f"{api_base}/kb/list", timeout=3)
        if r_list.status_code == 200:
            all_kbs_search = r_list.json().get("kbs", [])
    except:
        pass

    if not all_kbs_search:
        st.info("暂无知识库，请先去创建。")
        st.stop()

    # 1. 选择知识库
    kb_map = {kb['kbId']: kb.get('kbName', kb['kbId']) for kb in all_kbs_search}
    kb_ids = list(kb_map.keys())
    
    current_idx_search = 0
    if st.session_state.kb_id in kb_ids:
        current_idx_search = kb_ids.index(st.session_state.kb_id)
        
    selected_kb_search = st.selectbox(
        "选择检索知识库", 
        kb_ids, 
        format_func=lambda x: kb_map[x],
        index=current_idx_search,
        key="search_tab_kb_select"
    )
    
    if selected_kb_search != st.session_state.kb_id:
        st.session_state.kb_id = selected_kb_search
        st.session_state.current_kb_name = kb_map[selected_kb_search]
        st.session_state.file_id = None
        st.rerun()
        
    st.divider()

    # 2. 搜索输入
    query = st.text_input("搜索关键词")
    k = st.slider("Top K", 1, 10, 3)

    # 获取当前 KB 文件列表用于下拉选择
    kb_files_search = []
    try:
        r = requests.get(f"{api_base}/kb/files", params={"kbId": st.session_state.kb_id}, timeout=10)
        if r.status_code == 200:
            kb_files_search = r.json().get("files", [])
    except Exception:
        kb_files_search = []

    file_options = ["当前知识库 (All files)"] + [f["fileId"] for f in kb_files_search]

    default_idx = 0
    if st.session_state.file_id and st.session_state.file_id in file_options:
        default_idx = file_options.index(st.session_state.file_id)

    selected_option = st.selectbox("选择搜索范围", file_options, index=default_idx)
    
    if st.button("搜索"):
        try:
            payload = {
                "query": query,
                "k": k,
                "kbId": st.session_state.kb_id,
            }

            if selected_option != "当前知识库 (All files)":
                payload["fileId"] = selected_option
            
            resp = requests.post(f"{api_base}/index/search", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    st.info("未找到相关结果")
                else:
                    for i, res in enumerate(results):
                        score = res.get("score", 0)
                        res_file_id = res.get("entity_key", "Unknown")
                        chunk_text = res.get("chunk_text", "")
                        source_meta = res.get("source", "")
                        
                        # 动态替换图片链接，使其指向后端 API
                        def replace_img_url(match):
                            rel_path = match.group(1) # e.g. ./images/page26_img1.png
                            img_name = os.path.basename(rel_path)
                            # 对图片名进行 URL 编码，处理中文和空格
                            img_name_encoded = urllib.parse.quote(img_name)
                            base = api_base.rstrip('/')
                            return f"![Image]({base}/pdf/images?kbId={st.session_state.kb_id}&fileId={res_file_id}&imagePath={img_name_encoded})"
                        
                        # 替换 Markdown 图片语法
                        chunk_text_display = re.sub(r'!\[.*?\]\((.*?)\)', replace_img_url, chunk_text)
                        
                        with st.expander(f"Result {i+1} | Score: {score:.4f} | File: {res_file_id}", expanded=True):
                            # 尝试检测是否为结构化数据 (Excel/CSV 行)
                            # 特征：包含 "工作表:" 和 "行号:"
                            if "工作表:" in chunk_text and "行号:" in chunk_text:
                                try:
                                    # 解析 Key-Value
                                    data_dict = {}
                                    for line in chunk_text.split('\n'):
                                        if ": " in line:
                                            k, v = line.split(": ", 1)
                                            data_dict[k] = v
                                    
                                    # 展示为表格
                                    if data_dict:
                                        st.markdown("#### 📊 结构化数据匹配")
                                        # 转置显示，适合单行数据查看
                                        df_row = pd.DataFrame([data_dict]).T
                                        df_row.columns = ["值"]
                                        st.dataframe(df_row, use_container_width=True)
                                    else:
                                        st.markdown(chunk_text_display)
                                except:
                                    st.markdown(chunk_text_display)
                            else:
                                st.markdown(chunk_text_display)

                            st.divider()
                            st.caption(f"Source Metadata: {source_meta}")
            else:
                st.error(f"搜索失败: {resp.text}")
        except Exception as e:
            st.error(f"错误: {e}")


# --- Tab 6: 知识库预览 & 管理 ---
with tab6:
    if "current_kb_view" not in st.session_state:
        st.session_state.current_kb_view = None

    # === VIEW 1: 知识库概览列表 ===
    if st.session_state.current_kb_view is None:
        st.markdown("### 📚 知识库管理")
        st.caption("选择一个知识库进入管理，或创建新的知识库。")

        # 0. 预先获取现有知识库列表 (用于重名校验和展示)
        existing_kbs = []
        fetch_error = None
        try:
            r_list = requests.get(f"{api_base}/kb/list", timeout=5)
            if r_list.status_code == 200:
                existing_kbs = r_list.json().get("kbs", [])
            else:
                fetch_error = f"获取列表失败: {r_list.text}"
        except Exception as e:
            fetch_error = f"无法连接后端服务: {e}"

        # 1. 新建知识库 (使用辅助函数)
        handle_create_kb("tab5_overview", existing_kbs, api_base)
        
        st.divider()

        # 2. 知识库列表卡片
        if st.button("🔄 刷新列表", key="refresh_kb_list"):
            st.rerun()

        if fetch_error:
            st.error(fetch_error)
        else:
            kbs = existing_kbs
            if not kbs:
                st.info("暂无知识库，请先新建。")
            else:
                # 分列显示卡片
                cols = st.columns(3) # 每行3个
                for i, kb in enumerate(kbs):
                    with cols[i % 3]:
                        with st.container(border=True):
                            # 标题行 + 删除按钮
                            col_title, col_del = st.columns([0.8, 0.2])
                            with col_title:
                                st.subheader(f"📂 {kb.get('kbName')}")
                            with col_del:
                                # 垃圾桶按钮
                                if st.button("🗑️", key=f"pre_del_{kb['kbId']}", help="删除此知识库"):
                                    st.session_state["kb_confirm_delete"] = kb['kbId']
                                    st.rerun()
                            
                            # 删除确认逻辑
                            if st.session_state.get("kb_confirm_delete") == kb['kbId']:
                                st.warning("永久删除此知识库？此操作不可恢复。")
                                col_y, col_n = st.columns(2)
                                with col_y:
                                    if st.button("✅ 确认", key=f"yes_del_{kb['kbId']}", use_container_width=True):
                                        try:
                                            r = requests.post(
                                                f"{api_base}/kb/delete", 
                                                json={"kbId": kb['kbId']},
                                                timeout=10
                                            )
                                            if r.status_code == 200:
                                                st.success("删除成功")
                                                st.session_state["kb_confirm_delete"] = None
                                                time.sleep(1)
                                                st.rerun()
                                            else:
                                                st.error(f"失败: {r.text}")
                                        except Exception as ex:
                                            st.error(f"错误: {ex}")
                                with col_n:
                                    if st.button("❌ 取消", key=f"no_del_{kb['kbId']}", use_container_width=True):
                                        st.session_state["kb_confirm_delete"] = None
                                        st.rerun()
                            else:
                                # 正常显示信息
                                st.caption(f"ID: {kb.get('kbId')}")
                                
                                c1, c2 = st.columns(2)
                                c1.metric("文件数", kb.get('fileCount', 0))
                                c2.metric("类型", kb.get('vectorStoreType', 'faiss'))

                                if st.button("进入知识库 ➡️", key=f"enter_{kb['kbId']}", use_container_width=True):
                                    st.session_state.current_kb_view = kb['kbId']
                                    st.session_state.current_kb_name = kb['kbName']
                                    st.session_state.kb_id = kb['kbId'] # 同步到全局
                                    st.rerun()

    # === VIEW 2: 单个知识库详情 (原 Tab 5 功能) ===
    else:
        current_kb = st.session_state.current_kb_view
        
        # 0. 准备通用数据: 根据 current_kb 实时获取 KB信息 (名称, embedding model等)
        # 避免 session_state 中名称不同步的问题
        kb_embed_model = "bge-m3 (Default)"
        display_name = st.session_state.get("current_kb_name", current_kb)
        
        try:
            r_info = requests.get(f"{api_base}/kb/list", timeout=3)
            if r_info.status_code == 200:
                for k in r_info.json().get("kbs", []):
                    if k['kbId'] == current_kb:
                        kb_embed_model = k.get("embedModel", "Unknown")
                        display_name = k.get("kbName", display_name) # 强制更新 name
                        st.session_state.current_kb_name = display_name
                        break
        except: 
            pass
        
        # 头部导航
        col_nav1, col_nav2 = st.columns([1, 6])
        with col_nav1:
            if st.button("⬅️ 返回", use_container_width=True):
                st.session_state.current_kb_view = None
                st.rerun()
        with col_nav2:
             st.markdown(f"### 知识库: `{display_name}`")

        st.divider()

        # === 上传区域 ===
        with st.expander("📤 上传文件到当前知识库", expanded=True):
            uploaded_files = st.file_uploader(
                "选择多个文件 (支持 PDF, Word, Excel, CSV, 图片)",
                type=["pdf", "docx", "doc", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"],
                accept_multiple_files=True,
                key="uploader_tab5"
            )
            
            # 解析选项
            col_u1, col_u2 = st.columns([1, 1])
            with col_u1:
                parse_method_choice = st.radio(
                    "解析方式", 
                    ["original", "olmocr", "mineru"], 
                    format_func=lambda x: {
                        "original": "基础解析 (快, 传统OCR)",
                        "olmocr": "增强解析 (慢, 多模态大模型)",
                        "mineru": "MinerU (文档解析/表格增强)",
                    }[x],
                    horizontal=True,
                    key="parse_method_tab5"
                )

            if uploaded_files:
                # 0. 预先获取当前知识库的已有文件列表，用于查重
                existing_filenames = set()
                try:
                    if current_kb:
                        r_files = requests.get(f"{api_base}/kb/files", params={"kbId": current_kb}, timeout=5)
                        if r_files.status_code == 200:
                            f_list = r_files.json().get("files", [])
                            existing_filenames = {str(f.get("fileName")).strip().lower() for f in f_list if f.get("fileName")}
                        else:
                            st.warning(f"无法获取文件列表 (Code: {r_files.status_code})，查重功能可能受限")
                    else:
                        st.error("未检测到当前知识库ID")
                except Exception as e:
                    st.warning(f"查重请求失败: {e}")
                    pass

                # 状态存储初始化
                if "batch_status" not in st.session_state:
                    st.session_state.batch_status = {}  # key: filename_size, val: {fid: x, status: x}
                
                # 1. 自动上传队列
                st.caption(f"正在准备处理 {len(uploaded_files)} 个文件...")
                
                files_to_process = []
                
                # 进度容器
                upload_progress = st.empty()
                
                for i, up_file in enumerate(uploaded_files):
                    f_key = f"{up_file.name}_{up_file.size}"
                    
                    # 检查是否已上传
                    if f_key not in st.session_state.batch_status:
                        
                        # 查重逻辑
                        if up_file.name.strip().lower() in existing_filenames:
                            st.session_state.batch_status[f_key] = {"fid": None, "status": "duplicate"}
                            st.warning(f"⚠️ 跳过上传: `{up_file.name}` (知识库中已存在同名文件)")
                            continue

                        # 显示上传进度
                        # 计算整体进度
                        prog_val = (i + 1) / len(uploaded_files)
                        upload_progress.progress(prog_val, text=f"正在上传 ({i+1}/{len(uploaded_files)}): {up_file.name}")
                        
                        try:
                            # 指针归零以防万一
                            up_file.seek(0)
                            
                            mime_type = "application/octet-stream"
                            if up_file.name.endswith(".pdf"): mime_type = "application/pdf"
                            elif up_file.name.endswith(".docx"): mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            elif up_file.name.endswith(".doc"): mime_type = "application/msword"
                            elif up_file.name.endswith(".xlsx"): mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            elif up_file.name.endswith(".csv"): mime_type = "text/csv"
                            elif up_file.name.lower().endswith((".jpg", ".jpeg")): mime_type = "image/jpeg"
                            elif up_file.name.lower().endswith(".png"): mime_type = "image/png"
                            elif up_file.name.lower().endswith(".webp"): mime_type = "image/webp"
                            elif up_file.name.lower().endswith(".bmp"): mime_type = "image/bmp"
                            elif up_file.name.lower().endswith(".gif"): mime_type = "image/gif"
                            elif up_file.name.lower().endswith((".tif", ".tiff")): mime_type = "image/tiff"
                            
                            files = {"file": (up_file.name, up_file, mime_type)}
                            resp = requests.post(
                                f"{api_base}/pdf/upload",
                                files=files,
                                data={"kbId": current_kb},
                                timeout=120,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                f_id = data["fileId"]
                                st.session_state.batch_status[f_key] = {"fid": f_id, "status": "uploaded"}
                            else:
                                st.session_state.batch_status[f_key] = {"fid": None, "status": f"error: {resp.text}"}
                                st.error(f"Failed to upload {up_file.name}: {resp.text}")
                        except Exception as e:
                             st.session_state.batch_status[f_key] = {"fid": None, "status": f"error: {e}"}
                             st.error(f"Error uploading {up_file.name}: {e}")
                    
                    # 收集 ID
                    info = st.session_state.batch_status.get(f_key, {})
                    if info.get("fid"):
                        files_to_process.append({"name": up_file.name, "fid": info["fid"], "key": f_key})

                upload_progress.empty()
                
                if files_to_process:
                    st.success(f"✅ 已就绪 {len(files_to_process)} 个文件 (共 {len(uploaded_files)} 个)")
                    
                    # 2. 批量操作区
                    col_b1, col_b2 = st.columns(2)
                    uploaded_count = len(files_to_process)
                    
                    with col_b1:
                        if st.button(f"🚀 解析 ({uploaded_count})", use_container_width=True, type="primary"):
                            # 1. 提交任务
                            submit_bar = st.progress(0, text="正在分发解析任务...")
                            active_tasks = [] # list of dict: {fid, name, progress, status}
                            file_ids = [item["fid"] for item in files_to_process]
                            name_by_fid = {item["fid"]: item["name"] for item in files_to_process}
                            
                            try:
                                resp = requests.post(f"{api_base}/pdf/parse", json={
                                    "kbId": current_kb,
                                    "fileIds": file_ids,
                                    "method": parse_method_choice
                                }, timeout=30)
                                if resp.status_code == 200:
                                    submitted_jobs = resp.json().get("jobs", [])
                                    for job in submitted_jobs:
                                        fid = job.get("fileId")
                                        active_tasks.append({
                                            "fid": fid,
                                            "name": name_by_fid.get(fid, fid),
                                            "progress": 0,
                                            "status": "pending" if job.get("ok") else f"error: {_file_error_text(job)}"
                                        })
                                else:
                                    st.error(f"解析任务提交失败: {resp.text}")
                            except Exception as e:
                                st.error(f"解析任务提交失败: {e}")
                            submit_bar.progress(1.0, text=f"任务分发完成 1/1，共 {len(file_ids)} 个文件")
                            
                            submit_bar.empty()
                            st.toast(f"开始处理 {len(active_tasks)} 个文件的解析监控", icon="🕵️")
                            
                            # 2. 轮询监控进度
                            status_container = st.container(border=True)
                            with status_container:
                                st.markdown("**📊 实时解析进度**")
                                table_placeholder = st.empty()
                                
                                max_retries = PARSE_MONITOR_MAX_RETRIES
                                for _ in range(max_retries):
                                    all_done = True
                                    
                                    # 遍历更新状态
                                    for task in active_tasks:
                                        # 如果已经完成或失败，跳过请求
                                        if task["status"] == "ready" or str(task["status"]).startswith("error"):
                                            continue
                                            
                                        all_done = False
                                        try:
                                            r = requests.get(f"{api_base}/pdf/status", params={"kbId": current_kb, "fileId": task["fid"]}, timeout=PARSE_STATUS_TIMEOUT)
                                            if r.status_code == 200:
                                                d = r.json()
                                                # 使用 0-100 的整数进度，避免小数格式化问题
                                                task["progress"] = d.get("progress", 0) 
                                                task["status"] = d.get("status", "unknown")
                                        except:
                                            pass
                                    
                                    # 构造 DataFrame 显示
                                    df_status = pd.DataFrame(active_tasks)
                                    # 只需要简单的几列
                                    if not df_status.empty:
                                        table_placeholder.dataframe(
                                            df_status[["name", "progress", "status"]],
                                            column_config={
                                                "name": st.column_config.TextColumn("文件名", width="medium"),
                                                "progress": st.column_config.ProgressColumn(
                                                    "当前解析进度", 
                                                    min_value=0, 
                                                    max_value=100, 
                                                    format="%d%%"
                                                ),
                                                "status": st.column_config.TextColumn("状态", width="small")
                                            },
                                            use_container_width=True,
                                            hide_index=True,
                                            # 使用 dataframe 不需要每次强制刷新 key，除非数据没变但想刷 (这里数据在变)
                                            # key=f"status_table_{time.time()}" 
                                        )
                                    
                                    if all_done:
                                        st.success("🎉 所有文件解析完成！")
                                        break
                                    
                                    time.sleep(1.5)
                                else:
                                    st.warning("⚠️ 等待窗口已结束，后台可能仍在继续解析，请稍后在文件列表中查看最终状态。")

                    with col_b2:
                        # 索引一般需要解析完成后进行，但这里允许用户批量触发
                        if st.button(f"🚋 索引 ({uploaded_count})", use_container_width=True, help="建议确认文件解析完成（Ready）后再点击"):
                            # 准备显示容器
                            idx_container = st.container(border=True)
                            with idx_container:
                                st.markdown("**🏗️ 索引构建队列**")
                                idx_prog_bar = st.progress(0, text="准备开始...")
                                idx_status_text = st.empty()
                                
                                success_cnt = 0
                                errors = []
                                file_ids = [item["fid"] for item in files_to_process]
                                name_by_fid = {item["fid"]: item["name"] for item in files_to_process}
                                
                                idx_status_text.markdown(f"👉 正在处理: **{len(file_ids)} 个文件**")
                                try:
                                    resp = requests.post(f"{api_base}/index/build", json={
                                        "kbId": current_kb,
                                        "fileIds": file_ids
                                    }, timeout=3600)
                                    if resp.status_code == 200:
                                        data = resp.json()
                                        results = data.get("results") or []
                                        if results:
                                            for result in results:
                                                if result.get("ok"):
                                                    success_cnt += 1
                                                else:
                                                    fid = result.get("fileId")
                                                    errors.append(f"{name_by_fid.get(fid, fid)}: {_file_error_text(result)}")
                                        else:
                                            success_cnt = data.get("success", 0)
                                    else:
                                        errors.append(resp.text)
                                except Exception as e: 
                                    errors.append(str(e))

                                idx_prog_bar.progress(1.0)
                                
                                idx_status_text.success(f"✅ 完成！成功 {success_cnt} 个，失败 {len(errors)} 个")
                                if errors:
                                    st.error("失败详情:\n" + "\n".join(errors))
                                
                            time.sleep(2)
                            st.rerun()
                    
                    # 简单列表展示
                    with st.expander(f"查看当前批次文件 ({len(files_to_process)})", expanded=False):
                        for f in files_to_process:
                             st.text(f"📄 {f['name']} (ID: {f['fid']})")

                else:
                    if uploaded_files:
                        # 如果只是因为同名文件跳过，则不显示报错
                        all_duplicates = True
                        for up_file in uploaded_files:
                            f_key_check = f"{up_file.name}_{up_file.size}"
                            status_check = st.session_state.batch_status.get(f_key_check, {}).get("status")
                            if status_check != "duplicate":
                                all_duplicates = False
                                break
                        
                        if not all_duplicates:
                            st.error("没有文件上传成功，请检查后端服务。")

        st.divider()

        # === 库管理 Tabs (文件 / 图片 / 数值) ===
        m_tab1, m_tab2, m_tab3 = st.tabs(["📑 文件库管理", "🖼️ 图像管理", "📊 数值管理"])

        IMAGE_CACHE_SCHEMA = "image_page_fix_v5"

        def invalidate_image_cache(kb_id: str) -> None:
            cache_keys = [
                f"kb_imgs_{kb_id}",
                f"kb_imgs_loaded_{kb_id}",
                f"kb_imgs_schema_{kb_id}",
            ]
            for key in cache_keys:
                if key.endswith("_loaded_" + kb_id):
                    st.session_state[key] = False
                elif key.endswith("_schema_" + kb_id):
                    st.session_state[key] = IMAGE_CACHE_SCHEMA
                else:
                    st.session_state[key] = []
        
        # (KB信息已在顶部获取)

        # --- Tab 1: 文件管理 ---
        with m_tab1:
            kb_files = []
            try:
                r = requests.get(f"{api_base}/kb/files", params={"kbId": current_kb}, timeout=5)
                if r.status_code == 200:
                    kb_files = r.json().get("files", [])
            except Exception as e:
                st.error(f"无法获取文件列表: {e}")

            # 1. 批量操作区 / 列表
            if not kb_files:
                st.info("当前知识库为空，请先上传文件。")
            else:
                if "selected_files" not in st.session_state:
                    st.session_state.selected_files = set()
                valid_file_ids = {f.get("fileId") for f in kb_files if f.get("fileId")}
                st.session_state.selected_files.intersection_update(valid_file_ids)

                # 批量操作配置
                c_cfg1, c_cfg2 = st.columns([2, 5])
                with c_cfg1:
                     reparse_choice = st.selectbox(
                        "重新解析使用的模型:",
                        options=["original", "olmocr", "mineru"],
                        format_func=lambda x: {
                            "original": "基础解析 (快, 传统OCR)",
                            "olmocr": "增强解析 (慢, 多模态大模型)",
                            "mineru": "MinerU (文档解析/表格增强)",
                        }[x],
                        key="reparse_method_sel"
                    )

                # 工具栏
            col_tools_1, col_tools_2, col_tools_3, col_tools_4 = st.columns([1.5, 1.5, 1.5, 4])
            with col_tools_1:
                # 重新构建 (改为重新解析)
                if st.button("♻️ 重新解析", help="使用上方选择的解析模型，对选中的文件重新运行解析"):
                    if not st.session_state.selected_files:
                        st.warning("请先勾选文件")
                    else:
                        invalidate_image_cache(current_kb)
                        st.toast("正在启动重新解析任务...", icon="⏳")
                        
                        # 1. 准备任务列表
                        active_tasks = []
                        fid_name_map = {f['fileId']: f.get('fileName', f['fileId']) for f in kb_files}
                        
                        submit_bar = st.progress(0, text="正在分发任务...")
                        selected_file_ids = list(st.session_state.selected_files)
                        total_sel = len(selected_file_ids)
                        
                        cnt = 0
                        try:
                            resp = requests.post(
                                f"{api_base}/pdf/parse",
                                json={"kbId": current_kb, "fileIds": selected_file_ids, "method": reparse_choice},
                                timeout=30,
                            )
                            if resp.status_code == 200:
                                for job in resp.json().get("jobs", []):
                                    fid = job.get("fileId")
                                    fname = fid_name_map.get(fid, fid)
                                    if job.get("ok"):
                                        cnt += 1
                                        status = "pending"
                                    else:
                                        status = f"error: {_file_error_text(job)}"
                                    active_tasks.append({
                                        "fid": fid,
                                        "name": fname,
                                        "progress": 0,
                                        "status": status
                                    })
                            else:
                                st.error(f"任务提交失败: {resp.text}")
                        except Exception as e:
                            st.error(f"任务提交失败: {e}")

                        if not active_tasks:
                            for fid in selected_file_ids:
                                active_tasks.append({
                                    "fid": fid, 
                                    "name": fid_name_map.get(fid, fid), 
                                    "progress": 0, 
                                    "status": "error"
                                })
                        submit_bar.progress(1.0 if total_sel else 0)
                        
                        submit_bar.empty()
                        
                        if cnt > 0:
                            # 2. 进度监控
                            st.info(f"已提交 {cnt} 个解析任务，正在监控执行进度...")
                            status_container = st.container(border=True)
                            with status_container:
                                st.markdown("**📊 重新解析进度**")
                                table_placeholder = st.empty()
                                
                                max_retries = PARSE_MONITOR_MAX_RETRIES
                                for _ in range(max_retries):
                                    all_done = True
                                    for task in active_tasks:
                                        if task["status"] == "ready" or str(task["status"]).startswith("error"):
                                            continue
                                            
                                        all_done = False
                                        try:
                                            r = requests.get(f"{api_base}/pdf/status", params={"kbId": current_kb, "fileId": task["fid"]}, timeout=PARSE_STATUS_TIMEOUT)
                                            if r.status_code == 200:
                                                d = r.json()
                                                task["progress"] = d.get("progress", 0) 
                                                task["status"] = d.get("status", "unknown")
                                        except:
                                            pass
                                    
                                    # 渲染表格
                                    df_status = pd.DataFrame(active_tasks)
                                    if not df_status.empty:
                                        table_placeholder.dataframe(
                                            df_status[["name", "progress", "status"]],
                                            column_config={
                                                "name": st.column_config.TextColumn("文件名", width="medium"),
                                                "progress": st.column_config.ProgressColumn(
                                                    "当前解析进度", 
                                                    min_value=0, 
                                                    max_value=100, 
                                                    format="%d%%"
                                                ),
                                                "status": st.column_config.TextColumn("状态", width="small")
                                            },
                                            use_container_width=True,
                                            hide_index=True
                                        )
                                    
                                    if all_done:
                                        st.success("🎉 所有选中文件解析完成！")
                                        break
                                    
                                    time.sleep(1.5)
                                else:
                                    st.warning("⚠️ 等待窗口已结束，后台可能仍在继续解析，请稍后查看最终文件状态。")
                            
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("任务未能成功提交，请检查后端状态。")

            with col_tools_2:
                 # 重建索引
                if st.button("🏗️ 重建索引", help="基于现有的解析结果重新构建向量索引"):
                    if not st.session_state.selected_files:
                        st.warning("请先勾选文件")
                    else:
                        cnt = 0
                        errors = []
                        st.toast("正在提交索引构建任务...", icon="⏳")
                        
                        my_bar = st.progress(0, text="正在请求构建...")
                        selected_file_ids = list(st.session_state.selected_files)
                        fid_name_map = {f['fileId']: f.get('fileName', f['fileId']) for f in kb_files}
                        total = len(selected_file_ids)
                        
                        try:
                            r = requests.post(
                                f"{api_base}/index/build",
                                json={"kbId": current_kb, "fileIds": selected_file_ids},
                                timeout=3600,
                            )
                            if r.status_code == 200:
                                for result in r.json().get("results", []):
                                    fid = result.get("fileId")
                                    if result.get("ok"):
                                        cnt += 1
                                    else:
                                        errors.append(f"{fid_name_map.get(fid, fid)}: {_file_error_text(result)}")
                            else:
                                errors.append(r.text)
                        except Exception as e:
                            errors.append(str(e))
                        my_bar.progress(1.0 if total else 0)
                            
                        if errors:
                            st.error(f"完成 {cnt} 个，失败 {len(errors)} 个:\n" + "\n".join(errors))
                        else:
                            st.success(f"成功为 {cnt} 个文件重建索引")
                            time.sleep(1)
                            st.rerun()

            with col_tools_3:
                # 删除文件
                if st.button("🗑️ 删除文件", help="物理删除文件及其索引"):
                     if not st.session_state.selected_files:
                        st.warning("请先勾选文件")
                     else:
                        errors = []
                        for fid in st.session_state.selected_files:
                            try:
                                resp = requests.post(
                                    f"{api_base}/kb/file/delete", 
                                    json={"kbId": current_kb, "fileId": fid, "deleteFile": True, "deleteIndex": True}
                                )
                                if resp.status_code != 200:
                                    errors.append(f"{fid} 删除失败: {resp.text}")
                            except Exception as ex:
                                errors.append(f"{fid} 请求错误: {ex}")
                        
                        if errors:
                            st.error("\n".join(errors))
                        else:
                            st.session_state.selected_files = set()
                            st.success("文件已删除")
                            time.sleep(1)
                            st.rerun()

            with col_tools_4:
                # 删除索引
                if st.button("🧹 删除索引", help="仅清除向量索引，保留原文件"):
                     if not st.session_state.selected_files:
                        st.warning("请先勾选文件")
                     else:
                        errors = []
                        for fid in st.session_state.selected_files:
                            try:
                                resp = requests.post(
                                    f"{api_base}/kb/file/delete", 
                                    json={"kbId": current_kb, "fileId": fid, "deleteFile": False, "deleteIndex": True}
                                )
                                if resp.status_code != 200:
                                    errors.append(f"{fid} 索引清除失败: {resp.text}")
                            except Exception as ex:
                                errors.append(f"{fid} 请求错误: {ex}")
                        
                        if errors:
                            st.error("\n".join(errors))
                        else:
                           st.success("索引已清除")
                           time.sleep(1)
                           st.rerun()

           

            st.markdown("---")

            # 2. 文件列表头
            # 布局: [Check 0.5] [Filename 2.5] [Type 0.8] [ParseModel 1.5] [EmbedModel 1.5] [Status 1.5]
            h_c1, h_c2, h_c3, h_c4, h_c5, h_c6 = st.columns([0.5, 2.5, 0.8, 1.5, 1.5, 1.5])
            
            # === 全选逻辑 ===
            all_view_fids = [f.get('fileId') for f in kb_files]
            
            def on_change_select_all():
                is_select = st.session_state.select_all_files_key
                if is_select:
                    st.session_state.selected_files.update(all_view_fids)
                else:
                    st.session_state.selected_files.difference_update(all_view_fids)
                
                # 手动同步每个子 Checkbox 的状态，确保前端立刻刷新
                for fid in all_view_fids:
                    st.session_state[f"chk_{fid}"] = is_select

            # 计算当前是否全选以同步UI状态
            is_all_now = bool(all_view_fids) and all(fid in st.session_state.selected_files for fid in all_view_fids)
            st.session_state.select_all_files_key = is_all_now
            
            # 使用 checkbox 替代原来的 "**选择**" 文本
            # 空 label 避免占用额外高度，key 用于 callback
            h_c1.checkbox("全选", key="select_all_files_key", on_change=on_change_select_all)
            
            h_c2.markdown("<div style='text-align: left; font-weight: bold;'>文件名 (点击预览)</div>", unsafe_allow_html=True)
            h_c3.markdown("**类型**")
            h_c4.markdown("**分词/解析模型**")
            h_c5.markdown("**向量化模型**")
            h_c6.markdown("**状态**")

            # 定义预览弹窗
            def show_preview_dialog_content(fid, fname, is_excel, has_tables, page_count):
                st.caption(f"ID: {fid}")
                
                if is_excel:
                    preview_tabs = st.tabs(["📊 表格数据"])
                    with preview_tabs[0]:
                        with st.spinner("正在加载表格数据..."):
                            try:
                                r_df = requests.get(f"{api_base}/kb/file/dataframe", params={"kbId": current_kb, "fileId": fid})
                                if r_df.status_code == 200:
                                    sheets = r_df.json().get("sheets", {})
                                    if not sheets:
                                        st.warning("未识别到数据")
                                    else:
                                        # 如果有多个 sheet，用 tab 或 selectbox 切换
                                        sheet_names = list(sheets.keys())
                                        if len(sheet_names) > 1:
                                            selected_sheet = st.selectbox("选择工作表", sheet_names, key=f"sheet_sel_{fid}")
                                        else:
                                            selected_sheet = sheet_names[0]
                                        
                                        records = sheets[selected_sheet]
                                        df_preview = pd.DataFrame(records)
                                        st.dataframe(df_preview, use_container_width=True, height=500)
                                else:
                                    st.error(f"加载失败: {r_df.text}")
                            except Exception as e:
                                st.error(f"Error: {e}")


                else:
                    # PDF / 其它视图
                    tab_names = ["📝 解析内容 (Markdown)", "🖼️ 原始页面"]
                    if has_tables:
                        tab_names.insert(0, "📊 表格数据")
                    preview_tabs = st.tabs(tab_names)
                    tab_offset = 1 if has_tables else 0

                    if has_tables:
                        with preview_tabs[0]:
                            with st.spinner("正在加载表格数据..."):
                                try:
                                    r_df = requests.get(f"{api_base}/kb/file/dataframe", params={"kbId": current_kb, "fileId": fid})
                                    if r_df.status_code == 200:
                                        sheets = r_df.json().get("sheets", {})
                                        if not sheets:
                                            st.warning("未识别到表格")
                                        else:
                                            sheet_names = list(sheets.keys())
                                            if len(sheet_names) > 1:
                                                selected_sheet = st.selectbox("选择表格", sheet_names, key=f"table_sel_{fid}")
                                            else:
                                                selected_sheet = sheet_names[0]
                                            df_preview = pd.DataFrame(sheets[selected_sheet])
                                            st.dataframe(df_preview, use_container_width=True, height=500)
                                    else:
                                        st.error(f"加载失败: {r_df.text}")
                                except Exception as e:
                                    st.error(f"Error: {e}")
                    
                    # Tab 1: Content
                    with preview_tabs[tab_offset]:
                        try:
                            r_c = requests.get(f"{api_base}/kb/file/content", params={"kbId": current_kb, "fileId": fid})
                            if r_c.status_code == 200:
                                c = r_c.json().get("content", "")
                                st.text_area("Markdown Content", c, height=600)
                            else:
                                st.info("暂无 Markdown 内容 (请先解析)")
                        except Exception as e:
                            st.error(str(e))
                            
                    # Tab 2: Pages
                    with preview_tabs[tab_offset + 1]:
                        if page_count > 0:
                            # 顶部控制栏
                            col_ctrl, _ = st.columns([2, 2])
                            with col_ctrl:
                                mode = st.radio("显示模式", ["original", "parsed"], horizontal=True, 
                                                format_func=lambda x: "原始页面 (PDF)" if x=="original" else "解析预览 (检测框)",
                                                key=f"md_dlg_{fid}")
                            
                            st.divider()
                            
                            # 滚动容器显示所有页面
                            with st.container(height=650):
                                for pg in range(1, page_count + 1):
                                    st.caption(f"📄 Page {pg} / {page_count}")
                                    u = f"{api_base}/pdf/page?kbId={current_kb}&fileId={fid}&page={pg}&type={mode}"
                                    # 利用浏览器缓存，滚动加载
                                    st.image(u, use_container_width=True)
                                    st.divider()
                        else:
                            st.info("无页面图像")

            use_dialog = hasattr(st, "dialog")
            if use_dialog:
                @st.dialog("📄 文件预览", width="large")
                def open_prev_dlg(fid, fname, is_excel, has_tables, page_count):
                    show_preview_dialog_content(fid, fname, is_excel, has_tables, page_count)

            # 3. 渲染每一行 (使用滚动容器)
            with st.container(height=500):
                for f in kb_files:
                    fid = f.get('fileId')
                    fname = f.get('fileName') or fid
                    page_count = f.get('pageCount', 0)
                    file_type = f.get('type', 'unknown').upper()
                    is_excel = f.get('type') == 'excel'
                    has_tables = f.get('hasTables', False)
                    
                    # 行容器
                    row_c1, row_c2, row_c3, row_c4, row_c5, row_c6 = st.columns([0.5, 2.5, 0.8, 1.5, 1.5, 1.5])
                    
                    # Col 1: Checkbox
                    is_checked = fid in st.session_state.selected_files
                    
                    # Manual state handling
                    # 为了避免 Streamlit "created with a default value but also set via Session State API" 警告，
                    # 我们不再使用 value=... 参数，而是确保 key 在 session_state 中已经初始化。
                    if f"chk_{fid}" not in st.session_state:
                        st.session_state[f"chk_{fid}"] = is_checked

                    new_checked = row_c1.checkbox("", key=f"chk_{fid}")
                    if new_checked != is_checked:
                        if new_checked: st.session_state.selected_files.add(fid)
                        else: st.session_state.selected_files.discard(fid)
                        st.rerun()

                    # Col 2: Filename Button -> Preview
                    if row_c2.button(f"📄 {fname}", key=f"btn_file_{fid}", help="点击预览", use_container_width=True):
                        if use_dialog:
                            open_prev_dlg(fid, fname, is_excel, has_tables, page_count)
                        else:
                            # Fallback: Expander at top? or Toast
                            st.toast("升级 Streamlit 可使用弹窗预览", icon="⚠️")
                    
                    # Col 3: Type
                    row_c3.text(file_type)

                    # Col 4: Parsing Model
                    method_label_map = {
                        "original": "基础解析",
                        "olmocr": "OLMOCR",
                        "mineru": "MinerU",
                        "pandas": "Pandas",
                    }
                    parse_method = str(f.get("parseMethod") or "").lower()
                    p_model = method_label_map.get(parse_method) or f.get("parser") or "未记录"
                    if is_excel:
                        p_model = "Pandas"
                    row_c4.text(p_model)

                    # Col 5: Embed Model
                    row_c5.text(kb_embed_model)

                    # Col 6: Status
                    is_parsed = f.get('hasParsed', False)
                    is_indexed = f.get('isIndexed', False)
                    
                    status_md = ""
                    if is_parsed:
                        status_md += "✅ 解析完成<br>"
                    else:
                        status_md += "⏳ 解析中...<br>"
                        
                    if is_indexed:
                        status_md += "🔵 已索引"
                    else:
                        status_md += "⚪ 未索引"
                        
                    row_c6.markdown(status_md, unsafe_allow_html=True)
                    
                    st.divider()

        # --- Tab 2: 图像管理 ---
        with m_tab2:
            st.caption("管理知识库中提取的所有图片。可直接修改文件名和描述，或勾选删除后统一保存。")
            
            # 状态 Key
            k_imgs = f"kb_imgs_{current_kb}"
            # 标记是否已加载过 (用于自动加载)
            k_imgs_loaded = f"kb_imgs_loaded_{current_kb}"
            k_imgs_schema = f"kb_imgs_schema_{current_kb}"

            if k_imgs not in st.session_state:
                st.session_state[k_imgs] = []
            if k_imgs_loaded not in st.session_state:
                st.session_state[k_imgs_loaded] = False
            if st.session_state.get(k_imgs_schema) != IMAGE_CACHE_SCHEMA:
                st.session_state[k_imgs] = []
                st.session_state[k_imgs_loaded] = False
                st.session_state[k_imgs_schema] = IMAGE_CACHE_SCHEMA

            # 定义加载数据的函数
            def load_images_data():
                try:
                    r_imgs = requests.get(
                        f"{api_base}/kb/images",
                        params={"kbId": current_kb, "_ts": int(time.time())},
                        timeout=10,
                    )
                    if r_imgs.status_code == 200:
                        st.session_state[k_imgs] = r_imgs.json().get("images", [])
                        st.session_state[k_imgs_loaded] = True
                    else:
                        st.error(f"Failed: {r_imgs.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

            # 1. 自动加载逻辑 (如果从未加载过)
            if not st.session_state[k_imgs_loaded]:
                with st.spinner("正在自动加载图片列表..."):
                    load_images_data()
                    st.rerun()

            # 2. 手动刷新和保存按钮
            action_col_refresh, action_col_save = st.columns([1, 1])
            with action_col_refresh:
                if st.button("🔄 刷新图片列表", key="btn_load_imgs_real"):
                    with st.spinner("正在刷新..."):
                        load_images_data()
                        st.rerun()
            with action_col_save:
                save_images_requested = st.button(
                    "💾 保存图片修改",
                    type="primary",
                    key="btn_save_imgs",
                    disabled=not bool(st.session_state[k_imgs]),
                )
            
            images_data = st.session_state[k_imgs]
            if not images_data:
                if st.session_state[k_imgs_loaded]:
                    st.info("当前知识库未检测到已解析的图片。")
            else:
                # 转换为 DataFrame 以使用 DataEditor
                # 字段: Preview (Image URL), FileName, Source (Page), Summary (Editable)
                
                # 构造用于显示的列表
                display_rows = []
                for idx, img in enumerate(images_data):
                    fname = img.get('fileName', 'Unknown')
                    page = img.get('source_page_num', img.get('page_num', 0))
                    try:
                        page = int(page or 0)
                    except Exception:
                        page = 0
                    page_display = str(page) if page > 0 else "未知（需重新解析）"
                    desc = img.get('summary', '')
                    img_path = img.get('img_name', '')
                    fid = img.get('fileId')
                    
                    # 构造图片 URL
                    # 注意：api_base 可能是 localhost:8001/api/v1
                    # 需要 quote img_path
                    enc_path = urllib.parse.quote(img_path)
                    img_url = f"{api_base}/pdf/images?kbId={current_kb}&fileId={fid}&imagePath={enc_path}"
                    
                    display_rows.append({
                        "id": idx, # 用于索引
                        "file_id": fid,
                        "old_img_name": img_path, # 原始文件名，用于回传
                        "删除": False,
                        "图片预览": img_url,
                        "图片名称": img_path,
                        "图片来源": f"{fname} - P{page_display}",
                        "来源文件": fname,
                        "页码": page_display,
                        "图片描述 (可编辑)": desc
                    })
                
                df_imgs = pd.DataFrame(display_rows)
                
                # 配置列
                column_config = {
                    "删除": st.column_config.CheckboxColumn("删除", width="small", help="勾选后点击保存会删除该图片"),
                    "图片预览": st.column_config.ImageColumn("预览", width="medium"),
                    "图片名称": st.column_config.TextColumn("文件名", width="medium", help="可修改图片文件名；不写扩展名时后端会保留原扩展名"),
                    "来源文件": st.column_config.TextColumn("来源文件", width="small", disabled=True),
                    "页码": st.column_config.TextColumn("页码", width="small", disabled=True),
                    "图片描述 (可编辑)": st.column_config.TextColumn("图片描述", width="large"),
                    "id": None, # Hide
                    "file_id": None,
                    "old_img_name": None,
                    "图片来源": None
                }
                
                edited_df = st.data_editor(
                    df_imgs[["删除", "图片预览", "图片名称", "来源文件", "页码", "图片描述 (可编辑)", "id", "file_id", "old_img_name"]],
                    column_config=column_config,
                    use_container_width=True,
                    key="img_ed_tab2",
                    height=600,
                    hide_index=True
                )
                
                if save_images_requested:
                    new_records = edited_df.to_dict('records')
                    file_groups = {}
                    changed_file_ids = set()
                    proposed_names_by_file = {}
                    validation_errors = []
                    has_changes = False

                    for row in new_records:
                        idx = int(row['id'])
                        original = images_data[idx]
                        fid = original['fileId']
                        original_name = str(original.get('img_name', '')).strip()
                        mark_delete = bool(row.get("删除"))
                        new_name = str(row.get("图片名称") or "").strip()
                        new_desc = str(row.get("图片描述 (可编辑)") or "")

                        if mark_delete:
                            has_changes = True
                            changed_file_ids.add(fid)
                            continue

                        if not new_name:
                            validation_errors.append(f"{original_name}: 文件名不能为空")
                            continue
                        if re.search(r'[\\/:*?"<>|]', new_name):
                            validation_errors.append(f"{new_name}: 文件名不能包含 \\ / : * ? \" < > |")
                            continue

                        name_key = new_name.strip().lower()
                        proposed_names_by_file.setdefault(fid, set())
                        if name_key in proposed_names_by_file[fid]:
                            validation_errors.append(f"{new_name}: 同一文件下图片文件名重复")
                            continue
                        proposed_names_by_file[fid].add(name_key)

                        if new_name != original_name or new_desc != str(original.get('summary', '')):
                            has_changes = True
                            changed_file_ids.add(fid)

                        clean_item = {
                            "old_img_name": original_name,
                            "img_name": new_name,
                            "summary": new_desc,
                            "page_num": original.get("page_num"),
                            "source_page_num": original.get("source_page_num"),
                            "original_img_name": original.get("original_img_name") or original_name,
                        }
                        if original.get("bbox") is not None:
                            clean_item["bbox"] = original.get("bbox")
                        file_groups.setdefault(fid, []).append(clean_item)

                    if validation_errors:
                        st.error("请先修正以下问题：\n" + "\n".join(validation_errors[:6]))
                    elif not has_changes:
                        st.info("未检测到任何修改")
                    else:
                        updated_files = sorted(changed_file_ids)
                        success_count = 0
                        progress_bar = st.progress(0, text="正在保存图片修改...")

                        for i, fid in enumerate(updated_files):
                            subset = file_groups.get(fid, [])
                            try:
                                r_up = requests.post(f"{api_base}/kb/images/update", json={
                                    "kbId": current_kb,
                                    "fileId": fid,
                                    "summaries": subset
                                })
                                if r_up.status_code == 200:
                                    success_count += 1
                                else:
                                    st.error(f"文件 {fid} 更新失败: {r_up.text}")
                            except Exception as e:
                                st.error(f"Error updating {fid}: {e}")
                            progress_bar.progress((i + 1) / len(updated_files), text="正在保存图片修改...")

                        if success_count > 0:
                            st.session_state[k_imgs] = []
                            st.session_state[k_imgs_loaded] = False
                            st.success(f"成功更新 {success_count} 个文件的图片，索引已重建。")
                            time.sleep(1)
                            st.rerun()

        # --- Tab 3: 数值管理 ---
        with m_tab3:
            st.caption("管理知识库中所有结构化数值文件（Excel/CSV）以及从 PDF/Word 中提取出的表格。")
            
            # 过滤结构化文件
            struct_files = [f for f in kb_files if f.get('type') == 'excel' or f.get('hasTables')]
            
            if not struct_files:
                st.info("当前知识库没有结构化数值文件或已提取的 PDF/Word 表格。")
            else:
                # 初始化选择状态
                if "selected_struct_fid" not in st.session_state:
                    st.session_state.selected_struct_fid = None

                # 左右布局：列表 | 详情
                col_struct_list, col_struct_detail = st.columns([1, 3])
                
                # 左侧：可滚动的文件列表
                with col_struct_list:
                    st.markdown("### 📂 文件列表")
                    with st.container(height=600):
                        for f in struct_files:
                            fid = f.get('fileId')
                            fname = f.get('fileName') or fid
                            icon = "📄" if f.get('type') in ['pdf', 'word'] else "📊"
                            suffix = f" · {f.get('tableCount', 0)} 表" if f.get('hasTables') else ""
                            
                            # 选中高亮样式 (通过 type="primary" 实现)
                            btn_type = "primary" if st.session_state.selected_struct_fid == fid else "secondary"
                            
                            # 为了保证 key 唯一且点击有效
                            if st.button(f"{icon} {fname}{suffix}", key=f"btn_struct_{fid}", type=btn_type, use_container_width=True):
                                st.session_state.selected_struct_fid = fid
                                st.rerun()

                # 右侧：详情展示
                with col_struct_detail:
                    current_struct_fid = st.session_state.selected_struct_fid
                    # 校验选中文件是否仍在当前列表中
                    if current_struct_fid and not any(sf.get('fileId') == current_struct_fid for sf in struct_files):
                        current_struct_fid = None
                        st.session_state.selected_struct_fid = None
                    
                    if not current_struct_fid:
                        st.info("👈 请在左侧选择一个文件查看详情")
                    else:
                        # 获取当前选中文件的名称
                        curr_file_obj = next((f for f in struct_files if f['fileId'] == current_struct_fid), None)
                        curr_fname = curr_file_obj.get('fileName') if curr_file_obj else current_struct_fid
                        curr_type = curr_file_obj.get('type') if curr_file_obj else ""
                        
                        st.markdown(f"### 📄 {curr_fname}")
                        if curr_type == "pdf":
                            st.caption("来源：PDF 解析提取表格")
                        elif curr_type == "word":
                            st.caption("来源：Word 解析提取表格")
                        st.divider()
                        
                        # 加载数据
                        with st.spinner("正在加载数据..."):
                            try:
                                r_df = requests.get(f"{api_base}/kb/file/dataframe", params={"kbId": current_kb, "fileId": current_struct_fid})
                                if r_df.status_code == 200:
                                    sheets = r_df.json().get("sheets", {})
                                    if not sheets:
                                        st.warning("⚠️ 文件读取为空或格式不支持")
                                    else:
                                        # 多 Sheet 展示
                                        sheet_names = list(sheets.keys())
                                        if len(sheet_names) > 1:
                                            # 使用 Tabs 切换 Sheet
                                            tabs_sheets = st.tabs(sheet_names)
                                            for i, s_name in enumerate(sheet_names):
                                                with tabs_sheets[i]:
                                                    df_sheet = pd.DataFrame(sheets[s_name])
                                                    st.dataframe(df_sheet, use_container_width=True, height=550)
                                                    st.caption(f"共 {len(df_sheet)} 行 | Sheet: {s_name}")
                                        else:
                                            # 单 Sheet 直接展示
                                            s_name = sheet_names[0]
                                            df_sheet = pd.DataFrame(sheets[s_name])
                                            st.dataframe(df_sheet, use_container_width=True, height=600)
                                            st.caption(f"共 {len(df_sheet)} 行")
                                            
                                else:
                                    st.error(f"❌ 加载失败: {r_df.text}")
                            except Exception as e:
                                st.error(f"❌ 请求错误: {e}")

        st.caption("数据预处理已迁移到顶部同级页签“数据预处理”。")

# --- Tab 7: 数据预处理 ---
with tab7:
    st.header("数据预处理")
    render_data_preprocess_workspace()

# --- Tab 5: 知识提取 ---
with tab5:
    st.header("知识提取与结构化")
    st.caption("上传文档 -> 定义提取目标 -> 智能提取 -> 存入知识库")

    # init session state for extraction
    if "ext_job_id" not in st.session_state:
        st.session_state.ext_job_id = None
    if "ext_job_info" not in st.session_state:
        st.session_state.ext_job_info = None

    col_ex_1, col_ex_2 = st.columns([1, 1])

    with col_ex_1:
        st.subheader("1. 文件与配置")
        uploaded_file = st.file_uploader(
            "上传待提取的文件 (PDF, Word, Excel, CSV, TXT, 图片)",
            type=["pdf", "docx", "xlsx", "csv", "txt", "md", "png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff"],
        )
        
        # --- 预置模板逻辑 ---
        PRESET_TEMPLATES = {
            "地层压力和温度": (
                "请提取'地层压力和温度'表格。该表通常包含多级表头。\n"
                "目标列(JSON Key)：\n"
                "- 序号\n"
                "- 井号\n"
                "- 原始_饱和压力_MPa\n"
                "- 原始_地层压力_MPa\n"
                "- 原始_压力系数\n"
                "- 原始_油层温度_℃\n"
                "- 原始_地温梯度_℃/100m\n"
                "- 结论_温度\n"
                "- 结论_压力\n"
                "- 备注\n"
                "注意：请处理'原始'和'结论'下的合并单元格结构，将子列的数据准确提取到对应字段。"
            ),
            "油水关系及油藏类型": (
                "请提取'油水关系及油藏类型'表格。\n"
                "目标列(JSON Key)：\n"
                "- 序号\n"
                "- 层位\n"
                "- 油藏类型\n"
                "- 油藏类型细分\n"
                "- 边底水\n"
                "- 气顶\n"
                "- 油水界面_m\n"
                "- 备注\n"
                "注意：若存在合并行，请将合并内容填充到每一行。"
            ),
            "油分析": (
                "请提取'原油分析'或'油分析'表格。\n"
                "目标列(JSON Key)：\n"
                "- 序号\n"
                "- 层位\n"
                "- 取样_取样井号\n"
                "- 取样_取样井段_m\n"
                "- 取样_取样时间\n"
                "- 油分析_测粘温度_℃\n"
                "- 油分析_地面密度_g/cm3\n"
                "- 油分析_地面粘度_mPa.s\n"
                "- 油分析_凝固点_℃\n"
                "- 油分析_含硫_%\n"
                "- 油分析_含蜡_%\n"
                "- 油分析_H2S 含量_%\n"
                "- 结论\n"
                "注意：若存在合并行，请将合并内容填充到每一行。"
            ),
            "水分析": (
                "请提取'地层水分析'或'水分析'表格。\n"
                "目标列(JSON Key)：\n"
                "- 序号\n"
                "- 层位\n"
                "- 取样_取样井号\n"
                "- 取样_取样井段_m\n"
                "- 取样_取样时间\n"
                "- 水分析_Na+_mg/l\n"
                "- 水分析_Mg+_mg/l\n"
                "- 水分析_Ca+_mg/l\n"
                "- 水分析_Cl-_mg/l\n"
                "- 水分析_SO4-_mg/l\n"
                "- 水分析_CO3-_mg/l\n"
                "- 水分析_总矿化度_mg/l\n"
                "- 结论\n"
                "注意：若存在合并行，请将合并内容填充到每一行。"
            ),
            "气分析": (
                "请提取'天然气分析'或'气分析'表格。\n"
                "目标列(JSON Key)：\n"
                "- 序号\n"
                "- 层位\n"
                "- 取样_取样井号\n"
                "- 取样_取样井段_m\n"
                "- 取样_取样时间\n"
                "- 气分析_氦\n"
                "- 气分析_氢\n"
                "- 气分析_氧\n"
                "- 气分析_氮\n"
                "- 气分析_二氧化碳\n"
                "- 气分析_乙烷\n"
                "- 气分析_丙烷\n"
                "- 气分析_异丁烷\n"
                "- 气分析_正丁烷\n"
                "- 气分析_新戊烷\n"
                "- 气分析_异戊烷\n"
                "- 气分析_正戊烷\n"
                "- 气分析_己烷\n"
                "- 气分析_庚烷和更重组分\n"
                "- 气分析_一氧化碳\n"
                "- 气分析_硫化氢\n"
                "- 气分析_二氧化硫\n"
                "注意：若存在合并行，请将合并内容填充到每一行。"
            )
        }

        # 初始化 Prompt 状态键
        if "extraction_prompt_text" not in st.session_state:
            st.session_state.extraction_prompt_text = ""

        # 模式选择
        ext_mode = st.radio("指令模式", ["自定义输入", "预置模板 (油气领域)"], horizontal=True)
        
        if ext_mode == "预置模板 (油气领域)":
            selected_tmpl_key = st.selectbox("选择提取模板", list(PRESET_TEMPLATES.keys()))
            # 检测模板切换，自动填充 Text Area
            if st.session_state.get("last_selected_tmpl") != selected_tmpl_key:
                st.session_state.extraction_prompt_text = PRESET_TEMPLATES[selected_tmpl_key]
                st.session_state.last_selected_tmpl = selected_tmpl_key
        
        extraction_instruction = st.text_area(
            "提取指令 (Prompt)", 
            key="extraction_prompt_text",
            height=150,
            placeholder="例如：\n请提取文档中的所有发票信息，包含发票代码、号码、金额、日期。\n或者：提取所有提到的公司名称及其对应的地址。"
        )
        
        output_fmt = st.selectbox("输出格式", ["Excel", "CSV"])
        custom_filename = st.text_input("保存文件名 (可选)", placeholder="留空则自动生成: extracted_{timestamp}")
        
        parse_method = st.selectbox(
            "解析模型",
            options=["original", "olmocr", "mineru"],
            format_func=lambda x: {
                "original": "基础解析 (结构化OCR, 适合文本/表格)",
                "olmocr": "多模态大模型 (视觉增强, 适合复杂排版)",
                "mineru": "MinerU (文档解析/表格增强)",
            }[x]
        )
        
        if st.session_state.ext_job_id:
            if st.button("🔄 如果卡住点此重置状态"):
                st.session_state.ext_job_id = None
                st.session_state.ext_job_info = None
                st.rerun()

    with col_ex_2:
        st.subheader("2. 目标知识库")
        
        # Fetch KBs
        kb_options = {}
        try:
            r_kb = requests.get(f"{api_base}/kb/list", timeout=3)
            if r_kb.status_code == 200:
                kb_list_data = r_kb.json().get("kbs", [])
                for k in kb_list_data:
                    kid = k.get("kbId")
                    kname = k.get("kbName", kid)
                    display = f"{kname} ({kid})" if kname != kid else kid
                    kb_options[kid] = display
        except:
            pass
            
        kb_mode = st.radio("选择知识库模式", ["现有知识库", "新建知识库"], horizontal=True)
        
        target_kb_id = ""
        if kb_mode == "现有知识库":
            if kb_options:
                target_kb_id = st.selectbox(
                    "选择目标知识库", 
                    list(kb_options.keys()),
                    format_func=lambda x: kb_options[x]
                )
            else:
                st.warning("暂无可用知识库，请选择新建")
                kb_mode = "新建知识库" # Force new
        
        if kb_mode == "新建知识库":
            # 复用新建逻辑
            existing_kbs_list = []
            if kb_list_data:
                 existing_kbs_list = kb_list_data
            
            created_id = handle_create_kb("extract_tab", existing_kbs_list, api_base)
            if created_id:
                target_kb_id = created_id
            else:
                st.caption("请在上方新建知识库 (创建成功后请切换到'现有知识库'选择)")

    st.divider()
    
    # Action Button
    if st.button("🚀 开始提取", type="primary", use_container_width=True, disabled=(st.session_state.ext_job_id is not None)):
        if not uploaded_file:
            st.warning("请先上传文件")
        elif not target_kb_id:
            st.warning("请指定目标知识库")
        elif not extraction_instruction:
            st.warning("请输入提取指令")
        else:
            try:
                with st.spinner("正在上传文件并创建任务..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {
                        "instruction": extraction_instruction,
                        "kb_id": target_kb_id,
                        "output_format": output_fmt,
                        "custom_filename": custom_filename,
                        "parse_method": parse_method
                    }
                    resp = requests.post(f"{api_base}/extraction/extract", files=files, data=data, timeout=600)
                    if resp.status_code == 200:
                        job_data = resp.json()
                        st.session_state.ext_job_id = job_data.get("jobId")
                        st.session_state.ext_job_info = None
                        st.rerun()
                    else:
                        st.error(f"启动失败: {resp.text}")
            except Exception as e:
                st.error(f"请求错误: {e}")

    # Status Monitor
    if st.session_state.ext_job_id:
        st.info("🔄 任务进行中，自动刷新页面中...")
        
        try:
            r_stat = requests.get(f"{api_base}/extraction/status", params={"jobId": st.session_state.ext_job_id})
            if r_stat.status_code == 200:
                job_info = r_stat.json()
                st.session_state.ext_job_info = job_info
                
                status = job_info.get("status")
                progress = job_info.get("progress", 0)
                
                # Progress Bar
                st.progress(int(progress), text=f"当前阶段: {status} ({progress}%)")
                
                # Show parsed content if ready (Parsing happens at progress > 10, usually > 40 means done parsing)
                if job_info.get("parsed_file_path") and progress >= 40:
                    with st.expander("📝 能够查看解析后的中间内容 (Parsed Content)", expanded=False):
                        if st.button("加载/刷新解析内容"):
                            try:
                                r_cnt = requests.get(f"{api_base}/extraction/content", params={"jobId": st.session_state.ext_job_id})
                                if r_cnt.status_code == 200:
                                    st.text_area("解析结果", r_cnt.json().get("content"), height=400)
                                else:
                                    st.error("获取内容失败")
                            except:
                                st.error("网络请求失败")

                if status == "completed":
                    st.success("✅ 提取完成！")
                    extracted_data = job_info.get("data", [])
                    res_path = job_info.get("result_filepath", "")
                    rel_context = job_info.get("relevant_context", "")
                    rel_pages = job_info.get("relevant_pages", [])

                    if rel_context:
                        with st.expander("🔍 查看定位到的源文件上下文与页面 (Source Context & Pages)", expanded=False):
                            c1, c2 = st.columns([1, 1])
                            with c1:
                                st.text_area("提取所基于的文本上下文:", rel_context, height=400)
                            with c2:
                                if rel_pages:
                                    st.markdown(f"**定位到的相关页面 (共 {len(rel_pages)} 页)**")
                                    # Create Tabs for pages if multiple
                                    if len(rel_pages) > 1:
                                        p_tabs = st.tabs([f"Page {p}" for p in rel_pages])
                                        for idx, p in enumerate(rel_pages):
                                            with p_tabs[idx]:
                                                st.image(f"{api_base}/extraction/image?jobId={st.session_state.ext_job_id}&page={p}", caption=f"Original Page {p}", use_container_width=True)
                                    else:
                                        p = rel_pages[0]
                                        st.image(f"{api_base}/extraction/image?jobId={st.session_state.ext_job_id}&page={p}", caption=f"Original Page {p}", use_container_width=True)
                                else:
                                    st.info("未能自动定位到具体页码图像")
                    
                    st.subheader("提取结果预览")
                    if extracted_data:
                        df_res = pd.DataFrame(extracted_data)
                        
                        st.caption("✏️ 您可以直接双击下方表格单元格进行修改，如需增删行请使用表格工具栏。修改完成后请点击“保存修改并入库”。")
                        edited_df = st.data_editor(
                            df_res, 
                            use_container_width=True, 
                            num_rows="dynamic",
                            key="extraction_editor"
                        )
                        
                        col_btns_1, col_btns_2 = st.columns([1, 1])
                        
                        with col_btns_1:
                            if st.button("💾 保存修改并入库", type="primary"):
                                try:
                                    # Convert DF back to list of dicts
                                    # Handle NaN/inf for JSON compliance
                                    cleaned_df = edited_df.fillna("") 
                                    new_data = cleaned_df.to_dict(orient='records')
                                    
                                    r_up = requests.post(f"{api_base}/extraction/update_result", json={
                                        "jobId": st.session_state.ext_job_id,
                                        "data": new_data
                                    })
                                    
                                    if r_up.status_code == 200:
                                        st.toast("修改已保存到知识库！", icon="✅")
                                        # Update session state to reflect changes
                                        st.session_state.ext_job_info['data'] = new_data
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"保存失败: {r_up.text}")
                                except Exception as e:
                                    st.error(f"请求错误: {e}")

                        with col_btns_2:
                            # Download Button
                            if res_path and os.path.exists(res_path):
                                with open(res_path, "rb") as f:
                                    st.download_button(
                                        label=f"⬇️ 下载结果 ({output_fmt})",
                                        data=f,
                                        file_name=os.path.basename(res_path),
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if output_fmt == "Excel" else "text/csv"
                                    )
                    else:
                        st.warning("未提取到有效数据，请检查指令或文档内容。")
                    
                    if st.button("开启新任务"):
                        st.session_state.ext_job_id = None
                        st.session_state.ext_job_info = None
                        st.rerun()

                elif status == "failed":
                    st.error(f"❌ 任务失败: {job_info.get('error')}")
                    if st.button("重试 / 返回"):
                        st.session_state.ext_job_id = None
                        st.session_state.ext_job_info = None
                        st.rerun()
                else:
                    # Still running
                    time.sleep(2)
                    st.rerun()
            else:
                st.error("无法获取任务状态")
                time.sleep(5)
                st.rerun()
                
        except Exception as e:
            st.error(f"轮询错误: {e}")
            time.sleep(5)
            st.rerun()
