FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system gg && useradd --system --create-home --gid gg gg

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY config ./config
COPY README.md .

USER gg
CMD ["python", "-m", "bot.bot"]
