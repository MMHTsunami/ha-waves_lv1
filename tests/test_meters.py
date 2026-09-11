import asyncio
from types import SimpleNamespace

from custom_components.waves_lv1.coordinator import LV1Coordinator
from custom_components.waves_lv1.protocol.osc import OscArg, OscMessage


def test_handle_meters_parses_triplets() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        coordinator = LV1Coordinator.__new__(LV1Coordinator)
        coordinator.entry_id = "entry"
        coordinator.hass = SimpleNamespace(async_create_task=lambda coro: loop.create_task(coro))
        coordinator.channels = {}
        coordinator._meter_pending_updates = set()
        coordinator._meter_flush_task = None

        coordinator._handle_meters(
            OscMessage(
                "/Notify/Meters",
                [
                    OscArg("i", 0),
                    OscArg("i", 1),
                    OscArg("f", -6.25),
                    OscArg("i", 0),
                    OscArg("i", 2),
                    OscArg("f", -12.5),
                ],
            )
        )

        assert coordinator.channels[(0, 1)].meter == -6.25
        assert coordinator.channels[(0, 2)].meter == -12.5

        task = coordinator._meter_flush_task
        if task is not None and not task.done():
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    finally:
        loop.close()


def test_handle_meters_parses_count_preceded_payload() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        coordinator = LV1Coordinator.__new__(LV1Coordinator)
        coordinator.entry_id = "entry"
        coordinator.hass = SimpleNamespace(async_create_task=lambda coro: loop.create_task(coro))
        coordinator.channels = {}
        coordinator._meter_pending_updates = set()
        coordinator._meter_flush_task = None

        coordinator._handle_meters(
            OscMessage(
                "/Notify/Meters",
                [
                    OscArg("i", 2),
                    OscArg("i", 0),
                    OscArg("i", 3),
                    OscArg("f", -3.0),
                    OscArg("i", 1),
                    OscArg("i", 4),
                    OscArg("f", -9.5),
                ],
            )
        )

        assert coordinator.channels[(0, 3)].meter == -3.0
        assert coordinator.channels[(1, 4)].meter == -9.5

        task = coordinator._meter_flush_task
        if task is not None and not task.done():
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    finally:
        loop.close()
