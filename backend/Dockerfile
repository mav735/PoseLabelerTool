FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-inference.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Torch: GPU uses the CUDA 12.8 index (Blackwell sm_120); CPU build overrides with --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
RUN pip install --no-cache-dir --index-url ${TORCH_INDEX} torch torchvision \
    && pip install --no-cache-dir -r requirements-inference.txt

COPY app ./app
COPY config.example.yaml ./config.yaml

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
