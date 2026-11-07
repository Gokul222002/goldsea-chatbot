import uvicorn
import os
from backend.config import PORT, HOST

if __name__ == "__main__":
    print(f"Starting GoldSea Chatbot on http://{HOST}:{PORT}")
    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
