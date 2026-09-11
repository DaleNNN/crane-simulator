#!/usr/bin/env python3
"""
Selvtest av signalkontrakten. Krever ikke asyncua og ingen server.

    python selftest.py

Kjoer denne etter hver endring i signals.json - den fanger duplikater,
ugyldige stier, typefeil og range-feil foer serveren i det hele tatt startes.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

from signals import Contract, ContractError, Driver, Signal

HERE = Path(__file__).parent
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok    {name}")
    else:
        print(f"  FEIL  {name}  {detail}")
        failures.append(name)


def expect_error(name: str, raw: dict, fragment: str) -> None:
    doc = {"namespaceUri": "urn:test", "signals": [raw]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(doc, f)
        p = f.name
    try:
        Contract.load(p)
        check(name, False, "forventet ContractError, fikk ingen")
    except ContractError as e:
        check(name, fragment in str(e), f"meldingen manglet '{fragment}': {e}")
    finally:
        Path(p).unlink()


print("\n--- drivere ---")
sine = Driver(kind="sine", amplitude=30, period=5)
check("sine er 0 ved t=0", abs(sine.value_at(0, 0)) < 1e-9)
check("sine treffer toppen ved kvart periode", abs(sine.value_at(1.25, 0) - 30) < 1e-9)
check("sine treffer bunnen ved tre kvart", abs(sine.value_at(3.75, 0) + 30) < 1e-9)
check("sine er periodisk", abs(sine.value_at(0.7, 0) - sine.value_at(5.7, 0)) < 1e-9)

off = Driver(kind="sine", amplitude=10, period=4, offset=100)
check("offset loefter sine", abs(off.value_at(1.0, 0) - 110) < 1e-9)

ramp = Driver(kind="ramp", minimum=2, maximum=10, period=8)
check("ramp starter paa min", abs(ramp.value_at(0, 0) - 2) < 1e-9)
check("ramp er halvveis midt i", abs(ramp.value_at(4, 0) - 6) < 1e-9)
check("ramp resetter", abs(ramp.value_at(8, 0) - 2) < 1e-9)

tri = Driver(kind="triangle", minimum=0, maximum=8, period=10)
check("triangel topper midt i perioden", abs(tri.value_at(5, 0) - 8) < 1e-9)
check("triangel er symmetrisk", abs(tri.value_at(2.5, 0) - tri.value_at(7.5, 0)) < 1e-9)

sq = Driver(kind="square", minimum=-1, maximum=1, period=6)
check("firkant er hoey foerste halvdel", sq.value_at(1, 0) == 1)
check("firkant er lav andre halvdel", sq.value_at(4, 0) == -1)

const = Driver()
check("constant returnerer fallback", const.value_at(123.4, 7.5) == 7.5)

print("\n--- typer og klamping ---")
s = Signal(path="A.B", type="Double", limits=(-180, 180))
check("klamper oppover", s.coerce(500) == 180)
check("klamper nedover", s.coerce(-500) == -180)
check("slipper gjennom i omraadet", s.coerce(42.5) == 42.5)

i = Signal(path="A.C", type="Int32", limits=(0, 10))
check("Int32 blir int", isinstance(i.coerce("7.9"), int))
check("Int32 klamper", i.coerce(99) == 10)

b = Signal(path="A.D", type="Boolean")
check("Boolean fra 'true'", b.coerce("true") is True)
check("Boolean fra 'ja'", b.coerce("ja") is True)
check("Boolean fra '0'", b.coerce("0") is False)

driven = Signal(
    path="A.E", type="Double", direction="toUnity", initial=0.0,
    limits=(-5, 5), driver=Driver(kind="sine", amplitude=90, period=10),
)
check("driver klampes mot range", max(abs(driven.value_at(t / 10)) for t in range(200)) <= 5.0)

print("\n--- validering ---")
expect_error("tom sti avvises", {"path": ""}, "mangler 'path'")
expect_error("flat sti avvises", {"path": "SlewAngle"}, "minst ett objektnivaa")
expect_error("dobbel prikk avvises", {"path": "A..B"}, "ugyldig sti")
expect_error("ukjent type avvises", {"path": "A.B", "type": "Decimal"}, "ukjent type")
expect_error("ukjent retning avvises", {"path": "A.B", "direction": "begge"}, "direction")
expect_error("ukjent driver avvises", {"path": "A.B", "driver": {"kind": "kaos"}}, "ukjent driver")
expect_error("skjev range avvises", {"path": "A.B", "range": [10, 1]}, "mindre enn")
expect_error("range med feil lengde avvises", {"path": "A.B", "range": [1]}, "[min, max]")
expect_error("periode 0 avvises", {"path": "A.B", "driver": {"kind": "sine", "period": 0}}, "> 0")


def expect_doc_error(name: str, signals: list[dict], fragment: str) -> None:
    doc = {"namespaceUri": "urn:test", "signals": signals}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(doc, f)
        p = f.name
    try:
        Contract.load(p)
        check(name, False, "forventet ContractError")
    except ContractError as e:
        check(name, fragment in str(e), f"meldingen manglet '{fragment}': {e}")
    finally:
        Path(p).unlink()


expect_doc_error(
    "duplikat sti avvises",
    [{"path": "Crane.Slew"}, {"path": "Crane.Slew"}],
    "definert to ganger",
)
expect_doc_error(
    "sti som baade objekt og variabel avvises",
    [{"path": "Crane.Tip"}, {"path": "Crane.Tip.X"}],
    "baade som variabel",
)

print("\n--- signals.json ---")
try:
    c = Contract.load(HERE / "signals.json")
    check("kontrakten laster", True)

    paths = [s.path for s in c.signals]
    for required in ("Crane.SlewAngle", "Crane.BoomAngle", "Crane.TelescopeExtension"):
        check(f"{required} finnes (Unity abonnerer paa den)", required in paths)

    unity_nodes = ("Crane.SlewAngle", "Crane.BoomAngle", "Crane.TelescopeExtension")
    check(
        "Unity-nodene er toUnity",
        all(c.by_path(p).direction == "toUnity" for p in unity_nodes),
    )
    check(
        "Unity-nodene er ikke skrivbare for klient",
        all(not c.by_path(p).client_writable for p in unity_nodes),
    )
    check(
        "fromUnity-noder er skrivbare",
        all(s.client_writable for s in c.signals if s.direction == "fromUnity"),
    )

    # Foreldre maa komme foer barn, ellers feiler oppbyggingen av adresserommet.
    ordered = c.object_paths
    ok = all(
        "." not in p or p.rsplit(".", 1)[0] in ordered[:n]
        for n, p in enumerate(ordered)
    )
    check("objektnivaaer er sortert forelder foer barn", ok, str(ordered))
    check("Crane.Tip er med som objektnivaa", "Crane.Tip" in ordered)

    boom = c.by_path("Crane.BoomAngle")
    check(
        "BoomAngle matcher Sine-komponenten i CDP (30 @ 0.2 Hz)",
        boom.driver.amplitude == 30 and abs(boom.driver.period - 5) < 1e-9,
    )

    check("alle stier er unike", len(set(paths)) == len(paths))
    check(
        "ingen driver paa fromUnity-signaler",
        all(s.driver.kind == "constant" for s in c.signals if s.direction == "fromUnity"),
    )
    print(f"\n  {len(c.signals)} signaler, "
          f"{sum(1 for s in c.signals if s.direction == 'toUnity')} toUnity, "
          f"{sum(1 for s in c.signals if s.direction == 'fromUnity')} fromUnity")
except ContractError as e:
    check("kontrakten laster", False, str(e))

print()
if failures:
    print(f"{len(failures)} test(er) feilet: {', '.join(failures)}")
    sys.exit(1)
print("Alt gikk gjennom.")
