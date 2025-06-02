import os
import threading
import time
import signal
import sys
import logging
from main import bot, app, run_bot, run_api

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag to control shutdown
shutdown_flag = threading.Event()

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_flag.set()

def start_bot():
    """Start the Discord bot with error handling and restart logic"""
    while not shutdown_flag.is_set():
        try:
            logger.info("Starting Discord bot...")
            run_bot()
        except Exception as e:
            logger.error(f"Bot error: {e}")
            if not shutdown_flag.is_set():
                logger.info("Restarting bot in 5 seconds...")
                time.sleep(5)
            else:
                break
    logger.info("Bot thread shutting down.")

def start_api():
    """Start FastAPI with error handling"""
    try:
        logger.info("Starting FastAPI server...")
        run_api()
    except Exception as e:
        logger.error(f"API server error: {e}")
        shutdown_flag.set()

def health_monitor():
    """Monitor bot health and restart if needed"""
    while not shutdown_flag.is_set():
        time.sleep(30)  # Check every 30 seconds
        if not bot.is_ready() and not shutdown_flag.is_set():
            logger.warning("Bot appears to be disconnected, but letting Discord.py handle reconnection...")
        
def main():
    """Main function to coordinate all services"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Starting Discord Flashcard Bot API...")
    
    # Verify Discord token is present
    if not os.getenv('DISCORD_BOT_TOKEN'):
        logger.error("DISCORD_BOT_TOKEN environment variable not set!")
        sys.exit(1)
    
    # Start Discord bot in background thread
    bot_thread = threading.Thread(target=start_bot, daemon=False, name="DiscordBot")
    bot_thread.start()
    logger.info("Discord bot thread started")
    
    # Give the bot some time to initialize
    time.sleep(3)
    
    # Start health monitor
    health_thread = threading.Thread(target=health_monitor, daemon=True, name="HealthMonitor")
    health_thread.start()
    logger.info("Health monitor thread started")
    
    # Start FastAPI server (this will block)
    try:
        start_api()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        logger.info("Initiating shutdown...")
        shutdown_flag.set()
        
        # Wait for bot thread to finish
        if bot_thread.is_alive():
            logger.info("Waiting for bot thread to finish...")
            bot_thread.join(timeout=10)
        
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    main()