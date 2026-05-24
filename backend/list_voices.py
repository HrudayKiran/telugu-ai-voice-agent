import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

MURF_API_KEY = os.getenv("MURF_API_KEY")

def list_voices():
    if not MURF_API_KEY:
        print("Error: MURF_API_KEY is not set in your .env file or environment.")
        return

    url = "https://api.murf.ai/v1/speech/voices"
    headers = {
        "api-key": MURF_API_KEY
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch voices. Status Code: {response.status_code}")
            print(response.text)
            return

        voices = response.json()
        
        print("\n=== Murf.ai Voice List ===")
        print(f"Total voices found: {len(voices)}")
        print("-" * 60)
        print(f"{'Voice ID':<25} | {'Display Name':<15} | {'Locale':<10} | {'Model support':<10}")
        print("-" * 60)
        
        telugu_voices = []
        for voice in voices:
            voice_id = voice.get("voiceId", "")
            display_name = voice.get("displayName", voice.get("name", ""))
            locale = voice.get("locale", "")
            model = voice.get("model", "GEN2")
            
            # Match all Indian voices
            if "-in" in locale.lower() or "telugu" in display_name.lower() or "telugu" in voice_id.lower():
                telugu_voices.append((voice_id, display_name, locale, model))
            else:
                # Still output to console or just collect
                pass
                
        # Display Telugu voices first
        if telugu_voices:
            print("\n>>> SUGGESTED TELUGU VOICES:")
            for v_id, name, loc, mod in telugu_voices:
                print(f"{v_id:<25} | {name:<15} | {loc:<10} | {mod:<10}")
            print("-" * 60)
        else:
            print("\nNo direct Telugu (te-IN) voices found in your account's visible list.")
            print("Showing a sample of other voices in the library:")
            for voice in voices[:15]:
                v_id = voice.get("voiceId", "")
                name = voice.get("displayName", voice.get("name", ""))
                loc = voice.get("locale", "")
                mod = voice.get("model", "GEN2")
                print(f"{v_id:<25} | {name:<15} | {loc:<10} | {mod:<10}")
            print("... (truncated)")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    list_voices()
