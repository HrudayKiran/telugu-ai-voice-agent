import argparse
import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from loguru import logger

# Load environment variables using absolute path
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.google.tts import GoogleHttpTTSService
from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import (
    Frame, TranscriptionFrame, TextFrame, TTSSpeakFrame, EndFrame,
    UserAudioRawFrame, TTSAudioRawFrame,
)

from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.transcriptions.language import Language

# Google Cloud TTS is used via GoogleHttpTTSService (imported above)

# Configure loguru logger for debugging
# Note: PYTHONIOENCODING=utf-8 is set by main.py subprocess env,
# so sys.stdout is already UTF-8. encoding= is only valid for file sinks.
logger.remove()
logger.add(
    sys.stdout, 
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:7}</level> | {message}",
)
# Also log to file with UTF-8 for persistent debugging
logger.add(
    os.path.join(os.path.dirname(__file__), "agent_debug.log"),
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
    encoding="utf-8",
    rotation="5 MB",
)

class FrameLogger(FrameProcessor):
    """
    Debug FrameProcessor to trace the flow of frames through the pipeline.
    Filters out high-frequency audio frames to keep logs readable.
    """
    def __init__(self, name: str):
        super().__init__()
        self._name = name

    async def process_frame(self, frame: Frame, direction):
        # Only log non-audio frames to avoid flooding logs
        # (UserAudioRawFrame fires 50+ times/second)
        if not isinstance(frame, (UserAudioRawFrame, TTSAudioRawFrame)):
            logger.info(f"[{self._name}] Frame: {frame.__class__.__name__}")
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

class TranscriptSender(FrameProcessor):
    """
    Custom Pipecat FrameProcessor to intercept user transcription frames
    and assistant text frames (sentences) and send them as JSON data
    messages over the LiveKit data channel to the client app.
    """
    def __init__(self, transport: LiveKitTransport):
        super().__init__()
        self._transport = transport

    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)
        
        try:
            # User speech transcription completed
            if isinstance(frame, TranscriptionFrame):
                logger.info(f"User transcribed: {frame.text}")
                payload = json.dumps({
                    "type": "user_transcript",
                    "text": frame.text
                })
                await self._transport.send_message(payload)
                
            # Bot sentence completed
            elif isinstance(frame, TextFrame):
                text = frame.text.strip()
                # Ensure we only send readable text (filter out control sequences/metadata)
                if text and not text.startswith("{") and not text.endswith("}"):
                    logger.info(f"Bot speaking: {text}")
                    payload = json.dumps({
                        "type": "bot_transcript",
                        "text": text
                    })
                    await self._transport.send_message(payload)
        except Exception as e:
            logger.error(f"Error in TranscriptSender broadcasting data: {e}")

        await self.push_frame(frame, direction)


async def main():
    parser = argparse.ArgumentParser(description="AI Telugu Voice Agent Bot")
    parser.add_argument("--url", required=True, help="LiveKit Server URL")
    parser.add_argument("--token", required=True, help="LiveKit Access Token")
    parser.add_argument("--room", required=True, help="LiveKit Room Name")
    args = parser.parse_args()

    logger.info(f"Starting agent process for room: {args.room}")

    # 1. Initialize LiveKit transport
    transport = LiveKitTransport(
        url=args.url,
        token=args.token,
        room_name=args.room,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,   # STT (Whisper) expects 16kHz
            audio_out_enabled=True,
            audio_out_sample_rate=24000,  # TTS (Murf) outputs 24kHz
        )
    )

    # 2. Initialize STT (Groq Whisper) — using the Settings class (canonical API)
    stt = GroqSTTService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqSTTService.Settings(
            model="whisper-large-v3-turbo",
            language=Language.TE  # Telugu — use the Language enum
        )
    )

    # 3. Configure LLM Prompt & Initialize Google Gemini LLM
    system_instruction = (
        "You are Navya, a friendly Telugu AI voice assistant. "
        "Always respond in Telugu language. "
        "Keep your responses very short, conversational, and natural (1 to 2 sentences max). "
        "Do not use markdown, asterisks (*), emojis, list formatting, or bullet points, as your response will be spoken aloud. "
        "Example response: నమస్కారం! నేను మీకు ఎలా సహాయపడగలను?"
    )
    
    messages = [
        {
            "role": "system",
            "content": system_instruction
        }
    ]
    context = LLMContext(messages=messages)
    
    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            temperature=0.7
        )
    )

    # 4. Initialize Google Cloud TTS Service (WaveNet Telugu voice)
    credentials_path = os.path.join(os.path.dirname(__file__), os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH", "gcloud-credentials.json"))
    tts = GoogleHttpTTSService(
        credentials_path=credentials_path,
        settings=GoogleHttpTTSService.Settings(
            voice=os.getenv("GOOGLE_TTS_VOICE", "te-IN-Chirp3-HD-Achernar"),
            language=Language.TE,
        ),
        sample_rate=24000,
    )

    # 5. Context Aggregator Pair for tracking conversation history
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)
    
    # 6. Initialize custom Transcript Sender
    transcript_sender = TranscriptSender(transport)

    # 7. Create VAD processor (Silero VAD → pushes VADUserStarted/StoppedSpeakingFrame)
    #    This is REQUIRED for SegmentedSTTService (GroqSTTService) to know when
    #    the user starts/stops speaking so it can segment audio for transcription.
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())

    # 8. Build the pipeline
    #    Flow: Input → VAD → STT → UserAgg → LLM → TranscriptSender → TTS → Output → AssistantAgg
    pipeline = Pipeline([
        transport.input(),                 # LiveKit Audio Input
        vad,                               # VAD (Silero) — MUST be before STT
        FrameLogger("Post-VAD"),
        stt,                               # STT (Groq Whisper)
        FrameLogger("Post-STT"),
        user_aggregator,                   # User Context Aggregator
        llm,                               # LLM (Groq Llama 3.3 70B)
        FrameLogger("Post-LLM"),
        transcript_sender,                 # Broadcast transcripts to client
        tts,                               # TTS (Google Cloud WaveNet)
        FrameLogger("Post-TTS"),
        transport.output(),                # LiveKit Audio Output
        assistant_aggregator               # Assistant Context Aggregator
    ])

    # 9. Setup Runner and Task
    runner = PipelineRunner()
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
        )
    )

    # 9. Event Handlers
    has_greeted = False

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant, *args, **kwargs):
        nonlocal has_greeted
        if has_greeted:
            logger.info("Greeting already sent, skipping duplicate trigger.")
            return
        has_greeted = True

        participant_id = participant.identity if hasattr(participant, 'identity') else str(participant)
        logger.info(f"User joined the room: {participant_id}")
        
        # Greet the user in Telugu
        greeting_text = "హలో! నేను నవ్యను, మీ తెలుగు సహాయకురాలిని. మీకు ఎలా సహాయపడగలను?"
        logger.info("Sending greeting TTSSpeakFrame to pipeline...")
        
        # Wait a moment for connection to stabilize
        await asyncio.sleep(1.5)
        
        # Broadcast the greeting transcript to the data channel
        try:
            payload = json.dumps({
                "type": "bot_transcript",
                "text": greeting_text
            })
            await transport.send_message(payload)
            logger.info("Greeting transcript sent to data channel")
        except Exception as e:
            logger.error(f"Failed to send greeting transcript: {e}")
            
        # Queue the greeting for TTS synthesis and playback
        await task.queue_frame(TTSSpeakFrame(text=greeting_text))
        logger.info("TTSSpeakFrame queued successfully")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, *args, **kwargs):
        participant_id = participant.identity if hasattr(participant, 'identity') else str(participant)
        logger.info(f"User left the room: {participant_id}")
        await task.queue_frame(EndFrame())

    # 10. Run the bot
    try:
        logger.info("Starting pipeline runner...")
        await runner.run(task)
    except Exception as e:
        logger.error(f"Error running pipeline: {e}", exc_info=True)
    finally:
        logger.info("Agent process completed.")

if __name__ == "__main__":
    asyncio.run(main())
