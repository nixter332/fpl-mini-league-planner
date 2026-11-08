# The FastAPI backend as a container (used by the Hugging Face Space; see docs/deploy.md).
FROM python:3.11-slim

# libgomp1: the CBC solver bundled with PuLP links against it.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run containers as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user . .
RUN mkdir -p data/cache && chown -R user:user /app
USER user

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}"]
