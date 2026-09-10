# Role & Project Goal
You are an expert Python developer and Home Assistant Core integration architect.
Your task is to port the Bitfocus Companion module for Waves eMotion LV1 (TypeScript/Node.js) into a native Home Assistant custom component (`custom_components/waves_lv1`).

# Architecture & Design Requirements
1. **Asynchronous Architecture:**
   - Use `asyncio` exclusively. No blocking I/O calls on the main event loop.
   - Use Home Assistant's native helper methods for network connections, timers, and background tasks.

2. **Integration Structure:**
   - Follow modern Home Assistant integration standards (Config Flow, Options Flow, DataUpdateCoordinator).
   - Core files required:
     - `manifest.json`: Proper domain, dependencies, and codeowners.
     - `config_flow.py`: UI configuration for IP address, port, and polling intervals.
     - `const.py`: Centralized domain string, default ports, and property keys.
     - `coordinator.py`: `DataUpdateCoordinator` managing the connection and state retrieval.
     - `__init__.py`: Component setup, unload handlers, and platform loading.
     - `media_player.py`, `number.py`, `switch.py`, `button.py`: Home Assistant entities mapped to LV1 parameters.

3. **Source Reference Code (TypeScript -> Python):**
   - Translate state mapping, OSC/UDP/TCP command construction, and response parsing directly from the reference Companion module logic.
   - Abstract the low-level LV1 API network communication into a standalone pure Python library client (e.g., `PyWavesLV1` inside `api.py` or as a helper module) so Home Assistant entity platforms stay decoupled from protocol details.

4. **Code Quality & Typing:**
   - Strict Type Hints (`typing` module / Python 3.12+ syntax).
   - Use standard Home Assistant exceptions (`HomeAssistantError`, `ConfigEntryNotReady`).
   - Include clear docstrings for public classes and methods.

# Planning Instructions
- When in Plan mode, break work down into distinct, testable phases.
- Explicitly map Companion module concepts (actions, variables, feedback) to corresponding Home Assistant entities (buttons, numbers, sensors, switches, media players).

## Execution Rules
1. **Follow `PLAN.md` Sequentially:** Work through phases in order. Do not skip phases or generate code for future phases until prerequisites are verified.
2. **Asynchronous Code Only:** Use `asyncio` and native Home Assistant async methods (`async_setup_entry`, `async_dispatcher_send`, `async_add_entities`). Never use blocking I/O on the main loop.
3. **No `media_player` Platform:** All audio features map to `number`, `switch`, `button`, `select`, `sensor`, and `text` entities.
4. **Push-Based Architecture:** State changes are pushed via `async_dispatcher_send`. Do not use a polling `DataUpdateCoordinator`.
5. **Entity Defaulting:** Any high-cardinality entities (EQ bands, individual send matrices) MUST specify `entity_registry_enabled_default = False`.
6. **Testing:** Write unit tests alongside protocol modules using standard `pytest` without requiring a full Home Assistant runtime where possible.