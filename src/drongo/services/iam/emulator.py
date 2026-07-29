"""In-process gRPC emulator for IAM Admin (service accounts + keys).

IAM Admin's client is gRPC-only: no REST transport and no emulator env var. So
drongo runs a real in-process gRPC server backed by :class:`IAMBackend` and the
service's patchers inject a transport pointing at it (see
``force_local_grpc_patchers``). The user's normal ``IAMClient`` works unchanged.

Handlers are thin adapters over the per-project backend; this module owns all IAM
proto handling. Required libraries (``grpcio`` + ``google-cloud-iam``) are
optional; if absent, :meth:`start` no-ops and :attr:`address` is ``None``, so the
patchers leave the real client alone.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from drongo.core.emulator import BaseEmulator
from drongo.core.exceptions import DrongoHttpError
from drongo.services.iam.models import IAMBackend, ServiceAccount, iam_backends


class IAMEmulator(BaseEmulator):
    """Serves the IAM Admin gRPC API from an in-process server."""

    def __init__(self, backends: Any = iam_backends) -> None:
        self._backends = backends
        self._server: Any = None
        self._port: int | None = None
        self._available: bool | None = None
        self._grpc: Any = None
        self._it: Any = None
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
        # The server is reused across scopes (backend state is reset by the
        # controller); there is no env var to restore, so nothing to undo.
        return

    def _boot(self) -> bool:
        try:
            import grpc
            from google.cloud.iam_admin_v1 import types as it
            from google.protobuf import empty_pb2
        except Exception:
            return False
        from concurrent import futures

        self._grpc, self._it, self._empty = grpc, it, empty_pb2
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
        server.add_generic_rpc_handlers(self._build_handlers())
        self._port = server.add_insecure_port("localhost:0")
        server.start()
        self._server = server
        return True

    # -- routing -----------------------------------------------------------

    def _build_handlers(self) -> Any:
        grpc, it, empty = self._grpc, self._it, self._empty
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

        handlers = {
            "CreateServiceAccount": unary(
                it.CreateServiceAccountRequest, it.ServiceAccount, self._create
            ),
            "GetServiceAccount": unary(
                it.GetServiceAccountRequest, it.ServiceAccount, self._get
            ),
            "ListServiceAccounts": unary(
                it.ListServiceAccountsRequest,
                it.ListServiceAccountsResponse,
                self._list,
            ),
            "DeleteServiceAccount": unary(
                it.DeleteServiceAccountRequest, empty.Empty, self._delete
            ),
            "DisableServiceAccount": unary(
                it.DisableServiceAccountRequest, empty.Empty, self._disable
            ),
            "EnableServiceAccount": unary(
                it.EnableServiceAccountRequest, empty.Empty, self._enable
            ),
            "CreateServiceAccountKey": unary(
                it.CreateServiceAccountKeyRequest,
                it.ServiceAccountKey,
                self._create_key,
            ),
            "ListServiceAccountKeys": unary(
                it.ListServiceAccountKeysRequest,
                it.ListServiceAccountKeysResponse,
                self._list_keys,
            ),
            "GetServiceAccountKey": unary(
                it.GetServiceAccountKeyRequest, it.ServiceAccountKey, self._get_key
            ),
            "DeleteServiceAccountKey": unary(
                it.DeleteServiceAccountKeyRequest, empty.Empty, self._delete_key
            ),
        }
        return (
            grpc.method_handlers_generic_handler("google.iam.admin.v1.IAM", handlers),
        )

    # -- name parsing ------------------------------------------------------

    @staticmethod
    def _project(name: str) -> str:
        return name.split("/")[1]

    @staticmethod
    def _sa_identifier(name: str) -> str:
        # projects/<p>/serviceAccounts/<email-or-uid>[/keys/<id>]
        return name.split("/")[3]

    def _backend(self, name: str) -> IAMBackend:
        return self._backends[self._project(name)]

    # -- service-account handlers ------------------------------------------

    def _to_account(self, account: ServiceAccount) -> Any:
        return self._it.ServiceAccount(
            name=account.name,
            project_id=account.project,
            unique_id=account.unique_id,
            email=account.email,
            display_name=account.display_name,
            description=account.description,
            oauth2_client_id=account.unique_id,
            disabled=account.disabled,
        )

    def _create(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        account = backend.create_service_account(
            request.account_id,
            request.service_account.display_name,
            request.service_account.description,
        )
        return self._to_account(account)

    def _get(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        return self._to_account(
            backend.get_service_account(self._sa_identifier(request.name))
        )

    def _list(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        return self._it.ListServiceAccountsResponse(
            accounts=[self._to_account(a) for a in backend.list_service_accounts()]
        )

    def _delete(self, request: Any, context: Any) -> Any:
        self._backend(request.name).delete_service_account(
            self._sa_identifier(request.name)
        )
        return self._empty.Empty()

    def _disable(self, request: Any, context: Any) -> Any:
        self._backend(request.name).set_disabled(
            self._sa_identifier(request.name), True
        )
        return self._empty.Empty()

    def _enable(self, request: Any, context: Any) -> Any:
        self._backend(request.name).set_disabled(
            self._sa_identifier(request.name), False
        )
        return self._empty.Empty()

    # -- key handlers ------------------------------------------------------

    def _to_key(self, key: Any) -> Any:
        return self._it.ServiceAccountKey(
            name=key.name,
            private_key_type=key.private_key_type,
            key_algorithm=key.key_algorithm,
            private_key_data=key.private_key_data,
            public_key_data=key.public_key_data,
            disabled=key.disabled,
        )

    def _create_key(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        key = backend.create_key(
            self._sa_identifier(request.name),
            int(request.private_key_type),
            int(request.key_algorithm),
        )
        return self._to_key(key)

    def _list_keys(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        keys = backend.list_keys(self._sa_identifier(request.name))
        return self._it.ListServiceAccountKeysResponse(
            keys=[self._to_key(k) for k in keys]
        )

    def _get_key(self, request: Any, context: Any) -> Any:
        backend = self._backend(request.name)
        key_id = request.name.split("/keys/")[-1]
        return self._to_key(backend.get_key(self._sa_identifier(request.name), key_id))

    def _delete_key(self, request: Any, context: Any) -> Any:
        key_id = request.name.split("/keys/")[-1]
        self._backend(request.name).delete_key(
            self._sa_identifier(request.name), key_id
        )
        return self._empty.Empty()
