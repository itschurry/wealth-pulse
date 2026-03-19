# Stage 1: Build React app
FROM node:20-alpine AS builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: nginx serve
FROM nginx:alpine
RUN apk add --no-cache python3 tzdata
COPY --from=builder /build/dist /usr/share/nginx/html
COPY generate_index.py /app/generate_index.py
COPY api_server.py /app/api_server.py
COPY analyzer /app/analyzer
COPY collectors /app/collectors
COPY config /app/config
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
