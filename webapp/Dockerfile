FROM node:18-alpine

WORKDIR /app

COPY package.json /app/package.json

RUN npm install

COPY tailwind.config.js /app/tailwind.config.js
COPY postcss.config.js /app/postcss.config.js
COPY public /app/public
COPY src /app/src

CMD ["npm", "start"]
