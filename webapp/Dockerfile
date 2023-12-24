FROM node:16-alpine

WORKDIR /app

COPY package.json /app/package.json

RUN npm install

COPY public /app/public
COPY src /app/src

CMD ["npm", "start"]
