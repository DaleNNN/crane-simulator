# OPC UA-testserver

Står inn for CDP-applikasjonen slik at Unity-simulatoren kan testes uten PLS og
uten at CDP Studio kjører. Serveren eksponerer de samme nodene som
`OPCUAtest/CraneTest` gjør, med testbevegelse på inngangene, så du kan verifisere
at riktig ledd beveger seg riktig vei før noe kobles mot ekte utstyr.

## Kom i gang

```bash
cd tools/opcua-sim
pip install -r requirements.txt
python server.py
```

I Unity setter du `CraneOpcClient.serverUrl` til `opc.tcp://127.0.0.1:4840` og
trykker Play. Bommen skal begynne å bevege seg med en gang.

For å se kontrakten uten å starte noe — dette virker også uten at `asyncua` er
installert:

```bash
python server.py --list
```

## Signals.json er fasiten

Hele adresserommet bygges fra `signals.json`. Å legge til en node er en rad der,
ikke en kodeendring:

```json
{
  "path": "Crane.HoistSpeed",
  "type": "Double",
  "unit": "m/s",
  "direction": "toUnity",
  "range": [-2, 2],
  "driver": { "kind": "sine", "amplitude": 1.5, "period": 12 }
}
```

`path` blir NodeId-en direkte: `Crane.HoistSpeed` gir `ns=1;s=Crane.HoistSpeed`,
og prikkene blir nestede objekter i adresserommet, akkurat som `ObjectNode` og
`VariableNode` i CDP. Det betyr at den samme lista også er spesifikasjonen
CDP-siden skal implementere — og at avvik mellom de to blir synlige med én gang,
i stedet for som en node som mystisk aldri oppdaterer seg.

**`direction` er sett fra simulatoren:**

| verdi | betydning |
|---|---|
| `toUnity` | CDP eier verdien. Unity abonnerer. Serveren driver den med testbevegelse. |
| `fromUnity` | Simulatoren eier verdien. Unity skriver. Serveren logger skrivingen. |

Felter: `type` (Double, Float, Int32, UInt32, Int64, Boolean, String), `unit`,
`initial`, `range` som `[min, max]` (klamper alt som skrives), `description`, og
`driver` med `kind` lik `constant`, `sine`, `ramp`, `triangle` eller `square`.
Sine tar `amplitude`, `period`, `offset`, `phase`; de andre tar `min`, `max`,
`period`.

Kjør `python selftest.py` etter endringer. Den fanger duplikater, ugyldige stier,
typefeil og skjeve `range` før serveren i det hele tatt starter, og krever ikke
`asyncua`.

## Mens serveren kjører

```
list [filter]        vis noder og verdier, evt. bare de som matcher
get <path>           les én verdi
set <path> <verdi>   sett en verdi manuelt (slår av driveren for den noden)
drive <path> <spec>  off | sine:<amp>:<periode> | ramp:<min>:<max>:<periode>
quit
```

`set Crane.SlewAngle 90` er den raskeste måten å sjekke at fortegn og nullpunkt
stemmer: sett en verdi du vet hva skal bety, og se om krana i Unity peker dit du
forventer.

## Ting som pleier å gå galt

**Namespace må bli 1.** `CraneOpcClient` bruker `new NodeId(identifier, 1)`, altså
hardkodet `ns=1`. Serveren setter application-URI til kontraktens URI slik at
namespacet lander på indeks 1, og advarer høylytt i loggen hvis det likevel ikke
gjør det. Ser du den advarselen, finner ikke Unity nodene.

**`--host` er også det som annonseres.** Unity-klienten kaller `GetEndpoints` og
kobler til URL-en den får tilbake, så adressen serveren binder til er også den
klientene får utlevert. Standard er `auto`, som plukker maskinens LAN-adresse —
da virker både lokal og ekstern tilkobling uten at du gjør noe.

| `--host` | binder til | brukes når |
|---|---|---|
| *utelatt* / `auto` | maskinens LAN-IP | normalt |
| `local` | `127.0.0.1` | bare denne maskinen, ingen brannmurregel nødvendig |
| en konkret IP | den adressen | flere nettverkskort og du vil styre hvilket |

Du kan bare binde til en adresse maskinen faktisk har. Oppgir du en annen, sier
serveren fra og lister hvilke som finnes, i stedet for å kaste `OSError: could
not bind`. `--host 0.0.0.0` frarådes: da annonseres `opc.tcp://0.0.0.0:4840`, og
klienter på andre maskiner prøver å koble til seg selv.

Når serveren binder til en LAN-adresse trenger du en brannmurregel for innkommende
TCP 4840:

```powershell
New-NetFirewallRule -DisplayName "OPC UA 4840" -Direction Inbound `
  -Protocol TCP -LocalPort 4840 -Action Allow -Profile Any
```

**De to advarslene ved oppstart** — `No signing policy available` og
`No encrypting policy available` — kommer fordi serveren kjører uten sikkerhet.
Det er meningen for en testserver, og ufarlig på et lukket nett. Ikke gjør det
samme i produksjon.

**Sertifikatet.** `CraneOpcClient` laster en `.pfx` fra en hardkodet sti. Denne
serveren kjører uten sikkerhet (`SecurityMode=None`, anonym), men Unity-koden
laster sertifikatet uansett — så stien må peke på en fil som finnes, ellers
kommer du aldri forbi `Connect()`.

## Forholdet til CDP-prosjektet

`OPCUAtest/CraneTest` er den ekte serveren. Den har foreløpig tre noder under
`ObjectNode` `Crane`, der `BoomAngle` er rutet fra `Sine`-komponenten med
amplitude 30 og 0.2 Hz. `signals.json` speiler den med vilje, så de to skal
oppføre seg likt.

To ting å sjekke i CDP-prosjektet når nodelista vokser:

`IdType="Automatic"` på `VariableNode` lar CDP bestemme NodeId-ene selv. Unity
antar strengen `Crane.SlewAngle`. Bla i serveren med UaExpert og bekreft at det
faktisk er det du får — hvis CDP genererer numeriske ID-er i stedet, finner ikke
Unity noe som helst, uten at noe feiler høylytt.

`AccessLevel="125"` har ikke CurrentWrite-biten satt, så nodene er skrivebeskyttet
for klienter. Det holder for `toUnity`-signaler. Men alt Unity skal skrive tilbake
— `Crane.Tip.*`, `Sim.Heartbeat` og resten av `fromUnity`-lista — trenger 127.
