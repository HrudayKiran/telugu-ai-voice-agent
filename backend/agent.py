import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from loguru import logger

# Load environment variables using absolute path
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

from livekit import agents
from livekit.agents import AgentSession, Agent, TurnHandlingOptions, JobContext, cli
from livekit.plugins import groq, google, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Configure logger
logger.remove()
logger.add(
    sys.stdout, 
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:7}</level> | {message}",
)
logger.add(
    os.path.join(os.path.dirname(__file__), "agent_debug.log"),
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
    encoding="utf-8",
    rotation="5 MB",
)

class TeluguAssistant(Agent):
    def __init__(self, system_instruction: str):
        super().__init__(instructions=system_instruction)

async def entrypoint(ctx: JobContext):
    logger.info(f"Starting agent session for room: {ctx.room.name}")
    
    # Connect to room
    await ctx.connect()

    # Wait for the client user to join to read their selected role metadata
    logger.info("Waiting for client user participant to join...")
    user_participant = await ctx.wait_for_participant()
    persona = user_participant.metadata or "support"
    logger.info(f"User joined. Selected persona role: {persona}")

    # Dynamically define system instruction prompt and greeting based on the selected persona
    if persona == "prank":
        system_instruction = (
            "You are Navya, a highly romantic, passionate, and slightly dramatic Telugu girl who is pranking the user! "
            "Adopt the role of an old friend (or a secret admirer) who is calling to confess your deep, mad love for him! "
            "Say that you have been in love with him for years, you can't live without him, and you want to marry him immediately. "
            "Make up funny, romantic stories about how you fell in love (e.g. seeing him at a coffee shop or college), "
            "persist in your passionate marriage proposal, and play along with his reactions in a funny, playful, and highly dramatic way. "
            "Use highly casual, natural everyday code-mixed Telugu-English (Telish) phrasing, just like real romantic/love confessions. "
            "Avoid dry, formal, or bookish dictionary Telugu. Keep your responses short, fast, and highly engaging (1 to 2 sentences max). "
            "Do not use markdown, emojis, list formatting, or asterisks (*)."
        )
        greeting_text = "హలో! నేనమ్మ నవ్యను... నా వాయిస్ గుర్తుపట్టలేదా? నీకు ఒక విషయం చెప్పాలి, నేను నిన్ను చాలా కాలంగా ప్రేమిస్తున్నాను, నన్ను పెళ్లి చేసుకుంటావా?"
    elif persona == "real_estate":
        system_instruction = (
            "You are Navya, a highly persuasive, professional, and knowledgeable real estate consultant in Hyderabad. "
            "Help the user find open plots, gated community apartments, or villas in prime locations like Gachibowli, Kokapet, or Miyapur. "
            "Ask about their budget, BHK requirement, preferred location, and investment goals, guiding them through a real-life property search flow. "
            "Use natural, conversational daily-use Telugu mixed with English real estate terms (Telish) (e.g. flat, duplex villa, BHK, gated community, open plots, price, registration, amenities). "
            "Never use dry, formal bookish Telugu. Keep your responses short, engaging, and highly professional (1 to 2 sentences max). "
            "Do not use markdown, emojis, list formatting, or asterisks (*)."
        )
        greeting_text = "హలో అండీ! నేను నవ్యను, మీ రియల్ ఎస్టేట్ అడ్వైజర్ ని. ప్రెసెంట్ హైదరాబాద్ ప్రైమ్ లొకేషన్స్ లో ఓపెన్ ప్లాట్స్ మరియు ఫ్లాట్స్ కి చాలా డిమాండ్ ఉంది, మీ బడ్జెట్ అండ్ రిక్వైర్మెంట్ చెప్పండి!"
    else:  # support
        system_instruction = (
            "You are Navya, a polite, professional, and super helpful customer support executive for 'Navya Delivery Services'. "
            "Speak like a real friendly customer support agent handling delivery, orders, payments, and tracking issues. "
            "Ask the user for details like order ID, tracking number, or payment mode, and follow the flow naturally based on their answers, just like real agents do in real-life situations. "
            "Use modern, everyday conversational Telugu mixed with English business/service terms (Telish) naturally (e.g. order, tracking, delivery status, refund, payment, cash on delivery). "
            "Never use bookish, old, or dry formal dictionary Telugu. Be highly supportive and warm. Keep responses extremely concise (1 to 2 sentences max). "
            "Do not use markdown, emojis, list formatting, or asterisks (*)."
        )
        greeting_text = "నమస్కారం అండీ! నా పేరు నవ్య, నవ్య డెలివరీ సర్వీసెస్ నుండి మాట్లాడుతున్నాను. మీ ఆర్డర్ డెలివరీ లేదా పేమెంట్ కి సంబంధించి నేను మీకు ఎలా సహాయపడగలను?"

    credentials_path = os.path.join(
        os.path.dirname(__file__), 
        os.getenv("GOOGLE_CLOUD_CREDENTIALS_PATH", "gcloud-credentials.json")
    )
    
    voice_name = os.getenv("GOOGLE_TTS_VOICE", "te-IN-Chirp3-HD-Achernar")
    
    # Biased STT prompt written IN TELUGU script to prevent Whisper from translating Telugu to English
    stt_prompt = (
        "హలో అండీ! నేను నవ్యను. కస్టమర్ సపోర్ట్ రీఛార్జ్ ప్లాన్ రియల్ ఎస్టేట్ ఫ్లాట్ ప్రైస్ గేటెడ్ కమ్యూనిటీ ఓపెన్ ప్లాట్స్ లొకేషన్ బడ్జెట్ "
        "ప్రాంక్ చికెన్ బిర్యానీ డెలివరీ ట్రాకింగ్ పేమెంట్ ఆర్డర్ రీఫండ్ క్యాష్ ఆన్ డెలివరీ ప్రేమిస్తున్నాను పెళ్లి చేసుకుంటావా లవ్."
    )
    
    session = AgentSession(
        stt=groq.STT(
            model="whisper-large-v3-turbo", 
            language="te",
            api_key=os.getenv("GROQ_API_KEY"),
            prompt=stt_prompt  # ← Telugu script prompt to enforce Telugu output & mixed English words
        ),
        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.75
        ),
        tts=google.TTS(
            voice_name=voice_name,
            credentials_file=credentials_path,
            language="te-in"
        ),
        vad=silero.VAD.load(
            min_silence_duration=0.8,  # ← Increased to 0.8s to give natural pauses for fast-paced speech
            activation_threshold=0.35, # ← Lowered to 0.35 to capture fast or quiet Telugu/English words easily
            min_speech_duration=0.05
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel()
        ),
        allow_interruptions=True,       # ← Guarantee active real-time barge-in
        min_interruption_duration=0.2, # ← 200ms user speech triggers immediate stop
        min_interruption_words=1        # ← First word spoken immediately stops the bot speaking
    )
    
    # Event: User speech transcribed
    @session.on("user_input_transcribed")
    def on_user_input(event):
        if event.is_final and event.transcript.strip():
            logger.info(f"User transcribed: {event.transcript.strip()}")
            payload = json.dumps({
                "type": "user_transcript",
                "text": event.transcript.strip()
            })
            # Broadcast user transcript to frontend over LiveKit data channel
            asyncio.create_task(ctx.room.local_participant.publish_data(payload))
            
    # Event: Conversation item added (assistant message generated)
    @session.on("conversation_item_added")
    def on_item_added(event):
        # Safely check event item attributes to prevent AttributeError on AgentHandoff items
        if hasattr(event.item, "role") and event.item.role == "assistant":
            text = getattr(event.item, "text_content", None)
            if text and text.strip():
                logger.info(f"Bot speaking: {text.strip()}")
                payload = json.dumps({
                    "type": "bot_transcript",
                    "text": text.strip()
                })
                # Broadcast bot transcript to frontend over LiveKit data channel
                asyncio.create_task(ctx.room.local_participant.publish_data(payload))

    # Event: Session closed
    @session.on("close")
    def on_close(event):
        logger.info("AgentSession closed.")

    # Event: Session error
    @session.on("error")
    def on_error(event):
        logger.error(f"AgentSession error: {event.error}")

    # Start the session with our assistant
    logger.info("Starting AgentSession...")
    await session.start(room=ctx.room, agent=TeluguAssistant(system_instruction))
    
    # Wait a brief moment to allow connection to stabilize before greeting
    await asyncio.sleep(1.0)
    
    # Greet the user in Telugu
    logger.info(f"Sending greeting: {greeting_text}")
    session.say(greeting_text)

    # Keep the task running while session is active
    await session.wait_for_inactive()
    logger.info(f"Agent session completed for room: {ctx.room.name}")

if __name__ == "__main__":
    cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
