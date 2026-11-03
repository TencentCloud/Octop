"""直接运行 scripts/ 下入口脚本的 sys.path 引导（单点实现）。

背景：包内模块统一使用相对导入（from .xxx import），当入口脚本被直接执行
（如 `python scripts/cli.py`）时 __package__ 为 None，必须先把技能包根目录
加入 sys.path 才能用 `from scripts.xxx import` 绝对导入。

此前该路径设置逻辑在多个入口重复内联；现收敛到本模块单点实现——
新增入口只需一行 `import _bootstrap`，不得再复制 parent.parent 计算。

用法（入口脚本顶部）：

    if __name__ == '__main__' and __package__ is None:
        import _bootstrap  # noqa: F401 — 导入即生效
        from scripts.data_parser import DataParser
        ...
    else:
        from .data_parser import DataParser

说明：直接执行脚本时，解释器自动把脚本所在目录（scripts/）置于 sys.path[0]，
因此 `import _bootstrap` 总能命中本文件；幂等，重复导入无副作用。
"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
