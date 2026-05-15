# MUL-RAG 启动说明（后端 + 前端 + MinerU）

本文档包含本项目完整的启动方式：
- 一键脚本启动（推荐）
- 手动分别启动后端/前端
- 使用 `mineru` 解析方式时的独立环境配置
- 可选 OLMOCR 服务启动（仅在使用 `olmocr` 解析方式时需要）

## 0. 目录约定

以下命令默认在项目根目录执行：

```bash
cd /home/lrn/MUL_RAG
```

## 快速启动

如果只使用 `mineru` / `olmocr`，或主要解析 Word 文档，不想启动时预下载 Unstructured 的 `yolox_l0.05.onnx`，推荐：

```bash
cd /home/lrn/MUL_RAG
PRELOAD_UNSTRUCTURED_MODELS=0 bash start_mul_rag.sh
```

如果需要使用基础解析 `original`，则直接启动，会检查并下载 YOLOX 布局模型：

```bash
cd /home/lrn/MUL_RAG
bash start_mul_rag.sh
```

停止服务：

```bash
cd /home/lrn/MUL_RAG
bash stop_mul_rag.sh
```

## 1. Conda 环境准备

### 1.1 主环境（后端 + 前端）

```bash
conda env create -f mul_rag_environment.yml
```

如环境已存在，可跳过。

### 1.2 MinerU 独立环境（推荐，若使用 mineru）

MinerU 依赖较重，推荐放在独立环境中。后端仍运行在 `mul_rag` 主环境，通过 `MINERU_CMD` 调用独立环境里的 `mineru` 命令。

建议创建独立环境：

```bash
conda create -n mineru python=3.10 -y
conda activate mineru
pip install --upgrade pip
pip install uv
uv pip install -U "mineru[all]"
```

MinerU 官方 CLI 用法：

```bash
mineru -p <input_path> -o <output_path>
```

CPU 环境建议使用 `pipeline` 后端：

```bash
mineru -p <input_path> -o <output_path> -b pipeline
```

国内网络可切换模型源并提前下载模型：

```bash
export MINERU_MODEL_SOURCE=modelscope
mineru-models-download
```

如果已经下载到本地，并希望解析时只用本地模型：

```bash
export MINERU_MODEL_SOURCE=local
```

参考：
- MinerU GitHub: https://github.com/opendatalab/MinerU
- MinerU CLI 使用: https://opendatalab.github.io/MinerU/usage/quick_usage/
- MinerU 模型源: https://opendatalab.github.io/MinerU/usage/model_source/
- MinerU 输出文件: https://opendatalab.github.io/MinerU/reference/output_files/

## 2. 推荐方式：一键启动前后端

```bash
cd /home/lrn/MUL_RAG
bash start_mul_rag.sh
```

脚本会自动：
- 先预下载基础解析需要的布局模型 `unstructuredio/yolo_x_layout`
- 启动后端（`127.0.0.1:8002`）
- 启动前端（`127.0.0.1:8501`）
- 注入 `MINERU_CMD` / `MINERU_BACKEND`（若检测到独立环境）
- 如果存在 `~/mineru.json`，自动注入 `MINERU_MODEL_SOURCE=local`
- 写入日志到 `logs/`

预下载阶段会输出“缓存命中/下载中/下载完成”，默认超时 1800 秒（30 分钟）。

如果你暂时不想预下载，可以执行：

```bash
PRELOAD_UNSTRUCTURED_MODELS=0 bash start_mul_rag.sh
```

如果网络较慢，可调大超时：

```bash
PRELOAD_TIMEOUT_SEC=3600 bash start_mul_rag.sh
```

停止服务：

```bash
cd /home/lrn/MUL_RAG
bash stop_mul_rag.sh
```

## 3. 手动启动（分开启动后端/前端）

### 3.1 启动后端

```bash
conda activate mul_rag
cd /home/lrn/MUL_RAG/MUL_rag/mul_rag/backend
AUTO_DOWNLOAD_NLTK=False \
MINERU_CMD=/home/lrn/anaconda3/envs/mineru/bin/mineru \
MINERU_BACKEND=pipeline \
MINERU_MODEL_SOURCE=local \
uvicorn app:app --host 127.0.0.1 --port 8002
```

说明：
- `MINERU_CMD`：指向独立环境中的 `mineru` 可执行文件。
- `MINERU_BACKEND`：默认 `pipeline`，适合 CPU 或低显存环境；也可按 MinerU 官方文档改为 `hybrid-auto-engine` 等后端。
- `MINERU_METHOD`：可选 `auto` / `txt` / `ocr`，不设置时使用 MinerU 默认值。
- `MINERU_LANG`：可选 `ch` / `en` 等，中文文档可设为 `ch` 提升 OCR 识别。
- `MINERU_MODEL_SOURCE`：可设为 `modelscope`、`huggingface` 或 `local`。
- `MINERU_TIMEOUT=3600`：可选超时配置，单位秒。
- 后端请运行在 `mul_rag` 主环境，不要把后端直接切到 `mineru` 环境中。
- Word 文档（`.docx`）会自动使用 `mineru` 解析；`.doc` 会先转换为 `.docx` 再解析；`original` / `olmocr` 只适合 PDF。DOCX 图片标题通常优先取图片上方文本。

### 3.2 启动前端

#### streamlit前端启动
```bash
conda activate mul_rag
cd /home/lrn/MUL_RAG
python -m streamlit run MUL_rag/mul_rag/streamlit_app.py --server.address 127.0.0.1 --server.port 8501

```
#### vue前端启动
```bash
npm run dev -- --host 127.0.0.1 --port 5174
```

前端和后端需要分开执行：
- 先在一个终端启动后端，确认没有报错后再继续。
- 再开一个新终端启动前端。

## 4. 可选：OLMOCR 服务启动（仅 `olmocr` 解析方式需要）

当你在前端“解析方式”选择 `olmocr` 时，需要额外启动 OLMOCR 推理服务。

当前集成方式是：后端先把 PDF 页面渲染成图片，再请求本机 OpenAI-compatible vLLM 服务。根据 `allenai/olmOCR-2-7B-1025-FP8` 模型卡说明，页面图片应按最长边 `1288px` 渲染；后端的 `olmocr` 分支已按这个尺寸生成页面图。

注意：后端默认请求地址是 `http://127.0.0.1:8005/v1/chat/completions`，所以服务端口应为 `8005`。可用环境变量覆盖：

```bash
export OLMOCR_ENDPOINT=http://127.0.0.1:8005/v1/chat/completions
export OLMOCR_MODEL=olmocr
export OLMOCR_TIMEOUT=180
export OLMOCR_MAX_TOKENS=8000
export OLMOCR_TARGET_LONGEST_IMAGE_DIM=1288
export OLMOCR_GPU_MEMORY_UTILIZATION=0.8
```

当前项目不直接导入官方 `olmocr` Python toolkit，只需要已有 `olmocr` 环境能启动 vLLM 服务。推荐用仓库根目录的精简更新文件配置当前环境：

```bash
conda env update -n olmocr -f /home/lrn/MUL_RAG/olmocr_environment.yml
```

如果你要单独运行官方 `olmocr` toolkit，则需要 Python >= 3.11，可创建独立环境：

```bash
conda env create -n olmocr_py311 -f /home/lrn/MUL_RAG/olmocr_environment.py311.yml --solver libmamba
```

启动 OLMOCR vLLM（如果当前就在后端目录 `/home/lrn/MUL_RAG/MUL_rag/mul_rag/backend`，可直接输入）：

```bash
../../../start_olmocr_vllm.sh
```

不确定当前目录时，也可以使用绝对路径：

```bash
/home/lrn/MUL_RAG/start_olmocr_vllm.sh
```

如果想在后端终端中手动启动 OLMOCR vLLM（不通过启动脚本），可以执行：

```bash
conda run --no-capture-output -n olmocr \
  vllm serve /home/lrn/MUL_RAG/MUL_rag/olmocr/olmOCR-2-7B-1025-FP8 \
    --host 127.0.0.1 \
    --port 8005 \
    --served-model-name olmocr \
    --max-model-len 16384 \
    --gpu-memory-utilization 0.8
```

关闭 OLMOCR vLLM（可在后端终端直接输入）：

```bash
PID=$(cat /home/lrn/MUL_RAG/logs/olmocr_vllm.pid); kill -TERM -- -"$PID"
```

验证 OLMOCR vLLM 是否已关闭：

```bash
curl http://127.0.0.1:8005/v1/models
```

如果返回连接失败，说明服务已经关闭。

## 5. 启动后验证

后端健康检查：

```bash
curl http://127.0.0.1:8002/api/v1/health
```

前端访问：

```text
http://127.0.0.1:8501
```

## 6. 常见问题

1. 报错 `MINERU_CMD 当前指向主项目环境`

请确认使用了独立环境，并设置：

```bash
export MINERU_CMD=/home/lrn/anaconda3/envs/mineru/bin/mineru
```

2. `mineru` 解析超时

可增加超时：

```bash
export MINERU_TIMEOUT=7200
```

3. 前端无法连接后端

确认后端已监听 `127.0.0.1:8002`，并且健康检查接口可访问。
