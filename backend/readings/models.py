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

    soil_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(4095)]
    )
    ambient_light_level = models.PositiveIntegerField()
    humidity_levels = models.FloatField(default=0.0)
    temperature_levels = models.FloatField(default=0.0)
    device_id = models.CharField(max_length=100, default="default_device")
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, blank=True, null=True)
    plant_messages = models.JSONField(default=list, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_at']

    def __str__(self):
        condition = self.condition or 'unclassified'
        return f'soil={self.soil_level}, light={self.ambient_light_level} lux, {condition}'


class AppMode(models.Model):
    mode = models.CharField(max_length=10, default='sfw')

    def __str__(self):
        return self.mode
