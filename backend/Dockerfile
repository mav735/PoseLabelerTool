FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Heavy, rarely-changing layers FIRST. torch + the inference stack pull ~2 GB of
# CUDA wheels; the app's own requirements change often. With the app layer above
# them, adding one line to requirements.txt invalidated this install and dragged
# the whole CUDA download down again. Order matters more than tidiness here.
#
# The pip cache lives in a BuildKit cache mount rather than the image, so even a
# deliberate bust of this layer reuses already-downloaded wheels instead of
# refetching them. That is also why --no-cache-dir is gone: it would tell pip to
# throw away exactly what the mount exists to keep, while the mount keeps the
# cache out of the layer so the image does not grow.
COPY requirements-inference.txt ./
# GPU uses the CUDA 12.8 index (Blackwell sm_120); a CPU build overrides with
# --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url ${TORCH_INDEX} torch torchvision \
    && pip install -r requirements-inference.txt

# App dependencies last: editing requirements.txt now re-runs only this step.
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY config.example.yaml ./config.yaml

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
