"""Server-side roles and project scope; local demo remains a trusted local mode."""
import hashlib
import re
import secrets
from contextvars import ContextVar
from .config import model_settings,PROJECT_ID
from .db import connect,transaction,loads,dumps,init_db
from .errors import APIError
from .tools import now_iso

ACCESS_MODE=model_settings.access_mode
PRINCIPAL:ContextVar[dict|None]=ContextVar('access_principal',default=None)
ROLES={'viewer','inspector','reviewer','rectifier','admin'}


def scoped_sql(column='project_id'):
    principal=PRINCIPAL.get();projects=principal['projects'] if principal else ['*']
    if '*' in projects:return '1=1',[]
    return column+' IN ('+','.join('?' for _ in projects)+')',list(projects)


def authenticate(request):
    if ACCESS_MODE=='public_demo':
        return {'label':'公开演示访问者','role':'admin','projects':['*'],'mode':'public_demo'}
    header=request.headers.get('Authorization','')
    if not header and request.cookies.get('bim_access'):header='Bearer '+request.cookies['bim_access']
    if header:
        if not header.startswith('Bearer '):raise APIError(401,'access_token_required','请提供有效访问令牌')
        conn=connect()
        try:row=conn.execute('SELECT * FROM access_tokens WHERE token_hash=? AND active=1',(hashlib.sha256(header[7:].encode()).hexdigest(),)).fetchone()
        finally:conn.close()
        if not row:raise APIError(401,'invalid_access_token','访问令牌无效或已撤销')
        return {'label':row['label'],'role':row['role'],'projects':loads(row['projects_json'],[]),'mode':'token'}
    if ACCESS_MODE=='token':raise APIError(401,'access_token_required','当前服务要求访问令牌')
    peer=request.client.host if request.client else ''
    if peer not in {'127.0.0.1','::1','testclient'} or request.url.hostname not in {'127.0.0.1','localhost','::1','testserver'}:
        raise APIError(403,'local_demo_only','本机演示模式仅允许本机访问；远程服务需启用令牌模式')
    return {'label':'本机演示操作员','role':'admin','projects':['*'],'mode':'local_demo'}


def authorize(request,principal):
    path=request.url.path;role=principal['role'];projects=principal['projects'];case=None;project=None
    origin=request.headers.get('Origin')
    allowed_origins={str(request.base_url).rstrip('/'),'http://127.0.0.1:5173','http://localhost:5173'}
    if origin and origin not in allowed_origins:raise APIError(403,'origin_access_denied','请求来源不在当前平台范围内')
    if path=='/api/access/logout':return
    conn=connect()
    try:
        match=re.match(r'/api/cases/([^/]+)',path)
        run=re.match(r'/api/runs/([^/]+)',path)
        ev=re.match(r'/api/(?:files/)?evidence/([^/]+)',path)
        if match:case=conn.execute('SELECT project_id,status FROM cases WHERE case_id=?',(match[1],)).fetchone()
        elif run:case=conn.execute('SELECT c.project_id,c.status FROM runs r JOIN cases c ON c.case_id=r.case_id WHERE r.run_id=?',(run[1],)).fetchone()
        elif ev:
            row=conn.execute('SELECT project_id FROM evidence WHERE evidence_id=?',(ev[1],)).fetchone()
            project=row['project_id'] if row else None
        if case:project=case['project_id']
    finally:conn.close()
    if project and '*' not in projects and project not in projects:raise APIError(403,'project_access_denied','没有该项目的访问权限')
    if request.method in {'GET','HEAD','OPTIONS'}:
        if path in {'/api/agent/runtime','/api/demo/acceptance/latest'} and role!='admin':raise APIError(403,'role_access_denied','该运行信息仅管理员可查看')
        if not project and path not in {'/api/cases','/api/evidence','/api/tasks','/api/agent/runs','/api/access/session'} and '*' not in projects and PROJECT_ID not in projects:
            raise APIError(403,'project_access_denied','没有当前模型项目的访问权限')
        return
    if role=='admin':return
    allowed=False
    if path=='/api/cases':allowed=role=='inspector' and ('*' in projects or PROJECT_ID in projects)
    elif path.endswith(('/review','/verify')):allowed=role=='reviewer'
    elif path.endswith('/implementation'):allowed=role=='rectifier'
    elif path.endswith(('/analyze','/ask','/scope','/reopen','/resume','/cancel')):allowed=role=='inspector'
    elif '/site-notes' in path:allowed=role=='inspector'
    elif path.endswith('/activity-plan'):allowed=role=='inspector' or role=='rectifier' and case and case['status'] in {'approved','rectifying','pending_verification'}
    elif '/evidence' in path:allowed=role=='inspector' or role=='rectifier' and case and case['status'] in {'approved','rectifying','pending_verification'}
    if not allowed:raise APIError(403,'role_access_denied','当前角色无权执行此操作；修改显示姓名不会改变权限')


def record_access(principal,request,status):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        with transaction() as tx:tx.execute('INSERT INTO access_events(principal,role,method,path,status,at) VALUES(?,?,?,?,?,?)',
            (principal['label'],principal['role'],request.method,request.url.path,status,now_iso()))


def main():
    import argparse
    parser=argparse.ArgumentParser(description='管理BIM平台服务端访问令牌。令牌只显示一次，数据库仅存SHA256。')
    parser.add_argument('operation',choices=['create','revoke'])
    parser.add_argument('--label',required=True)
    parser.add_argument('--role',choices=sorted(ROLES),default='viewer')
    parser.add_argument('--project',action='append',default=[])
    args=parser.parse_args();init_db()
    with transaction() as tx:
        if args.operation=='revoke':tx.execute('UPDATE access_tokens SET active=0 WHERE label=?',(args.label,));print('已撤销');return
        projects=args.project or [PROJECT_ID]
        if '*' in projects and args.role!='admin':parser.error('只有管理员可授权全部项目')
        for project in projects:
            if project!='*' and not tx.execute('SELECT 1 FROM projects WHERE project_id=?',(project,)).fetchone():parser.error('项目不存在')
        token=secrets.token_urlsafe(32)
        tx.execute('INSERT INTO access_tokens(token_hash,label,role,projects_json) VALUES(?,?,?,?)',
            (hashlib.sha256(token.encode()).hexdigest(),args.label,args.role,dumps(projects)))
    print(token)


if __name__=='__main__':main()
