import threading
import webbrowser

import uvicorn

try:
    from poshshare.server import app
except ImportError:
    from server import app


if __name__ == "__main__":
    # Open dashboard shortly after server starts
    threading.Timer(0.8, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


