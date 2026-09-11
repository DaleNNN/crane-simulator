#!/usr/bin/env python3
"""
Intern roeyktest av server.py mot en stand-in for asyncua.

Dette verifiserer LOGIKKEN i serveren - at adresserommet bygges i riktig
rekkefoelge, at NodeId-ene blir som Unity forventer, at driverne ticker og at
konsollkommandoene virker. Den verifiserer IKKE at kallene matcher ekte
asyncua-API; det krever en faktisk installasjon.

Kjoerer uten asyncua installert, saa den kan brukes til aa sjekke at en endring
ikke har brukket noe foer serveren startes for alvor.
"""

import asyncio
import sys
import types
from dataclasses import dataclass

# ----------------------------------------------------------- fake asyncua

created_objects: list[str] = []
created_vars: dict[str, dict] = {}


class _VariantType:
    def __init__(self, n): self.name = n
    def __repr__(self): return f"VariantType.{self.name}"


class _NodeIdType:
    String = "String"


@dataclass
class _NodeId:
    Identifier: str
    NamespaceIndex: int
    NodeIdType: str = None
    def __hash__(self): return hash((self.Identifier, self.NamespaceIndex))
    def __str__(self): return f"ns={self.NamespaceIndex};s={self.Identifier}"


@dataclass
class _QualifiedName:
    Name: str
    NamespaceIndex: int


class _Variant:
    def __init__(self, value, vtype=None):
        self.Value, self.VariantType = value, vtype


class _DataValue:
    def __init__(self, v): self.Value = v


class _LocalizedText:
    def __init__(self, t): self.Text = t


class _AttributeIds:
    Description = 13


class _SecurityPolicyType:
    NoSecurity = "NoSecurity"


class _Node:
    def __init__(self, nodeid, name):
        self.nodeid, self.name = nodeid, name
        self.value = None
        self.writable = False
        self.description = None

    def __hash__(self):
        return hash(self.nodeid)

    async def add_object(self, nodeid, bname):
        created_objects.append(nodeid.Identifier)
        return _Node(nodeid, bname.Name)

    async def add_variable(self, nodeid, bname, val, varianttype=None):
        n = _Node(nodeid, bname.Name)
        n.value = val
        created_vars[nodeid.Identifier] = {
            "ns": nodeid.NamespaceIndex,
            "browse": bname.Name,
            "browse_ns": bname.NamespaceIndex,
            "type": varianttype,
            "node": n,
        }
        return n

    async def set_writable(self, flag=True):
        self.writable = flag

    async def write_attribute(self, attr, dv):
        self.description = dv.Value.Value.Text

    async def write_value(self, v):
        self.value = v.Value if isinstance(v, _Variant) else v

    async def read_value(self):
        return self.value


class _Sub:
    def __init__(self): self.nodes = []
    async def subscribe_data_change(self, nodes): self.nodes = nodes


class _Server:
    def __init__(self):
        self.nodes = types.SimpleNamespace(objects=_Node(_NodeId("Objects", 0), "Objects"))
        self.endpoint = self.name = self.app_uri = None
        self.policies = None
        self._ns = ["http://opcfoundation.org/UA/", "urn:freeopcua:python:server"]

    async def init(self): pass
    def set_endpoint(self, ep): self.endpoint = ep
    def set_server_name(self, n): self.name = n
    def set_security_policy(self, p): self.policies = p

    def set_application_uri(self, uri):
        self.app_uri = uri
        self._ns[1] = uri

    async def register_namespace(self, uri):
        if uri in self._ns:
            return self._ns.index(uri)
        self._ns.append(uri)
        return len(self._ns) - 1

    async def get_namespace_array(self): return list(self._ns)
    async def create_subscription(self, period, handler): return _Sub()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


ua = types.SimpleNamespace(
    VariantType=types.SimpleNamespace(**{
        n: _VariantType(n) for n in
        ("Double", "Float", "Int32", "UInt32", "Int64", "Boolean", "String")
    }),
    NodeId=_NodeId, NodeIdType=_NodeIdType, QualifiedName=_QualifiedName,
    Variant=_Variant, DataValue=_DataValue, LocalizedText=_LocalizedText,
    AttributeIds=_AttributeIds, SecurityPolicyType=_SecurityPolicyType,
)
sys.modules["asyncua"] = types.SimpleNamespace(Server=_Server, ua=ua)

# ------------------------------------------------------------------ test

from signals import Contract  # noqa: E402
import server as srv  # noqa: E402
srv.load_ua()

failures = []


def check(name, cond, detail=""):
    print(f"  {'ok   ' if cond else 'FEIL '} {name}  {'' if cond else detail}")
    if not cond:
        failures.append(name)


async def main():
    contract = Contract.load("signals.json")
    s = srv.CraneSimServer(contract, "127.0.0.1", 4840, 20.0)
    await s.build()

    print("\n--- adresserom ---")
    check("namespace landet paa ns=1", s.idx == 1, f"ble {s.idx}")
    check("application-uri satt til kontraktens uri",
          s.server.app_uri == contract.namespace_uri)
    check("endepunkt er 127.0.0.1", s.server.endpoint == "opc.tcp://127.0.0.1:4840/")
    check("security policy er NoSecurity", s.server.policies == ["NoSecurity"])

    check("Crane-objekt opprettet", "Crane" in created_objects)
    check("Vessel-objekt opprettet", "Vessel" in created_objects)
    check("nestet objekt Crane.Tip opprettet", "Crane.Tip" in created_objects)
    check("Crane kommer foer Crane.Tip",
          created_objects.index("Crane") < created_objects.index("Crane.Tip"))

    check("alle 21 variabler opprettet", len(created_vars) == 21, str(len(created_vars)))

    v = created_vars.get("Crane.SlewAngle")
    check("Crane.SlewAngle finnes som NodeId-streng", v is not None)
    check("ligger i ns=1", v and v["ns"] == 1)
    check("browsename er bare siste ledd", v and v["browse"] == "SlewAngle")
    check("er Double", v and v["type"].name == "Double")
    check("er IKKE skrivbar for klient (toUnity)", v and not v["node"].writable)
    check("har beskrivelse", v and v["node"].description)

    hb = created_vars.get("Sim.Heartbeat")
    check("Sim.Heartbeat er UInt32", hb and hb["type"].name == "UInt32")
    check("fromUnity-node er skrivbar", hb and hb["node"].writable)

    tip = created_vars.get("Crane.Tip.X")
    check("nestet variabel Crane.Tip.X finnes", tip is not None)
    check("browsename for nestet er 'X'", tip and tip["browse"] == "X")

    print("\n--- drivere ticker ---")
    s.t0 = 0.0  # frys tiden slik at value_at(t) er forutsigbar
    import time as _t
    real = _t.monotonic
    _t.monotonic = lambda: 1.25  # kvart periode for BoomAngle (5s)
    await s.tick()
    boom = created_vars["Crane.BoomAngle"]["node"].value
    check("BoomAngle naadde toppen (30)", abs(boom - 30) < 1e-6, str(boom))

    _t.monotonic = lambda: 0.0
    await s.tick()
    check("BoomAngle tilbake til 0", abs(created_vars["Crane.BoomAngle"]["node"].value) < 1e-6)
    check("fromUnity-node roeres ikke av tick",
          created_vars["Sim.Heartbeat"]["node"].value == 0)
    _t.monotonic = real

    print("\n--- konsoll ---")
    await s._command("set", ["Crane.SlewAngle", "45"])
    check("set skriver verdien", created_vars["Crane.SlewAngle"]["node"].value == 45)
    check("set registrerer override", "Crane.SlewAngle" in s.overrides)
    await s.tick()
    check("driver overstyres ikke etterpaa",
          created_vars["Crane.SlewAngle"]["node"].value == 45)

    await s._command("set", ["Crane.SlewAngle", "9999"])
    check("set klamper mot range", created_vars["Crane.SlewAngle"]["node"].value == 180)

    await s._command("drive", ["Crane.SlewAngle", "sine:10:4"])
    check("drive fjerner override", "Crane.SlewAngle" not in s.overrides)
    check("drive setter ny driver",
          contract.by_path("Crane.SlewAngle").driver.amplitude == 10)

    await s._command("drive", ["Crane.SlewAngle", "off"])
    check("drive off fryser verdien", "Crane.SlewAngle" in s.overrides)

    for bad, why in [
        (("set", ["Tull.Finnes.Ikke", "1"]), "ukjent node"),
        (("set", ["Crane.SlewAngle"]), "for faa argumenter"),
        (("blah", []), "ukjent kommando"),
        (("drive", ["Crane.BoomAngle", "sine:bare-en"]), "ugyldig driverspec"),
    ]:
        (cmd, args) = bad
        try:
            await s._command(cmd, args)
            check(f"feilhaandtering: {why}", False, "kastet ingen feil")
        except Exception:
            check(f"feilhaandtering: {why}", True)

    await s._command("list", ["Vessel"])
    await s._command("get", ["Vessel.Heave"])
    check("list og get kjoerer uten feil", True)


asyncio.run(main())
print()
if failures:
    print(f"{len(failures)} feilet: {failures}")
    sys.exit(1)
print("Roeyktest ok.")
