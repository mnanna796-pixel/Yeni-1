import os
import threading
import asyncio
from flask import Flask
from bot import start_polling

app = Flask(__name__)

@app.route("/")
@app.route("/health")
def health():
    return "OK"

def run_bot():
    asyncio.run(start_polling())

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
