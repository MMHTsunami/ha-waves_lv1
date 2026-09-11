from types import SimpleNamespace

from custom_components.waves_lv1.diagnostics import async_get_config_entry_diagnostics


def test_async_get_config_entry_diagnostics_includes_state() -> None:
    coordinator = SimpleNamespace(
        host="192.168.1.10",
        port=9000,
        connected=True,
        channels={
            (0, 1): SimpleNamespace(
                muted=True,
                gain=-3.5,
                solo=False,
                color=(1.0, 0.5, 0.25),
                name="Kick",
                pan=0.1,
                width=1.0,
                meter=-6.0,
            )
        },
        sends={},
        mute_groups={0: True},
        scenes={1: "Scene A"},
        current_scene=1,
        current_scene_name="Scene A",
        current_tempo=120.0,
        current_flip_target=None,
        user_keys={0: SimpleNamespace(name="A", func="Fader", assigned=True)},
        detected=SimpleNamespace(channels=80, auxes=8, aux_names=["Bus 1", "Bus 2"]),
    )

    entry = SimpleNamespace(
        entry_id="abc123",
        title="Waves LV1",
        unique_id="192.168.1.10:9000",
    )
    hass = SimpleNamespace(data={"waves_lv1": {"abc123": coordinator}})

    data = __import__('asyncio').run(async_get_config_entry_diagnostics(hass, entry))

    assert data["host"] == "192.168.1.10"
    assert data["port"] == 9000
    assert data["connected"] is True
    assert data["topology"]["channels"] == 80
    assert data["tracks"][(0, 1)]["name"] == "Kick"
    assert data["scene"]["current_scene_name"] == "Scene A"
    assert data["user_keys"][0]["func"] == "Fader"
