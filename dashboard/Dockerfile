FROM node:20-alpine AS builder

WORKDIR /app

# Vite reads VITE_* env vars at build time and bakes them into the bundle, so
# they have to be present BEFORE `npm run build`. Pass them in via --build-arg
# from flyctl deploy (see .github/workflows/deploy.yml).
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_API_KEY=devkey-please-change
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_KEY=$VITE_API_KEY

COPY package.json package-lock.json* /app/
RUN npm install --no-audit --no-fund

COPY . /app/
RUN npm run build


FROM nginx:alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/conf.d/default.conf.bak

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
