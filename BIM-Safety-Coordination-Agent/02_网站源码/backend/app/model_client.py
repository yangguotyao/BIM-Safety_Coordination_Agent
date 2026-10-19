"""Small JSON model adapter with credential-free call records."""
from contextvars import ContextVar
import json
import time
from datetime import datetime
from typing import Any

import httpx

from .db import dumps, transaction
from .errors import APIError

CURRENT_RUN: ContextVar[str | None] = ContextVar('model_run_id', default=None)


def chat_json(*, base_url: str, key: str, model: str, messages: list,
              timeout: int, thinking: bool, purpose: str, case_id: str | None = None,
              evidence_id: str | None = None) -> dict[str, Any]:
    from .durable import guard_run
    guard_run(CURRENT_RUN.get(),model_call=True)
    if not (base_url and key and model):
        raise RuntimeError('模型配置不完整')
    payload = {'model': model, 'messages': messages, 'max_tokens': 2200,
               'stream': purpose=='risk_summary', 'response_format': {'type': 'json_object'}}
    if payload['stream']:payload['stream_options']={'include_usage':True}
    if 'deepseek.com' in base_url:
        payload['thinking'] = {'type': 'enabled' if thinking else 'disabled'}
    else:
        payload['enable_thinking'] = thinking
    started = time.monotonic()
    usage: dict[str, int] = {}
    status, error = 'failed', None
    try:
        with httpx.Client(timeout=timeout) as client:
            if payload['stream']:
                from .run_stream import partial_summary,publish
                publish(CURRENT_RUN.get(),'','generating')
                pieces=[];latest='';last_emit=0;provider_usage={}
                with client.stream('POST',base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload) as response:
                    response.raise_for_status()
                    if 'text/event-stream' in response.headers.get('content-type',''):
                        for line in response.iter_lines():
                            if not line.startswith('data:'):continue
                            data=line[5:].strip()
                            if data=='[DONE]':break
                            packet=json.loads(data)
                            provider_usage=packet.get('usage') or provider_usage
                            choices=packet.get('choices') or []
                            delta=choices[0].get('delta',{}).get('content') if choices else None
                            if not delta:continue
                            pieces.append(delta)
                            text=partial_summary(''.join(pieces))
                            if text!=latest and (not latest or time.monotonic()-last_emit>=.06):
                                latest=text;last_emit=time.monotonic();publish(CURRENT_RUN.get(),text,'generating')
                        body={'choices':[{'message':{'content':''.join(pieces)}}],'usage':provider_usage}
                    else:
                        response.read();body=response.json()
            else:
                response=client.post(base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},json=payload)
                response.raise_for_status();body=response.json()
        guard_run(CURRENT_RUN.get())
        usage = {k: v for k, v in (body.get('usage') or {}).items()
                 if k in {'prompt_tokens', 'completion_tokens', 'total_tokens', 'prompt_cache_hit_tokens'} and type(v) is int}
        content = body['choices'][0]['message']['content']
        if isinstance(content, list):
            content = ''.join(item.get('text', '') for item in content if item.get('type') == 'text')
        content = content.strip()
        start, end = content.find('{'), content.rfind('}')
        result = json.loads(content[start:end + 1] if start >= 0 and end > start else content)
        if not isinstance(result, dict):
            raise ValueError('模型输出必须是JSON对象')
        status = 'succeeded'
        return result
    except APIError as exc:
        error=exc.code
        raise
    except Exception as exc:
        error = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            error += ':' + str(exc.response.status_code)
        raise RuntimeError('模型请求失败：' + error) from None
    finally:
        with transaction() as conn:
            conn.execute('''INSERT INTO model_calls
                (case_id,run_id,evidence_id,purpose,model,status,elapsed_ms,usage_json,error,at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (case_id, CURRENT_RUN.get(), evidence_id, purpose, model, status,
                 round((time.monotonic() - started) * 1000), dumps(usage), error,
                 datetime.now().astimezone().isoformat(timespec='seconds')))
