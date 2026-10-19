"""一次性构建工具：把界面中文文案批量翻译成英文，生成前端静态词典。

产物：02_网站源码/frontend/src/i18n/ui-en.ts
该文件是构建产物，运行时不再调用模型。

用法：
    python scripts/build_ui_dict.py           # 增量翻译缺失条目并重写词典
    python scripts/build_ui_dict.py --collect # 仅重新汇总源文件中的中文 key
"""
import json
import os
import re
import sys
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, '.env')
SRC_DIR = os.path.join(ROOT, 'BIM-Safety-Coordination-Agent', '02_网站源码', 'frontend', 'src')
CLEAN_PATH = os.path.join(ROOT, 'BIM-Safety-Coordination-Agent', '_i18n_clean.json')
OUT_PATH = os.path.join(SRC_DIR, 'i18n', 'ui-en.ts')
MID_PATH = os.path.join(ROOT, 'BIM-Safety-Coordination-Agent', '_i18n_en.json')

CJK = re.compile(r'[\u4e00-\u9fff]')
CALL = re.compile(r"\bt\(\s*'((?:\\.|[^'\\])*)'|\bt\(\s*\"((?:\\.|[^\"\\])*)\"")


def collect() -> list[str]:
    """扫描源码里所有 t('中文') 的 key，保持出现顺序稳定。"""
    seen: dict[str, None] = {}
    for base, _dirs, files in os.walk(SRC_DIR):
        if 'i18n' in base.split(os.sep):
            continue
        for name in sorted(files):
            if not name.endswith(('.vue', '.ts')):
                continue
            text = open(os.path.join(base, name), encoding='utf-8').read()
            for match in CALL.finditer(text):
                key = match.group(1) if match.group(1) is not None else match.group(2)
                key = key.replace("\\'", "'").replace('\\"', '"')
                if key and CJK.search(key) and key not in seen:
                    seen[key] = None
    return list(seen)

SYSTEM = (
    '你是建筑施工安全领域的专业译者，负责把中文界面文案翻译成简洁的英文界面用语。\n'
    '规则：\n'
    '1. 输出 JSON 对象，键必须与输入数组中的字符串完全一致，一个都不能少。\n'
    '2. 使用安全领域标准术语：Safety Case, Risk Candidate, Check Item, Control Measure, '
    'Rectification, Verification, Slab Edge, Open Edge, Evidence, Finding, Control。\n'
    '3. 规范编号（GB55034-2022、JGJ80-2016）、GUID、EV-xxx、CASE-xxx、单位符号原样保留，不翻译。\n'
    '4. 界面用语要简短，适合按钮、标签、表头；完整句子保持专业、克制。\n'
    '5. 不要添加解释，不要输出 JSON 以外的任何内容。'
)


def load_env() -> dict:
    cfg = {}
    for line in open(ENV_PATH, encoding='utf-8', errors='ignore'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def translate_batch(client: httpx.Client, cfg: dict, batch: list[str]) -> dict:
    payload = {
        'model': cfg['MODEL_NAME'],
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(batch, ensure_ascii=False)},
        ],
        'response_format': {'type': 'json_object'},
        'temperature': 0,
        'max_tokens': 4000,
    }
    url = cfg['MODEL_BASE_URL'].rstrip('/') + '/chat/completions'
    response = client.post(
        url,
        headers={'Authorization': 'Bearer ' + cfg['MODEL_API_KEY']},
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    body = response.json()
    content = body['choices'][0]['message']['content'].strip()
    start, end = content.find('{'), content.rfind('}')
    return json.loads(content[start:end + 1])


def main() -> int:
    texts = collect()
    json.dump(texts, open(CLEAN_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'源文件中文文案 {len(texts)} 条')
    if '--collect' in sys.argv:
        return 0

    cfg = load_env()
    if not (cfg.get('MODEL_BASE_URL') and cfg.get('MODEL_API_KEY') and cfg.get('MODEL_NAME')):
        print('模型配置不完整，无法生成词典')
        return 1

    result: dict[str, str] = {}

    if os.path.exists(MID_PATH):
        cached = json.load(open(MID_PATH, encoding='utf-8'))
        result = {item: cached[item] for item in texts if item in cached}
        if len(result) == len(texts):
            print(f'复用已翻译结果: {len(result)} 条')
            return write_ts(texts, result)
        print(f'复用 {len(result)} 条，需新增翻译 {len(texts) - len(result)} 条')

    pending = [item for item in texts if item not in result]
    if not pending:
        print(f'全部命中缓存: {len(result)} 条')
        return write_ts(texts, result)
    size = 40
    batches = [pending[i:i + size] for i in range(0, len(pending), size)]
    print(f'共 {len(texts)} 条，待译 {len(pending)} 条，分 {len(batches)} 批')

    with httpx.Client() as client:
        for index, batch in enumerate(batches, 1):
            for attempt in range(3):
                try:
                    part = translate_batch(client, cfg, batch)
                    missing = [item for item in batch if item not in part]
                    result.update({k: v for k, v in part.items() if k in batch})
                    print(f'  批次 {index}/{len(batches)}: 得到 {len(part)} 条，缺 {len(missing)} 条')
                    if missing and attempt == 2:
                        for item in missing:
                            result.setdefault(item, item)
                    break
                except Exception as exc:  # noqa: BLE001
                    print(f'  批次 {index} 第 {attempt + 1} 次失败: {type(exc).__name__}')
                    time.sleep(2)
            else:
                for item in batch:
                    result.setdefault(item, item)

    for item in texts:
        result.setdefault(item, item)
    json.dump(result, open(MID_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return write_ts(texts, result)


def write_ts(texts: list[str], result: dict[str, str]) -> int:
    lines = [
        '/** 界面文案英文对照表（构建产物，key 为中文原文）。',
        ' * 由 scripts/build_ui_dict.py 生成，新增界面文案后可重新生成。',
        ' */',
        'const uiEn: Record<string, string> = {',
    ]
    for key in texts:
        value = result[key].replace('\\', '\\\\').replace("'", "\\'")
        safe_key = key.replace('\\', '\\\\').replace("'", "\\'")
        lines.append(f"  '{safe_key}': '{value}',")
    lines.append('}')
    lines.append('')
    lines.append('export default uiEn')
    open(OUT_PATH, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')

    untranslated = [k for k in texts if result[k] == k]
    print(f'完成：写入 {len(result)} 条，未翻译 {len(untranslated)} 条')
    return 0


if __name__ == '__main__':
    sys.exit(main())
