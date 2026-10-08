# 预处理方法扩展目录

新增方法建议放在本目录，每个方法一个 Python 模块。模块导入时调用
`register_preprocess_method(...)` 完成注册，后端启动时会自动发现本目录下的模块。

最小示例：

```python
from __future__ import annotations

from typing import Any, Dict, Tuple

import pandas as pd

from services.preprocessing.registry import PreprocessContext, register_preprocess_method


def run_my_method(df: pd.DataFrame, context: PreprocessContext) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    out = df.copy()
    # Python 脚本、预训练模型推理或其他处理逻辑写在这里。
    # context.method_output_dir 可存放该方法的中间文件、模型输出和审计附件。
    return out, {"message": "done"}


register_preprocess_method(
    method_id="my_method",
    name="我的预处理方法",
    description="一句话描述该方法会做什么。",
    runner=run_my_method,
    category="custom",
    method_type="python",
)
```

约定：

- `method_id` 使用小写英文、数字和下划线，保持稳定，前端会用它提交任务。
- `runner` 入参固定为 `(df, context)`，返回 `(处理后的 DataFrame, 审计信息 dict)`。
- 预训练模型文件建议放在 `preprocessing/models/`，脚本型资源建议放在
  `preprocessing/scripts/`，方法运行中产生的文件放在 `context.method_output_dir`。
- 如果方法依赖大型模型或外部服务，优先在模块级懒加载，避免后端启动变慢。
