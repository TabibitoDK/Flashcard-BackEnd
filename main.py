import discord
from discord.ext import commands
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
import threading
import uvicorn
import os
from typing import List, Dict, Optional
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

# FastAPI Setup
app = FastAPI(title="Discord Flashcard Bot API")

# Pydantic models for request validation
class ChallengeResult(BaseModel):
    correct: int
    incorrect: int

# Global variables
guild_id = None
flashcard_category_id = None
challenge_history_channel_id = None

@bot.event
async def on_ready():
    global guild_id, flashcard_category_id, challenge_history_channel_id
    logger.info(f'{bot.user} has logged in!')

    for guild in bot.guilds:
        guild_id = guild.id
        logger.info(f'Connected to guild: {guild.name}')

        for category in guild.categories:
            if 'flashcard' in category.name.lower():
                flashcard_category_id = category.id
                logger.info(f'Found flashcard category: {category.name}')
                break

        for channel in guild.text_channels:
            if channel.name.lower() == 'challengehistory':
                challenge_history_channel_id = channel.id
                logger.info(f'Found challenge history channel: {channel.name}')
                break
        break

@bot.event
async def on_disconnect():
    logger.warning("Bot disconnected from Discord")

@bot.event
async def on_resumed():
    logger.info("Bot resumed connection to Discord")

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Discord error in {event}: {args}")

# ========== Core Logic ==========

async def get_flashcard_folders():
    if not guild_id or not flashcard_category_id:
        return []

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Guild {guild_id} not found")
            return []
            
        category = discord.utils.get(guild.categories, id=flashcard_category_id)
        if not category:
            logger.error(f"Category {flashcard_category_id} not found")
            return []

        folders = []
        for channel in category.text_channels:
            # Exclude 'challengehistory' by name
            if channel.name.lower() == 'challengehistory':
                continue

            flashcard_count = 0
            try:
                async for message in channel.history(limit=None):
                    if not message.reference:
                        flashcard_count += 1
            except discord.Forbidden:
                logger.error(f"No permission to read channel {channel.name}")
                continue
            except Exception as e:
                logger.error(f"Error reading channel {channel.name}: {e}")
                continue

            # Get statistics for this folder
            stats = await get_folder_statistics(str(channel.id))
            
            folders.append({
                "folder_id": str(channel.id),
                "folder_name": channel.name,
                "total_flashcards": flashcard_count,
                "total_correct": stats["total_correct"],
                "total_incorrect": stats["total_incorrect"],
                "total_challenges": stats["total_challenges"]
            })

        return folders
    except Exception as e:
        logger.error(f"Error in get_flashcard_folders: {e}")
        return []

async def get_flashcards_in_folder(folder_id: str):
    if not guild_id:
        return []

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            return []
            
        channel = guild.get_channel(int(folder_id))
        if not channel:
            return []

        flashcards = []
        messages = []
        
        try:
            messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
        except discord.Forbidden:
            logger.error(f"No permission to read channel {channel.name}")
            return []
        except Exception as e:
            logger.error(f"Error reading messages from channel {folder_id}: {e}")
            return []

        for message in messages:
            if not message.reference:
                question_content = {
                    "text": message.content or "",
                    "image_url": message.attachments[0].url if message.attachments else None
                }
                answers = []
                for reply in messages:
                    if reply.reference and reply.reference.message_id == message.id:
                        answers.append({
                            "text": reply.content or "",
                            "image_url": reply.attachments[0].url if reply.attachments else None
                        })
                flashcards.append({
                    "question_id": str(message.id),
                    "question": question_content,
                    "answers": answers
                })
        return flashcards
    except Exception as e:
        logger.error(f"Error in get_flashcards_in_folder: {e}")
        return []

async def get_challenge_history():
    if not guild_id or not challenge_history_channel_id:
        return []

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            return []
            
        channel = guild.get_channel(challenge_history_channel_id)
        if not channel:
            return []

        history_records = []
        async for message in channel.history(limit=1):
            if message.content.strip():
                lines = [line.strip() for line in message.content.strip().split('\n') if line.strip()]
                for line in lines:
                    try:
                        # Parse JSON format: {"folder_id": "123", "correct": 5, "incorrect": 2, "timestamp": "..."}
                        record = json.loads(line)
                        history_records.append(record)
                    except json.JSONDecodeError:
                        # Handle old format (just folder_id) for backward compatibility
                        if line.isdigit():
                            history_records.append({
                                "folder_id": line,
                                "correct": 0,
                                "incorrect": 0,
                                "timestamp": "unknown"
                            })
        return history_records
    except Exception as e:
        logger.error(f"Error in get_challenge_history: {e}")
        return []

async def get_folder_statistics(folder_id: str):
    """Get aggregated statistics for a specific folder"""
    try:
        history = await get_challenge_history()
        
        total_correct = 0
        total_incorrect = 0
        total_challenges = 0
        
        for record in history:
            if record.get("folder_id") == folder_id:
                total_correct += record.get("correct", 0)
                total_incorrect += record.get("incorrect", 0)
                total_challenges += 1
        
        return {
            "total_correct": total_correct,
            "total_incorrect": total_incorrect,
            "total_challenges": total_challenges
        }
    except Exception as e:
        logger.error(f"Error in get_folder_statistics: {e}")
        return {
            "total_correct": 0,
            "total_incorrect": 0,
            "total_challenges": 0
        }

async def update_challenge_history(folder_id: str, correct: int, incorrect: int):
    if not guild_id or not challenge_history_channel_id:
        return False

    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            return False
            
        channel = guild.get_channel(challenge_history_channel_id)
        if not channel:
            return False

        # Create new record
        from datetime import datetime
        new_record = {
            "folder_id": folder_id,
            "correct": correct,
            "incorrect": incorrect,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Get existing history
        current_records = []
        async for message in channel.history(limit=1):
            if message.content.strip():
                lines = [line.strip() for line in message.content.strip().split('\n') if line.strip()]
                for line in lines:
                    try:
                        record = json.loads(line)
                        current_records.append(record)
                    except json.JSONDecodeError:
                        # Handle old format for backward compatibility
                        if line.isdigit():
                            current_records.append({
                                "folder_id": line,
                                "correct": 0,
                                "incorrect": 0,
                                "timestamp": "unknown"
                            })
            break
        
        # Add new record at the beginning and limit to 50 records
        updated_records = [new_record] + current_records[:49]
        
        # Convert back to string format
        history_lines = [json.dumps(record) for record in updated_records]
        new_content = '\n'.join(history_lines)
        
        # Update or create message
        message_found = False
        async for message in channel.history(limit=1):
            await message.edit(content=new_content)
            message_found = True
            break
        
        if not message_found:
            await channel.send(new_content)
        
        return True
    except Exception as e:
        logger.error(f"Error in update_challenge_history: {e}")
        return False

# ========== FastAPI Endpoints ==========

def run_discord_coro(coro):
    try:
        future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        return future.result(timeout=30)  # Increased timeout
    except asyncio.TimeoutError:
        logger.error("Discord operation timed out")
        raise HTTPException(status_code=504, detail="Discord operation timed out")
    except Exception as e:
        logger.error(f"Error running Discord operation: {e}")
        raise HTTPException(status_code=500, detail=f"Discord operation failed: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Discord Flashcard Bot API is running", "status": "healthy"}

@app.get("/flashcard-lists")
async def get_flashcard_lists():
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        folders = run_discord_coro(get_flashcard_folders())
        return JSONResponse(content=folders)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_flashcard_lists: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/flashcard-folder/{folder_id}")
async def get_flashcard_folder(folder_id: str):
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        flashcards = run_discord_coro(get_flashcards_in_folder(folder_id))
        return JSONResponse(content=flashcards)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_flashcard_folder: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/challenge-history")
async def get_challenge_history_api():
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        history = run_discord_coro(get_challenge_history())
        return JSONResponse(content={
            "challenge_history": history,
            "total_challenges": len(history)
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_challenge_history_api: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/folder-statistics/{folder_id}")
async def get_folder_statistics_api(folder_id: str):
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        stats = run_discord_coro(get_folder_statistics(folder_id))
        return JSONResponse(content=stats)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_folder_statistics_api: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/done-challenge/{folder_id}")
async def done_challenge(folder_id: str, result: ChallengeResult):
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        
        if result.correct < 0 or result.incorrect < 0:
            raise HTTPException(status_code=400, detail="Correct and incorrect counts must be non-negative")
        
        success = run_discord_coro(update_challenge_history(folder_id, result.correct, result.incorrect))
        if success:
            return JSONResponse(content={
                "message": "Challenge history updated successfully",
                "folder_id": folder_id,
                "correct": result.correct,
                "incorrect": result.incorrect
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to update challenge history")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in done_challenge: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/health")
async def health_check():
    bot_status = "connected" if bot.is_ready() else "disconnected"
    guild_status = "connected" if guild_id else "no_guild"
    
    return {
        "status": "healthy",
        "bot_status": bot_status,
        "guild_status": guild_status,
        "guild_id": guild_id,
        "flashcard_category_id": flashcard_category_id,
        "challenge_history_channel_id": challenge_history_channel_id
    }

# ========== Startup ==========

def run_bot():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        logger.error("DISCORD_BOT_TOKEN environment variable not set!")
        return
    
    try:
        logger.info("Starting Discord bot...")
        bot.run(token, reconnect=True)
    except Exception as e:
        logger.error(f"Bot startup error: {e}")
        raise

def run_api():
    port = int(os.getenv('PORT', 7860))
    host = os.getenv('HOST', '0.0.0.0')
    
    logger.info(f"Starting FastAPI server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
        timeout_keep_alive=30,
        timeout_graceful_shutdown=30
    )

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    time.sleep(3)  # Give bot time to start
    run_api()