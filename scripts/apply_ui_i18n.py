"""一次性工具：把 .vue 模板中的中文字面量包成 t('中文')。

只处理 <template> 区域，跳过注释、跳过 <style>、跳过已有 t(...) 包裹的片段。
script 中的映射表需要人工改造，不在本脚本范围内。
"""
import os
import re
import sys

ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'BIM-Safety-Coordination-Agent', '02_网站源码', 'frontend', 'src',
)

CJK = re.compile(r'[\u4e00-\u9fa5]')
TEMPLATE = re.compile(r'(<template>)(.*?)(</template>)', re.S)
COMMENT = re.compile(r'<!--.*?-->', re.S)
STYLE = re.compile(r'<style[^>]*>.*?</style>', re.S)

# 文本节点：>中文文本<
TEXT_NODE = re.compile(r'>([^<>{}]*[\u4e00-\u9fa5][^<>{}]*)<')
# 静态属性
ATTR = re.compile(r'(?<!:)("?)(placeholder|aria-label|title|alt)="([^"]*[\u4e00-\u9fa5][^"]*)"')
# {{ }} 内的字符串字面量
MUSTACHE = re.compile(r'\{\{(.*?)\}\}', re.S)
LITERAL = re.compile(r"(?<![\\w.])'([^'\n]*[\u4e00-\u9fa5][^'\n]*)'")


def need_import(src: str) -> str:
    if re.search(r"import\s*\{[^}]*\bt\b[^}]*\}\s*from\s*'\.\./i18n'", src):
        return src
    return src.replace(
        '<script setup lang="ts">',
        "<script setup lang=\"ts\">\nimport { t } from '../i18n'",
        1,
    )


def wrap_text_nodes(chunk: str) -> tuple[str, int]:
    def repl(match: re.Match) -> str:
        text = match.group(1)
        stripped = text.strip()
        if not stripped or not CJK.search(stripped):
            return match.group(0)
        if stripped.startswith('{{') or stripped.endswith('}}'):
            return match.group(0)
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        escaped = stripped.replace('\\', '\\\\').replace("'", "\\'")
        return f'>{leading}{{{{ t(\'{escaped}\') }}}}{trailing}<'

    return TEXT_NODE.subn(repl, chunk)


def wrap_attrs(chunk: str) -> tuple[str, int]:
    def repl(match: re.Match) -> str:
        name, value = match.group(2), match.group(3)
        escaped = value.replace('\\', '\\\\').replace("'", "\\'")
        return f':{name}="t(\'{escaped}\')"'

    return ATTR.subn(repl, chunk)


def wrap_mustache(chunk: str) -> tuple[str, int]:
    total = 0

    def on_mustache(match: re.Match) -> str:
        nonlocal total
        body = match.group(1)

        def on_literal(lit: re.Match) -> str:
            nonlocal total
            start = lit.start()
            prefix = body[max(0, start - 2):start]
            if prefix.endswith('t(') or prefix.endswith('t( '):
                return lit.group(0)
            total += 1
            value = lit.group(1).replace('\\', '\\\\').replace("'", "\\'")
            return f"t('{value}')"

        return '{{' + LITERAL.sub(on_literal, body) + '}}'

    return MUSTACHE.subn(on_mustache, chunk), total


def process_file(path: str) -> tuple[int, int, int]:
    src = open(path, encoding='utf-8').read()
    if '<template>' not in src:
        return 0, 0, 0

    texts = attrs = mustaches = 0

    def on_template(match: re.Match) -> str:
        nonlocal texts, attrs, mustaches
        head, body, tail = match.group(1), match.group(2), match.group(3)
        # 保护注释
        comments: list[str] = []

        def hide(m: re.Match) -> str:
            comments.append(m.group(0))
            return f'\x00CMT{len(comments) - 1}\x00'

        body = COMMENT.sub(hide, body)
        body, n_text = wrap_text_nodes(body)
        body, n_attr = wrap_attrs(body)
        body, n_must = wrap_mustache(body)
        texts += n_text
        attrs += n_attr
        mustaches += n_must
        for index, value in enumerate(comments):
            body = body.replace(f'\x00CMT{index}\x00', value)
        return head + body + tail

    updated = TEMPLATE.sub(on_template, src, count=1)
    if texts + attrs + mustaches:
        updated = need_import(updated)
        open(path, 'w', encoding='utf-8').write(updated)
    return texts, attrs, mustaches


def main() -> int:
    grand = [0, 0, 0]
    changed = []
    for dirpath, _, filenames in os.walk(ROOT):
        if 'node_modules' in dirpath:
            continue
        for name in filenames:
            if not name.endswith('.vue'):
                continue
            path = os.path.join(dirpath, name)
            counts = process_file(path)
            if sum(counts):
                changed.append((os.path.relpath(path, ROOT), counts))
                grand = [a + b for a, b in zip(grand, counts)]
    for name, counts in sorted(changed):
        print(f'  {name}: 文本{counts[0]} 属性{counts[1]} 插值{counts[2]}')
    print(f'合计: 文本{grand[0]} 属性{grand[1]} 插值{grand[2]}，文件{len(changed)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
