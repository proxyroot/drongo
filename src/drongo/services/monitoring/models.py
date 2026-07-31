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
        #: Uptime configs, groups, snoozes, services and SLOs share one
        #: name-keyed store; the collection segment keeps them apart.
        self.resources: dict[str, dict[str, Any]] = {}
        self._series_index: dict[tuple, dict[str, Any]] = {}
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
        """Store points, merging into the existing series of the same identity.

        A time series is identified by its metric (type + labels) and monitored
        resource, so repeated writes to the same identity accumulate points on one
        series - as they do in real Monitoring - rather than piling up duplicates.
        """
        for incoming in series:
            key = _identity(incoming)
            existing = self._series_index.get(key)
            if existing is not None:
                existing.setdefault("points", []).extend(incoming.get("points", []))
            else:
                stored = dict(incoming)
                stored["points"] = list(incoming.get("points", []))
                self.time_series.append(stored)
                self._series_index[key] = stored

    def list_time_series(
        self,
        metric_type: str | None,
        resource_type: str | None,
        start_time: str | None,
        end_time: str | None,
        aggregation: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return stored series matching the metric/resource, points in window.

        When an ``aggregation`` is supplied its per-series aligner and
        cross-series reducer are applied over scalar points (see ``_aggregate``).
        """
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
        if aggregation:
            result = _aggregate(result, aggregation, end)
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

    # -- generic resources (uptime configs, groups, snoozes, services, SLOs)

    def create_resource(
        self, parent: str, collection: str, resource: dict[str, Any]
    ) -> dict[str, Any]:
        name = f"{parent}/{collection}/{self._next()}"
        resource = dict(resource)
        resource["name"] = name
        self.resources[name] = resource
        return resource

    def get_resource(self, name: str) -> dict[str, Any]:
        try:
            return self.resources[name]
        except KeyError:
            raise exceptions.not_found(f"Not found: {name}")

    def list_resources(self, parent: str, collection: str) -> list[dict[str, Any]]:
        prefix = f"{parent}/{collection}/"
        return [
            self.resources[n]
            for n in sorted(self.resources)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]

    def delete_resource(self, name: str) -> None:
        if name not in self.resources:
            raise exceptions.not_found(f"Not found: {name}")
        del self.resources[name]

    def update_resource(
        self, resource: dict[str, Any], paths: list[str]
    ) -> dict[str, Any]:
        stored = self.get_resource(resource.get("name", ""))
        _apply_update(stored, resource, paths)
        return stored


def _identity(series: dict[str, Any]) -> tuple:
    """The (metric, resource) identity that uniquely names a time series."""
    metric = series.get("metric", {})
    resource = series.get("resource", {})
    return (
        metric.get("type"),
        tuple(sorted((metric.get("labels") or {}).items())),
        resource.get("type"),
        tuple(sorted((resource.get("labels") or {}).items())),
    )


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


# -- aggregation -----------------------------------------------------------
#
# A subset of Cloud Monitoring's aggregation: per-series alignment into
# fixed-width buckets, then optional cross-series reduction grouped by label
# fields. Scalar values (double / int64 / bool) are combined arithmetically;
# distribution values are merged histogram-wise, and a percentile aligner /
# reducer reads a value off the (merged) distribution. RATE/DELTA are
# approximated (sum over the period, or sum/period).

_PERCENTILES = {"05": 5.0, "50": 50.0, "95": 95.0, "99": 99.0}


def _aggregate(
    series_list: list[dict[str, Any]], aggregation: dict[str, Any], anchor: float | None
) -> list[dict[str, Any]]:
    period = _duration_seconds(aggregation.get("alignment_period"))
    aligner = aggregation.get("per_series_aligner") or "ALIGN_NONE"
    reducer = aggregation.get("cross_series_reducer") or "REDUCE_NONE"
    group_by = aggregation.get("group_by_fields") or []
    aligned = [_align_series(s, aligner, period, anchor) for s in series_list]
    if reducer in ("", "REDUCE_NONE"):
        return aligned
    return _reduce_series(aligned, reducer, group_by)


def _align_series(
    series: dict[str, Any], aligner: str, period: float | None, anchor: float | None
) -> dict[str, Any]:
    if aligner in ("", "ALIGN_NONE") or not period:
        return series
    buckets: dict[float, list[dict[str, Any]]] = {}
    for point in series.get("points", []):
        moment = _epoch(point.get("interval", {}).get("end_time"))
        if moment is None:
            continue
        base = anchor if anchor is not None else moment
        index = int((base - moment) // period)
        bucket_end = base - index * period
        buckets.setdefault(bucket_end, []).append(point)
    points = [
        _point_at(
            bucket_end - period,
            bucket_end,
            _combine(buckets[bucket_end], aligner, period),
        )
        for bucket_end in sorted(buckets, reverse=True)
    ]
    return {
        "metric": series.get("metric", {}),
        "resource": series.get("resource", {}),
        "points": points,
    }


def _reduce_series(
    aligned: list[dict[str, Any]], reducer: str, group_by: list[str]
) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for series in aligned:
        key = tuple(_extract_field(series, field) for field in group_by)
        groups.setdefault(key, []).append(series)

    result: list[dict[str, Any]] = []
    for members in groups.values():
        by_end: dict[str, list[dict[str, Any]]] = {}
        for series in members:
            for point in series.get("points", []):
                end = point.get("interval", {}).get("end_time")
                if end is not None:
                    by_end.setdefault(end, []).append(point)
        points = [
            _point_at(None, end, _combine(by_end[end], reducer, None))
            for end in sorted(by_end, reverse=True)
        ]
        result.append(_grouped_series(members[0], group_by, points))
    return result


def _combine(
    points: list[dict[str, Any]], op: str, period: float | None
) -> dict[str, Any]:
    """Combine a bucket of points with an aligner/reducer into one TypedValue."""
    percentile = _percentile_target(op)
    dists = [d for p in points if (d := _distribution(p)) is not None]
    if dists:
        merged = _merge_distributions(dists)
        if percentile is not None:
            return {"double_value": _distribution_percentile(merged, percentile)}
        return {"distribution_value": merged}
    values = [v for p in points if (v := _scalar(p)) is not None]
    if not values:
        return {"double_value": 0.0}
    nums = [v for v, _ in values]
    all_int = all(is_int for _, is_int in values)
    if percentile is not None:
        return {"double_value": _quantile(nums, percentile)}
    if op.endswith("_MEAN"):
        return {"double_value": sum(nums) / len(nums)}
    if op.endswith("_MIN"):
        return _typed_value(min(nums), all_int)
    if op.endswith("_MAX"):
        return _typed_value(max(nums), all_int)
    if op.endswith("_COUNT"):
        return {"int64_value": len(nums)}
    if op == "ALIGN_RATE" and period:
        return {"double_value": sum(nums) / period}
    if op in ("ALIGN_SUM", "ALIGN_DELTA", "REDUCE_SUM"):
        return _typed_value(sum(nums), all_int)
    return {"double_value": sum(nums) / len(nums)}  # unknown op: mean


def _grouped_series(
    sample: dict[str, Any], group_by: list[str], points: list[dict[str, Any]]
) -> dict[str, Any]:
    metric: dict[str, Any] = {"type": sample.get("metric", {}).get("type", "")}
    resource: dict[str, Any] = {"type": sample.get("resource", {}).get("type", "")}
    metric_labels, resource_labels = {}, {}
    for field in group_by:
        target, key = _label_target(field)
        if target == "metric" and key:
            value = sample.get("metric", {}).get("labels", {}).get(key)
            if value is not None:
                metric_labels[key] = value
        elif target == "resource" and key:
            value = sample.get("resource", {}).get("labels", {}).get(key)
            if value is not None:
                resource_labels[key] = value
    if metric_labels:
        metric["labels"] = metric_labels
    if resource_labels:
        resource["labels"] = resource_labels
    return {"metric": metric, "resource": resource, "points": points}


def _extract_field(series: dict[str, Any], field: str) -> Any:
    if field == "resource.type":
        return series.get("resource", {}).get("type")
    if field == "metric.type":
        return series.get("metric", {}).get("type")
    target, key = _label_target(field)
    if target and key:
        return series.get(target, {}).get("labels", {}).get(key)
    return None


def _label_target(field: str) -> tuple[str | None, str | None]:
    parts = field.split(".")
    if (
        len(parts) >= 3
        and parts[0] in ("metric", "resource")
        and parts[1]
        in (
            "label",
            "labels",
        )
    ):
        return parts[0], ".".join(parts[2:])
    return None, None


def _scalar(point: dict[str, Any]) -> tuple[float, bool] | None:
    value = point.get("value", {})
    if "double_value" in value:
        return float(value["double_value"]), False
    if "int64_value" in value:
        return float(value["int64_value"]), True
    if "bool_value" in value:
        return (1.0 if value["bool_value"] else 0.0), True
    return None


def _distribution(point: dict[str, Any]) -> dict[str, Any] | None:
    return point.get("value", {}).get("distribution_value")


def _point_at(
    start: float | None, end: float | str, value: dict[str, Any]
) -> dict[str, Any]:
    interval = {"end_time": _rfc3339(end) if isinstance(end, (int, float)) else end}
    if start is not None:
        interval["start_time"] = _rfc3339(start)
    return {"interval": interval, "value": value}


def _typed_value(value: float, is_int: bool) -> dict[str, Any]:
    if is_int:
        return {"int64_value": int(round(value))}
    return {"double_value": value}


def _percentile_target(op: str) -> float | None:
    for suffix, pct in _PERCENTILES.items():
        if op.endswith("PERCENTILE_" + suffix):
            return pct
    return None


def _quantile(nums: list[float], pct: float) -> float:
    ordered = sorted(nums)
    if not ordered:
        return 0.0
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _merge_distributions(dists: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine histograms: add counts and bucket_counts, pool mean and deviation."""
    total = sum(int(d.get("count", 0) or 0) for d in dists)
    mean = (
        sum(int(d.get("count", 0) or 0) * float(d.get("mean", 0.0)) for d in dists)
        / total
        if total
        else 0.0
    )
    deviation = 0.0
    bucket_counts: list[int] = []
    for dist in dists:
        count = int(dist.get("count", 0) or 0)
        deviation += float(dist.get("sum_of_squared_deviation", 0.0))
        deviation += count * (float(dist.get("mean", 0.0)) - mean) ** 2
        for index, raw in enumerate(dist.get("bucket_counts", [])):
            if index < len(bucket_counts):
                bucket_counts[index] += int(raw)
            else:
                bucket_counts.append(int(raw))
    merged: dict[str, Any] = {
        "count": total,
        "mean": mean,
        "sum_of_squared_deviation": deviation,
        "bucket_counts": bucket_counts,
    }
    options = next(
        (d.get("bucket_options") for d in dists if d.get("bucket_options")), None
    )
    if options:
        merged["bucket_options"] = options
    return merged


def _distribution_percentile(dist: dict[str, Any], pct: float) -> float:
    counts = [int(c) for c in dist.get("bucket_counts", [])]
    total = sum(counts)
    if total == 0:
        return float(dist.get("mean", 0.0))
    bounds = _bucket_bounds(dist.get("bucket_options", {}), len(counts))
    target = pct / 100.0 * total
    cumulative = 0
    for index, count in enumerate(counts):
        cumulative += count
        if cumulative >= target:
            lower = (
                bounds[index - 1]
                if 0 < index <= len(bounds)
                else (bounds[0] if bounds else 0.0)
            )
            upper = bounds[index] if index < len(bounds) else lower
            return (lower + upper) / 2.0
    return bounds[-1] if bounds else float(dist.get("mean", 0.0))


def _bucket_bounds(options: dict[str, Any], count: int) -> list[float]:
    if "explicit_buckets" in options:
        return [float(b) for b in options["explicit_buckets"].get("bounds", [])]
    if "linear_buckets" in options:
        linear = options["linear_buckets"]
        num = int(linear.get("num_finite_buckets", 0))
        width = float(linear.get("width", 0.0))
        offset = float(linear.get("offset", 0.0))
        return [offset + width * i for i in range(num + 1)]
    if "exponential_buckets" in options:
        exp = options["exponential_buckets"]
        num = int(exp.get("num_finite_buckets", 0))
        growth = float(exp.get("growth_factor", 1.0))
        scale = float(exp.get("scale", 1.0))
        return [scale * growth**i for i in range(num + 1)]
    return []


def _duration_seconds(duration: Any) -> float | None:
    if not duration:
        return None
    text = str(duration)
    if text.endswith("s"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def _rfc3339(epoch: float) -> str:
    moment = datetime.fromtimestamp(epoch, tz=timezone.utc)
    if moment.microsecond:
        return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


#: Project-keyed backends, inspectable via ``get_backend("monitoring")[project]``.
monitoring_backends: BackendDict[MonitoringBackend] = BackendDict(
    MonitoringBackend, "monitoring"
)
