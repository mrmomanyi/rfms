"""Database models for the Forest Resource Monitoring System."""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .calculations import GrowthParams


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
class County(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, blank=True, null=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'counties'

    def __str__(self):
        return self.name


class SubCounty(models.Model):
    county = models.ForeignKey(County, on_delete=models.CASCADE, related_name='subcounties')
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['county__name', 'name']
        unique_together = ['county', 'name']
        verbose_name_plural = 'sub-counties'

    def __str__(self):
        return f'{self.name}, {self.county.name}'


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------
class TreeSpecies(models.Model):
    name = models.CharField(max_length=100, unique=True)
    scientific_name = models.CharField(max_length=200, blank=True, null=True)

    # Legacy per-year rates from the first version. Kept so old data is not lost,
    # but the carbon and oxygen figures are now derived from tree size.
    carbon_sequestration_rate = models.FloatField(
        default=0, help_text='Legacy. Not used by the current calculations.')
    oxygen_production_rate = models.FloatField(
        default=0, help_text='Legacy. Not used by the current calculations.')

    # Inputs for the biomass equation
    wood_density = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.1), MaxValueValidator(1.5)],
        help_text='Basic wood density in g/cm³ (Global Wood Density Database). '
                  'Leave empty to use the default.')
    density_source = models.CharField(
        max_length=200, blank=True, help_text='Where the wood density came from')

    # Optional growth-curve parameters. Empty means "use the generic defaults".
    growth_dbh_max_cm = models.FloatField(null=True, blank=True, help_text='Maximum trunk diameter, cm')
    growth_dbh_k = models.FloatField(null=True, blank=True, help_text='Diameter growth rate constant')
    growth_height_max_m = models.FloatField(null=True, blank=True, help_text='Maximum height, m')
    growth_height_k = models.FloatField(null=True, blank=True, help_text='Height growth rate constant')
    growth_shape = models.FloatField(null=True, blank=True, help_text='Curve shape parameter')
    growth_source = models.CharField(max_length=200, blank=True, help_text='Source of the growth parameters')

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'tree species'

    def __str__(self):
        return self.name

    @property
    def has_calibrated_density(self):
        return self.wood_density is not None

    def growth_params(self):
        """Growth parameters for this species, falling back to generic defaults."""
        d = GrowthParams()
        return GrowthParams(
            dbh_max_cm=self.growth_dbh_max_cm or d.dbh_max_cm,
            dbh_k=self.growth_dbh_k or d.dbh_k,
            height_max_m=self.growth_height_max_m or d.height_max_m,
            height_k=self.growth_height_k or d.height_k,
            shape=self.growth_shape or d.shape,
        )


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------
def generate_tree_id():
    """Unique, human-friendly tree ID such as TREE-3F9A1C7B."""
    return f'TREE-{uuid.uuid4().hex[:8].upper()}'


class Tree(models.Model):
    FOREST_CATEGORY_CHOICES = [
        ('afforestation', 'Afforestation (New Forest)'),
        ('reafforestation', 'Reafforestation (Restored Forest)'),
        ('existing', 'Existing / Old Forest'),
    ]
    TREE_STATUS_CHOICES = [('alive', 'Alive'), ('dead', 'Dead')]
    CONTRIBUTOR_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('institution', 'Institution / School'),
        ('organization', 'Organization'),
    ]
    VERIFICATION_CHOICES = [
        ('pending', 'Pending review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    # Identification
    tree_id = models.CharField(max_length=20, unique=True, default=generate_tree_id, editable=False)

    # Tree details
    species = models.ForeignKey(TreeSpecies, on_delete=models.PROTECT)
    forest_category = models.CharField(max_length=50, choices=FOREST_CATEGORY_CHOICES)
    tree_status = models.CharField(max_length=10, choices=TREE_STATUS_CHOICES)
    planting_date = models.DateField(
        null=True, blank=True, help_text='When the tree was planted, if known')

    # Location
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    county = models.ForeignKey(County, on_delete=models.PROTECT)
    subcounty = models.ForeignKey(SubCounty, on_delete=models.PROTECT)
    plot_name = models.CharField(max_length=200)

    # Contributor
    contributor_type = models.CharField(max_length=50, choices=CONTRIBUTOR_TYPE_CHOICES)
    contributor_name = models.CharField(max_length=200)

    # Review
    verification_status = models.CharField(
        max_length=10, choices=VERIFICATION_CHOICES, default='pending')
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_trees')
    verified_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    registration_date = models.DateTimeField(default=timezone.now)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='registered_trees')
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-registration_date']
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['registration_date']),
            models.Index(fields=['tree_status', 'is_active']),
        ]

    def __str__(self):
        return f'{self.tree_id} - {self.species.name}'

    # -- helpers ------------------------------------------------------------
    @property
    def counts_as_removal(self):
        """Planted trees count as carbon removal. Existing forest is stock only."""
        return self.forest_category in ('afforestation', 'reafforestation')

    # -- validation ---------------------------------------------------------
    def clean(self):
        """Rules that apply everywhere: the form, Django admin and the API."""
        errors = {}

        if self.county_id and self.subcounty_id and self.subcounty.county_id != self.county_id:
            errors['subcounty'] = 'This sub-county does not belong to the selected county.'

        if self.planting_date and self.planting_date > timezone.localdate():
            errors['planting_date'] = 'The planting date cannot be in the future.'

        if self.latitude is not None and self.longitude is not None:
            # imported here to avoid a circular import
            from .spatial import find_trees_within, in_kenya
            lat, lng = float(self.latitude), float(self.longitude)
            if not in_kenya(lat, lng):
                errors['latitude'] = 'These coordinates are outside Kenya.'
            else:
                radius = getattr(settings, 'RFMS_DUPLICATE_RADIUS_M', 1.0)
                hits = find_trees_within(lat, lng, radius, exclude_pk=self.pk)
                if hits:
                    other, distance = hits[0]
                    errors['latitude'] = (
                        f'Tree {other.tree_id} is already registered {distance:.1f} m from here. '
                        f'Trees must be at least {radius:g} m apart.')

        if errors:
            raise ValidationError(errors)


class Measurement(models.Model):
    """A field measurement of one tree. Many measurements can exist per tree."""
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name='measurements')
    measured_on = models.DateField(default=timezone.localdate)
    dbh_cm = models.FloatField(
        validators=[MinValueValidator(0.1), MaxValueValidator(500)],
        help_text='Trunk diameter at breast height (1.3 m), in cm')
    height_m = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0.1), MaxValueValidator(120)],
        help_text='Tree height in metres (optional)')
    measured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='measurements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-measured_on', '-id']

    def __str__(self):
        return f'{self.tree.tree_id} measured {self.measured_on}'

    def clean(self):
        if self.measured_on and self.measured_on > timezone.localdate():
            raise ValidationError({'measured_on': 'The measurement date cannot be in the future.'})


class TreeEvent(models.Model):
    """Audit trail: who did what to a tree, and when."""
    EVENT_TYPES = [
        ('registered', 'Registered'),
        ('measured', 'Measured'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('status_changed', 'Status changed'),
        ('note', 'Note'),
    ]
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    note = models.CharField(max_length=300, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tree_events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.tree.tree_id}: {self.get_event_type_display()}'
