"""In-process gRPC emulator for Cloud Monitoring.

Cloud Monitoring's clients are gRPC-only: no REST transport and no emulator env
var. So drongo runs a real in-process gRPC server backed by
:class:`MonitoringBackend` and the service's patchers inject a transport pointing
at it (see ``force_local_grpc_patchers``). The user's normal clients work
unchanged.

The server speaks three services - ``MetricService``, ``AlertPolicyService`` and
``NotificationChannelService`` - built with generic gRPC handlers using the
client library's own proto (de)serializers, so no generated servicer classes are
needed. Each handler converts the request proto to a proto-JSON dict, calls the
backend, and rebuilds a response proto. Required libraries (``grpcio`` +
``google-cloud-monitoring``) are optional; if absent, :meth:`start` no-ops.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError
from drongo.services.monitoring.models import MonitoringBackend, monitoring_backends

_METRIC_TYPE = re.compile(r'metric\.type\s*=\s*"([^"]+)"')
_RESOURCE_TYPE = re.compile(r'resource\.type\s*=\s*"([^"]+)"')


class MonitoringEmulator(BaseEmulator):
    """Serves the Cloud Monitoring gRPC API from an in-process server."""

    def __init__(self, backends: Any = monitoring_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._grpc: Any = None
        self._mt: Any = None  # monitoring_v3.types
        self._metric_pb2: Any = None
        self._json: Any = None
        self._empty: Any = None

    @property
    def address(self) -> str | None:
        if self._server is None or self._port is None:
            return None
        return f"localhost:{self._port}"

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._available is False:
            return
        if self._server is None and not self._boot():
            self._available = False
            return
        self._available = True

    def stop(self) -> None:
        # Reused across scopes (backend state is reset by the controller); no env
        # var to restore, so nothing to undo.
        return

    def _boot(self) -> bool:
        try:
            import grpc
            from google.api import metric_pb2
            from google.cloud import monitoring_v3
            from google.protobuf import empty_pb2, json_format
        except Exception:
            return False
        from concurrent import futures

        self._grpc = grpc
        self._mt = monitoring_v3.types
        self._metric_pb2 = metric_pb2
        self._json = json_format
        self._empty = empty_pb2

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- proto <-> dict ----------------------------------------------------

    def _dict(self, proto: Any) -> dict[str, Any]:
        pb = getattr(proto, "_pb", proto)
        return self._json.MessageToDict(pb, preserving_proto_field_name=True)

    def _raw(self, message_type: Any, data: dict[str, Any]) -> Any:
        return self._json.ParseDict(data, message_type(), ignore_unknown_fields=True)

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, mt, empty = self._grpc, self._mt, self._empty
        status = {
            400: grpc.StatusCode.INVALID_ARGUMENT,
            404: grpc.StatusCode.NOT_FOUND,
            409: grpc.StatusCode.ALREADY_EXISTS,
        }

        def guard(fn: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(request: Any, context: Any) -> Any:
                try:
                    return fn(request, context)
                except DrongoHttpError as exc:
                    return context.abort(
                        status.get(exc.status_code, grpc.StatusCode.UNKNOWN),
                        exc.message,
                    )

            return wrapped

        def unary(req_t: Any, resp_t: Any, fn: Callable[..., Any]) -> Any:
            ser = getattr(resp_t, "serialize", None) or resp_t.SerializeToString
            de = getattr(req_t, "deserialize", None) or req_t.FromString
            return grpc.unary_unary_rpc_method_handler(
                guard(fn), request_deserializer=de, response_serializer=ser
            )

        metric = {
            "CreateMetricDescriptor": unary(
                mt.CreateMetricDescriptorRequest,
                self._metric_pb2.MetricDescriptor,
                self._create_metric_descriptor,
            ),
            "GetMetricDescriptor": unary(
                mt.GetMetricDescriptorRequest,
                self._metric_pb2.MetricDescriptor,
                self._get_metric_descriptor,
            ),
            "ListMetricDescriptors": unary(
                mt.ListMetricDescriptorsRequest,
                mt.ListMetricDescriptorsResponse,
                self._list_metric_descriptors,
            ),
            "DeleteMetricDescriptor": unary(
                mt.DeleteMetricDescriptorRequest,
                empty.Empty,
                self._delete_metric_descriptor,
            ),
            "CreateTimeSeries": unary(
                mt.CreateTimeSeriesRequest, empty.Empty, self._create_time_series
            ),
            "CreateServiceTimeSeries": unary(
                mt.CreateTimeSeriesRequest, empty.Empty, self._create_time_series
            ),
            "ListTimeSeries": unary(
                mt.ListTimeSeriesRequest,
                mt.ListTimeSeriesResponse,
                self._list_time_series,
            ),
            "ListMonitoredResourceDescriptors": unary(
                mt.ListMonitoredResourceDescriptorsRequest,
                mt.ListMonitoredResourceDescriptorsResponse,
                self._list_monitored_resource_descriptors,
            ),
        }
        alert = {
            "CreateAlertPolicy": unary(
                mt.CreateAlertPolicyRequest, mt.AlertPolicy, self._create_alert_policy
            ),
            "GetAlertPolicy": unary(
                mt.GetAlertPolicyRequest, mt.AlertPolicy, self._get_alert_policy
            ),
            "ListAlertPolicies": unary(
                mt.ListAlertPoliciesRequest,
                mt.ListAlertPoliciesResponse,
                self._list_alert_policies,
            ),
            "DeleteAlertPolicy": unary(
                mt.DeleteAlertPolicyRequest, empty.Empty, self._delete_alert_policy
            ),
            "UpdateAlertPolicy": unary(
                mt.UpdateAlertPolicyRequest, mt.AlertPolicy, self._update_alert_policy
            ),
        }
        channel = {
            "CreateNotificationChannel": unary(
                mt.CreateNotificationChannelRequest,
                mt.NotificationChannel,
                self._create_notification_channel,
            ),
            "GetNotificationChannel": unary(
                mt.GetNotificationChannelRequest,
                mt.NotificationChannel,
                self._get_notification_channel,
            ),
            "ListNotificationChannels": unary(
                mt.ListNotificationChannelsRequest,
                mt.ListNotificationChannelsResponse,
                self._list_notification_channels,
            ),
            "DeleteNotificationChannel": unary(
                mt.DeleteNotificationChannelRequest,
                empty.Empty,
                self._delete_notification_channel,
            ),
            "UpdateNotificationChannel": unary(
                mt.UpdateNotificationChannelRequest,
                mt.NotificationChannel,
                self._update_notification_channel,
            ),
        }

        # Uptime configs, groups, snoozes, services and SLOs are uniform CRUD, so
        # they are built from a config table over generic handlers.
        def make_create(collection: str, field: str, rtype: Any) -> Any:
            def handler(request: Any, context: Any) -> Any:
                req = self._dict(request)
                parent = str(req.get("parent") or req.get("name") or "")
                created = self._backend(parent).create_resource(
                    parent, collection, req.get(field, {})
                )
                return rtype(created)

            return handler

        def make_get(rtype: Any) -> Any:
            def handler(request: Any, context: Any) -> Any:
                req = self._dict(request)
                return rtype(self._backend(req["name"]).get_resource(req["name"]))

            return handler

        def make_list(collection: str, list_field: str, rtype: Any) -> Any:
            def handler(request: Any, context: Any) -> Any:
                req = self._dict(request)
                parent = str(req.get("parent") or req.get("name") or "")
                items = self._backend(parent).list_resources(parent, collection)
                return rtype({list_field: items})

            return handler

        def make_update(field: str, rtype: Any) -> Any:
            def handler(request: Any, context: Any) -> Any:
                req = self._dict(request)
                resource = req.get(field, {})
                updated = self._backend(resource["name"]).update_resource(
                    resource, _mask_paths(req.get("update_mask"))
                )
                return rtype(updated)

            return handler

        def make_delete() -> Any:
            def handler(request: Any, context: Any) -> Any:
                req = self._dict(request)
                self._backend(req["name"]).delete_resource(req["name"])
                return empty.Empty()

            return handler

        def crud(config: tuple) -> dict[str, Any]:
            collection, field, list_field, singular, plural, has_delete = config
            rtype = getattr(mt, singular)
            list_resp = getattr(mt, f"List{plural}Response")
            handlers = {
                f"Create{singular}": unary(
                    getattr(mt, f"Create{singular}Request"),
                    rtype,
                    make_create(collection, field, rtype),
                ),
                f"Get{singular}": unary(
                    getattr(mt, f"Get{singular}Request"), rtype, make_get(rtype)
                ),
                f"List{plural}": unary(
                    getattr(mt, f"List{plural}Request"),
                    list_resp,
                    make_list(collection, list_field, list_resp),
                ),
                f"Update{singular}": unary(
                    getattr(mt, f"Update{singular}Request"),
                    rtype,
                    make_update(field, rtype),
                ),
            }
            if has_delete:
                handlers[f"Delete{singular}"] = unary(
                    getattr(mt, f"Delete{singular}Request"), empty.Empty, make_delete()
                )
            return handlers

        uptime = crud(
            (
                "uptimeCheckConfigs",
                "uptime_check_config",
                "uptime_check_configs",
                "UptimeCheckConfig",
                "UptimeCheckConfigs",
                True,
            )
        )
        group = crud(("groups", "group", "group", "Group", "Groups", True))
        snooze = crud(("snoozes", "snooze", "snoozes", "Snooze", "Snoozes", False))
        service = crud(("services", "service", "services", "Service", "Services", True))
        slo = crud(
            (
                "serviceLevelObjectives",
                "service_level_objective",
                "service_level_objectives",
                "ServiceLevelObjective",
                "ServiceLevelObjectives",
                True,
            )
        )

        generic = grpc.method_handlers_generic_handler
        return (
            generic("google.monitoring.v3.MetricService", metric),
            generic("google.monitoring.v3.AlertPolicyService", alert),
            generic("google.monitoring.v3.NotificationChannelService", channel),
            generic("google.monitoring.v3.UptimeCheckService", uptime),
            generic("google.monitoring.v3.GroupService", group),
            generic("google.monitoring.v3.SnoozeService", snooze),
            generic(
                "google.monitoring.v3.ServiceMonitoringService", {**service, **slo}
            ),
        )

    def _backend(self, name: str) -> MonitoringBackend:
        return self._backends[name.split("/")[1]]

    # -- metric descriptors ------------------------------------------------

    def _create_metric_descriptor(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        created = self._backend(req["name"]).create_metric_descriptor(
            req.get("metric_descriptor", {})
        )
        return self._raw(self._metric_pb2.MetricDescriptor, created)

    def _get_metric_descriptor(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        metric_type = req["name"].split("/metricDescriptors/", 1)[1]
        descriptor = self._backend(req["name"]).get_metric_descriptor(metric_type)
        return self._raw(self._metric_pb2.MetricDescriptor, descriptor)

    def _list_metric_descriptors(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        descriptors = self._backend(req["name"]).list_metric_descriptors()
        return self._mt.ListMetricDescriptorsResponse(
            {"metric_descriptors": descriptors}
        )

    def _delete_metric_descriptor(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        metric_type = req["name"].split("/metricDescriptors/", 1)[1]
        self._backend(req["name"]).delete_metric_descriptor(metric_type)
        return self._empty.Empty()

    # -- time series -------------------------------------------------------

    def _create_time_series(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        self._backend(req["name"]).create_time_series(req.get("time_series", []))
        return self._empty.Empty()

    def _list_time_series(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        filter_str = req.get("filter", "")
        metric = _first(_METRIC_TYPE, filter_str)
        resource = _first(_RESOURCE_TYPE, filter_str)
        interval = req.get("interval", {})
        series = self._backend(req["name"]).list_time_series(
            metric,
            resource,
            interval.get("start_time"),
            interval.get("end_time"),
            req.get("aggregation"),
        )
        return self._mt.ListTimeSeriesResponse({"time_series": series})

    def _list_monitored_resource_descriptors(self, request: Any, context: Any) -> Any:
        return self._mt.ListMonitoredResourceDescriptorsResponse()

    # -- alert policies ----------------------------------------------------

    def _create_alert_policy(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        created = self._backend(req["name"]).create_alert_policy(
            req.get("alert_policy", {})
        )
        return self._mt.AlertPolicy(created)

    def _get_alert_policy(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        return self._mt.AlertPolicy(
            self._backend(req["name"]).get_alert_policy(req["name"])
        )

    def _list_alert_policies(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        policies = self._backend(req["name"]).list_alert_policies()
        return self._mt.ListAlertPoliciesResponse({"alert_policies": policies})

    def _delete_alert_policy(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        self._backend(req["name"]).delete_alert_policy(req["name"])
        return self._empty.Empty()

    def _update_alert_policy(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        policy = req.get("alert_policy", {})
        return self._mt.AlertPolicy(
            self._backend(policy["name"]).update_alert_policy(
                policy, _mask_paths(req.get("update_mask"))
            )
        )

    # -- notification channels ---------------------------------------------

    def _create_notification_channel(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        created = self._backend(req["name"]).create_notification_channel(
            req.get("notification_channel", {})
        )
        return self._mt.NotificationChannel(created)

    def _get_notification_channel(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        return self._mt.NotificationChannel(
            self._backend(req["name"]).get_notification_channel(req["name"])
        )

    def _list_notification_channels(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        channels = self._backend(req["name"]).list_notification_channels()
        return self._mt.ListNotificationChannelsResponse(
            {"notification_channels": channels}
        )

    def _delete_notification_channel(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        self._backend(req["name"]).delete_notification_channel(req["name"])
        return self._empty.Empty()

    def _update_notification_channel(self, request: Any, context: Any) -> Any:
        req = self._dict(request)
        channel = req.get("notification_channel", {})
        return self._mt.NotificationChannel(
            self._backend(channel["name"]).update_notification_channel(
                channel, _mask_paths(req.get("update_mask"))
            )
        )


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text or "")
    return match.group(1) if match else None


def _mask_paths(mask: Any) -> list[str]:
    """FieldMask paths, normalised to snake_case to match the stored dict.

    Over JSON a FieldMask is a comma-separated string with camelCase paths
    (``"displayName"``), whereas resources are stored with proto field names
    (``display_name``), so the paths have to be converted before they line up.
    """
    if isinstance(mask, str):
        raw = [path for path in mask.split(",") if path]
    elif isinstance(mask, dict):
        raw = mask.get("paths", [])
    else:
        raw = []
    return [_snake(path) for path in raw]


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
