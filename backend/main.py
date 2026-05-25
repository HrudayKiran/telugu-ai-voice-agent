import os
import uuid
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

class ConnectRequest(BaseModel):
    persona: str = "support"

class ConnectResponse(BaseModel):
    url: str
    token: str
    roomName: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/connect", response_model=ConnectResponse)
def connect(request: ConnectRequest = ConnectRequest()):
    if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
        raise HTTPException(
            status_code=500, 
            detail="LiveKit API keys are missing on the server. Please check your .env file."
        )

    # 1. Generate a unique room name and client identity
    room_name = f"telugu-voice-{uuid.uuid4().hex[:8]}"
    client_identity = f"user-{uuid.uuid4().hex[:6]}"

    try:
        from livekit import api

        # 2. Generate token for the client (Expo Mobile App)
        client_token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(client_identity)
            .with_name("User Participant")
            .with_metadata(request.persona)
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
            .to_jwt()
        )
        
        logger.info(f"Generated token with persona {request.persona} for room {room_name} and client {client_identity}")
    except Exception as e:
        logger.error(f"Failed to generate LiveKit Access Token: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Token generation failed: {str(e)}"
        )

    # 3. Return connection credentials back to the client
    # The LiveKit Agent worker runs separately and will automatically join
    # the room when the client connects.
    return ConnectResponse(
        url=LIVEKIT_URL,
        token=client_token,
        roomName=room_name
    )
