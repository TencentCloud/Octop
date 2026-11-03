"""数据转换器。执行 LLM 生成的 pandas 代码，将原始 DataFrame 转为图表所需格式。

安全机制（三层校验，无需用户确认）：
1. 关键字黑名单校验 — 在执行前扫描代码中的危险关键字，阻止恶意代码运行
2. AST 白名单校验 — 解析代码的抽象语法树，仅允许安全的 AST 节点类型
3. 沙箱内置函数 — 仅暴露安全的内置函数，禁止 open/exec/eval/__import__ 等
"""

import ast
import contextlib
import re
import signal
import sys
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

from .exceptions import TransformError, ErrorCode


# ── 关键字黑名单 ──────────────────────────────────────────────
# 阻止包含这些关键字的代码执行，防止文件操作、网络访问、系统命令等危险行为
KEYWORD_BLACKLIST: List[str] = [
    # 动态执行
    'exec(', 'eval(', 'compile(',
    # 导入与模块
    '__import__', 'importlib', 'import ',
    # 文件操作
    'open(', 'read(', 'write(', 'remove(', 'os.rename(',
    'os.path', 'shutil', 'pathlib.Path',
    # 网络访问
    'socket', 'requests', 'urllib', 'http.', 'subprocess',
    # 系统命令
    'os.system', 'os.popen', 'os.exec', 'os.spawn',
    'sys.exit', 'sys.argv',
    # 反射与内部属性
    '__class__', '__bases__', '__subclasses__', '__globals__',
    '__code__', '__closure__', '__dict__', '__mro__',
    # P2-sandbox 止血：补齐逃逸相关 dunder。注意 getattr( 子串拦不住
    # __getattribute__/__getattr__（后缀不同须独立列出）；pd/np 模块对象
    # 上天然存在 __builtins__，是取回真实 builtins 的逃逸路径，必须封堵
    '__builtins__', '__getattribute__', '__getattr__', '__loader__',
    '__spec__', '__self__', '__func__', '__reduce__',
    'getattr(', 'setattr(', 'delattr(',
    # 危险内置函数
    'breakpoint(', 'exit(', 'quit(',
    # 装饰器绕过
    '@property', '@classmethod', '@staticmethod',
]

# ── 危险属性名黑名单 ──────────────────────────────────────────
# 关键字黑名单只拦裸名（open/import），拦不住模块自带的文件/网络 I/O 方法。
# 这里通过 AST Attribute 精确匹配属性名，拦截 pd.read_csv / np.load / to_pickle 等
# 绕过手法。只匹配属性名、不匹配字符串字面量（字符串是 Constant 节点），因此
# 列名恰为 read_csv 时（如 df['read_csv']）不会误伤。
DANGEROUS_ATTRIBUTES: Set[str] = {
    # pandas 文件 I/O（读）
    'read_csv', 'read_excel', 'read_json', 'read_pickle', 'read_hdf', 'read_html',
    # P1-1 补漏：嵌套模块路径上的文件/网络句柄工厂。此前 open_memmap / get_handle
    # 不在名单内，可绕过「裸 open 被拦」的防线真实落盘与发起网络请求。
    'get_handle', 'open_memmap', 'urlopen', 'urlretrieve',
    'read_sql', 'read_sql_query', 'read_sql_table', 'read_table', 'read_fwf',
    'read_clipboard', 'read_feather', 'read_parquet', 'read_orc', 'read_sas',
    'read_spss', 'read_stata', 'read_gbq',
    # pandas 文件 I/O（写）
    'to_csv', 'to_excel', 'to_json', 'to_pickle', 'to_hdf', 'to_sql',
    'to_feather', 'to_parquet', 'to_stata', 'to_gbq',
    # pandas 文件句柄 / 引擎
    'hdfstore', 'excelwriter', 'excelfile',
    # numpy 文件 I/O
    'load', 'save', 'savez', 'savez_compressed', 'loadtxt', 'savetxt',
    'fromfile', 'tofile', 'genfromtxt', 'fromregex', 'frombuffer', 'fromstring',
    'memmap',
}

# ── 危险模块路径前缀 ──────────────────────────────────────────
# 属性名黑名单只能逐个点名，永远追不上 pandas/numpy 的模块树。这里按点分路径
# 整体封禁已知的 I/O 子树：pd.io.* 与 np.lib.* 下全是文件/网络句柄实现
# （pd.io.common.get_handle、np.lib.format.open_memmap 等），数据转换场景无需访问。
DANGEROUS_MODULE_PREFIXES: Tuple[str, ...] = ('pd.io', 'np.lib')


def _dotted_name(node) -> str:
    """把属性链 a.b.c 还原为点分路径（用于模块前缀封禁）。非纯名字链返回能还原的部分。"""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


class _DangerousAttributeVisitor(ast.NodeVisitor):
    """遍历 AST，命中 DANGEROUS_ATTRIBUTES 中的属性访问即记录违规。

    同时按点分路径封禁 DANGEROUS_MODULE_PREFIXES 下的整棵子树。
    """

    def __init__(self):
        self.violations: List[str] = []

    def visit_Attribute(self, node):
        if node.attr.lower() in DANGEROUS_ATTRIBUTES:
            self.violations.append(f"不允许的属性访问: .{node.attr}")
        else:
            path = _dotted_name(node).lower()
            for prefix in DANGEROUS_MODULE_PREFIXES:
                if path == prefix or path.startswith(prefix + '.'):
                    self.violations.append(f"不允许的模块路径访问: {_dotted_name(node)}")
                    break
        self.generic_visit(node)


# ── AST 白名单 ────────────────────────────────────────────────
# 仅允许这些 AST 节点类型出现在转换代码中
# 不在白名单中的节点类型将被拒绝执行
AST_WHITELIST: Set[type] = {
    # 模块与表达式
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    # 变量与常量
    ast.Name, ast.Constant, ast.Num, ast.Str,
    # 运算符
    ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare,
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    # 位运算符：pandas 布尔向量运算（& / | / ^）必需，无系统调用风险
    ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    # 数据结构
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    # 索引与切片
    ast.Subscript, ast.Index, ast.Slice,
    # 属性访问与方法调用
    ast.Attribute, ast.Call, ast.keyword,
    # 控制流（有限允许）
    ast.If, ast.IfExp,
    # 循环（有限允许）
    ast.For, ast.While,
    # 推导式
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.comprehension,
    # f-string（P0-6）：JoinedStr 是 f-string 本体，FormattedValue 是其中的插值槽。
    # 二者无执行能力、只做字符串插值；内嵌表达式仍由 ast.walk 逐个走白名单校验，
    # 与 SKILL.md/REFERENCE.md 推荐的列重命名模板一致（此前该写法被自身校验器拒绝）。
    ast.JoinedStr, ast.FormattedValue,
    # 函数定义（允许 lambda 和 def）
    ast.Lambda, ast.FunctionDef, ast.Return,
    ast.arguments, ast.arg,
    # 类型相关
    ast.Starred,
}

# Python 3.12+ 移除了 ast.Num/ast.Str，用 ast.Constant 替代
# 但为了兼容性，如果存在则保留
for _t in (getattr(ast, 'Num', None), getattr(ast, 'Str', None),
           getattr(ast, 'Index', None), getattr(ast, 'NameConstant', None)):
    if _t is not None:
        AST_WHITELIST.add(_t)


class CodeValidationError(TransformError):
    """代码安全校验失败时抛出的错误。"""
    pass


def _strip_comments_and_strings(code: str) -> str:
    """剥离代码中的注释和字符串字面量，返回纯代码文本。

    防止黑名单子串匹配误报注释中的关键字（如 `# import pandas`）。
    保留字符串内容用于检测，因为某些攻击可能通过字符串拼接构造危险调用。
    """
    # 剥离 # 注释（不跨行）
    lines = []
    in_string = False
    string_char = None
    for line in code.split('\n'):
        result_chars = []
        i = 0
        while i < len(line):
            c = line[i]
            if in_string:
                result_chars.append(c)
                if c == string_char and (i == 0 or line[i-1] != '\\'):
                    in_string = False
                    string_char = None
            elif c in ('"', "'"):
                in_string = True
                string_char = c
                result_chars.append(c)
            elif c == '#':
                # 注释开始，跳过本行剩余部分
                break
            else:
                result_chars.append(c)
            i += 1
        lines.append(''.join(result_chars))
    return '\n'.join(lines)


def validate_code_blacklist(code: str) -> List[str]:
    """关键字黑名单校验。返回匹配到的危险关键字列表（空列表表示通过）。

    在匹配前剥离注释，防止注释中的关键字（如 `# import pandas`）导致误报。
    字符串字面量保留检测，因为某些绕过手法通过字符串拼接构造调用名。
    """
    violations = []
    # 剥离注释后进行匹配
    code_clean = _strip_comments_and_strings(code)
    code_lower = code_clean.lower()
    for keyword in KEYWORD_BLACKLIST:
        kw_lower = keyword.lower()
        if kw_lower in code_lower:
            violations.append(keyword)
    return violations


def validate_code_ast(code: str) -> List[str]:
    """AST 白名单校验。解析代码的抽象语法树，返回不在白名单中的节点类型列表。

    同时做危险属性名检测（DANGEROUS_ATTRIBUTES），拦截 pd.read_csv / np.load 等
    模块级文件 I/O 绕过手法。
    """
    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误: {e}"]

    for node in ast.walk(tree):
        # ast.Load / ast.Store / ast.Del 是 Name 节点的上下文，不算违规
        if isinstance(node, (ast.Load, ast.Store, ast.Del)):
            continue
        if type(node) not in AST_WHITELIST:
            violations.append(f"不允许的语法节点: {type(node).__name__}")

    # 危险属性名检测（独立于白名单，精确匹配属性访问，不误伤字符串字面量）
    visitor = _DangerousAttributeVisitor()
    visitor.visit(tree)
    violations.extend(visitor.violations)

    return violations


class DataTransformer:
    """执行 LLM 生成的数据转换代码。

    安全执行流程（三层校验，无需用户确认）：
    1. 黑名单校验 → 拒绝包含危险关键字的代码
    2. AST 白名单校验 → 拒绝包含不允许语法节点的代码
    3. 沙箱执行 → 仅暴露安全的内置函数，带超时和资源限制
    """

    # 沙箱执行的时间限制（秒）
    SANDBOX_TIMEOUT_SECONDS = 10
    # 沙箱执行的最大递归深度
    SANDBOX_MAX_RECURSION = 500

    def __init__(self, timeout: int = None):
        """
        Args:
            timeout: 沙箱执行超时时间（秒），默认 SANDBOX_TIMEOUT_SECONDS。
        """
        self.timeout = timeout or self.SANDBOX_TIMEOUT_SECONDS

    def transform(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """
        执行转换代码。

        code 中可使用: df, pd, np
        code 必须产出: result (pd.DataFrame)

        执行前会依次进行：
        1. 关键字黑名单校验
        2. AST 白名单校验
        3. 沙箱执行（无需用户确认，三层校验已保证安全）
        """
        if not code or not code.strip():
            return df

        # ── 第1步：关键字黑名单校验 ──
        blacklist_violations = validate_code_blacklist(code)
        if blacklist_violations:
            raise CodeValidationError(
                f"代码包含危险关键字，已阻止执行: {', '.join(blacklist_violations)}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={
                    'code': code,
                    'violations': blacklist_violations,
                    'reason': '这些关键字可能用于文件操作、网络访问、动态执行或系统命令，'
                              '在数据转换场景中不需要。如确需使用，请检查数据是否需要预处理。',
                    'suggestion': '移除这些危险关键字；如确需文件/网络操作，请改用其他工具预处理数据后再导入',
                },
            )

        # ── 第2步：AST 白名单校验 ──
        ast_violations = validate_code_ast(code)
        if ast_violations:
            raise CodeValidationError(
                f"代码包含不允许的语法结构，已阻止执行: {', '.join(ast_violations)}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={
                    'code': code,
                    'violations': ast_violations,
                    'reason': '数据转换代码仅允许使用赋值、运算、方法调用、条件判断、'
                              '循环和推导式等基本语法。不允许导入模块、定义类、'
                              '异常处理等复杂结构。',
                    'suggestion': '仅使用赋值、运算、方法调用、条件判断、循环和推导式等基本语法；去掉 import、类定义、异常处理等结构',
                },
            )

        # ── 第3步：沙箱执行 ──
        return self._execute_in_sandbox(df, code)

    def _execute_in_sandbox(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """在受限沙箱中执行代码。

        安全措施：
        - 仅暴露安全的内置函数
        - 设置递归深度上限，防止栈溢出
        - 设置执行超时，防止无限循环（仅 Unix：signal SIGALRM；Windows 无 SIGALRM 时无超时）
        """
        # P0-2 修复：exec 必须使用**单一**命名空间。
        # 此前用 exec(code, globals, locals) 双命名空间：顶层赋值写进 locals，但
        # lambda / 生成器 / 嵌套函数的自由变量按 Python 闭包规则只在 globals 里查，
        # 于是「先算中间变量、再在 lambda 里引用」这类主流写法必然 NameError。
        # 单一命名空间下 globals is locals，闭包查找与顶层赋值落在同一个 dict。
        ns: Dict[str, Any] = {'df': df.copy(), 'pd': pd, 'np': np}
        # 安全沙箱：仅暴露安全的内置函数，禁止 open/exec/eval/__import__ 等
        safe_builtins = {
            'len': len, 'range': range, 'list': list, 'dict': dict,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'sorted': sorted, 'enumerate': enumerate, 'zip': zip,
            'map': map, 'filter': filter, 'sum': sum, 'min': min, 'max': max,
            'abs': abs, 'round': round, 'set': set, 'tuple': tuple,
            'isinstance': isinstance, 'hasattr': hasattr, 'print': print,
            'True': True, 'False': False, 'None': None,
        }
        ns['__builtins__'] = safe_builtins

        # 限制递归深度，防止递归攻击导致栈溢出
        original_recursion_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(self.SANDBOX_MAX_RECURSION)

        # 超时机制
        timed_out = [False]

        def _timeout_handler(signum, frame):
            timed_out[0] = True
            raise TimeoutError("转换代码执行超时")

        # 优先使用 signal（Unix），不支持时跳过（Windows 无 SIGALRM）
        use_signal = False
        old_handler = None
        try:
            if hasattr(signal, 'SIGALRM'):
                use_signal = True
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(self.timeout)
        except (ImportError, ValueError, OSError):
            pass

        try:
            # P2-print 修复：把 transform 代码里的 print 重定向到 stderr，
            # 避免污染 cli.py 末尾输出到 stdout 的 JSON 契约。
            with contextlib.redirect_stdout(sys.stderr):
                exec(code, ns)
        except TimeoutError:
            raise TransformError(
                f"转换代码执行超时（超过 {self.timeout} 秒），可能存在无限循环",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={'code': code, 'timeout': self.timeout,
                         'suggestion': '检查代码是否含死循环或过重计算；如需更复杂处理，请在本地用 pandas 完成后再导入'},
            )
        except Exception as e:
            raise TransformError(
                f"转换代码执行失败: {e}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={'code': code, 'error': str(e),
                         'suggestion': '根据报错信息修正转换代码；可先用 print(df.columns) 或 print(df.head()) 检查列名与数据类型'},
            )
        finally:
            # 恢复递归深度
            sys.setrecursionlimit(original_recursion_limit)
            # 取消超时
            if use_signal:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)

        if 'result' not in ns:
            raise TransformError(
                "转换代码必须产出 result 变量",
                ErrorCode.TRANSFORM_NO_RESULT,
                details={'code': code},
            )

        result = ns['result']
        if not isinstance(result, pd.DataFrame):
            raise TransformError(
                f"result 必须是 DataFrame，实际类型: {type(result).__name__}",
                ErrorCode.TRANSFORM_INVALID_RESULT,
                details={'code': code, 'result_type': type(result).__name__},
            )

        if result.empty:
            raise TransformError(
                "转换后数据为空，请检查转换逻辑",
                ErrorCode.TRANSFORM_EMPTY_RESULT,
                details={'code': code},
            )

        return result
