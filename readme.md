# Discord Flashcard Bot API

A Discord bot that provides REST API endpoints for managing flashcards stored in Discord channels.

## Features

- **Flashcard Management**: Organize flashcards in Discord channels within a "flashcard" category
- **REST API**: Access flashcards through HTTP endpoints
- **Challenge Tracking**: Track completed challenges in a dedicated channel

## Setup Instructions

### Discord Setup

1. **Create a Discord Bot**:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and bot
   - Copy the bot token
   - Enable the following bot permissions:
     - Read Messages/View Channels
     - Send Messages
     - Read Message History
     - Manage Messages

2. **Server Setup**:
   - Create a category named "flashcard" (or similar)
   - Create channels within this category for different subjects (e.g., "math", "physics")
   - Create a channel named "challengehistory" for tracking completed challenges
   - Add flashcards as messages (questions) with replies as answers

### Environment Variables

Set the following environment variable:
- `DISCORD_BOT_TOKEN`: Your Discord bot token

### Deployment on Hugging Face Spaces

1. Create a new Space on Hugging Face
2. Choose "Docker" as the SDK
3. Upload all the files from this project
4. Set the `DISCORD_BOT_TOKEN` as a secret in your Space settings
5. Your API will be available at `https://[your-space-name].hf.space`

## API Endpoints

### GET `/flashcard-lists`
Returns a list of all flashcard folders with their IDs, names, and total flashcard counts.

**Response:**
```json
[
  {
    "folder_id": "123456789",
    "folder_name": "math",
    "total_flashcards": 15
  }
]
```

### GET `/flashcard-folder/{folder_id}`
Returns all flashcards from a specific folder.

**Response:**
```json
[
  {
    "question_id": "987654321",
    "question": {
      "text": "What is 2+2?",
      "image_url": null
    },
    "answers": [
      {
        "text": "4",
        "image_url": null
      }
    ]
  }
]
```

### GET `/challenge-history`
Returns the list of completed challenges in order (most recent first).

**Response:**
```json
{
  "challenge_history": ["3", "0", "1"],
  "total_challenges": 3
}
```

### POST `/done-challenge/{folder_id}`
Marks a challenge as completed and updates the challenge history.

**Response:**
```json
{
  "message": "Challenge history updated successfully"
}
```

### GET `/health`
Health check endpoint to verify bot and API status.

**Response:**
```json
{
  "status": "healthy",
  "bot_status": "connected"
}
```

## Discord Structure

```
Server
├── Category: "flashcard"
│   ├── Channel: "math" (math flashcards)
│   ├── Channel: "physics" (physics flashcards)
│   └── ... (other subject channels)
└── Channel: "challengehistory" (completed challenges)
```

### Flashcard Format
- **Question**: A message without a reply (can contain text and/or images)
- **Answer**: A reply to the question message (can contain text and/or images)

### Challenge History Format
The challenge history channel contains a single message with completed challenge IDs:
```
3
0
1
```
This indicates challenge 3 was completed most recently, then 0, then 1.

## Local Development

1. Install dependencies: `pip install -r requirements.txt`
2. Set environment variable: `export DISCORD_BOT_TOKEN=your_token_here`
3. Run: `python main.py`
4. API will be available at `http://localhost:7860`
