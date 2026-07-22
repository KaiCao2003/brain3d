"""Unit coverage for worker-owned repository construction."""

from __future__ import annotations

from mouse_brain_planner.gui.workers.atlas_worker import (
    AtlasCatalogWorker,
    AtlasLoadWorker,
    AtlasRepositoryProtocol,
)


def _failing_repository_factory() -> AtlasRepositoryProtocol:
    raise RuntimeError("repository construction failed")


def test_repository_factory_failures_use_existing_worker_failure_signals() -> None:
    catalog_worker = AtlasCatalogWorker(_failing_repository_factory)
    load_worker = AtlasLoadWorker(_failing_repository_factory, "allen_mouse_25um")
    catalog_failures: list[str] = []
    load_failures: list[str] = []
    load_cancellations: list[str] = []
    catalog_finished: list[bool] = []
    load_finished: list[bool] = []
    catalog_worker.failed.connect(catalog_failures.append)
    catalog_worker.finished.connect(lambda: catalog_finished.append(True))
    load_worker.failed.connect(load_failures.append)
    load_worker.cancelled.connect(load_cancellations.append)
    load_worker.finished.connect(lambda: load_finished.append(True))

    catalog_worker.run()
    load_worker.run()

    expected = ["RuntimeError: repository construction failed"]
    assert catalog_failures == expected
    assert load_failures == expected
    assert load_cancellations == []
    assert catalog_finished == [True]
    assert load_finished == [True]


def test_pre_cancelled_workers_do_not_construct_repository_and_always_finish() -> None:
    factory_calls: list[bool] = []

    def unexpected_factory() -> AtlasRepositoryProtocol:
        factory_calls.append(True)
        raise AssertionError("pre-cancelled worker constructed a repository")

    catalog_worker = AtlasCatalogWorker(unexpected_factory)
    load_worker = AtlasLoadWorker(unexpected_factory, "allen_mouse_25um")
    catalog_failures: list[str] = []
    load_failures: list[str] = []
    load_cancellations: list[str] = []
    catalog_finished: list[bool] = []
    load_finished: list[bool] = []
    catalog_worker.failed.connect(catalog_failures.append)
    catalog_worker.finished.connect(lambda: catalog_finished.append(True))
    load_worker.failed.connect(load_failures.append)
    load_worker.cancelled.connect(load_cancellations.append)
    load_worker.finished.connect(lambda: load_finished.append(True))

    catalog_worker.request_cancel()
    load_worker.request_cancel()
    catalog_worker.run()
    load_worker.run()

    assert factory_calls == []
    assert catalog_failures == []
    assert load_failures == []
    assert load_cancellations == ["atlas acquisition cancelled: allen_mouse_25um"]
    assert catalog_finished == [True]
    assert load_finished == [True]


def test_callable_injected_repository_is_not_mistaken_for_factory() -> None:
    class CallableRepository:
        def __call__(self) -> AtlasRepositoryProtocol:
            raise AssertionError("injected repository was called as a factory")

        def open(self, *args: object, **kwargs: object) -> object:
            del args, kwargs
            raise RuntimeError("injected open method reached")

    worker = AtlasLoadWorker(
        CallableRepository(),  # type: ignore[arg-type]  # Worker only needs open().
        "allen_mouse_25um",
    )
    failures: list[str] = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == ["RuntimeError: injected open method reached"]
