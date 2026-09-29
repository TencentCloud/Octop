"""★ `python3 -m scripts.audit` 转发（与入口等价）。"""
import sys

from .current_tree import main

if __name__ == "__main__":
    sys.exit(main())
