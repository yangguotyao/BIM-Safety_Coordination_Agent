"""Rasterize the Word-exported plan PDF with the packaged DOCX renderer.

The bundled Windows runtime has no LibreOffice binary. Word exported this exact
read-only DOCX to qa/plan/区域施工方案.pdf. Only the PDF conversion boundary is
adapted here; the managed renderer and its PNG naming remain unchanged.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'data/demo/s1_case_001'
SKILL=Path.home()/'.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents'
spec=importlib.util.spec_from_file_location('packaged_docx_renderer',SKILL/'render_docx.py')
renderer=importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)
docx=PACKAGE/'documents/区域施工方案.docx'
pdf=PACKAGE/'qa/plan/区域施工方案.pdf'
if not pdf.is_file() or pdf.stat().st_mtime < docx.stat().st_mtime:
    raise RuntimeError('Export the latest DOCX using Word before rendering')
renderer.convert_to_pdf=lambda *args,**kwargs:(str(pdf),'PDF conversion performed by Microsoft Word')
pages=renderer.rasterize(str(docx),str(pdf.parent),150,False,False)
report={'renderer':'packaged render_docx.py rasterize, Word PDF conversion adapter',
        'docx_sha256':hashlib.sha256(docx.read_bytes()).hexdigest(),
        'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':pages,
        'visual_review':'pending'}
(pdf.parent/'render_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages':len(pages),'directory':str(pdf.parent)},ensure_ascii=False))
