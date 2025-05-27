import os
import threading
import time
from main import bot, app, run_bot, run_api

def start_bot():
    """Start the Discord bot in background"""
    try:
        run_bot()
    except Exception as e:
        print(f"Bot error: {e}")

# Start Discord bot in background thread
bot_thread = threading.Thread(target=start_bot, daemon=True)
bot_thread.start()

# Optional: Give the bot some time
time.sleep(2)

# Start FastAPI app if run directly (for docker)
if __name__ == "__main__":
    run_api()
