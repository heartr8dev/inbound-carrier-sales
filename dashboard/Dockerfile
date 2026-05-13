FROM node:20-alpine AS builder

WORKDIR /app

COPY dashboard/package.json dashboard/package-lock.json* /app/
RUN npm install --no-audit --no-fund

COPY dashboard /app/
RUN npm run build


FROM nginx:alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/conf.d/default.conf.bak

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
