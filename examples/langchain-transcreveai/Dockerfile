FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY video_kb ./video_kb
COPY examples/langchain-transcreveai/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir . -r requirements.txt && useradd --create-home app
COPY examples/langchain-transcreveai/app.py examples/langchain-transcreveai/web.py examples/langchain-transcreveai/index.html ./
USER app
CMD ["uvicorn", "web:app", "--host", "0.0.0.0", "--port", "8000"]
