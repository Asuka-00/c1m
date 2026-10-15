# 生产后端镜像：FastAPI + uv（依赖按 uv.lock 冻结安装，不含开发依赖）
ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE}

# 国内服务器可通过构建参数改用镜像源（如阿里云）
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} uv==0.9.26

WORKDIR /app/
COPY uv.lock pyproject.toml /app/
COPY backend/pyproject.toml /app/backend/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package app

COPY backend/scripts /app/backend/scripts
COPY backend/alembic.ini /app/backend/
COPY backend/app /app/backend/app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package app

WORKDIR /app/backend/
RUN useradd --system --uid 10001 app && mkdir -p data/uploads && chown -R app data
USER app
EXPOSE 8000
CMD ["fastapi", "run", "--workers", "2", "--proxy-headers", "--port", "8000"]
