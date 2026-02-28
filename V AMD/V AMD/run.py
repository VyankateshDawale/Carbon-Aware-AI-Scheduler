"""
AntiGravity Core v1.0 — Runner
"""
from server import app
import config

if __name__ == "__main__":
    print(f"\n⚡ AntiGravity Core v1.0 — http://localhost:{config.SERVER_PORT}\n")
    app.run(host=config.SERVER_HOST, port=config.SERVER_PORT, debug=True)
