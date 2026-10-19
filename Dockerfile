# Build stage: Chainguard's minimal Python image (Wolfi-based, rebuilt daily, very few packages).
FROM cgr.dev/chainguard/python:latest-dev AS build
WORKDIR /srv
RUN python -m venv /srv/venv
ENV PATH="/srv/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage: no shell, no package manager, non-root by default.
FROM cgr.dev/chainguard/python:latest
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 \
    PATH="/srv/venv/bin:$PATH"
WORKDIR /srv
COPY --from=build /srv/venv /srv/venv
COPY app ./app
COPY VERSION .
COPY docs/stock-face ./docs/stock-face
COPY serve.py .
EXPOSE 8080
ENTRYPOINT ["python", "serve.py"]
