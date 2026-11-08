import os
import uvicorn

def get_port() -> int:
    raw = os.environ.get("PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return 8080

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = get_port()
    env = os.environ.get("ENVIRONMENT", "production").strip() or "production"
    is_dev = env.lower() == "development"
    print(f"Starting GoldSea Chatbot on http://{host}:{port} (env={env}, reload={is_dev})")
    uvicorn.run("backend.main:app", host=host, port=port, reload=is_dev)
