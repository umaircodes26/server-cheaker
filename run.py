import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print("=" * 60)
    print("🛡️  VPS Sentinel 24/7 Watchdog Starting...")
    print(f"📊 Dashboard GUI accessible at: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run("app.main:app", host=host, port=port, reload=False)

