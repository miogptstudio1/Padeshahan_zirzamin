"""Render Web Service entrypoint for the API + Telegram bot in one process."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), proxy_headers=True, forwarded_allow_ips="*")
