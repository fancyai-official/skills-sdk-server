FROM oven/bun:1.3-debian

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    bash \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    && ln -sf python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY package.json tsconfig.json ./
RUN bun install

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY src ./src
COPY .claude ./.claude

ENV NODE_ENV=production
ENV APP_LANG=en
ENV HOME=/app/runtime
ENV ICON_DESIGNER_PROVIDER=mock

RUN mkdir -p /app/runtime/.claude /app/.generated && chown -R bun:bun /app

USER bun
EXPOSE 20001

CMD ["bun", "run", "src/server.ts"]
