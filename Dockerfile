# Stage 1: Build React app
FROM node:20-alpine AS builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: nginx serve
FROM nginx:alpine
RUN apk add --no-cache python3 py3-pip tzdata
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /app/requirements.txt
COPY --from=builder /build/dist /usr/share/nginx/html
COPY generate_index.py /app/generate_index.py
COPY api_server.py /app/api_server.py
COPY market_utils.py /app/market_utils.py
COPY api /app/api
COPY analyzer /app/analyzer
COPY broker /app/broker
COPY collectors /app/collectors
COPY config /app/config
COPY reporter /app/reporter
COPY scripts /app/scripts
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 80
ENTRYPOINT ["/entrypoint.sh"]
