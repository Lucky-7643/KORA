# KORA — production image
# Builds the frontend + bundles the server, then runs them on PORT.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Hosted container must accept external traffic (localhost default is for the
# local desktop app only).
ENV KORA_HOST=0.0.0.0
COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
COPY --from=build /app/assets ./assets
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "dist/server.cjs"]