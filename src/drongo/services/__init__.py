"""Service implementations.

Importing this package imports every service subpackage, and each one registers
itself with :mod:`drongo.core.registry` as a side effect. Add a new service by
creating a subpackage here and importing it below.
"""

from __future__ import annotations

from drongo.services import (
    bigquery,
    bigtable,
    cloudfunctions,
    cloudrun,
    cloudscheduler,
    cloudtasks,
    datastore,
    documentai,
    firestore,
    iam,
    kms,
    logging,
    memorystore,
    monitoring,
    pubsub,
    resourcemanager,
    secretmanager,
    storage,
    storagetransfer,
    vertexai,
)

__all__ = [
    "bigquery",
    "bigtable",
    "cloudfunctions",
    "cloudrun",
    "cloudscheduler",
    "cloudtasks",
    "datastore",
    "documentai",
    "firestore",
    "iam",
    "kms",
    "logging",
    "memorystore",
    "monitoring",
    "pubsub",
    "resourcemanager",
    "secretmanager",
    "storage",
    "storagetransfer",
    "vertexai",
]
