from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from random import Random
from typing import Any, Iterable, Mapping


SOURCE = "xenomind_neural_interface"
SANDBOX_WIDTH = 520
SANDBOX_HEIGHT = 120
REQUIRED_RECORD_FIELDS = {
    "timestamp",
    "session_id",
    "sequence",
    "event_type",
    "source",
    "synthetic",
    "scenario",
    "application",
    "details",
    "scope",
    "real_input_sent",
}


@dataclass(frozen=True)
class ScenarioAction:
    event_type: str
    application: str
    details: str
    preview_text: str | None = None
    location: str | None = None
    visual_pointer: bool = False


@dataclass(frozen=True)
class SimulationEvent:
    timestamp: str
    session_id: str
    sequence: int
    event_type: str
    source: str
    synthetic: bool
    scenario: str
    application: str
    details: str
    preview_text: str | None = None
    location: str | None = None
    surface_x: int | None = None
    surface_y: int | None = None

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["scope"] = "in_app_sandbox"
        record["real_input_sent"] = False
        return record


SCENARIOS: dict[str, tuple[ScenarioAction, ...]] = {
    "First Contact": (
        ScenarioAction(
            "neural_firing",
            "Cortical Lattice",
            "A luminous impulse crossed the left hemisphere.",
            visual_pointer=True,
        ),
        ScenarioAction(
            "memory_recall",
            "Mnemonic Vault",
            "A synthetic memory shard surfaced from the deep cortex.",
            location="/Cortex/Memories/shard-07",
        ),
        ScenarioAction(
            "dream_fragment",
            "Dream Archive",
            "An unfamiliar thought-form materialized in the neural stream.",
            preview_text="The stars remember a shape that has never existed.",
        ),
        ScenarioAction(
            "hemisphere_shift",
            "Abyssal Relay",
            "Signal coherence shifted across the divided hemispheres.",
        ),
        ScenarioAction(
            "lattice_scan",
            "Cortical Lattice",
            "The outer synaptic lattice folded inward for a synthetic scan.",
            location="/Cortex/Lattice/ring-03",
        ),
        ScenarioAction(
            "signal_resonance",
            "Exocortex",
            "A carrier wave resonated through the dormant outer nodes.",
        ),
    ),
    "Dream Sequence": (
        ScenarioAction(
            "memory_recall",
            "Mnemonic Vault",
            "A synthetic memory shard surfaced from the deep cortex.",
            location="/Cortex/Memories/shard-07",
        ),
        ScenarioAction(
            "dream_fragment",
            "Dream Archive",
            "An unfamiliar thought-form materialized in the neural stream.",
            preview_text="The stars remember a shape that has never existed.",
        ),
        ScenarioAction(
            "signal_resonance",
            "Exocortex",
            "A carrier wave resonated through the dormant outer nodes.",
        ),
        ScenarioAction(
            "neural_firing",
            "Cortical Lattice",
            "A luminous impulse crossed the left hemisphere.",
            visual_pointer=True,
        ),
    ),
    "Signal Migration": (
        ScenarioAction(
            "lattice_scan",
            "Cortical Lattice",
            "The outer synaptic lattice folded inward for a synthetic scan.",
            location="/Cortex/Lattice/ring-03",
        ),
        ScenarioAction(
            "hemisphere_shift",
            "Abyssal Relay",
            "Signal coherence shifted across the divided hemispheres.",
        ),
        ScenarioAction(
            "neural_firing",
            "Cortical Lattice",
            "A luminous impulse crossed the left hemisphere.",
            visual_pointer=True,
        ),
        ScenarioAction(
            "memory_recall",
            "Mnemonic Vault",
            "A synthetic memory shard surfaced from the deep cortex.",
            location="/Cortex/Memories/shard-07",
        ),
    ),
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class ScenarioEngine:
    def __init__(self, scenario: str, seed: int) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        self.scenario = scenario
        self._random = Random(seed)

    def next_event(self, session_id: str, sequence: int) -> SimulationEvent:
        action = self._random.choice(SCENARIOS[self.scenario])
        surface_x = None
        surface_y = None
        if action.visual_pointer:
            surface_x = self._random.randint(16, SANDBOX_WIDTH - 16)
            surface_y = self._random.randint(16, SANDBOX_HEIGHT - 16)

        return SimulationEvent(
            timestamp=_timestamp(),
            session_id=session_id,
            sequence=sequence,
            event_type=action.event_type,
            source=SOURCE,
            synthetic=True,
            scenario=self.scenario,
            application=action.application,
            details=action.details,
            preview_text=action.preview_text,
            location=action.location,
            surface_x=surface_x,
            surface_y=surface_y,
        )


def control_event(
    scenario: str,
    session_id: str,
    sequence: int,
    event_type: str,
    details: str,
) -> SimulationEvent:
    return SimulationEvent(
        timestamp=_timestamp(),
        session_id=session_id,
        sequence=sequence,
        event_type=event_type,
        source=SOURCE,
        synthetic=True,
        scenario=scenario,
        application="Xenomind Core",
        details=details,
    )


def append_event(path: str | PathLike[str] | Path, event: SimulationEvent) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="\n") as event_file:
        event_file.write(json.dumps(event.to_record(), ensure_ascii=False) + "\n")
