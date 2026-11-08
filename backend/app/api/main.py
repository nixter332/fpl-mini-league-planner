"""FastAPI entry point. Phase 1 only exposes a health check."""

from fastapi import FastAPI

app = FastAPI(title="FPL Mini-League Planner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
