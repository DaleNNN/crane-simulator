"""
Signalkontrakt for crane-simulator.

Denne modulen er bevisst fri for OPC UA-avhengigheter. Alt som handler om
hvilke noder som finnes, hvordan de er strukturert og hvilke verdier
testdriverne produserer, ligger her og kan kjoeres og testes uten en server.

server.py legger OPC UA-laget oppaa.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Retning sett fra simulatoren (Unity).
#   toUnity   - reguleringsprogrammet (CDP) eier verdien, Unity abonnerer.
#   fromUnity - simulatoren eier verdien, Unity skriver, CDP abonnerer.
DIRECTIONS = ("toUnity", "fromUnity")

# UA-typer vi stoetter, med Python-konverterer og startverdi.
TYPES: dict[str, tuple[type, Any]] = {
    "Double": (float, 0.0),
    "Float": (float, 0.0),
    "Int32": (int, 0),
    "UInt32": (int, 0),
    "Int64": (int, 0),
    "Boolean": (bool, False),
    "String": (str, ""),
}


class ContractError(ValueError):
    """Feil i signals.json."""


# ---------------------------------------------------------------- drivere


@dataclass
class Driver:
    """Testbevegelse for en node. Brukes bare paa toUnity-signaler."""

    kind: str = "constant"
    amplitude: float = 0.0
    period: float = 10.0
    offset: float = 0.0
    phase: float = 0.0  # grader
    minimum: float = 0.0
    maximum: float = 1.0

    @classmethod
    def parse(cls, raw: Any, where: str) -> "Driver":
        if raw is None:
            return cls()
        if isinstance(raw, str):
            raw = {"kind": raw}
        if not isinstance(raw, dict):
            raise ContractError(f"{where}: driver maa vaere objekt eller streng")

        kind = raw.get("kind", "constant")
        known = ("constant", "sine", "ramp", "triangle", "square")
        if kind not in known:
            raise ContractError(
                f"{where}: ukjent driver '{kind}', maa vaere en av {known}"
            )

        d = cls(
            kind=kind,
            amplitude=float(raw.get("amplitude", 0.0)),
            period=float(raw.get("period", 10.0)),
            offset=float(raw.get("offset", 0.0)),
            phase=float(raw.get("phase", 0.0)),
            minimum=float(raw.get("min", 0.0)),
            maximum=float(raw.get("max", 1.0)),
        )
        if d.period <= 0:
            raise ContractError(f"{where}: period maa vaere > 0")
        return d

    def value_at(self, t: float, fallback: float) -> float:
        """Verdi ved tid t. fallback brukes naar driveren er 'constant'."""
        if self.kind == "constant":
            return fallback

        cycles = t / self.period
        phase = math.radians(self.phase)

        if self.kind == "sine":
            return self.offset + self.amplitude * math.sin(2 * math.pi * cycles + phase)

        # Posisjon i syklusen, 0..1
        u = (cycles + self.phase / 360.0) % 1.0

        if self.kind == "ramp":
            return self.minimum + (self.maximum - self.minimum) * u
        if self.kind == "triangle":
            tri = 2 * u if u < 0.5 else 2 * (1 - u)
            return self.minimum + (self.maximum - self.minimum) * tri
        if self.kind == "square":
            return self.maximum if u < 0.5 else self.minimum

        raise AssertionError(f"uhaandtert driver {self.kind}")


# ---------------------------------------------------------------- signaler


@dataclass
class Signal:
    path: str  # "Crane.SlewAngle" - dette blir ogsaa NodeId-strengen
    type: str = "Double"
    unit: str = ""
    direction: str = "toUnity"
    initial: Any = None
    limits: tuple[float, float] | None = None
    driver: Driver = field(default_factory=Driver)
    description: str = ""

    @property
    def segments(self) -> list[str]:
        return self.path.split(".")

    @property
    def browse_name(self) -> str:
        return self.segments[-1]

    @property
    def parent_path(self) -> str:
        return ".".join(self.segments[:-1])

    @property
    def python_type(self) -> type:
        return TYPES[self.type][0]

    @property
    def driven(self) -> bool:
        return self.direction == "toUnity" and self.driver.kind != "constant"

    @property
    def client_writable(self) -> bool:
        """Unity skriver bare paa signaler simulatoren eier."""
        return self.direction == "fromUnity"

    def coerce(self, value: Any) -> Any:
        """Tving en verdi over paa signalets type, med klamping mot range."""
        py = self.python_type
        if py is bool:
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "on", "ja", "yes")
            return bool(value)
        if py is str:
            return str(value)

        num = py(float(value))
        if self.limits is not None:
            lo, hi = self.limits
            num = py(max(lo, min(hi, num)))
        return num

    def value_at(self, t: float) -> Any:
        if not self.driven:
            return self.initial
        return self.coerce(self.driver.value_at(t, float(self.initial or 0.0)))

    @classmethod
    def parse(cls, raw: dict, index: int) -> "Signal":
        where = f"signal #{index}"
        if not isinstance(raw, dict):
            raise ContractError(f"{where}: maa vaere et objekt")

        path = str(raw.get("path", "")).strip()
        where = f"signal '{path or index}'"
        if not path:
            raise ContractError(f"{where}: mangler 'path'")
        if path.startswith(".") or path.endswith(".") or ".." in path:
            raise ContractError(f"{where}: ugyldig sti")
        if len(path.split(".")) < 2:
            raise ContractError(
                f"{where}: stien maa ha minst ett objektnivaa, f.eks. 'Crane.SlewAngle'"
            )

        typ = raw.get("type", "Double")
        if typ not in TYPES:
            raise ContractError(
                f"{where}: ukjent type '{typ}', maa vaere en av {tuple(TYPES)}"
            )

        direction = raw.get("direction", "toUnity")
        if direction not in DIRECTIONS:
            raise ContractError(
                f"{where}: direction maa vaere en av {DIRECTIONS}, ikke '{direction}'"
            )

        limits = raw.get("range")
        if limits is not None:
            if not (isinstance(limits, (list, tuple)) and len(limits) == 2):
                raise ContractError(f"{where}: 'range' maa vaere [min, max]")
            limits = (float(limits[0]), float(limits[1]))
            if limits[0] >= limits[1]:
                raise ContractError(f"{where}: range min maa vaere mindre enn max")

        sig = cls(
            path=path,
            type=typ,
            unit=str(raw.get("unit", "")),
            direction=direction,
            limits=limits,
            driver=Driver.parse(raw.get("driver"), where),
            description=str(raw.get("description", "")),
        )
        raw_initial = raw.get("initial", TYPES[typ][1])
        sig.initial = sig.coerce(raw_initial)
        return sig


@dataclass
class Contract:
    namespace_uri: str
    signals: list[Signal]

    @property
    def object_paths(self) -> list[str]:
        """Alle objektnivaaer som maa finnes, foreldre foer barn."""
        seen: list[str] = []
        for sig in self.signals:
            parts = sig.segments[:-1]
            for i in range(1, len(parts) + 1):
                p = ".".join(parts[:i])
                if p not in seen:
                    seen.append(p)
        return seen

    def by_path(self, path: str) -> Signal | None:
        for s in self.signals:
            if s.path == path:
                return s
        return None

    def matching(self, pattern: str) -> list[Signal]:
        p = pattern.lower()
        return [s for s in self.signals if p in s.path.lower()]

    @classmethod
    def load(cls, path: str | Path) -> "Contract":
        p = Path(path)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ContractError(f"finner ikke {p}")
        except json.JSONDecodeError as e:
            raise ContractError(f"{p} er ikke gyldig JSON: {e}")

        uri = raw.get("namespaceUri")
        if not uri:
            raise ContractError("mangler 'namespaceUri'")

        entries = raw.get("signals")
        if not isinstance(entries, list) or not entries:
            raise ContractError("'signals' maa vaere en ikke-tom liste")

        signals = [Signal.parse(e, i) for i, e in enumerate(entries)]

        # Duplikater er lette aa lage naar lista vokser, og gir en server som
        # starter fint men oppfoerer seg uforutsigbart. Stopp den her.
        seen: dict[str, int] = {}
        for i, s in enumerate(signals):
            if s.path in seen:
                raise ContractError(
                    f"'{s.path}' er definert to ganger (#{seen[s.path]} og #{i})"
                )
            seen[s.path] = i

        # En sti kan ikke vaere baade objekt og variabel.
        objects = set()
        for s in signals:
            parts = s.segments[:-1]
            for i in range(1, len(parts) + 1):
                objects.add(".".join(parts[:i]))
        for s in signals:
            if s.path in objects:
                raise ContractError(
                    f"'{s.path}' brukes baade som variabel og som objektnivaa"
                )

        return cls(namespace_uri=uri, signals=signals)


def format_table(contract: Contract) -> str:
    """Oversikt over kontrakten, til konsollen og til --list."""
    rows = [("NODE-ID (ns=1)", "TYPE", "ENHET", "RETNING", "DRIVER")]
    for s in contract.signals:
        drv = s.driver.kind
        if drv == "sine":
            drv = f"sine {s.driver.amplitude:g} @ {s.driver.period:g}s"
        elif drv in ("ramp", "triangle", "square"):
            drv = f"{drv} {s.driver.minimum:g}..{s.driver.maximum:g} @ {s.driver.period:g}s"
        elif s.direction == "fromUnity":
            drv = "(skrives av Unity)"
        else:
            drv = "-"
        rows.append((s.path, s.type, s.unit or "-", s.direction, drv))

    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    out = []
    for n, row in enumerate(rows):
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
        if n == 0:
            out.append("  ".join("-" * w for w in widths))
    return "\n".join(out)
