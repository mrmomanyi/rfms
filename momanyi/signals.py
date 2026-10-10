"""Clear the cached scorecard whenever the data behind it changes."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Measurement, Tree, TreeSpecies
from .selectors import invalidate_scorecard


@receiver([post_save, post_delete], sender=Tree)
@receiver([post_save, post_delete], sender=Measurement)
@receiver([post_save, post_delete], sender=TreeSpecies)
def clear_scorecard_cache(sender, **kwargs):
    invalidate_scorecard()
