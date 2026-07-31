# Cloud Monitoring

- **Client:** `google-cloud-monitoring` (`monitoring_v3` service clients)
- **Transport:** gRPC only. Monitoring ships no REST transport and honors no
  emulator env var, so drongo runs an in-process gRPC emulator and injects a
  transport pointing the default clients at it.
- **Backend:** per-project.

Use the normal clients with no `transport` argument. Covers **metrics** (metric
descriptors + time series) and **alerting** (alert policies + notification
channels).

## Metric descriptors and time series

```python
from drongo import mock_gcp


@mock_gcp
def test_metrics():
    from google.api import metric_pb2
    from google.cloud import monitoring_v3

    project = "projects/my-project"
    client = monitoring_v3.MetricServiceClient()

    client.create_metric_descriptor(
        name=project,
        metric_descriptor=metric_pb2.MetricDescriptor(
            type="custom.googleapis.com/my_metric",
            metric_kind=metric_pb2.MetricDescriptor.GAUGE,
            value_type=metric_pb2.MetricDescriptor.DOUBLE,
        ),
    )

    now = 1_700_000_000
    series = monitoring_v3.TimeSeries()
    series.metric.type = "custom.googleapis.com/my_metric"
    series.resource.type = "global"
    series.points = [
        monitoring_v3.Point(
            interval=monitoring_v3.TimeInterval(end_time={"seconds": now}),
            value=monitoring_v3.TypedValue(double_value=42.5),
        )
    ]
    client.create_time_series(name=project, time_series=[series])

    results = list(
        client.list_time_series(
            name=project,
            filter='metric.type = "custom.googleapis.com/my_metric"',
            interval=monitoring_v3.TimeInterval(
                start_time={"seconds": now - 3600}, end_time={"seconds": now + 3600}
            ),
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        )
    )
    assert results[0].points[0].value.double_value == 42.5
```

`list_time_series` filters the written points by `metric.type` / `resource.type`
in the filter string and by the requested interval. Aggregation (alignment /
reduction) is not applied - points are returned as written.

## Alert policies and notification channels

```python
@mock_gcp
def test_alerting():
    from google.cloud import monitoring_v3
    from google.protobuf import field_mask_pb2

    project = "projects/my-project"
    alerts = monitoring_v3.AlertPolicyServiceClient()

    policy = alerts.create_alert_policy(
        name=project,
        alert_policy=monitoring_v3.AlertPolicy(display_name="High CPU"),
    )
    policy.display_name = "Higher CPU"
    alerts.update_alert_policy(
        alert_policy=policy,
        update_mask=field_mask_pb2.FieldMask(paths=["display_name"]),
    )
    assert alerts.get_alert_policy(name=policy.name).display_name == "Higher CPU"

    channels = monitoring_v3.NotificationChannelServiceClient()
    channels.create_notification_channel(
        name=project,
        notification_channel=monitoring_v3.NotificationChannel(
            type_="email", labels={"email_address": "ops@example.com"}
        ),
    )
```

Missing resources raise `google.api_core.exceptions.NotFound`.

## Coverage

| Operation | Status |
| --- | --- |
| Metric descriptors: create / get / list / delete | Supported |
| Time series: write (`create_time_series`) | Supported |
| Time series: read (`list_time_series`, filter + interval) | Supported |
| Alert policies: create / get / list / update / delete | Supported |
| Notification channels: create / get / list / update / delete | Supported |
| Time-series aggregation (alignment / reduction), MQL query | Planned |
| Uptime checks, SLOs, groups, snoozes | Planned |
