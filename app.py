import os
import threading
import time
from main import bot, app, run_bot

def start_bot():
    """Start the Discord bot in background"""
    try:
        run_bot()
    except Exception as e:
        print(f"Bot error: {e}")

# Start Discord bot in background thread
if __name__ == "__main__":
    # Start bot in background
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Give the bot a moment to start
    time.sleep(2)

# Export the FastAPI app for Hugging Face Spaces
if __name__ != "__main__":
    # Start bot when module is imported
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
