"""Run the unified FoxWatch API (observations + BFI). Same as ``foxwatch.main:app``."""

from foxwatch.main import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
