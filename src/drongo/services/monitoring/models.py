"""In-memory models for Cloud Monitoring (``monitoring_v3``).

Cloud Monitoring's clients are gRPC-only (no REST transport, no emulator env
var), so drongo serves them from an in-process gRPC :class:`MonitoringEmulator`
(see emulator.py) with an injected transport. This layer is a plain store: the
emulator owns all proto handling and hands the backend proto-JSON dicts (snake
case), so models.py stays free of any client-library imports.

State kept per project:

* metric descriptors, keyed by metric ``type``
* written time series (accumulated points)
* alert policies and notification channels, keyed by full resource name
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["MonitoringBackend", "monitoring_backends"]


class MonitoringBackend(BaseBackend):
    """In-memory Cloud Monitoring state for a single project."""

    def setup(self) -> None:
        self.metric_descriptors: dict[str, dict[str, Any]] = {}
        self.time_series: list[dict[str, Any]] = []
        self.alert_policies: dict[str, dict[str, Any]] = {}
        self.notification_channels: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def _next(self) -> int:
        self._counter += 1
        return self._counter

    # -- metric descriptors ------------------------------------------------

    def create_metric_descriptor(self, descriptor: dict[str, Any]) -> dict[str, Any]:
        metric_type = descriptor.get("type", "")
        descriptor = dict(descriptor)
        descriptor["name"] = f"projects/{self.project}/metricDescriptors/{metric_type}"
        self.metric_descriptors[metric_type] = descriptor
        return descriptor

    def get_metric_descriptor(self, metric_type: str) -> dict[str, Any]:
        try:
            return self.metric_descriptors[metric_type]
        except KeyError:
            raise exceptions.not_found(f"Metric descriptor not found: {metric_type}")

    def list_metric_descriptors(self) -> list[dict[str, Any]]:
        return [self.metric_descriptors[t] for t in sorted(self.metric_descriptors)]

    def delete_metric_descriptor(self, metric_type: str) -> None:
        if metric_type not in self.metric_descriptors:
            raise exceptions.not_found(f"Metric descriptor not found: {metric_type}")
        del self.metric_descriptors[metric_type]

    # -- time series -------------------------------------------------------

    def create_time_series(self, series: list[dict[str, Any]]) -> None:
        self.time_series.extend(series)

    def list_time_series(
        self,
        metric_type: str | None,
        resource_type: str | None,
        start_time: str | None,
        end_time: str | None,
    ) -> list[dict[str, Any]]:
        """Return stored series matching the metric/resource, points in window."""
        start, end = _epoch(start_time), _epoch(end_time)
        result: list[dict[str, Any]] = []
        for series in self.time_series:
            if metric_type and series.get("metric", {}).get("type") != metric_type:
                continue
            if (
                resource_type
                and series.get("resource", {}).get("type") != resource_type
            ):
                continue
            points = [p for p in series.get("points", []) if _in_window(p, start, end)]
            if points:
                matched = dict(series)
                matched["points"] = points
                result.append(matched)
        return result

    # -- alert policies ----------------------------------------------------

    def create_alert_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        name = f"projects/{self.project}/alertPolicies/{self._next()}"
        policy = dict(policy)
        policy["name"] = name
        self.alert_policies[name] = policy
        return policy

    def get_alert_policy(self, name: str) -> dict[str, Any]:
        try:
            return self.alert_policies[name]
        except KeyError:
            raise exceptions.not_found(f"Alert policy not found: {name}")

    def list_alert_policies(self) -> list[dict[str, Any]]:
        return [self.alert_policies[n] for n in sorted(self.alert_policies)]

    def delete_alert_policy(self, name: str) -> None:
        if name not in self.alert_policies:
            raise exceptions.not_found(f"Alert policy not found: {name}")
        del self.alert_policies[name]

    def update_alert_policy(
        self, policy: dict[str, Any], paths: list[str]
    ) -> dict[str, Any]:
        stored = self.get_alert_policy(policy.get("name", ""))
        _apply_update(stored, policy, paths)
        return stored

    # -- notification channels ---------------------------------------------

    def create_notification_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        name = f"projects/{self.project}/notificationChannels/{self._next()}"
        channel = dict(channel)
        channel["name"] = name
        self.notification_channels[name] = channel
        return channel

    def get_notification_channel(self, name: str) -> dict[str, Any]:
        try:
            return self.notification_channels[name]
        except KeyError:
            raise exceptions.not_found(f"Notification channel not found: {name}")

    def list_notification_channels(self) -> list[dict[str, Any]]:
        return [
            self.notification_channels[n] for n in sorted(self.notification_channels)
        ]

    def delete_notification_channel(self, name: str) -> None:
        if name not in self.notification_channels:
            raise exceptions.not_found(f"Notification channel not found: {name}")
        del self.notification_channels[name]

    def update_notification_channel(
        self, channel: dict[str, Any], paths: list[str]
    ) -> dict[str, Any]:
        stored = self.get_notification_channel(channel.get("name", ""))
        _apply_update(stored, channel, paths)
        return stored


def _apply_update(
    stored: dict[str, Any], incoming: dict[str, Any], paths: list[str]
) -> None:
    """Apply an update: only the masked top-level fields, or all provided ones."""
    fields = paths or [k for k in incoming if k != "name"]
    for field in fields:
        top = field.split(".")[0]
        if top in incoming:
            stored[top] = incoming[top]


def _in_window(point: dict[str, Any], start: float | None, end: float | None) -> bool:
    if start is None and end is None:
        return True
    moment = _epoch(point.get("interval", {}).get("end_time"))
    if moment is None:
        return True  # unparseable timestamp: keep it rather than silently drop
    if start is not None and moment < start:
        return False
    return not (end is not None and moment > end)


def _epoch(rfc3339: str | None) -> float | None:
    if not rfc3339:
        return None
    text = rfc3339.replace("Z", "+00:00")
    if "." in text:  # trim fractional seconds to microseconds for fromisoformat
        head, _, tail = text.partition(".")
        digits = "".join(c for c in tail if c.isdigit())
        offset = tail[len(digits) :]
        text = f"{head}.{digits[:6]}{offset}"
    try:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


#: Project-keyed backends, inspectable via ``get_backend("monitoring")[project]``.
monitoring_backends: BackendDict[MonitoringBackend] = BackendDict(
    MonitoringBackend, "monitoring"
)
