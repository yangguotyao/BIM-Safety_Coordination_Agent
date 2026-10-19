"""在解压后的资料包内运行 python 验证资料完整性.py，只读检查正式附件。"""
from pathlib import Path
import csv,hashlib,sys
root=Path(__file__).resolve().parents[1]
failures=[];count=0
with (root/'01_资料清单/文件校验SHA256.csv').open(encoding='utf-8-sig') as f:
 for row in csv.DictReader(f):
  p=root/row['相对路径'];count+=1
  if not p.is_file():failures.append(row['相对路径']+' 缺失');continue
  h=hashlib.sha256()
  with p.open('rb') as stream:
   while data:=stream.read(1024*1024):h.update(data)
  if h.hexdigest()!=row['SHA256']:failures.append(row['相对路径']+' 摘要不一致')
print('已检查',count,'个文件')
if failures:
 print('\n'.join(failures));sys.exit(1)
print('附件完整性检查通过')
