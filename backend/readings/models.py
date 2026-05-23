from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class PlantReading(models.Model):
    CONDITION_GOOD = 'good'
    CONDITION_NEUTRAL = 'neutral'
    CONDITION_BAD = 'bad'
    CONDITION_CHOICES = [
        (CONDITION_GOOD, 'Good'),
        (CONDITION_NEUTRAL, 'Neutral'),
        (CONDITION_BAD, 'Bad'),
    ]
    ANALYSIS_PENDING = 'pending'
    ANALYSIS_PROCESSING = 'processing'
    ANALYSIS_COMPLETED = 'completed'
    ANALYSIS_FAILED = 'failed'
    ANALYSIS_STATUS_CHOICES = [
        (ANALYSIS_PENDING, 'Pending'),
        (ANALYSIS_PROCESSING, 'Processing'),
        (ANALYSIS_COMPLETED, 'Completed'),
        (ANALYSIS_FAILED, 'Failed'),
    ]
    ANALYSIS_MODE_SFW = 'sfw'
    ANALYSIS_MODE_NSFW = 'nsfw'
    ANALYSIS_MODE_CHOICES = [
        (ANALYSIS_MODE_SFW, 'Safe for Work'),
        (ANALYSIS_MODE_NSFW, 'Not Safe for Work'),
    ]

    soil_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(4095)]
    )
    ambient_light_level = models.PositiveIntegerField()
    humidity_levels = models.FloatField(default=0.0)
    temperature_levels = models.FloatField(default=0.0)
    device_id = models.CharField(max_length=100, default="default_device")
    analysis_status = models.CharField(
        max_length=12,
        choices=ANALYSIS_STATUS_CHOICES,
        default=ANALYSIS_PENDING,
        db_index=True,
    )
    analysis_mode = models.CharField(
        max_length=10,
        choices=ANALYSIS_MODE_CHOICES,
        default=ANALYSIS_MODE_SFW,
    )
    analysis_error = models.TextField(blank=True, default='')
    analysis_started_at = models.DateTimeField(blank=True, null=True)
    analysis_completed_at = models.DateTimeField(blank=True, null=True)
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, blank=True, null=True)
    plant_messages = models.JSONField(default=list, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        condition = self.condition or 'unclassified'
        return (
            f'soil={self.soil_level}, light={self.ambient_light_level} lux, '
            f'{condition}, analysis={self.analysis_status}'
        )


class AppMode(models.Model):
    mode = models.CharField(max_length=10, default='sfw')

    def __str__(self):
        return self.mode
