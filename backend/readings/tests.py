import json
import ssl
import urllib.error
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import PlantReading
from .services import PlantAnalysisError, PlantTtsError, analyze_reading_with_llm, synthesize_speech_mp3


class _FakeUrlopenResponse:
    def __init__(self, payload_bytes):
        self._payload_bytes = payload_bytes

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload_bytes


class PlantReadingApiTests(TestCase):
    def test_health_check_returns_ok(self):
        response = self.client.get(reverse('health_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_app_mode_get_and_post(self):
        # Default mode
        response = self.client.get(reverse('app_mode'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'sfw')

        # Update mode
        response = self.client.post(
            reverse('app_mode'),
            data=json.dumps({'mode': 'nsfw'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['mode'], 'nsfw')

        # Verify update
        response = self.client.get(reverse('app_mode'))
        self.assertEqual(response.json()['mode'], 'nsfw')

        # Invalid mode
        response = self.client.post(
            reverse('app_mode'),
            data=json.dumps({'mode': 'invalid_mode'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_get_readings_returns_latest_and_items(self):
        PlantReading.objects.create(
            soil_level=44,
            ambient_light_level=680,
            analysis_status=PlantReading.ANALYSIS_COMPLETED,
            condition='neutral',
            plant_messages=['I feel okay.'] * 5,
        )

        response = self.client.get(reverse('readings_collection'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['items']), 1)
        self.assertEqual(payload['latest']['soilLevel'], 44)

    @patch('readings.views.schedule_pending_analyses', return_value=0)
    @patch('readings.views.enqueue_reading_analysis', return_value=1)
    def test_post_reading_creates_record(self, _enqueue_mock, _schedule_mock):
        response = self.client.post(
            reverse('readings_collection'),
            data=json.dumps(
                {
                    'soilLevel': 61,
                    'ambientLightLevel': 420,
                    'humidityLevels': 40.5,
                    'temperatureLevels': 22.0,
                    'deviceId': 'test-device',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(PlantReading.objects.count(), 1)
        created = PlantReading.objects.first()
        self.assertEqual(created.soil_level, 61)
        self.assertEqual(created.analysis_status, PlantReading.ANALYSIS_PENDING)
        self.assertEqual(created.analysis_mode, 'sfw')
        self.assertIsNone(created.condition)
        self.assertEqual(created.plant_messages, [])

    def test_post_reading_rejects_invalid_soil_level(self):
        response = self.client.post(
            reverse('readings_collection'),
            data=json.dumps(
                {
                    'soilLevel': 5000,
                    'ambientLightLevel': 520,
                    'humidityLevels': 40.5,
                    'temperatureLevels': 22.0,
                    'deviceId': 'test-device',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)

    @patch('readings.views.schedule_pending_analyses', return_value=0)
    @patch('readings.views.enqueue_reading_analysis', return_value=1)
    def test_post_reading_accepts_raw_esp32_soil_value(self, _enqueue_mock, _schedule_mock):
        response = self.client.post(
            reverse('readings_collection'),
            data=json.dumps(
                {
                    'soilLevel': 3120,
                    'ambientLightLevel': 520,
                    'humidityLevels': 40.5,
                    'temperatureLevels': 22.0,
                    'deviceId': 'esp32-test-device',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(PlantReading.objects.count(), 1)
        self.assertEqual(PlantReading.objects.first().soil_level, 3120)
        self.assertEqual(PlantReading.objects.first().analysis_status, PlantReading.ANALYSIS_PENDING)

    @patch('readings.views.random.choice', return_value='I need a little more water.')
    def test_plant_status_returns_condition_and_message(self, _choice_mock):
        PlantReading.objects.create(
            soil_level=38,
            ambient_light_level=240,
            analysis_status=PlantReading.ANALYSIS_COMPLETED,
            condition='bad',
            plant_messages=[
                'I need a little more water.',
                'I am struggling today.',
                'Please move me somewhere brighter.',
                'My soil feels too dry.',
                'I could use some care.',
            ],
        )

        response = self.client.get(reverse('plant_status'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['condition'], 'bad')
        self.assertEqual(payload['message'], 'I need a little more water.')

    @patch('readings.views.synthesize_speech_mp3', return_value=b'MP3DATA')
    @patch('readings.views.random.choice', return_value='I feel great today.')
    def test_plant_voice_returns_mp3(self, _choice_mock, _tts_mock):
        PlantReading.objects.create(
            soil_level=71,
            ambient_light_level=530,
            analysis_status=PlantReading.ANALYSIS_COMPLETED,
            condition='good',
            plant_messages=[
                'I feel great today.',
                'That light is perfect.',
                'My roots are happy.',
                'I am feeling strong.',
                'Keep this up.',
            ],
        )

        response = self.client.get(reverse('plant_voice'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'audio/mpeg')
        self.assertEqual(response['X-Plant-Condition'], 'good')
        self.assertEqual(response['X-Plant-Message'], 'I feel great today.')
        self.assertEqual(response.content, b'MP3DATA')

    @patch('readings.views.synthesize_speech_mp3', return_value=b'MP3DATA')
    @patch('readings.views.random.choice', return_value='Line 1\r\nLine 2')
    def test_plant_voice_sanitizes_message_header(self, _choice_mock, _tts_mock):
        PlantReading.objects.create(
            soil_level=71,
            ambient_light_level=530,
            analysis_status=PlantReading.ANALYSIS_COMPLETED,
            condition='good',
            plant_messages=[
                'Line 1\r\nLine 2',
                'That light is perfect.',
                'My roots are happy.',
                'I am feeling strong.',
                'Keep this up.',
            ],
        )

        response = self.client.get(reverse('plant_voice'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Plant-Message'], 'Line 1  Line 2')


class PlantAnalysisTlsTests(TestCase):
    @override_settings(GOOGLE_API_KEY='')
    def test_synthesize_speech_mp3_real_generation(self):
        # We test the actual unmocked gTTS fallback to ensure it genuinely generates an MP3 file
        audio_bytes = synthesize_speech_mp3("This is a live test of the plant voice.")
        
        # Verify we got data back
        self.assertGreater(len(audio_bytes), 1000)
        
        # Verify the file has an MP3/MPEG header. 
        # ID3 tags start with b'ID3', while raw ADTS/MPEG frames typically start with b'\xff'
        has_id3 = audio_bytes.startswith(b'ID3')
        has_mpeg_sync = audio_bytes.startswith(b'\xff')
        
        self.assertTrue(has_id3 or has_mpeg_sync, "Resulting byte string is not a valid MP3 file")

    @staticmethod
    def _mock_payload():
        return json.dumps(
            {
                'choices': [
                    {
                        'message': {
                            'content': json.dumps(
                                {
                                    'condition': 'good',
                                    'messages': [
                                        'I feel great.',
                                        'My roots are happy.',
                                        'The light is lovely.',
                                        'My leaves feel fresh.',
                                        'Thank you for the care.',
                                    ],
                                }
                            )
                        }
                    }
                ]
            }
        ).encode('utf-8')

    @override_settings(OPENROUTER_API_KEY='test-key', OPENROUTER_CA_BUNDLE='/tmp/custom-ca.pem')
    @patch('readings.services.ssl.create_default_context')
    @patch('readings.services.urllib.request.urlopen')
    def test_openrouter_uses_configured_ca_bundle(self, urlopen_mock, create_context_mock):
        context = object()
        create_context_mock.return_value = context
        urlopen_mock.return_value = _FakeUrlopenResponse(self._mock_payload())

        analyze_reading_with_llm(soil_level=50, ambient_light_level=400, humidity_levels=40.0, temperature_levels=22.0, device_id='test')

        create_context_mock.assert_called_once_with(cafile='/tmp/custom-ca.pem')
        _args, kwargs = urlopen_mock.call_args
        self.assertEqual(kwargs['context'], context)

    @override_settings(OPENROUTER_API_KEY='test-key', OPENROUTER_CA_BUNDLE='')
    @patch('readings.services.certifi.where', return_value='/tmp/certifi-ca.pem')
    @patch('readings.services.ssl.create_default_context')
    @patch('readings.services.urllib.request.urlopen')
    def test_openrouter_uses_certifi_bundle_by_default(
        self, urlopen_mock, create_context_mock, certifi_where_mock
    ):
        context = object()
        create_context_mock.return_value = context
        urlopen_mock.return_value = _FakeUrlopenResponse(self._mock_payload())

        analyze_reading_with_llm(soil_level=50, ambient_light_level=400, humidity_levels=40.0, temperature_levels=22.0, device_id='test')

        certifi_where_mock.assert_called_once_with()
        create_context_mock.assert_called_once_with(cafile='/tmp/certifi-ca.pem')
        _args, kwargs = urlopen_mock.call_args
        self.assertEqual(kwargs['context'], context)

    @override_settings(OPENROUTER_API_KEY='test-key')
    @patch(
        'readings.services.urllib.request.urlopen',
        side_effect=urllib.error.URLError(
            ssl.SSLCertVerificationError('unable to get local issuer certificate')
        ),
    )
    def test_openrouter_ssl_error_has_actionable_message(self, _urlopen_mock):
        with self.assertRaises(PlantAnalysisError) as error_context:
            analyze_reading_with_llm(soil_level=50, ambient_light_level=400, humidity_levels=40.0, temperature_levels=22.0, device_id='test')

        self.assertIn('TLS certificate verification failed', str(error_context.exception))

    @override_settings(GOOGLE_API_KEY='test-google-key')
    @patch('readings.services._synthesize_with_google_tts', side_effect=PlantTtsError('google failed'))
    @patch('readings.services._synthesize_with_gtts', return_value=b'FALLBACK')
    def test_synthesize_speech_falls_back_to_gtts_on_google_failure(
        self, gtts_mock, _google_mock
    ):
        audio = synthesize_speech_mp3('Hello plant')
        self.assertEqual(audio, b'FALLBACK')
        gtts_mock.assert_called_once_with('Hello plant')

    @override_settings(GOOGLE_API_KEY='test-google-key')
    @patch('readings.services._synthesize_with_google_tts', side_effect=PlantTtsError('google failed'))
    @patch('readings.services._synthesize_with_gtts', side_effect=PlantTtsError('gtts failed'))
    def test_synthesize_speech_raises_if_google_and_fallback_fail(
        self, _gtts_mock, _google_mock
    ):
        with self.assertRaises(PlantTtsError) as error_context:
            synthesize_speech_mp3('Hello plant')

        self.assertIn('Google TTS failed', str(error_context.exception))
