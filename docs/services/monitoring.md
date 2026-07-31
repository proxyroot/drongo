# Cloud Monitoring

- **Client:** `google-cloud-monitoring` (`monitoring_v3` service clients)
- **Transport:** gRPC only. Monitoring ships no REST transport and honors no
  emulator env var, so drongo runs an in-process gRPC emulator and injects a
  transport pointing the default clients at it.
- **Backend:** per-project.

Use the normal clients with no `transport` argument. Covers **metrics** (metric
descriptors + time series, with aggregation), **alerting** (alert policies +
notification channels), and the **uptime check**, **group**, **snooze** and
**service/SLO** clients.

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
in the filter string and by the requested interval. Passing an `aggregation`
applies per-series alignment (mean / sum / min / max / count / rate / delta /
percentile over the alignment period) and, when a `cross_series_reducer` and
`group_by_fields` are set, reduction across the series in each group. Scalar
values are combined arithmetically; distribution values are merged histogram-wise
(and a percentile aligner reads a value off the merged distribution).

Beyond metrics and alerting, the uptime check, group, snooze and
service/SLO (`ServiceMonitoring`) clients work too:

```python
@mock_gcp
def test_uptime_and_slo():
    from google.cloud import monitoring_v3

    project = "projects/my-project"

    uptime = monitoring_v3.UptimeCheckServiceClient()
    uptime.create_uptime_check_config(
        parent=project,
        uptime_check_config=monitoring_v3.UptimeCheckConfig(display_name="ping"),
    )

    services = monitoring_v3.ServiceMonitoringServiceClient()
    service = services.create_service(
        parent=project, service=monitoring_v3.Service(display_name="checkout")
    )
    services.create_service_level_objective(
        parent=service.name,
        service_level_objective=monitoring_v3.ServiceLevelObjective(
            display_name="99.9", goal=0.999
        ),
    )
```

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
| Aggregation: scalar alignment + cross-series reduction | Supported |
| Aggregation: distribution merge + percentile | Supported |
| Alert policies: create / get / list / update / delete | Supported |
| Notification channels: create / get / list / update / delete | Supported |
| Uptime check configs: create / get / list / update / delete | Supported |
| Groups: create / get / list / update / delete | Supported |
| Snoozes: create / get / list / update | Supported |
| Services + SLOs: create / get / list / update / delete | Supported |
| MQL query (separate `QueryService`) | Planned |
