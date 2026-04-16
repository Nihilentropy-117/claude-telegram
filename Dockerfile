FROM python:3.12

# System packages: build tools, media processing, dev libraries, utilities
RUN apt-get update && apt-get install -y \
    curl git wget sudo build-essential cmake pkg-config \
    jq ripgrep fd-find tree htop \
    openssh-client rsync zip unzip \
    ffmpeg imagemagick pandoc poppler-utils ghostscript \
    sox libsox-fmt-all libimage-exiftool-perl \
    libffi-dev libssl-dev libxml2-dev libxslt1-dev sqlite3 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN echo "ALL ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Python package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Persistent venv — bind-mounted from host
ENV VIRTUAL_ENV=/venv
ENV PATH="/venv/bin:$PATH"
ENV PIP_CACHE_DIR=/pip-cache

# Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g claudish

# Install bot package
COPY pyproject.toml /app/pyproject.toml
COPY claude_telegram/ /app/claude_telegram/
RUN pip install --no-cache-dir /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "claude_telegram"]
