import base64
import binascii
import io
import json
import ssl
import urllib.error
import urllib.request

import certifi
from django.conf import settings
from gtts import gTTS


class PlantAnalysisError(Exception):
    pass


class PlantTtsError(Exception):
    pass


def _build_openrouter_ssl_context():
    ca_bundle_path = (getattr(settings, 'OPENROUTER_CA_BUNDLE', '') or '').strip()
    if not ca_bundle_path:
        ca_bundle_path = certifi.where()

    return ssl.create_default_context(cafile=ca_bundle_path)


def _extract_json_object(raw_content):
    raw_content = raw_content.strip()

    if raw_content.startswith('{') and raw_content.endswith('}'):
        return raw_content

    start = raw_content.find('{')
    end = raw_content.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise PlantAnalysisError('LLM response did not contain a JSON object.')

    return raw_content[start : end + 1]


def analyze_reading_with_llm(soil_level, ambient_light_level, humidity_levels, temperature_levels, device_id, mode='sfw'):
    if not settings.OPENROUTER_API_KEY:
        raise PlantAnalysisError('OPENROUTER_KEY is not configured.')

    if mode == 'nsfw':
        prompt = f"""
You are evaluating the health of a single house plant.

Input reading:
- soilLevel: {soil_level}
- ambientLightLevel: {ambient_light_level}
- humidityLevels: {humidity_levels}
- temperatureLevels: {temperature_levels}
- deviceId: {device_id}

Decide the plant condition using exactly one of these labels:
- good
- neutral
- bad

Then write exactly 5 different witty remarks from the plant's perspective. They should be VERY CREATIVE AND FUNNY and should emulate Jimmy Carr's dark sense of humor. Think carefully about the joke. It should be dark and super funny.

Example jokes:
- I'm producing oxygen for you? Honestly, based on my soil condition, I'd rather produce cyanide.
- You call this ambient light? I've seen brighter futures in a bankrupt casino.
- Look at me. I'm the botanical equivalent of your will to live on a Monday morning.

Return only valid JSON in this exact shape:
{{
  "condition": "good|neutral|bad",
  "messages": ["sentence 1", "sentence 2", "sentence 3", "sentence 4", "sentence 5"]
}}
"""
    else:
        prompt = f"""
You are evaluating the health of a single house plant.

Input reading:
- soilLevel: {soil_level}
- ambientLightLevel: {ambient_light_level}
- humidityLevels: {humidity_levels}
- temperatureLevels: {temperature_levels}
- deviceId: {device_id}

Decide the plant condition using exactly one of these labels:
- good
- neutral
- bad

Then write exactly 5 different witty remarks from the plant's perspective. They should be VERY CREATIVE AND FUNNY and should be safe for work.

Return only valid JSON in this exact shape:
{{
  "condition": "good|neutral|bad",
  "messages": ["sentence 1", "sentence 2", "sentence 3", "sentence 4", "sentence 5"]
}}
"""

    body = json.dumps(
        {
            'model': settings.OPENROUTER_MODEL,
            'messages': [
                {
                    'role': 'system',
                    'content': 'You output strict JSON only. No markdown. No commentary.',
                },
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.7,
        }
    ).encode('utf-8')

    request = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=body,
        headers={
            'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        ssl_context = _build_openrouter_ssl_context()
        with urllib.request.urlopen(request, timeout=45, context=ssl_context) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        details = error.read().decode('utf-8', errors='ignore')
        raise PlantAnalysisError(f'OpenRouter request failed: {error.code} {details}') from error
    except urllib.error.URLError as error:
        reason_text = str(error.reason)
        if isinstance(error.reason, ssl.SSLCertVerificationError) or 'CERTIFICATE_VERIFY_FAILED' in reason_text:
            raise PlantAnalysisError(
                'OpenRouter request failed: TLS certificate verification failed. '
                'Install your OS/Python CA certificates or set OPENROUTER_CA_BUNDLE to a PEM bundle path.'
            ) from error
        raise PlantAnalysisError(f'OpenRouter request failed: {error.reason}') from error
    except OSError as error:
        raise PlantAnalysisError(f'OpenRouter SSL setup failed: {error}') from error

    try:
        content = payload['choices'][0]['message']['content']
        analysis = json.loads(_extract_json_object(content))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise PlantAnalysisError('Failed to parse LLM response.') from error

    condition = analysis.get('condition')
    messages = analysis.get('messages')
    valid_conditions = {'good', 'neutral', 'bad'}

    if condition not in valid_conditions:
        raise PlantAnalysisError('LLM returned an invalid condition.')

    if not isinstance(messages, list) or len(messages) != 5:
        raise PlantAnalysisError('LLM did not return exactly 5 messages.')

    cleaned_messages = []
    for message in messages:
        cleaned_message = str(message).strip()
        if not cleaned_message:
            raise PlantAnalysisError('LLM returned an empty message.')
        cleaned_messages.append(cleaned_message)

    return {
        'condition': condition,
        'messages': cleaned_messages,
    }


def _synthesize_with_gtts(text):
    audio_buffer = io.BytesIO()
    try:
        tts = gTTS(text=text, lang=settings.PLANT_TTS_LANGUAGE)
        tts.write_to_fp(audio_buffer)
        return audio_buffer.getvalue()
    except Exception as error:
        raise PlantTtsError(f'gTTS generation failed: {error}') from error


def _synthesize_with_google_tts(text):
    voice = getattr(settings, 'GOOGLE_TTS_VOICE', 'en-US-Journey-F')
    language_code = '-'.join(voice.split('-')[:2]) if '-' in voice else 'en-US'
    url = f'https://texttospeech.googleapis.com/v1/text:synthesize?key={settings.GOOGLE_API_KEY}'

    request = urllib.request.Request(
        url,
        data=json.dumps(
            {
                'input': {'text': text},
                'voice': {'languageCode': language_code, 'name': voice},
                'audioConfig': {'audioEncoding': 'MP3'},
            }
        ).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        ssl_context = _build_openrouter_ssl_context()
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        details = error.read().decode('utf-8', errors='ignore')
        raise PlantTtsError(f'Google TTS request failed: {error.code} {details}') from error
    except urllib.error.URLError as error:
        raise PlantTtsError(f'Google TTS request failed: {error.reason}') from error
    except OSError as error:
        raise PlantTtsError(f'Google TTS SSL setup failed: {error}') from error
    except json.JSONDecodeError as error:
        raise PlantTtsError('Google TTS response was not valid JSON.') from error

    try:
        return base64.b64decode(payload['audioContent'])
    except (KeyError, TypeError, binascii.Error) as error:
        raise PlantTtsError('Google TTS response did not include valid audio data.') from error


def synthesize_speech_mp3(text):
    clean_text = str(text or '').strip()
    if not clean_text:
        raise PlantTtsError('TTS text is empty.')

    if not settings.GOOGLE_API_KEY:
        return _synthesize_with_gtts(clean_text)

    try:
        return _synthesize_with_google_tts(clean_text)
    except PlantTtsError as google_error:
        # Keep the endpoint resilient if Google TTS is rate-limited or temporarily unavailable.
        try:
            return _synthesize_with_gtts(clean_text)
        except PlantTtsError as gtts_error:
            raise PlantTtsError(
                f'Google TTS failed: {google_error}. gTTS fallback failed: {gtts_error}.'
            ) from gtts_error
