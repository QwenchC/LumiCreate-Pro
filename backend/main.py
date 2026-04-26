"""LumiCreate-Local Backend Entry Point"""
import uvicorn
from app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=18520,
        reload=False,
        log_level="info"
    )
