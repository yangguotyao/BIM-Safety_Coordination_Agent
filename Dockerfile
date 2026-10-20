# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
COPY BIM-Safety-Coordination-Agent/02_网站源码/frontend/package.json BIM-Safety-Coordination-Agent/02_网站源码/frontend/package-lock.json ./
RUN npm ci
COPY BIM-Safety-Coordination-Agent/02_网站源码/frontend/ ./
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATA_ROOT=/srv/project/01_资料与依据 \
    RUNTIME_DIR=/srv/project/02_网站源码/backend/runtime \
    FRONTEND_DIST=/srv/project/02_网站源码/frontend/dist

WORKDIR /srv/project/02_网站源码/backend

COPY BIM-Safety-Coordination-Agent/02_网站源码/backend/requirements-lock.txt ./requirements-lock.txt
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY BIM-Safety-Coordination-Agent/02_网站源码/backend/app ./app
COPY BIM-Safety-Coordination-Agent/01_资料与依据 /srv/project/01_资料与依据
COPY BIM-Safety-Coordination-Agent/00_执行计划与自检 /srv/project/00_执行计划与自检
COPY --from=frontend-builder /build/frontend/dist /srv/project/02_网站源码/frontend/dist

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app \
    && mkdir -p /srv/project/02_网站源码/backend/runtime \
    && chown -R app:app /srv/project/02_网站源码/backend/runtime

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
