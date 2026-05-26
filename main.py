try:
    import uvicorn
except ModuleNotFoundError:  # pragma: no cover
    uvicorn = None

from web.simple_server import run_simple_server


if __name__ == "__main__":
    if uvicorn is None:
        run_simple_server(host="127.0.0.1", port=8000)
    else:
        uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=False)
