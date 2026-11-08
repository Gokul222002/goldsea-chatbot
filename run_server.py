import uvicorn
import os
from backend.config import PORT, HOST, ENVIRONMENT

if __name__ == "__main__":
    is_dev = ENVIRONMENT.lower() == "development"
    print(f"Starting GoldSea Chatbot on http://{HOST}:{PORT} (env={ENVIRONMENT}, reload={is_dev})")
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=is_dev)
