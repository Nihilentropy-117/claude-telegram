FROM python:3.12

# Full system: build tools, media, dev libraries, utilities
RUN apt-get update && apt-get install -y \
    curl git wget sudo build-essential cmake pkg-config \
    jq ripgrep fd-find tree htop \
    openssh-client rsync zip unzip \
    # Media & conversion
    ffmpeg imagemagick pandoc poppler-utils ghostscript \
    sox libsox-fmt-all libimage-exiftool-perl \
    # Dev libraries (for pip compiled packages)
    libffi-dev libssl-dev libxml2-dev libxslt1-dev sqlite3 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Passwordless sudo
RUN echo "ALL ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Persistent venv — bind-mounted from host
ENV VIRTUAL_ENV=/venv
ENV PATH="/venv/bin:$PATH"
ENV PIP_CACHE_DIR=/pip-cache

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g claudish


# Install bot deps (goes into /venv once it exists, or system python on build)
# Entrypoint creates the venv; on first run pip install runs again to populate it
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY bot.py /app/bot.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "bot.py"]
