"""Bounded live narrative snapshots; only validated output becomes a conclusion."""
import asyncio
import json
import re
from .db import connect,transaction
from .tools import now_iso


def partial_summary(content):
    match=re.search(r'"summary"\s*:\s*"',content)
    if not match:return ''
    start=match.end()-1;escaped=False;end=len(content)
    for i in range(start+1,len(content)):
        char=content[i]
        if char=='"' and not escaped:
            end=i+1;break
        escaped=char=='\\' and not escaped
    raw=content[start:end]
    for trim in range(7):
        try:
            candidate=raw if raw.endswith('"') and end<len(content)+1 and trim==0 else raw[:len(raw)-trim]+'"'
            value=json.loads(candidate)
            return ''.join(ch for ch in value if not 0xD800<=ord(ch)<=0xDFFF)[:600]
        except (ValueError,TypeError):pass
    return ''


def publish(run_id,text,status):
    if not run_id:return
    with transaction() as conn:
        conn.execute('INSERT INTO run_narratives VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET '
            'text=excluded.text,status=excluded.status,updated_at=excluded.updated_at',
            (run_id,text[:600],status,now_iso()))


async def events(run_id,request):
    previous=None;seq=0
    while not await request.is_disconnected():
        conn=connect()
        try:
            run=conn.execute('SELECT status,error FROM runs WHERE run_id=?',(run_id,)).fetchone()
            narrative=conn.execute('SELECT text,status FROM run_narratives WHERE run_id=?',(run_id,)).fetchone()
            nodes=[dict(r) for r in conn.execute('SELECT seq,node,tool,status FROM agent_events WHERE run_id=? AND seq>? ORDER BY seq',(run_id,seq))]
        finally:conn.close()
        if narrative and tuple(narrative)!=previous:
            previous=tuple(narrative)
            yield 'event: output\ndata: '+json.dumps(dict(narrative),ensure_ascii=False)+'\n\n'
        for node in nodes:
            seq=node['seq'];yield 'event: node\ndata: '+json.dumps(node,ensure_ascii=False)+'\n\n'
        if not run or run['status'] in {'succeeded','failed'}:
            yield 'event: complete\ndata: '+json.dumps(dict(run) if run else {'status':'failed'},ensure_ascii=False)+'\n\n'
            return
        await asyncio.sleep(.15)
