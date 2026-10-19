"""展示层翻译服务。

中文是系统唯一的业务语义与数据基准；本模块只把中文文本投影成英文，
用于网页展示与 Word 导出。它不参与业务写入，不改变案例状态、风险结论、
规则匹配、记忆或任何业务记录。

设计约束：
- 纯函数式能力，不做规划、不调用业务工具、不进入 Agent 图。
- 失败时返回中文原文，绝不阻断业务，也不抛 500。
- 结果写入独立的 translation_cache 表，与业务表完全隔离。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

import httpx

from .config import MODEL_API_KEY, MODEL_BASE_URL, MODEL_NAME, MODEL_TIMEOUT_SECONDS
from .db import transaction

SUPPORTED_LANGS = ("zh", "en")
CACHE_VERSION = "v1"
BATCH_SIZE = 20
MAX_BATCH_CHARS = 1800
MAX_OUTPUT_TOKENS = 8000

CJK = re.compile(r"[\u4e00-\u9fa5]")

# 不可翻译片段：GUID、规范编号、条款号、业务 ID、数值带单位。
PROTECTED = re.compile(
    r"(?:"
    r"[0-9A-Za-z_]{20,}"                        # GUID 与长标识
    r"|(?:GB|JGJ|CJJ|DB)\s?\d{2,5}(?:[-—]\d{2,4})?"  # 规范编号
    r"|(?:CASE|TASK|RUN|EV|RULE|FIND|CTRL|ZONE|S1)-[0-9A-Za-z-]{2,}"  # 业务 ID
    r"|\d+(?:\.\d+)?\s?(?:mm|cm|m|km|kg|t|s|min|h|%|°)"  # 数值带单位
    r"|\d+\.\d+(?:\.\d+)?"                      # 条款号
    r")"
)

# 这些分支下的文本属于原始资料（规范原文、方案段落、现场文本），按设计不翻译。
SKIP_BRANCH_KEYS = {
    "rules",
    "site_notes",
    "paragraphs",
    "body",
    "text",
    "quote",
    "source_path",
    "file_path",
    "image_url",
}


def _is_case_identity(node: Any) -> bool:
    """案例标题是业务标识，前端依赖其前缀区分验收用例，保持原文。"""
    if not isinstance(node, dict):
        return False
    if "case_id" in node and "status" in node:
        return True
    return str(node.get("title", "")).startswith("验收 ")


def _skip_key(key: str, parent: Any) -> bool:
    if key in SKIP_BRANCH_KEYS:
        return True
    if key == "title" and _is_case_identity(parent):
        return True
    return False

SYSTEM_PROMPT = (
    "你是建筑施工安全领域的专业译者，把中文业务文本翻译成英文，用于界面展示与报告导出。\n"
    "规则：\n"
    "1. 输出 JSON 对象，键与输入数组中的字符串完全一致，不得遗漏或改写键。\n"
    "2. 固定术语：Safety Case、Risk Candidate、Check Item、Control Measure、"
    "Rectification、Verification、Slab Edge、Open Edge、Evidence、Finding。\n"
    "3. 占位符形如 {{P0}}、{{P1}}，必须原样保留，不得翻译或移动位置。\n"
    "4. 保持专业、简洁、客观，不添加解释，不改变原意。\n"
    "5. 只输出 JSON。"
)


def normalize_lang(value: str | None) -> str:
    """把请求头或参数规范成受支持的语言，默认中文。"""
    text = (value or "").strip().lower()
    if text.startswith("en"):
        return "en"
    return "zh"


def _ensure_table() -> None:
    with transaction() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS translation_cache(
                   input_hash TEXT PRIMARY KEY,
                   lang TEXT NOT NULL,
                   source TEXT NOT NULL,
                   output TEXT NOT NULL,
                   model TEXT,
                   created_at TEXT NOT NULL
               )"""
        )


def _hash(text: str, lang: str) -> str:
    payload = f"{CACHE_VERSION}\x1f{lang}\x1f{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def replace(match: re.Match) -> str:
        tokens.append(match.group(0))
        return f"{{{{P{len(tokens) - 1}}}}}"

    return PROTECTED.sub(replace, text), tokens


def _restore(text: str, tokens: list[str]) -> str:
    for index, value in enumerate(tokens):
        text = text.replace(f"{{{{P{index}}}}}", value)
    return text


def _needs_translation(value: Any) -> bool:
    return isinstance(value, str) and bool(CJK.search(value)) and not PROTECTED.fullmatch(value.strip())


def _cache_lookup(texts: list[str], lang: str) -> dict[str, str]:
    if not texts:
        return {}
    _ensure_table()
    hashes = {_hash(text, lang): text for text in texts}
    placeholders = ",".join("?" for _ in hashes)
    with transaction() as conn:
        rows = conn.execute(
            f"SELECT input_hash, output FROM translation_cache WHERE lang = ? AND input_hash IN ({placeholders})",
            (lang, *hashes.keys()),
        ).fetchall()
    return {hashes[row[0]]: row[1] for row in rows if row[0] in hashes}


def _cache_store(pairs: dict[str, str], lang: str) -> None:
    if not pairs:
        return
    from datetime import datetime

    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with transaction() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO translation_cache(input_hash, lang, source, output, model, created_at) VALUES (?,?,?,?,?,?)",
            [(_hash(source, lang), lang, source, output, MODEL_NAME, stamp) for source, output in pairs.items()],
        )


def _batches(items: list[str]) -> Iterable[list[str]]:
    current: list[str] = []
    size = 0
    for item in items:
        length = len(item)
        if current and (len(current) >= BATCH_SIZE or size + length > MAX_BATCH_CHARS):
            yield current
            current, size = [], 0
        current.append(item)
        size += length
    if current:
        yield current


def _call_model(batch: list[list[str]]) -> dict[str, str]:
    """batch 中每项是 [脱敏后的文本, 占位符列表]，返回 脱敏文本 -> 译文。"""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps([item[0] for item in batch], ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    url = MODEL_BASE_URL.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=max(MODEL_TIMEOUT_SECONDS, 90)) as client:
        response = client.post(
            url,
            headers={"Authorization": "Bearer " + MODEL_API_KEY},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
    content = body["choices"][0]["message"]["content"].strip()
    start, end = content.find("{"), content.rfind("}")
    parsed = json.loads(content[start:end + 1] if start >= 0 else content)
    if not isinstance(parsed, dict):
        raise ValueError("翻译结果不是 JSON 对象")
    return {str(key): str(value) for key, value in parsed.items()}


def _translate_chunk(chunk: list[str], depth: int = 0) -> dict[str, str]:
    """翻译一小批；失败时二分重试，仍失败则放弃该批（回退原文）。"""
    if not chunk:
        return {}
    prepared = []
    for text in chunk:
        masked, tokens = _protect(text)
        prepared.append([masked, tokens])
    try:
        answers = _call_model(prepared)
    except Exception:  # noqa: BLE001 - 翻译失败必须降级，不能阻断业务
        if len(chunk) == 1 or depth >= 3:
            return {}
        middle = len(chunk) // 2
        merged = _translate_chunk(chunk[:middle], depth + 1)
        merged.update(_translate_chunk(chunk[middle:], depth + 1))
        return merged
    produced: dict[str, str] = {}
    for text, (masked, tokens) in zip(chunk, prepared):
        value = answers.get(masked)
        if value:
            produced[text] = _restore(value, tokens)
    return produced


def translate_texts(texts: list[str], lang: str = "en") -> list[str]:
    """批量翻译文本。无法翻译时逐项回退为原文。"""
    lang = normalize_lang(lang)
    if lang != "en" or not texts:
        return list(texts)
    if not (MODEL_BASE_URL and MODEL_API_KEY and MODEL_NAME):
        return list(texts)

    unique = [text for text in dict.fromkeys(texts) if _needs_translation(text)]
    if not unique:
        return list(texts)

    known = _cache_lookup(unique, lang)
    pending = [text for text in unique if text not in known]

    produced: dict[str, str] = {}
    for chunk in _batches(pending):
        produced.update(_translate_chunk(chunk))

    if produced:
        try:
            _cache_store(produced, lang)
        except Exception:  # noqa: BLE001 - 缓存失败不影响本次展示
            pass

    mapping = {**known, **produced}
    return [mapping.get(text, text) for text in texts]


def _should_translate(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or not CJK.search(text):
        return False
    if PROTECTED.fullmatch(text):
        return False
    return True


def _walk(node: Any, sink: list[str], skip: bool = False) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if _skip_key(key, node):
                continue
            _walk(value, sink, skip)
    elif isinstance(node, list):
        for item in node:
            _walk(item, sink, skip)
    elif _should_translate(node):
        sink.append(node)


def _apply(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {
            key: value if _skip_key(key, node) else _apply(value, mapping)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_apply(item, mapping) for item in node]
    if isinstance(node, str):
        return mapping.get(node, node)
    return node


def translate_payload(payload: Any, lang: str = "en") -> Any:
    """把任意响应负载中的中文文本投影成英文，保持结构、标识与枚举不变。"""
    lang = normalize_lang(lang)
    if lang != "en" or payload is None:
        return payload

    collected: list[str] = []
    _walk(payload, collected)
    if not collected:
        return payload

    translated = translate_texts(collected, lang)
    mapping = dict(zip(collected, translated))
    if all(mapping.get(key) == key for key in mapping):
        return payload
    return _apply(payload, mapping)


def translate_words(texts: list[str], lang: str = "en") -> list[str]:
    """面向固定短语的轻量入口，供导出与测试复用。"""
    return translate_texts(texts, lang)
