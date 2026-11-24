FROM node:22-alpine AS web-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md rubric.default.json ./
COPY pkt_grader ./pkt_grader
COPY --from=web-builder /app/web/dist ./web/dist
RUN pip install --no-cache-dir .
ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000
CMD ["pkt-grade-web"]
