import os
import requests
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path, override=True)

MURF_API_KEY = os.getenv("MURF_API_KEY")
MURF_VOICE_ID = os.getenv("MURF_VOICE_ID", "Navya")

print(f"API Key found: {MURF_API_KEY is not None}")
print(f"Voice ID: {MURF_VOICE_ID}")

url = "https://api.murf.ai/v1/speech/generate"
headers = {
    "Content-Type": "application/json",
    "api-key": MURF_API_KEY
}
payload = {
    "text": "నమస్కారం! నేను నవ్యను, మీ తెలుగు సహాయకురాలిని.",
    "voiceId": "hi-IN-shweta",
    "modelVersion": "GEN2",
    "style": "Conversational",
    "format": "WAV",
    "sampleRate": 24000,
    "channelType": "mono",
    "encodeAsBase64": True
}

try:
    print("Sending request to Murf.ai...")
    response = requests.post(url, json=payload, headers=headers)
    print(f"Response Status: {response.status_code}")
    print("Response Content (truncated):", response.text[:400])
except Exception as e:
    print(f"Exception: {e}")
