#!/usr/bin/env python3
"""
OPC UA-testserver for crane-simulator.

Staar inn for CDP-applikasjonen slik at Unity kan testes uten PLS eller
CDP Studio. Hele adresserommet bygges fra signals.json, saa aa legge til en
node er en rad i JSON-fila - ikke en kodeendring.

    python server.py                     # start paa 127.0.0.1:4840
    python server.py --list              # bare skriv ut kontrakten
    python server.py --host 0.0.0.0      # naabar fra andre maskiner

Konsollkommandoer mens den kjoerer:
    list [filter]              vis noder og verdier
    get <path>                 les en verdi
    set <path> <verdi>         sett en verdi (slaar av driveren)
    drive <path> <spec>        off | sine:<amp>:<periode> | ramp:<min>:<max>:<periode>
    quit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
import time
from pathlib import Path

from signals import Contract, ContractError, Driver, Signal, format_table

log = logging.getLogger("cranesim")

# asyncua importeres foerst naar serveren faktisk skal starte, slik at
# --list og validering av signals.json virker uten at pakka er installert.
Server = None
ua = None
UA_TYPES: dict = {}


def load_ua() -> None:
    global Server, ua, UA_TYPES
    try:
        from asyncua import Server as _Server, ua as _ua
    except ImportError:
        sys.exit(
            "Mangler asyncua.\n"
            "    pip install -r requirements.txt\n"
            "eller\n"
            "    pip install asyncua"
        )
    Server, ua = _Server, _ua
    UA_TYPES = {
        name: getattr(ua.VariantType, name)
        for name in ("Double", "Float", "Int32", "UInt32", "Int64", "Boolean", "String")
    }


def primary_ipv4() -> str | None:
    """IP-en paa nettverkskortet som har default gateway.

    UDP-socketen kobler ikke opp noe og sender ingen pakker; den brukes bare
    til aa faa operativsystemet til aa velge utgaaende interface.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def local_ipv4_addresses() -> list[str]:
    """Adresser denne maskinen faktisk kan binde til."""
    found = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except socket.gaierror:
        pass
    if (p := primary_ipv4()):
        found.add(p)
    return sorted(found)


class WriteLogger:
    """Logger naar en klient skriver til en fromUnity-node."""

    def __init__(self, paths: dict[int, str]) -> None:
        self.paths = paths
        self.seen: dict[str, object] = {}
        # Abonnementet fyrer en gang per node med startverdien med det samme
        # det opprettes. Det er ikke noen som har skrevet noe, saa vi hopper
        # over foerste varsel per node.
        self.initialised: set[str] = set()

    def datachange_notification(self, node, val, data) -> None:  # asyncua-API
        path = self.paths.get(hash(node), str(node))
        if path not in self.initialised:
            self.initialised.add(path)
            self.seen[path] = val
            return
        if self.seen.get(path) != val:
            self.seen[path] = val
            log.info("Unity skrev  %s = %s", path, val)


class CraneSimServer:
    def __init__(self, contract: Contract, host: str, port: int, rate: float) -> None:
        self.contract = contract
        self.host = host
        self.port = port
        self.period = 1.0 / rate
        self.server = Server()
        self.idx = 1
        self.nodes: dict[str, object] = {}
        self.overrides: dict[str, object] = {}  # path -> verdi satt manuelt
        self.t0 = time.monotonic()

    # ------------------------------------------------------------ oppsett

    async def build(self) -> None:
        await self.server.init()

        endpoint = f"opc.tcp://{self.host}:{self.port}/"
        self.server.set_endpoint(endpoint)
        self.server.set_server_name("CraneSim Test Server")

        # Unity-klienten ber om SecurityMode.None og anonym bruker.
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

        # CraneOpcClient bruker new NodeId(identifier, 1), altsaa ns=1.
        # Namespace 1 er serverens egen application-URI, saa vi setter den
        # til kontraktens URI foer vi registrerer den.
        uri = self.contract.namespace_uri
        maybe = self.server.set_application_uri(uri)
        if asyncio.iscoroutine(maybe):
            await maybe
        self.idx = await self.server.register_namespace(uri)

        if self.idx != 1:
            log.warning(
                "Namespace '%s' havnet paa indeks %d, ikke 1. "
                "Unity-klienten er hardkodet til ns=1 og vil ikke finne nodene. "
                "Namespace-array: %s",
                uri,
                self.idx,
                await self.server.get_namespace_array(),
            )

        await self._build_address_space()
        await self._watch_client_writes()

    async def _build_address_space(self) -> None:
        objects = self.server.nodes.objects

        # Objektnivaaene foerst, foreldre foer barn (Contract garanterer ordenen).
        folders: dict[str, object] = {}
        for path in self.contract.object_paths:
            parent = objects
            if "." in path:
                parent = folders[path.rsplit(".", 1)[0]]
            name = path.rsplit(".", 1)[-1]
            folders[path] = await parent.add_object(
                ua.NodeId(path, self.idx, ua.NodeIdType.String),
                ua.QualifiedName(name, self.idx),
            )

        for sig in self.contract.signals:
            parent = folders[sig.parent_path]
            node = await parent.add_variable(
                ua.NodeId(sig.path, self.idx, ua.NodeIdType.String),
                ua.QualifiedName(sig.browse_name, self.idx),
                sig.initial,
                varianttype=UA_TYPES[sig.type],
            )
            if sig.client_writable:
                await node.set_writable(True)
            if sig.description:
                await node.write_attribute(
                    ua.AttributeIds.Description,
                    ua.DataValue(ua.Variant(ua.LocalizedText(sig.description))),
                )
            self.nodes[sig.path] = node

    async def _watch_client_writes(self) -> None:
        writable = [s for s in self.contract.signals if s.client_writable]
        if not writable:
            return
        nodes = [self.nodes[s.path] for s in writable]
        handler = WriteLogger({hash(n): s.path for n, s in zip(nodes, writable)})
        sub = await self.server.create_subscription(250, handler)
        await sub.subscribe_data_change(nodes)

    # ------------------------------------------------------------- kjoering

    async def tick(self) -> None:
        """Oppdater alle drevne noder en gang."""
        t = time.monotonic() - self.t0
        for sig in self.contract.signals:
            if sig.path in self.overrides or not sig.driven:
                continue
            await self.nodes[sig.path].write_value(
                ua.Variant(sig.value_at(t), UA_TYPES[sig.type])
            )

    async def run(self) -> None:
        async with self.server:
            log.info("Server oppe paa opc.tcp://%s:%d/  (ns=%d)", self.host, self.port, self.idx)
            log.info("Skriv 'help' for kommandoer, 'quit' for aa avslutte.\n")
            console = asyncio.create_task(self.console())
            try:
                while not console.done():
                    await self.tick()
                    await asyncio.sleep(self.period)
            finally:
                console.cancel()

    # ------------------------------------------------------------- konsoll

    async def console(self) -> None:
        while True:
            try:
                line = (await asyncio.to_thread(input, "")).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not line:
                continue
            cmd, *rest = line.split()
            cmd = cmd.lower()

            if cmd in ("quit", "exit", "q"):
                return
            if cmd in ("help", "?"):
                print(__doc__.split("Konsollkommandoer")[1].rstrip())
                continue
            try:
                await self._command(cmd, rest)
            except Exception as e:  # konsollen skal aldri ta ned serveren
                print(f"  feil: {e}")

    async def _command(self, cmd: str, args: list[str]) -> None:
        if cmd == "list":
            pattern = args[0] if args else ""
            hits = self.contract.matching(pattern)
            if not hits:
                print(f"  ingen noder matcher '{pattern}'")
                return
            width = max(len(s.path) for s in hits)
            for s in hits:
                val = await self.nodes[s.path].read_value()
                mark = "*" if s.path in self.overrides else " "
                shown = f"{val:10.3f}" if isinstance(val, float) else f"{val!s:>10}"
                print(f" {mark}{s.path.ljust(width)}  {shown}  {s.unit}")
            if any(s.path in self.overrides for s in hits):
                print("  (* = satt manuelt, driver av)")
            return

        if cmd == "get":
            sig = self._need(args, 1, "get <path>")
            print(f"  {sig.path} = {await self.nodes[sig.path].read_value()} {sig.unit}")
            return

        if cmd == "set":
            sig = self._need(args, 2, "set <path> <verdi>")
            value = sig.coerce(args[1])
            self.overrides[sig.path] = value
            await self.nodes[sig.path].write_value(ua.Variant(value, UA_TYPES[sig.type]))
            print(f"  {sig.path} = {value} {sig.unit}  (driver av)")
            return

        if cmd == "drive":
            sig = self._need(args, 2, "drive <path> off|sine:<amp>:<periode>|ramp:<min>:<max>:<periode>")
            spec = args[1].lower()
            if spec == "off":
                sig.driver = Driver()
                self.overrides[sig.path] = await self.nodes[sig.path].read_value()
                print(f"  {sig.path}: driver av, verdien fryses")
                return
            kind, *params = spec.split(":")
            nums = [float(p) for p in params]
            if kind == "sine" and len(nums) == 2:
                sig.driver = Driver(kind="sine", amplitude=nums[0], period=nums[1])
            elif kind in ("ramp", "triangle", "square") and len(nums) == 3:
                sig.driver = Driver(kind=kind, minimum=nums[0], maximum=nums[1], period=nums[2])
            else:
                raise ValueError(f"forstod ikke '{spec}'")
            self.overrides.pop(sig.path, None)
            print(f"  {sig.path}: {spec}")
            return

        raise ValueError(f"ukjent kommando '{cmd}' - skriv 'help'")

    def _need(self, args: list[str], n: int, usage: str) -> Signal:
        if len(args) < n:
            raise ValueError(f"bruk: {usage}")
        sig = self.contract.by_path(args[0])
        if sig is None:
            near = self.contract.matching(args[0])
            hint = f" Mente du {near[0].path}?" if len(near) == 1 else ""
            raise ValueError(f"finner ingen node '{args[0]}'.{hint}")
        return sig


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[1])
    here = Path(__file__).parent
    ap.add_argument("--signals", default=here / "signals.json", type=Path)
    ap.add_argument(
        "--host",
        default="auto",
        help="Adressen serveren lytter paa OG annonserer. 'auto' (standard) "
        "velger maskinens LAN-adresse, 'local' binder bare til 127.0.0.1. "
        "Unity kobler til den URL-en discovery returnerer, saa denne maa vaere "
        "en adresse klientene faktisk kan naa",
    )
    ap.add_argument("--port", default=4840, type=int)
    ap.add_argument("--rate", default=20.0, type=float, help="driveroppdateringer per sekund")
    ap.add_argument("--list", action="store_true", help="skriv ut kontrakten og avslutt")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("asyncua").setLevel(logging.DEBUG if args.verbose else logging.WARNING)

    try:
        contract = Contract.load(args.signals)
    except ContractError as e:
        print(f"Feil i signalkontrakten: {e}", file=sys.stderr)
        return 1

    print(format_table(contract))
    print()
    if args.list:
        return 0

    host = args.host
    available = local_ipv4_addresses()

    if host == "auto":
        host = primary_ipv4() or "127.0.0.1"
        if host == "127.0.0.1":
            print(
                "Fant ingen LAN-adresse automatisk, binder til 127.0.0.1.\n"
                "Bare denne maskinen naar serveren. Oppgi adressen selv hvis andre skal inn:\n"
                f"    python server.py --host <ip>\n"
                f"Adresser paa denne maskinen: {', '.join(available)}\n",
                file=sys.stderr,
            )
    elif host == "local":
        host = "127.0.0.1"
    elif host == "0.0.0.0":
        print(
            "Advarsel: med --host 0.0.0.0 annonserer serveren opc.tcp://0.0.0.0:4840,\n"
            "og klienter paa andre maskiner vil forsoeke aa koble til seg selv.\n"
            f"Bruk en konkret adresse i stedet: {', '.join(available)}\n",
            file=sys.stderr,
        )
    elif host not in available:
        print(
            f"Kan ikke binde til {host} - denne maskinen har ikke den adressen.\n"
            f"Tilgjengelige adresser: {', '.join(available)}\n"
            f"Eller dropp --host helt, saa velges {primary_ipv4() or '127.0.0.1'} automatisk.",
            file=sys.stderr,
        )
        return 1

    if host not in ("127.0.0.1", "0.0.0.0"):
        print(f"Andre maskiner kobler til:  opc.tcp://{host}:{args.port}")
        print("(husk brannmurregel for TCP 4840 inn)\n")

    load_ua()
    server = CraneSimServer(contract, host, args.port, args.rate)

    async def go() -> None:
        await server.build()
        await server.run()

    try:
        asyncio.run(go())
    except KeyboardInterrupt:
        pass
    print("Server stoppet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
