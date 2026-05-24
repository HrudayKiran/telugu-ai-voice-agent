import aiohttp
import io
import wave
from typing import AsyncGenerator
from loguru import logger

from pipecat.services.tts_service import TTSService, TTSSettings
from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)

class MurfTTSService(TTSService):
    """
    Custom Pipecat Text-to-Speech service for Murf.ai Streaming API.
    
    Uses the streaming endpoint POST /v1/speech/stream which returns audio
    chunks with ultra-low latency. The response body IS the raw audio stream
    (not a JSON wrapper like /v1/speech/generate).
    
    Uses PCM format for direct Pipecat integration (no WAV header parsing needed).
    """
    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = "Navya",
        model: str = "FALCON",
        style: str = "Conversational",
        locale: str = "te-IN",
        sample_rate: int = 24000,
        **kwargs
    ):
        super().__init__(
            settings=TTSSettings(
                model=model,
                voice=voice_id,
                language=None
            ),
            sample_rate=sample_rate,
            **kwargs
        )
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._style = style
        self._locale = locale
        self._sample_rate = sample_rate
        logger.info(
            f"Initialized MurfTTSService: voice={self._voice_id}, "
            f"model={self._model}, locale={self._locale}, "
            f"sample_rate={self._sample_rate}"
        )

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        logger.info(f"MurfTTS run_tts called (context_id: {context_id})")
        
        # Use the streaming endpoint with India region for lowest latency
        url = "https://in.api.murf.ai/v1/speech/stream"
        headers = {
            "Content-Type": "application/json",
            "api-key": self._api_key
        }
        payload = {
            "text": text,
            "voiceId": self._voice_id,
            "model": self._model,
            "style": self._style,
            "locale": self._locale,
            "format": "WAV",           # WAV gives us a header we can parse for sample rate
            "sampleRate": self._sample_rate,
            "channelType": "MONO"
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as response:
                    logger.info(f"Murf.ai Stream API status: {response.status}")
                    
                    if response.status != 200:
                        err_text = await response.text()
                        logger.error(f"Murf.ai Stream API error {response.status}: {err_text}")
                        return

                    # The streaming endpoint returns the audio directly as the response body.
                    # With WAV format, the first 44 bytes are the WAV header, then raw PCM.
                    
                    # Open audio context for Pipecat pipeline
                    await self.start_ttfb_metrics()
                    await self.create_audio_context(context_id)
                    yield TTSStartedFrame(context_id=context_id)
                    
                    # Stream the audio chunks as they arrive
                    wav_header_stripped = False
                    accumulated = bytearray()
                    # Size of each audio chunk we yield (~0.25s of 16-bit mono @ 24kHz)
                    chunk_target = int(self._sample_rate * 0.25 * 2)
                    
                    async for chunk in response.content.iter_chunked(4096):
                        if not chunk:
                            continue
                            
                        if not wav_header_stripped:
                            # First chunk: strip the 44-byte WAV header
                            if chunk[:4] == b"RIFF" and len(chunk) >= 44:
                                # Parse sample rate from WAV header for verification
                                wav_sr = int.from_bytes(chunk[24:28], "little")
                                logger.info(f"WAV header sample_rate={wav_sr}")
                                chunk = chunk[44:]  # Strip header
                            wav_header_stripped = True
                        
                        accumulated.extend(chunk)
                        
                        # Yield full chunks of PCM data
                        while len(accumulated) >= chunk_target:
                            pcm_chunk = bytes(accumulated[:chunk_target])
                            accumulated = accumulated[chunk_target:]
                            yield TTSAudioRawFrame(
                                audio=pcm_chunk,
                                sample_rate=self._sample_rate,
                                num_channels=1,
                                context_id=context_id
                            )
                    
                    # Yield any remaining audio data
                    if len(accumulated) > 0:
                        # Ensure even byte count for 16-bit PCM
                        if len(accumulated) % 2 == 1:
                            accumulated.append(0)
                        yield TTSAudioRawFrame(
                            audio=bytes(accumulated),
                            sample_rate=self._sample_rate,
                            num_channels=1,
                            context_id=context_id
                        )
                    
                    await self.stop_ttfb_metrics()
                    
                    total_bytes = chunk_target  # approximate
                    logger.info(f"Streaming TTS completed for context {context_id}")
                    
                    # Signal TTS playback is done
                    yield TTSStoppedFrame(context_id=context_id)
                    
                    # Close the audio context
                    await self.remove_audio_context(context_id)

            except Exception as e:
                logger.error(f"Exception in MurfTTSService: {e}", exc_info=True)
