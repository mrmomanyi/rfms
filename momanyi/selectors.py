"""Database queries and caching used by the views."""
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import services
from .models import Tree

_CACHE_KEYS = ('rfms:scorecard:0', 'rfms:scorecard:1')


def alive_trees():
    """Living, active trees with everything the scorecard needs, in few queries."""
    return (
        Tree.objects.filter(tree_status='alive', is_active=True)
        .exclude(verification_status='rejected')
        .select_related('species', 'county', 'subcounty')
        .prefetch_related('measurements')
    )


def invalidate_scorecard():
    cache.delete_many(list(_CACHE_KEYS))


def get_scorecard():
    """The full scorecard, cached for a few minutes and cleared on any data change."""
    rank_verified_only = bool(getattr(settings, 'RFMS_RANK_VERIFIED_ONLY', False))
    key = f'rfms:scorecard:{int(rank_verified_only)}'
    seconds = getattr(settings, 'RFMS_SCORECARD_CACHE_SECONDS', 300)

    card = cache.get(key) if seconds else None
    if card is None:
        card = services.build_scorecard(
            alive_trees(), today=timezone.localdate(), rank_verified_only=rank_verified_only)
        if seconds:
            cache.set(key, card, seconds)
    return card
