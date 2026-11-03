"""
法律条文查询脚本（最终版）
数据源：
  1. lawtext/laws GitHub（git clone，git grep 搜索，全量法律）
  2. just-laws GitHub（备用，git cat-file，民法典等主要法律）

用法：
  python search_law.py <关键词> [--repo <仓库路径>] [--local <目录>]

首次设置：
  git clone --depth=1 https://github.com/lawtext/laws <目标路径>
"""
import sys
import os
import re
import subprocess
import argparse
from pathlib import Path


def run_git(repo: str, args: list, timeout: int = 30) -> subprocess.CompletedProcess:
    """运行 git 命令"""
    cmd = ['git', '-C', repo] + args
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 1, '', 'timeout')


def git_grep(repo: str, keyword: str, max_results: int = 30) -> list:
    """用 git grep 搜索本地仓库（全程 git 命令，绕过 HTTP）"""
    try:
        result = run_git(repo, ['grep', '-n', '-B', '1', '-A', '1', '--', '*.md', keyword], timeout=30)
        # 0=找到，1=未找到，>1=错误
        if result.returncode not in (0, 1):
            return []
        if not result.stdout.strip():
            return []

        # 解析 git grep 输出：filepath:linenum:content
        # filepath 可能包含 : ，从最后一个 : 分割得到 linenum:content
        results = []
        current_file = None
        current_lines = []

        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            # 找最后一个冒号（linenum:content 分隔）
            last_colon = line.rfind(':')
            if last_colon == -1:
                continue
            before = line[:last_colon]
            after = line[last_colon+1:]

            # before 中最后一个冒号前面是 filepath
            filepath = before.rsplit(':', 1)[-1] if ':' in before else before

            # 检查是否是行号（after 的开头）
            colon2 = after.find(':')
            if colon2 > 0 and after[:colon2].isdigit():
                linenum = after[:colon2]
                content = after[colon2+1:]
            else:
                linenum = ''
                content = after

            # 去掉引号
            filepath = filepath.strip('"\'')

            if filepath != current_file:
                if current_file and current_lines:
                    full = '\n'.join(current_lines)
                    if keyword in full:
                        results.append({'file': current_file, 'lines': current_lines.copy()})
                current_file = filepath
                current_lines = []

            current_lines.append(content.strip())

        if current_file and current_lines:
            full = '\n'.join(current_lines)
            if keyword in full:
                results.append({'file': current_file, 'lines': current_lines.copy()})

        return results[:max_results]

    except Exception as e:
        print(f'[git grep 异常] {str(e)[:80]}', file=sys.stderr)
        return []


def just_laws_grep(repo: str, keyword: str, max_results: int = 20) -> list:
    """在 just-laws 仓库中搜索（通过 git cat-file，绕过 HTTP）"""
    # just-laws 的法律索引
    JUST_LAWS_FILES = {
        '民法典-总则': 'docs/civil-and-commercial/civil-code/01-general-principles.md',
        '民法典-物权编': 'docs/civil-and-commercial/civil-code/02-property-rights.md',
        '民法典-合同编': 'docs/civil-and-commercial/civil-code/03-contracts.md',
        '民法典-人格权': 'docs/civil-and-commercial/civil-code/04-personality-rights.md',
        '民法典-婚姻': 'docs/civil-and-commercial/civil-code/05-marriage-and-family.md',
        '民法典-继承': 'docs/civil-and-commercial/civil-code/06-inheritance.md',
        '民法典-侵权': 'docs/civil-and-commercial/civil-code/07-tort-liability.md',
        '行政处罚法': 'docs/administrative/administrative-penalty/README.md',
        '行政强制法': 'docs/administrative/administrative-compulsion-law/README.md',
        '行政许可法': 'docs/administrative/administrative-licensing-law/README.md',
        '行政复议法': 'docs/administrative/administrative-reconsideration-law/README.md',
        '劳动法': 'docs/social/labor-law/README.md',
        '劳动合同法': 'docs/social/labor-contract-law/README.md',
        '安全生产法': 'docs/social/work-safety-law/README.md',
        '未成年人保护法': 'docs/social/protection-of-minors/README.md',
    }

    results = []
    for name, path in JUST_LAWS_FILES.items():
        # 先搜索
        grep_result = run_git(repo, [
            'grep', '-n', '-B', '1', '-A', '1',
            '--', f'docs/{path}', keyword
        ], timeout=5)

        if grep_result.returncode == 0 and grep_result.stdout.strip():
            lines = grep_result.stdout.splitlines()
            for line in lines:
                if ':' in line:
                    parts = line.rsplit(':', 2)
                    if len(parts) >= 3:
                        content = parts[-1].strip()
                        if keyword.lower() in content.lower():
                            results.append({'name': name, 'file': path, 'line': parts[-2], 'content': content})
                            if len(results) >= max_results:
                                break

    return results


def search_local(directory: str, keywords: list) -> list:
    """搜索本地 PDF/DOCX"""
    if not os.path.exists(directory):
        return []
    matches = []
    for root, _, files in os.walk(directory):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in ('.pdf', '.docx', '.doc', '.txt'):
                continue
            for kw in keywords:
                if kw in fname:
                    matches.append({'name': fname, 'file': str(Path(root) / fname)})
                    break
    return matches


def guess_category(filepath: str) -> str:
    """猜测分类"""
    f = filepath.lower()
    if 'appendix' in f or '附录' in filepath:
        return '附录/司法解释'
    elif '民法典' in filepath or 'civil' in f:
        return '民法典'
    elif '刑法' in filepath or 'criminal' in f:
        return '刑法'
    elif '行政' in filepath or 'admin' in f:
        return '行政法'
    elif '劳动' in filepath or 'labor' in f:
        return '社会法'
    elif '经济' in filepath or '公司' in filepath or '证券' in filepath or 'economic' in f:
        return '经济法'
    elif '宪法' in filepath or 'constitution' in f:
        return '宪法相关'
    else:
        return '其他'


def format_output(keyword: str, grep_results: list, just_results: list, local_results: list) -> str:
    lines = []
    lines.append('=' * 60)
    lines.append(f'法律条文查询 | 关键词: {keyword}')
    lines.append('=' * 60)

    total_grep = len(grep_results)
    total_just = len(just_results)

    if total_grep > 0:
        lines.append(f'\n[全国法律数据库] 共 {total_grep} 条匹配\n')
        # 按分类汇总
        by_cat = {}
        for r in grep_results:
            cat = guess_category(r['file'])
            by_cat.setdefault(cat, []).append(r)
        for cat, items in sorted(by_cat.items()):
            lines.append(f'## 【{cat}】{len(items)} 条\n')
            for item in items[:3]:
                lines.append(f'  ▶ {item["file"]}')
                text = '\n'.join(item['lines'])
                text = re.sub(r'\*+', '', text)
                text = re.sub(r'\n{3,}', '\n', text).strip()
                lines.append(f'    {text[:300]}')
                lines.append('')

    if total_just > 0:
        lines.append(f'\n[just-laws 主要法律] {total_just} 条匹配\n')
        for r in just_results[:10]:
            lines.append(f'  ▶ 【{r["name"]}】第{r["line"]}行')
            lines.append(f'    {r["content"][:200]}')
            lines.append('')

    if local_results:
        lines.append(f'\n[本地知识库] {len(local_results)} 条\n')
        for r in local_results:
            lines.append(f'  · {r["name"]} | {r["file"]}')

    if total_grep == 0 and total_just == 0 and not local_results:
        lines.append('\n[未找到匹配]')

    lines.append('\n' + '=' * 60)
    return '\n'.join(lines)


# ─── 主程序 ─────────────────────────────────────────────────

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # 查找 lawtext/laws 仓库
    repo = os.environ.get('LAWTEXT_REPO', r'E:\OpenClaw\data\workspace-如意\temp\laws')

    parser = argparse.ArgumentParser(
        description='法律条文查询 - lawtext/laws 全量法律库（git grep 本地搜索）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
首次设置：
  git clone --depth=1 https://github.com/lawtext/laws <目标路径>

覆盖范围：全国所有法律（全国人大、行政法规、司法解释、地方法规等）
        '''
    )
    parser.add_argument('keyword', nargs='?', default=None)
    parser.add_argument('--repo', '-r', default=repo)
    parser.add_argument('--local', '-l', default=None)
    parser.add_argument('--max', '-n', type=int, default=30)
    parser.add_argument('--list', action='store_true')

    args = parser.parse_args()

    if args.list:
        if os.path.exists(os.path.join(args.repo, '.git')):
            result = run_git(args.repo, ['ls-tree', '--name-only', '-r', 'HEAD:content'])
            if result.returncode == 0:
                files = [f for f in result.stdout.splitlines() if f.endswith('.md')]
                cats = {}
                for f in files:
                    parts = f.split('/')
                    if len(parts) > 1:
                        cat = parts[1]
                        cats.setdefault(cat, 0)
                        cats[cat] += 1
                print('=== lawtext/laws 法律库 ===\n')
                for cat in sorted(cats):
                    print(f'  [{cat}]: {cats[cat]} 部')
        else:
            print('[ERROR] 仓库不存在或不是 git 仓库')
        return

    keyword = args.keyword
    if not keyword:
        print('[ERROR] 请提供关键词', file=sys.stderr)
        sys.exit(1)

    keyword = keyword.strip()
    print(f'[搜索中] 关键词: {keyword}', file=sys.stderr)

    # 1. git grep 搜索 lawtext/laws
    grep_results = []
    if os.path.exists(os.path.join(args.repo, '.git')):
        print(f'[1/2] 搜索 lawtext/laws 本地库...', file=sys.stderr)
        grep_results = git_grep(args.repo, keyword, args.max)
        print(f'  -> 找到 {len(grep_results)} 条', file=sys.stderr)

    # 2. just-laws 备用（通过 git）
    just_results = []
    print('[2/2] 搜索 just-laws 主要法律...', file=sys.stderr)
    just_results = just_laws_grep(args.repo, keyword, max_results=20)
    print(f'  -> {len(just_results)} 条', file=sys.stderr)

    # 3. 本地文件兜底
    local_results = []
    if args.local:
        local_results = search_local(args.local, keyword.split())

    print()
    print(format_output(keyword, grep_results, just_results, local_results))
    sys.exit(0 if (grep_results or just_results or local_results) else 1)


if __name__ == '__main__':
    main()
