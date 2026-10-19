"""把 .vue 文件 script 区块中的中文字面量包装为 t('中文')。

规则与安全边界：
1. 只处理 <script> 区块，不触碰 <template> 与 <style>。
2. 跳过含换行的字面量、含 ${} 的模板字符串（需人工改为占位符形式）。
3. 跳过对象键名、已包装过的字面量、注释内的文字。
4. 跳过绑定到接口写入字段的默认值（人工维护 SKIP_LINES），
   保证"中文是数据基准"——提交给后端的内容不随界面语言变化。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'BIM-Safety-Coordination-Agent' / '02_网站源码' / 'frontend' / 'src'

CJK = re.compile(r'[\u4e00-\u9fff]')
SCRIPT = re.compile(r'(<script[^>]*>)(.*?)(</script>)', re.S)
LITERAL = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.S)
LINE_COMMENT = re.compile(r'//[^\n]*')
BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.S)

# 提交给后端的字段默认值，保持中文，不随界面语言变化
SKIP_EXACT = {
    '演示安全员',            # reviewer / actor 默认值，写入审核与事件记录
    '演示机电班组',          # 整改责任人默认值
    '机电班组', '装修班组',   # 作业计划责任主体默认值
    '机电', '装修',           # 作业计划工种默认值
    '材料转运', '相邻墙面作业',  # 作业计划活动名称默认值
    '人工编制演示作业计划',   # 作业计划变更原因，写入 coordination 记录
    '按批准的整改措施完成处置。',  # 整改说明默认值
    '新证据显示条件变化，需要重新检查。',  # 重开原因默认值
    '本演示由人工核对并填写观察参数。',  # 观察说明默认值
    '全面检查 L05 楼板区域的临边防护和人员暴露风险，结合现场证据与规范依据提出整改要求。',
    '验收 ',                 # 业务标识前缀，参与 startsWith 判定
    '简体中文',              # 语言选项固定显示母语名称
}
SKIP_PREFIX = ('演示整改：',)  # 整改资料说明模板，作为数据提交

# 出现在这些语法位置的中文字面量参与逻辑判断，不能包装
GUARD_TOKENS = ('startsWith(', 'endsWith(', 'includes(', '===', '!==', '==', '!=')

# 已被 t(...) 包装（注意 toast( 这类以 t( 结尾的标识符不算）
ALREADY_WRAPPED = re.compile(r'(?<![\w$])t\s*\(\s*$')


def mask_comments(body: str) -> str:
    """把注释替换为等长空白，保持字符偏移不变。"""
    def blank(match: re.Match[str]) -> str:
        return ' ' * len(match.group(0))

    masked = BLOCK_COMMENT.sub(blank, body)
    return LINE_COMMENT.sub(blank, masked)


def ensure_import(text: str, tag_end: int, depth: str) -> str:
    if re.search(r"from\s+'[^']*i18n'", text):
        return text
    insert = f"\nimport {{ t }} from '{depth}i18n'"
    return text[:tag_end] + insert + text[tag_end:]


def process(path: Path, dry: bool) -> int:
    rel = path.as_posix()
    text = path.read_text(encoding='utf-8')
    depth = '../' if '/views/' in '/' + rel or '/components/' in '/' + rel else './'
    count = 0
    out = ''
    cursor = 0
    for block in SCRIPT.finditer(text):
        body = block.group(2)
        masked = mask_comments(body)
        edits: list[tuple[int, int, str]] = []
        for match in LITERAL.finditer(body):
            raw = match.group(0)
            inner = raw[1:-1]
            if not CJK.search(inner):
                continue
            if '\n' in raw or '\r' in raw:
                continue
            if raw.startswith('`') and '${' in inner:
                continue
            # 注释内
            if masked[match.start():match.end()].strip() == '':
                continue
            if inner in SKIP_EXACT or inner.startswith(SKIP_PREFIX):
                continue
            before = body[:match.start()].rstrip()
            if ALREADY_WRAPPED.search(before):
                continue
            if before.endswith(GUARD_TOKENS):
                continue
            after = body[match.end():].lstrip()
            prev_char = before[-1] if before else ''
            if after.startswith(':') and prev_char in '{,':
                continue  # 对象键名
            if before.endswith('.') or before.endswith('${'):
                continue
            edits.append((match.start(), match.end(), f't({raw})'))

        for start, end, replacement in reversed(edits):
            body = body[:start] + replacement + body[end:]
        count += len(edits)
        out += text[cursor:block.start(2)] + body
        cursor = block.end(2)
    out += text[cursor:]
    if count and not dry:
        out = ensure_import(out, out.find('>', out.find('<script')) + 1, depth)
        path.write_text(out, encoding='utf-8')
    return count


def main() -> int:
    dry = '--apply' not in sys.argv
    total = 0
    for path in sorted(SRC.rglob('*.vue')):
        if 'i18n' in path.parts:
            continue
        n = process(path, dry)
        if n:
            print(f'{path.relative_to(SRC)}: {n}')
            total += n
    print(('DRY-RUN 共 ' if dry else '已包装 ') + str(total) + ' 处')
    return 0


if __name__ == '__main__':
    sys.exit(main())
