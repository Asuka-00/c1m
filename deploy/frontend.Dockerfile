# 生产前端镜像：构建静态文件后由 nginx 托管，并反向代理 /api 到后端
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.27-alpine
FROM ${NODE_IMAGE} AS build
ARG NPM_REGISTRY=https://registry.npmmirror.com
WORKDIR /src
RUN npm config set registry ${NPM_REGISTRY} && npm i -g pnpm@10 --registry ${NPM_REGISTRY}
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm config set registry ${NPM_REGISTRY} && pnpm install --frozen-lockfile
COPY frontend/ ./
# 空字符串 = 同源访问 /api（由 nginx 反代）
ENV VITE_API_URL=""
RUN pnpm exec vite build

FROM ${NGINX_IMAGE}
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
