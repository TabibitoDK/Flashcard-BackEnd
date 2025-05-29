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
    print(f'{bot.user} has logged in!')

    for guild in bot.guilds:
        guild_id = guild.id
        print(f'Connected to guild: {guild.name}')

        for category in guild.categories:
            if 'flashcard' in category.name.lower():
                flashcard_category_id = category.id
                print(f'Found flashcard category: {category.name}')
                break

        for channel in guild.text_channels:
            if channel.name.lower() == 'challengehistory':
                challenge_history_channel_id = channel.id
                print(f'Found challenge history channel: {channel.name}')
                break
        break

# ========== Core Logic ==========

async def get_flashcard_folders():
    if not guild_id or not flashcard_category_id:
        return []

    guild = bot.get_guild(guild_id)
    category = discord.utils.get(guild.categories, id=flashcard_category_id)

    folders = []
    for channel in category.text_channels:
        # Exclude 'challengehistory' by name
        if channel.name.lower() == 'challengehistory':
            continue

        flashcard_count = 0
        async for message in channel.history(limit=None):
            if not message.reference:
                flashcard_count += 1

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

async def get_flashcards_in_folder(folder_id: str):
    if not guild_id:
        return []

    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(int(folder_id))

    flashcards = []
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]

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

async def get_challenge_history():
    if not guild_id or not challenge_history_channel_id:
        return []

    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(challenge_history_channel_id)

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

async def get_folder_statistics(folder_id: str):
    """Get aggregated statistics for a specific folder"""
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

async def update_challenge_history(folder_id: str, correct: int, incorrect: int):
    if not guild_id or not challenge_history_channel_id:
        return False

    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(challenge_history_channel_id)

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

# ========== FastAPI Endpoints ==========

def run_discord_coro(coro):
    future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return future.result(timeout=15)

@app.get("/")
async def root():
    return {"message": "Discord Flashcard Bot API is running"}

@app.get("/flashcard-lists")
async def get_flashcard_lists():
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        folders = run_discord_coro(get_flashcard_folders())
        return JSONResponse(content=folders)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/flashcard-folder/{folder_id}")
async def get_flashcard_folder(folder_id: str):
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        flashcards = run_discord_coro(get_flashcards_in_folder(folder_id))
        return JSONResponse(content=flashcards)
    except Exception as e:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/folder-statistics/{folder_id}")
async def get_folder_statistics_api(folder_id: str):
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet.")
        stats = run_discord_coro(get_folder_statistics(folder_id))
        return JSONResponse(content=stats)
    except Exception as e:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_status": "connected" if bot.is_ready() else "disconnected"
    }

# ========== Startup ==========

def run_bot():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("DISCORD_BOT_TOKEN environment variable not set!")
        return
    bot.run(token)

def run_api():
    port = int(os.getenv('PORT', 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    run_api()