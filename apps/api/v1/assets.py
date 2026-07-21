"""Asset CRUD + scan history + remote rescan."""
from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.agents.services import issue_rescan_command
from apps.api.v1.serializers.assets import (
    AssetCreateSerializer, AssetSerializer, AssetTypeSerializer,
    ScanSessionListSerializer,
)
from apps.assets.filters import AssetFilter
from apps.assets.models import Asset, AssetType
from apps.assets.selectors import list_assets
from apps.assets.services import create_manual_asset, reassign_owner
from apps.core.permissions import MinRole


class AssetTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AssetType.objects.all().order_by("label")
    serializer_class = AssetTypeSerializer
    permission_classes = [IsAuthenticated]


class AssetViewSet(viewsets.ModelViewSet):
    queryset = list_assets()
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated, MinRole]
    filterset_class = AssetFilter
    search_fields = ["hostname", "fqdn", "serial_number", "manufacturer", "model"]
    ordering_fields = ["hostname", "last_seen_at", "first_seen_at", "manufacturer", "os_name"]
    ordering = ["-last_seen_at", "hostname"]

    min_role_map = {
        "list": "viewer",
        "retrieve": "viewer",
        "scans": "viewer",
        "create": "operator",
        "update": "operator",
        "partial_update": "operator",
        "rescan": "operator",
        "set_owner": "operator",
        "destroy": "admin",
    }

    def get_serializer_class(self):
        if self.action == "create":
            return AssetCreateSerializer
        return AssetSerializer

    def perform_create(self, serializer):
        serializer.instance = create_manual_asset(
            hostname=serializer.validated_data["hostname"],
            asset_type=serializer.validated_data.get("asset_type"),
            owner_email=serializer.validated_data.get("current_owner_email", ""),
            notes=serializer.validated_data.get("notes", ""),
            actor=self.request.user,
        )

    @action(detail=True, methods=["post"], url_path="rescan")
    def rescan(self, request, pk=None):
        asset = self.get_object()
        agent = getattr(asset, "agent", None)
        if agent is None:
            return Response(
                {"error": {"code": "no_agent", "message": "Asset has no enrolled agent"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if agent.is_revoked:
            return Response(
                {"error": {"code": "agent_revoked", "message": "Agent is revoked"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cmd = issue_rescan_command(agent=agent, requested_by=request.user)
        return Response(
            {"command_id": str(cmd.id), "status": cmd.status},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="scans")
    def scans(self, request, pk=None):
        asset = self.get_object()
        qs = asset.scan_sessions.all().order_by("-received_at")
        page = self.paginate_queryset(qs)
        ser = ScanSessionListSerializer(page or qs, many=True)
        if page is not None:
            return self.get_paginated_response(ser.data)
        return Response(ser.data)

    @action(detail=True, methods=["post"], url_path="set-owner")
    def set_owner(self, request, pk=None):
        """Assign an owner by email string. Pass "" to clear."""
        asset = self.get_object()
        email = (request.data.get("email") or "").strip()
        reassign_owner(asset=asset, new_owner_email=email, actor=request.user)
        return Response(AssetSerializer(asset).data)
