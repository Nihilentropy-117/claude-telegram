FROM node:22-alpine
RUN npm install -g obsidian-headless
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
