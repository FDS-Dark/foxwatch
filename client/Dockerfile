# Build context: repository root (docker build -f client/Dockerfile .)
FROM oven/bun:1 AS build

WORKDIR /app/client

COPY client/package.json client/bun.lock ./
RUN bun install --frozen-lockfile

COPY client/ ./
RUN bun run build

FROM nginx:1.27-alpine

COPY client/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/client/dist /usr/share/nginx/html

EXPOSE 80
