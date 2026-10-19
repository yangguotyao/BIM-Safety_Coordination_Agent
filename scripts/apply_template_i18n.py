"""把 .vue 文件 template 区块中的中文界面文案包装为 t(...)。

覆盖四类位置：
1. 动态属性表达式  :title="a ? '中文' : '中文'"
2. 静态属性        placeholder="中文"  →  :placeholder="t('中文')"
3. 文本节点        <span>中文</span>    →  <span>{{ t('中文') }}</span>
4. 插值表达式      {{ x ? '中文' : '中文' }}

跳过 <script>、<style>、HTML 注释，以及已包装过的 t(...)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'BIM-Safety-Coordination-Agent' / '02_网站源码' / 'frontend' / 'src'

CJK = re.compile(r'[\u4e00-\u9fff]')
LITERAL = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"")
ALREADY = re.compile(r'(?<![\w$])t\s*\(\s*$')
GUARD_TOKENS = ('startsWith(', 'endsWith(', 'includes(', '===', '!==', '==', '!=')
DYNAMIC_ATTR = re.compile(r'(\s)([:@][\w:.\-\[\]]+)="([^"]*)"')
STATIC_ATTR = re.compile(r'(\s)(placeholder|aria-label|alt)="([^"]*)"')
STATIC_TITLE = re.compile(r'(\s)(title)="([^"]*)"')
TEXT_NODE = re.compile(r'>([^<>]*?)<', re.S)
MUSTACHE = re.compile(r'\{\{(.*?)\}\}', re.S)
COMMENT = re.compile(r'<!--.*?-->', re.S)

SKIP_EXACT = {
    '演示安全员', '演示机电班组', '机电班组', '装修班组', '机电', '装修',
    '材料转运', '相邻墙面作业', '人工编制演示作业计划', '按批准的整改措施完成处置。',
    '新证据显示条件变化，需要重新检查。', '本演示由人工核对并填写观察参数。',
    '全面检查 L05 楼板区域的临边防护和人员暴露风险，结合现场证据与规范依据提出整改要求。',
    '验收 ', '简体中文',
}
SKIP_PREFIX = ('演示整改：',)


def blank_regions(text: str) -> str:
    """把 script / style / 注释替换为等长空白，保证偏移一致。"""
    out = list(text)
    for pattern in (re.compile(r'<script[^>]*>.*?</script>', re.S),
                    re.compile(r'<style[^>]*>.*?</style>', re.S),
                    COMMENT):
        for match in pattern.finditer(text):
            for index in range(match.start(), match.end()):
                if out[index] != '\n':
                    out[index] = ' '
    return ''.join(out)


def quote(key: str) -> str:
    return key.replace('\\', '\\\\').replace("'", "\\'")


def wrap_literals(expr: str, base: int, edits: list[tuple[int, int, str]]) -> None:
    """把表达式里的中文字面量包成 t(...)，偏移基于整个文件。"""
    for match in LITERAL.finditer(expr):
        raw = match.group(0)
        inner = raw[1:-1]
        if not CJK.search(inner):
            continue
        if inner in SKIP_EXACT or inner.startswith(SKIP_PREFIX):
            continue
        before = expr[:match.start()].rstrip()
        if ALREADY.search(before) or before.endswith(GUARD_TOKENS):
            continue
        after = expr[match.end():].lstrip()
        prev_char = before[-1] if before else ''
        if after.startswith(':') and prev_char in '{,':
            continue
        edits.append((base + match.start(), base + match.end(), f"t({raw})"))


def process(path: Path, dry: bool) -> int:
    text = path.read_text(encoding='utf-8')
    mask = blank_regions(text)
    edits: list[tuple[int, int, str]] = []
    occupied: list[tuple[int, int]] = []

    # 1. 动态属性表达式
    for attr in DYNAMIC_ATTR.finditer(mask):
        expr = attr.group(3)
        if not CJK.search(expr):
            continue
        wrap_literals(expr, attr.start(3), edits)
        occupied.append((attr.start(3), attr.end(3)))

    # 2. 静态属性 → 绑定 t()
    for pattern in (STATIC_ATTR, STATIC_TITLE):
        for attr in pattern.finditer(mask):
            value = attr.group(3)
            if not CJK.search(value) or '{{' in value:
                continue
            if any(start <= attr.start(2) < end for start, end in occupied):
                continue
            edits.append((attr.start(2), attr.end(3),
                          f":{attr.group(2)}=\"t('{quote(value)}')\""))

    # 3. 插值表达式
    for must in MUSTACHE.finditer(mask):
        expr = must.group(1)
        if not CJK.search(expr):
            continue
        wrap_literals(expr, must.start(1), edits)

    # 4. 文本节点
    for node in TEXT_NODE.finditer(mask):
        raw = node.group(1)
        if not CJK.search(raw) or '{{' in raw or '}}' in raw:
            continue
        stripped = raw.strip()
        key = re.sub(r'\s+', ' ', stripped)
        if key in SKIP_EXACT or key.startswith(SKIP_PREFIX):
            continue
        lead = raw[:len(raw) - len(raw.lstrip())]
        tail = raw[len(raw.rstrip()):]
        edits.append((node.start(1), node.end(1), f"{lead}{{{{ t('{quote(key)}') }}}}{tail}"))

    # 去重与冲突消解：区间不重叠，优先保留先收集的（属性表达式优先）
    edits.sort(key=lambda item: item[0])
    final: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, replacement in edits:
        if start < last_end:
            continue
        final.append((start, end, replacement))
        last_end = end

    if not final:
        return 0
    if not dry:
        for start, end, replacement in reversed(final):
            text = text[:start] + replacement + text[end:]
        path.write_text(text, encoding='utf-8')
    return len(final)


def main() -> int:
    dry = '--apply' not in sys.argv
    total = 0
    for path in sorted(SRC.rglob('*.vue')):
        if 'i18n' in path.parts:
            continue
        count = process(path, dry)
        if count:
            print(f'{path.relative_to(SRC)}: {count}')
            total += count
    print(('DRY-RUN 共 ' if dry else '已包装 ') + str(total) + ' 处')
    return 0


if __name__ == '__main__':
    sys.exit(main())
