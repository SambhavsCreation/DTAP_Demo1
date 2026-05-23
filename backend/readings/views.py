import json
import random

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import PlantReading, AppMode
from .services import (
    PlantTtsError,
    enqueue_reading_analysis,
    schedule_pending_analyses,
    synthesize_speech_mp3,
)


SOIL_LEVEL_MIN = 0
SOIL_LEVEL_MAX = 4095


def _serialize_reading(reading):
    return {
        'id': reading.id,
        'soilLevel': reading.soil_level,
        'ambientLightLevel': reading.ambient_light_level,
        'humidityLevels': reading.humidity_levels,
        'temperatureLevels': reading.temperature_levels,
        'deviceId': reading.device_id,
        'analysisStatus': reading.analysis_status,
        'analysisMode': reading.analysis_mode,
        'analysisError': reading.analysis_error,
        'analysisStartedAt': reading.analysis_started_at.isoformat() if reading.analysis_started_at else None,
        'analysisCompletedAt': reading.analysis_completed_at.isoformat() if reading.analysis_completed_at else None,
        'condition': reading.condition,
        'plantMessages': reading.plant_messages,
        'recordedAt': reading.recorded_at.isoformat(),
    }


def _validate_payload(payload):
    required_fields = ['soilLevel', 'ambientLightLevel', 'humidityLevels', 'temperatureLevels', 'deviceId']
    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        return None, f"Missing required fields: {', '.join(missing_fields)}"

    try:
        soil_level = int(payload['soilLevel'])
        ambient_light_level = int(payload['ambientLightLevel'])
        humidity_levels = float(payload['humidityLevels'])
        temperature_levels = float(payload['temperatureLevels'])
        device_id = str(payload['deviceId'])
    except (TypeError, ValueError):
        return None, 'soilLevel and ambientLightLevel must be integers. humidityLevels and temperatureLevels must be numbers.'

    if not SOIL_LEVEL_MIN <= soil_level <= SOIL_LEVEL_MAX:
        return None, f'soilLevel must be between {SOIL_LEVEL_MIN} and {SOIL_LEVEL_MAX}.'

    if ambient_light_level < 0:
        return None, 'ambientLightLevel must be zero or greater.'

    return {
        'soil_level': soil_level,
        'ambient_light_level': ambient_light_level,
        'humidity_levels': humidity_levels,
        'temperature_levels': temperature_levels,
        'device_id': device_id,
    }, None


def _sanitize_header_value(value, max_len=256):
    text = str(value or '').replace('\r', ' ').replace('\n', ' ').strip()
    return text[:max_len]


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def app_mode(request):
    setting, _ = AppMode.objects.get_or_create(id=1)
    if request.method == 'GET':
        return JsonResponse({'mode': setting.mode})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Request body must be valid JSON.'}, status=400)

    new_mode = payload.get('mode')
    if new_mode in ['sfw', 'nsfw']:
        setting.mode = new_mode
        setting.save()
        return JsonResponse({'mode': setting.mode})
    return JsonResponse({'error': 'Mode must be "sfw" or "nsfw".'}, status=400)


@require_http_methods(['GET'])
def health_check(_request):
    return JsonResponse({'status': 'ok'})


def _get_latest_analyzed_reading(device_id=None):
    qs = PlantReading.objects.filter(analysis_status=PlantReading.ANALYSIS_COMPLETED)
    if device_id:
        qs = qs.filter(device_id=device_id)

    for reading in qs:
        if isinstance(reading.plant_messages, list) and reading.plant_messages:
            return reading

    return None


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def readings_collection(request):
    if request.method == 'GET':
        device_id = request.GET.get('deviceId')
        qs = PlantReading.objects.all()
        if device_id:
            qs = qs.filter(device_id=device_id)
        readings = [_serialize_reading(reading) for reading in qs[:20]]
        latest = readings[0] if readings else None
        return JsonResponse({'items': readings, 'latest': latest})

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Request body must be valid JSON.'}, status=400)

    reading_data, error = _validate_payload(payload)
    if error:
        return JsonResponse({'error': error}, status=400)

    setting, _ = AppMode.objects.get_or_create(id=1)

    reading = PlantReading.objects.create(
        **reading_data,
        analysis_mode=setting.mode,
        analysis_status=PlantReading.ANALYSIS_PENDING,
        condition=None,
        plant_messages=[],
    )
    queued_now = enqueue_reading_analysis(reading.id)
    schedule_pending_analyses(limit=2)

    response_payload = _serialize_reading(reading)
    response_payload['analysisQueued'] = bool(queued_now)
    return JsonResponse(response_payload, status=202)


@require_http_methods(['GET'])
def plant_status(request):
    schedule_pending_analyses(limit=2)
    device_id = request.GET.get('deviceId')
    reading = _get_latest_analyzed_reading(device_id)
    if reading is None:
        return JsonResponse({'error': 'No analyzed plant reading is available yet.'}, status=404)

    selected_message = random.choice(reading.plant_messages)
    return JsonResponse(
        {
            'condition': reading.condition,
            'message': selected_message,
            'messages': reading.plant_messages,
            'reading': _serialize_reading(reading),
        }
    )


@require_http_methods(['GET'])
def plant_voice(request):
    schedule_pending_analyses(limit=2)
    device_id = request.GET.get('deviceId')
    reading = _get_latest_analyzed_reading(device_id)
    if reading is None:
        return JsonResponse({'error': 'No analyzed plant reading is available yet.'}, status=404)

    selected_message = random.choice(reading.plant_messages)

    try:
        audio_bytes = synthesize_speech_mp3(selected_message)
    except PlantTtsError as error:
        return JsonResponse({'error': f'TTS generation failed: {error}'}, status=502)

    response = HttpResponse(audio_bytes, content_type='audio/mpeg')
    response['Content-Disposition'] = 'inline; filename="plant-voice.mp3"'
    response['X-Plant-Condition'] = _sanitize_header_value(reading.condition, max_len=32)
    response['X-Plant-Message'] = _sanitize_header_value(selected_message)
    return response
