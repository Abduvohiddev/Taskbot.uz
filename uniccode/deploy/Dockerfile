# Faqat @uniccodebot uchun yengil image (asosiy Taskbot bog'liqliklarisiz).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=Asia/Tashkent
WORKDIR /app

COPY uniccode/deploy/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY uniccode /app/uniccode
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "uniccode"]
