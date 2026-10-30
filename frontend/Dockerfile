FROM node:22-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-slim
WORKDIR /web
ENV NODE_ENV=production
COPY --from=build /web ./
USER node
EXPOSE 3000
CMD ["npm", "start"]
