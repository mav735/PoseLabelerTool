FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
# Drop the stock IPv6 entrypoint script. It runs `apk manifest nginx`, which
# reaches the Alpine package CDN at container START; outbound access is
# constrained on this deployment, so that call hangs forever and nginx never
# gets exec'd. The container then reports "running" while serving nothing,
# which is the worst shape of failure to diagnose. All the script does is add
# an IPv6 listen directive, and this host does not route IPv6.
RUN rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
