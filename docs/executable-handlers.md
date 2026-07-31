# Executable handlers

By default drongo mocks the **API surface**: it records state and returns
realistic responses, but it does not run your workload. That is enough for many
tests, and it mirrors how moto behaves for most services.

Sometimes you want more: you want the mock to **actually run your code** when a
job runs, a task dispatches, or a message is published, so a test exercises the
full producer -> consumer path in-process. That is what **executable handlers**
are for.

The idea is uniform across services: **register a Python callable, and drongo
invokes it when the corresponding action fires.** Handlers are opt-in. If you do
not register one, behavior is exactly as before.

Every service offers the same two registration styles:

- a **decorator**, `@<service>.<thing>_handler(name)`, and
- a **backend method**, `get_backend("<service>")[project].register_handler(name, fn)`.

Handlers are bound to the in-memory backend, so they are cleared automatically
when the `mock_gcp` scope resets between tests.

| Service | Register | Invoked when | Handler receives |
| --- | --- | --- | --- |
| Cloud Run Jobs | `cloudrun.job_handler(job)` | `run_job` | nothing (zero-arg) |
| Cloud Tasks | `cloudtasks.task_handler(queue)` | `run_task`; `create_task` on a running queue | a `TaskRequest` |
| Pub/Sub | `pubsub.subscription_handler(sub)` | `publish` fans out to the subscription | a `PushMessage` |
| Cloud Scheduler | `cloudscheduler.job_handler(job)` | `run_job` | a `SchedulerRequest` |
| Vertex AI | `vertexai.prediction_handler(endpoint)` | `predict` on the endpoint | `(instances, parameters)` |

## Cloud Run Jobs

`run_job` invokes the registered function. If it raises, the execution is marked
failed (Cloud Run reports the failure on the `Execution`, it does not fail the
operation), so you can assert on `failed_count` / `conditions`.

```python
from drongo import mock_gcp, cloudrun

PARENT = "projects/p/locations/us-central1"
JOB = f"{PARENT}/jobs/nightly"


@mock_gcp
def test_job_runs_real_code():
    from google.cloud import run_v2

    ran = []

    @cloudrun.job_handler(JOB)
    def nightly():
        ran.append("did the work")  # your real logic

    jobs = run_v2.JobsClient()
    job = run_v2.Job(
        template=run_v2.ExecutionTemplate(
            template=run_v2.TaskTemplate(
                containers=[run_v2.Container(image="gcr.io/p/img")]
            )
        )
    )
    jobs.create_job(
        request={"parent": PARENT, "job": job, "job_id": "nightly"}
    ).result()

    execution = jobs.run_job(request={"name": JOB}).result()

    assert ran == ["did the work"]
    assert execution.succeeded_count == 1
```

## Cloud Tasks

The handler receives a `TaskRequest` describing the task's HTTP target (`url`,
`method`, `headers`, and `body` decoded to `bytes`). A **running** queue delivers
on `create_task`, so a producer-only test still exercises the consumer;
`run_task` always delivers. A raising handler is recorded on the task's
`last_error` rather than raised to the producer, exactly as a real queue does not
surface a consumer failure to the caller of `create_task`.

```python
from drongo import mock_gcp, cloudtasks

PARENT = "projects/p/locations/us-central1"
QUEUE = f"{PARENT}/queues/emails"


@mock_gcp
def test_task_runs_consumer():
    from google.cloud import tasks_v2

    delivered = []

    @cloudtasks.task_handler(QUEUE)
    def handle(request):
        assert request.method == "POST"
        delivered.append(request.body)

    client = tasks_v2.CloudTasksClient()
    client.create_queue(request={"parent": PARENT, "queue": {"name": QUEUE}})

    client.create_task(
        request={
            "parent": QUEUE,
            "task": {
                "http_request": {
                    "url": "https://example.com/handler",
                    "http_method": "POST",
                    "body": b"payload",
                }
            },
        }
    )

    assert delivered == [b"payload"]  # delivered on create (queue is running)
```

## Pub/Sub

The handler receives a `PushMessage` (`data`, `attributes`, `message_id`,
`ordering_key`, `publish_time`). Returning normally **acks** the message; raising
or calling `message.nack()` returns it to the pullable backlog, so push and pull
coexist.

```python
from drongo import mock_gcp, pubsub

TOPIC = "projects/p/topics/orders"
SUB = "projects/p/subscriptions/worker"


@mock_gcp
def test_publish_pushes_to_subscriber():
    from google.cloud import pubsub_v1

    seen = []

    @pubsub.subscription_handler(SUB)
    def on_message(message):
        seen.append(message.data)  # returning acks; raising redelivers

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    publisher.create_topic(request={"name": TOPIC})
    subscriber.create_subscription(request={"name": SUB, "topic": TOPIC})

    publisher.publish(TOPIC, b'{"id": 1}', kind="order").result()

    assert seen == [b'{"id": 1}']
```

## Registering programmatically

The `@..._handler` decorators are sugar over each backend's `register_handler`,
which you can call directly, for example to register dynamically or from a
fixture:

```python
from drongo import get_backend

get_backend("cloudrun")["my-project"].register_handler(job_name, my_fn)
get_backend("cloudtasks")["my-project"].register_handler(queue_name, my_fn)
get_backend("pubsub")["my-project"].register_handler(sub_name, my_fn)

# Vertex AI's predict handler has its own name:
get_backend("vertexai")["my-project"].register_prediction_handler(endpoint_name, my_fn)
```
