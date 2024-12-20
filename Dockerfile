FROM python:3.12.7-alpine3.20

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync

COPY data ./data
COPY main.py .
COPY lmbatbot ./lmbatbot

CMD [ "uv", "run", "main.py" ]
