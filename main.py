import discord
from discord.ext import commands
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import asyncio
import threading
import uvicorn
import os
from typing import List, Dict, Optional
import json
import re

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

# FastAPI Setup
app = FastAPI(title="Discord Flashcard Bot API")

# Global variables
guild_id = None
flashcard_category_id = None
challenge_history_channel_id = None

@bot.event
async def on_ready():
    global guild_id, flashcard_category_id, challenge_history_channel_id
    print(f'{bot.user} has logged in!')
    
    # Find the guild and flashcard category
    for guild in bot.guilds:
        guild_id = guild.id
        print(f'Connected to guild: {guild.name}')
        
        # Look for flashcard category
        for category in guild.categories:
            if 'flashcard' in category.name.lower():
                flashcard_category_id = category.id
                print(f'Found flashcard category: {category.name}')
                break
        
        # Look for challenge history channel
        for channel in guild.text_channels:
            if channel.name.lower() == 'challengehistory':
                challenge_history_channel_id = channel.id
                print(f'Found challenge history channel: {channel.name}')
                break
        
        break

async def get_flashcard_folders():
    """Get all flashcard folders (channels in flashcard category)"""
    if not guild_id:
        print("Error: guild_id is None")
        return []
    if not flashcard_category_id:
        print("Error: flashcard_category_id is None")
        return []

    guild = bot.get_guild(guild_id)
    if not guild:
        print("Error: Guild not found with id", guild_id)
        return []

    category = discord.utils.get(guild.categories, id=flashcard_category_id)
    if not category:
        print("Error: Flashcard category not found with id", flashcard_category_id)
        return []
    
    folders = []
    for channel in category.text_channels:
        # Count flashcards (messages without replies)
        flashcard_count = 0
        async for message in channel.history(limit=None):
            if not message.reference:  # Not a reply
                flashcard_count += 1
        
        folders.append({
            "folder_id": str(channel.id),
            "folder_name": channel.name,
            "total_flashcards": flashcard_count
        })
    
    return folders

async def get_flashcards_in_folder(folder_id: str):
    """Get all flashcards from a specific folder"""
    if not guild_id:
        return []
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return []
    
    channel = guild.get_channel(int(folder_id))
    if not channel:
        return []
    
    flashcards = []
    
    # Get all messages and organize them
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        messages.append(message)
    
    # Find questions (messages without replies) and their answers
    for message in messages:
        if not message.reference:  # This is a question
            question_content = {
                "text": message.content if message.content else "",
                "image_url": message.attachments[0].url if message.attachments else None
            }
            
            # Find all replies to this question
            answers = []
            for reply in messages:
                if reply.reference and reply.reference.message_id == message.id:
                    answer_content = {
                        "text": reply.content if reply.content else "",
                        "image_url": reply.attachments[0].url if reply.attachments else None
                    }
                    answers.append(answer_content)
            
            flashcards.append({
                "question_id": str(message.id),
                "question": question_content,
                "answers": answers
            })
    
    return flashcards

async def get_challenge_history():
    """Get the challenge history list"""
    if not guild_id or not challenge_history_channel_id:
        return []
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return []
    
    channel = guild.get_channel(challenge_history_channel_id)
    if not channel:
        return []
    
    # Get the current history
    history_message = None
    async for message in channel.history(limit=1):
        history_message = message
        break
    
    if history_message and history_message.content.strip():
        # Parse current history
        history_list = history_message.content.strip().split('\n')
        # Filter out empty strings and return as list of folder IDs
        return [folder_id.strip() for folder_id in history_list if folder_id.strip()]
    
    return []

async def update_challenge_history(folder_id: str):
    """Update challenge history with new completed challenge"""
    if not guild_id or not challenge_history_channel_id:
        return False
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return False
    
    channel = guild.get_channel(challenge_history_channel_id)
    if not channel:
        return False
    
    # Get the current history
    history_message = None
    async for message in channel.history(limit=1):
        history_message = message
        break
    
    if history_message:
        # Parse current history
        current_history = history_message.content.strip().split('\n') if history_message.content.strip() else []
        # Add new challenge to the front
        new_history = [folder_id] + [h for h in current_history if h.strip()]
        # Keep only last 10 entries
        new_history = new_history[:10]
        
        # Update the message
        await history_message.edit(content='\n'.join(new_history))
    else:
        # Create new history message
        await channel.send(folder_id)
    
    return True

# REST API Endpoints
@app.get("/")
async def root():
    return {"message": "Discord Flashcard Bot API is running"}

@app.get("/flashcard-lists")
async def get_flashcard_lists():
    """Get list of all flashcard folders"""
    try:
        if not bot.is_ready():
            raise HTTPException(status_code=503, detail="Bot is not ready yet. Please try again in a few seconds.")
        folders = await get_flashcard_folders()
        return JSONResponse(content=folders)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/flashcard-folder/{folder_id}")
async def get_flashcard_folder(folder_id: str):
    """Get all flashcards from a specific folder"""
    try:
        flashcards = await get_flashcards_in_folder(folder_id)
        return JSONResponse(content=flashcards)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/challenge-history")
async def get_challenge_history_api():
    """Get the list of completed challenges in order (most recent first)"""
    try:
        history = await get_challenge_history()
        return JSONResponse(content={
            "challenge_history": history,
            "total_challenges": len(history)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/done-challenge/{folder_id}")
async def done_challenge(folder_id: str):
    """Mark a challenge as completed"""
    try:
        success = await update_challenge_history(folder_id)
        if success:
            return JSONResponse(content={"message": "Challenge history updated successfully"})
        else:
            raise HTTPException(status_code=500, detail="Failed to update challenge history")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    bot_status = "connected" if bot.is_ready() else "disconnected"
    return {"status": "healthy", "bot_status": bot_status}

def run_bot():
    """Run the Discord bot"""
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("DISCORD_BOT_TOKEN environment variable not set!")
        return
    bot.run(token)

def run_api():
    """Run the FastAPI server"""
    port = int(os.getenv('PORT', 7860))  # Hugging Face Spaces uses port 7860
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Start Discord bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start FastAPI server
    run_api()
