# ── Stage 1: Build ────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Serve with Nginx ─────────────────
FROM nginx:1.27-alpine

# Remove default Nginx site
RUN rm /etc/nginx/conf.d/default.conf

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy Nginx config (mounted from project root at build time)
COPY nginx.conf /etc/nginx/conf.d/coldgrid.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
