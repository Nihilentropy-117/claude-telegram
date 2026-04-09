FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/venv \
    PATH="/venv/bin:/app/src:$PATH" \
    PIP_CACHE_DIR=/pip-cache \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    ffmpeg \
    fd-find \
    ghostscript \
    git \
    htop \
    imagemagick \
    jq \
    libffi-dev \
    libimage-exiftool-perl \
    libsox-fmt-all \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    openssh-client \
    pandoc \
    poppler-utils \
    pkg-config \
    ripgrep \
    rsync \
    sox \
    sqlite3 \
    sudo \
    tree \
    unzip \
    wget \
    zip \
    && rm -rf /var/lib/apt/lists/*

RUN echo "ALL ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

WORKDIR /app

COPY requirements.txt /app/requirements.txt
COPY entrypoint.sh /entrypoint.sh
COPY src /app/src
COPY bot.py /app/bot.py

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "claude_telegram"]
