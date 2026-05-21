FROM node:20-alpine

RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app

COPY pnpm-workspace.yaml ./
COPY packages/ab-leaderboard/package.json packages/ab-leaderboard/pnpm-lock.yaml* packages/ab-leaderboard/
COPY packages/ab-leaderboard ./packages/ab-leaderboard

WORKDIR /app/packages/ab-leaderboard

RUN pnpm install --frozen-lockfile=false

EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]
