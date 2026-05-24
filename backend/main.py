import os
import sys
import uuid
import subprocess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env
load_dotenv(override=True)

app = FastAPI(title="AI Telugu Voice Agent Backend")

# Enable CORS for React Native development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Grab LiveKit config from environment
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Validate credentials are set
if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    logger.warning("LiveKit API credentials are not fully set in .env. /connect will fail until configured.")

class ConnectResponse(BaseModel):
    url: str
    token: str
    roomName: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/connect", response_model=ConnectResponse)
def connect():
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        raise HTTPException(
            status_code=500, 
            detail="LiveKit API keys are missing on the server. Please check your .env file."
        )

    # 1. Generate a unique room name
    room_name = f"telugu-voice-{uuid.uuid4().hex[:8]}"
    client_identity = f"user-{uuid.uuid4().hex[:6]}"
    agent_identity = f"agent-bot-{room_name}"

    try:
        from livekit import api

        # 2. Generate token for the client (Expo Mobile App)
        client_token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(client_identity)
            .with_name("User Participant")
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
            .to_jwt()
        )

        # 3. Generate token for the agent (Pipecat Bot)
        agent_token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(agent_identity)
            .with_name("Telugu Voice Agent")
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
            .to_jwt()
        )
    except Exception as e:
        logger.error(f"Failed to generate LiveKit Access Tokens: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Token generation failed: {str(e)}"
        )

    # 4. Launch Pipecat agent script in a background process
    agent_script = os.path.join(os.path.dirname(__file__), "agent.py")
    
    # We pass the current process environment copy to the subprocess
    # so that the agent has access to all API keys (Groq, OpenRouter, Murf)
    env = os.environ.copy()
    # Force UTF-8 encoding for the subprocess to handle Telugu text properly
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        log_path = os.path.join(os.path.dirname(__file__), "agent.log")
        log_file = open(log_path, "a", encoding="utf-8")
        # Popen runs the process in the background without blocking the HTTP request
        subprocess.Popen(
            [
                sys.executable,
                agent_script,
                "--url", LIVEKIT_URL,
                "--token", agent_token,
                "--room", room_name
            ],
            env=env,
            stdout=log_file,
            stderr=log_file
        )
        logger.info(f"Successfully spawned agent background process for room {room_name} (logging to {log_path})")
    except Exception as e:
        logger.error(f"Failed to spawn agent background process: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to spawn conversation agent: {str(e)}"
        )

    # 5. Return connection credentials back to the client
    return ConnectResponse(
        url=LIVEKIT_URL,
        token=client_token,
        roomName=room_name
    )
