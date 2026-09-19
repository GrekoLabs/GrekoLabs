from fastapi import FastAPI

app = FastAPI(title="GrekoLabs API")


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "GrekoLabs API",
        "status": "running",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
