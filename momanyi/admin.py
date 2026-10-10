from django.contrib import admin, messages
from django.utils import timezone

from .models import County, Measurement, SubCounty, Tree, TreeEvent, TreeSpecies


class MeasurementInline(admin.TabularInline):
    model = Measurement
    extra = 0
    fields = ('measured_on', 'dbh_cm', 'height_m', 'measured_by')


class TreeEventInline(admin.TabularInline):
    model = TreeEvent
    extra = 0
    can_delete = False
    fields = ('event_type', 'note', 'user', 'created_at')
    readonly_fields = ('event_type', 'note', 'user', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Tree)
class TreeAdmin(admin.ModelAdmin):
    list_display = ('tree_id', 'species', 'county', 'subcounty', 'forest_category',
                    'tree_status', 'verification_status', 'contributor_name',
                    'registration_date', 'is_active')
    list_filter = ('is_active', 'verification_status', 'tree_status', 'forest_category',
                   'county', 'contributor_type', 'registration_date')
    search_fields = ('tree_id', 'plot_name', 'contributor_name')
    list_select_related = ('species', 'county', 'subcounty')
    autocomplete_fields = ('species', 'county', 'subcounty', 'registered_by')
    date_hierarchy = 'registration_date'
    readonly_fields = ('tree_id', 'last_updated', 'verified_by', 'verified_at')
    inlines = [MeasurementInline, TreeEventInline]
    actions = ['mark_verified', 'mark_rejected', 'mark_pending']
    fieldsets = (
        ('Tree', {'fields': ('tree_id', 'species', 'forest_category', 'tree_status', 'planting_date')}),
        ('Location', {'fields': ('latitude', 'longitude', 'county', 'subcounty', 'plot_name')}),
        ('Contributor', {'fields': ('contributor_type', 'contributor_name')}),
        ('Review', {'fields': ('verification_status', 'verified_by', 'verified_at')}),
        ('Record', {'fields': ('registration_date', 'registered_by', 'is_active', 'last_updated')}),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.registered_by_id:
            obj.registered_by = request.user
        super().save_model(request, obj, form, change)
        if not change:
            TreeEvent.objects.create(
                tree=obj, event_type='registered', user=request.user, note='Added in the admin site')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for obj in instances:
            if isinstance(obj, Measurement):
                is_new = obj.pk is None
                if not obj.measured_by_id:
                    obj.measured_by = request.user
                obj.save()
                if is_new:
                    TreeEvent.objects.create(
                        tree=obj.tree, event_type='measured', user=request.user,
                        note=f'DBH {obj.dbh_cm:g} cm')
            else:
                obj.save()
        formset.save_m2m()

    def _review(self, request, queryset, status, event_type, label):
        count = 0
        for tree in queryset:
            tree.verification_status = status
            tree.verified_by = request.user if status == 'verified' else None
            tree.verified_at = timezone.now() if status == 'verified' else None
            tree.save(update_fields=['verification_status', 'verified_by', 'verified_at', 'last_updated'])
            TreeEvent.objects.create(tree=tree, event_type=event_type, user=request.user, note=label)
            count += 1
        self.message_user(request, f'{count} tree(s) marked {status}.', messages.SUCCESS)

    @admin.action(description='Mark selected trees as verified')
    def mark_verified(self, request, queryset):
        self._review(request, queryset, 'verified', 'verified', 'Verified by a reviewer')

    @admin.action(description='Mark selected trees as rejected')
    def mark_rejected(self, request, queryset):
        self._review(request, queryset, 'rejected', 'rejected', 'Rejected by a reviewer')

    @admin.action(description='Return selected trees to pending review')
    def mark_pending(self, request, queryset):
        self._review(request, queryset, 'pending', 'note', 'Returned to pending review')


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name',)


@admin.register(SubCounty)
class SubCountyAdmin(admin.ModelAdmin):
    list_display = ('name', 'county')
    list_filter = ('county',)
    search_fields = ('name', 'county__name')
    autocomplete_fields = ('county',)


@admin.register(TreeSpecies)
class TreeSpeciesAdmin(admin.ModelAdmin):
    list_display = ('name', 'scientific_name', 'wood_density', 'density_source')
    search_fields = ('name', 'scientific_name')
    fieldsets = (
        (None, {'fields': ('name', 'scientific_name')}),
        ('Biomass equation input', {'fields': ('wood_density', 'density_source')}),
        ('Growth curve (optional, empty uses generic defaults)', {
            'fields': ('growth_dbh_max_cm', 'growth_dbh_k', 'growth_height_max_m',
                       'growth_height_k', 'growth_shape', 'growth_source')}),
        ('Legacy values from version 1', {
            'classes': ('collapse',),
            'fields': ('carbon_sequestration_rate', 'oxygen_production_rate')}),
    )


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    list_display = ('tree', 'measured_on', 'dbh_cm', 'height_m', 'measured_by')
    list_filter = ('measured_on',)
    search_fields = ('tree__tree_id',)
    autocomplete_fields = ('tree', 'measured_by')
