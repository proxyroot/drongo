"""Cloud Monitoring tests using the real monitoring_v3 clients (in-process gRPC)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

pytest.importorskip("google.cloud.monitoring_v3")

pytestmark = pytest.mark.usefixtures("drongo")

PROJECT = "test-project"
PN = f"projects/{PROJECT}"


def _metric_client():
    from google.cloud import monitoring_v3

    return monitoring_v3.MetricServiceClient()


def _alert_client():
    from google.cloud import monitoring_v3

    return monitoring_v3.AlertPolicyServiceClient()


def _channel_client():
    from google.cloud import monitoring_v3

    return monitoring_v3.NotificationChannelServiceClient()


# -- metric descriptors -----------------------------------------------------


def test_metric_descriptor_crud() -> None:
    from google.api import metric_pb2

    client = _metric_client()
    descriptor = metric_pb2.MetricDescriptor(
        type="custom.googleapis.com/my_metric",
        display_name="My Metric",
        metric_kind=metric_pb2.MetricDescriptor.GAUGE,
        value_type=metric_pb2.MetricDescriptor.DOUBLE,
    )
    created = client.create_metric_descriptor(name=PN, metric_descriptor=descriptor)
    assert created.name == f"{PN}/metricDescriptors/custom.googleapis.com/my_metric"
    assert created.metric_kind == metric_pb2.MetricDescriptor.GAUGE

    fetched = client.get_metric_descriptor(name=created.name)
    assert fetched.display_name == "My Metric"
    assert [d.type for d in client.list_metric_descriptors(name=PN)] == [
        "custom.googleapis.com/my_metric"
    ]

    client.delete_metric_descriptor(name=created.name)
    assert list(client.list_metric_descriptors(name=PN)) == []


def test_get_missing_metric_descriptor_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _metric_client().get_metric_descriptor(name=f"{PN}/metricDescriptors/ghost")


# -- time series ------------------------------------------------------------


def test_write_and_read_time_series() -> None:
    from google.cloud import monitoring_v3

    client = _metric_client()
    now = 1_700_000_000
    series = monitoring_v3.TimeSeries()
    series.metric.type = "custom.googleapis.com/my_metric"
    series.resource.type = "global"
    series.resource.labels["project_id"] = PROJECT
    series.points = [
        monitoring_v3.Point(
            interval=monitoring_v3.TimeInterval(end_time={"seconds": now}),
            value=monitoring_v3.TypedValue(double_value=42.5),
        )
    ]
    client.create_time_series(name=PN, time_series=[series])

    interval = monitoring_v3.TimeInterval(
        start_time={"seconds": now - 3600}, end_time={"seconds": now + 3600}
    )
    results = list(
        client.list_time_series(
            name=PN,
            filter='metric.type = "custom.googleapis.com/my_metric"',
            interval=interval,
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        )
    )
    assert len(results) == 1
    assert results[0].points[0].value.double_value == 42.5


def test_list_time_series_filters_by_metric_type() -> None:
    from google.cloud import monitoring_v3

    client = _metric_client()
    now = 1_700_000_000
    for metric_type in ("custom.googleapis.com/a", "custom.googleapis.com/b"):
        series = monitoring_v3.TimeSeries()
        series.metric.type = metric_type
        series.resource.type = "global"
        series.points = [
            monitoring_v3.Point(
                interval=monitoring_v3.TimeInterval(end_time={"seconds": now}),
                value=monitoring_v3.TypedValue(int64_value=1),
            )
        ]
        client.create_time_series(name=PN, time_series=[series])

    interval = monitoring_v3.TimeInterval(
        start_time={"seconds": now - 60}, end_time={"seconds": now + 60}
    )
    results = list(
        client.list_time_series(
            name=PN,
            filter='metric.type = "custom.googleapis.com/a"',
            interval=interval,
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        )
    )
    assert [r.metric.type for r in results] == ["custom.googleapis.com/a"]


def _write_point(client, metric_type, labels, seconds, value) -> None:
    from google.cloud import monitoring_v3

    series = monitoring_v3.TimeSeries()
    series.metric.type = metric_type
    series.resource.type = "global"
    for key, val in labels.items():
        series.resource.labels[key] = val
    series.points = [
        monitoring_v3.Point(
            interval=monitoring_v3.TimeInterval(end_time={"seconds": seconds}),
            value=monitoring_v3.TypedValue(double_value=value),
        )
    ]
    client.create_time_series(name=PN, time_series=[series])


def test_list_time_series_aligns_per_series() -> None:
    from google.cloud import monitoring_v3

    client = _metric_client()
    now = 1_700_000_000
    metric = "custom.googleapis.com/aligned"
    _write_point(client, metric, {"zone": "us"}, now - 100, 10.0)
    _write_point(client, metric, {"zone": "us"}, now - 250, 20.0)  # same 300s bucket

    request = monitoring_v3.ListTimeSeriesRequest(
        name=PN,
        filter=f'metric.type = "{metric}"',
        interval=monitoring_v3.TimeInterval(
            start_time={"seconds": now - 600}, end_time={"seconds": now}
        ),
        view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        aggregation=monitoring_v3.Aggregation(
            alignment_period={"seconds": 300},
            per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
        ),
    )
    (result,) = list(client.list_time_series(request=request))
    # The two points fall in one 300s bucket: mean(10, 20) == 15.
    assert result.points[0].value.double_value == 15.0


def test_list_time_series_reduces_across_series() -> None:
    from google.cloud import monitoring_v3

    client = _metric_client()
    now = 1_700_000_000
    metric = "custom.googleapis.com/reduced"
    # Two distinct series in zone "us" (different instance), one in "eu".
    _write_point(client, metric, {"zone": "us", "instance": "a"}, now - 100, 15.0)
    _write_point(client, metric, {"zone": "us", "instance": "b"}, now - 100, 30.0)
    _write_point(client, metric, {"zone": "eu", "instance": "c"}, now - 100, 7.0)

    request = monitoring_v3.ListTimeSeriesRequest(
        name=PN,
        filter=f'metric.type = "{metric}"',
        interval=monitoring_v3.TimeInterval(
            start_time={"seconds": now - 600}, end_time={"seconds": now}
        ),
        view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        aggregation=monitoring_v3.Aggregation(
            alignment_period={"seconds": 300},
            per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
            cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_SUM,
            group_by_fields=["resource.label.zone"],
        ),
    )
    results = list(client.list_time_series(request=request))
    by_zone = {
        r.resource.labels["zone"]: r.points[0].value.double_value for r in results
    }
    assert by_zone == {"us": 45.0, "eu": 7.0}


# -- alert policies ---------------------------------------------------------


def test_alert_policy_crud_and_update() -> None:
    from google.cloud import monitoring_v3
    from google.protobuf import field_mask_pb2

    client = _alert_client()
    policy = client.create_alert_policy(
        name=PN,
        alert_policy=monitoring_v3.AlertPolicy(
            display_name="High CPU",
            combiner=monitoring_v3.AlertPolicy.ConditionCombinerType.OR,
        ),
    )
    assert policy.name.startswith(f"{PN}/alertPolicies/")
    assert client.get_alert_policy(name=policy.name).display_name == "High CPU"

    policy.display_name = "Higher CPU"
    updated = client.update_alert_policy(
        alert_policy=policy,
        update_mask=field_mask_pb2.FieldMask(paths=["display_name"]),
    )
    assert updated.display_name == "Higher CPU"
    assert client.get_alert_policy(name=policy.name).display_name == "Higher CPU"

    client.delete_alert_policy(name=policy.name)
    assert list(client.list_alert_policies(name=PN)) == []


# -- notification channels --------------------------------------------------


def test_notification_channel_crud() -> None:
    from google.cloud import monitoring_v3

    client = _channel_client()
    channel = client.create_notification_channel(
        name=PN,
        notification_channel=monitoring_v3.NotificationChannel(
            type_="email",
            display_name="Ops",
            labels={"email_address": "ops@example.com"},
        ),
    )
    assert channel.name.startswith(f"{PN}/notificationChannels/")

    fetched = client.get_notification_channel(name=channel.name)
    assert dict(fetched.labels) == {"email_address": "ops@example.com"}
    assert [c.display_name for c in client.list_notification_channels(name=PN)] == [
        "Ops"
    ]

    client.delete_notification_channel(name=channel.name)
    assert list(client.list_notification_channels(name=PN)) == []
