import django_filters

from apps.assets.models import Asset


class AssetFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status")
    os_name = django_filters.CharFilter(field_name="os_name", lookup_expr="iexact")
    asset_type = django_filters.CharFilter(field_name="asset_type__code")
    owner = django_filters.NumberFilter(field_name="current_owner_id")
    manufacturer = django_filters.CharFilter(field_name="manufacturer", lookup_expr="iexact")
    last_seen_after = django_filters.IsoDateTimeFilter(field_name="last_seen_at", lookup_expr="gte")
    last_seen_before = django_filters.IsoDateTimeFilter(field_name="last_seen_at", lookup_expr="lte")
    is_manual = django_filters.BooleanFilter(field_name="is_manual")

    class Meta:
        model = Asset
        fields = ["status", "os_name", "asset_type", "owner", "manufacturer", "is_manual"]
