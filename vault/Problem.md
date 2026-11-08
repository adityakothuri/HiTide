---
tags: [hitide, problem, sources]
status: done
updated: 2026-11-07
---

# Problem

Flash floods kill people in cars. The water is often moving, the road looks passable, and the driver is alone. We want to reach opted-in drivers before they drive into water, and to escalate when they are already stuck.

## Why vehicles

- NWS says that more deaths occur in flooding than from any other thunderstorm-related hazard. [NWS, Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown)
- The same NWS page cites the CDC: "over half of all flood-related drownings occur when a vehicle is driven into hazardous flood water." [NWS, Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown)
- "Many of the deaths occur in cars swept downstream." [NWS, Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown)

> [!warning] Brief wording differs from the source
> The brief says "most flood deaths occur in vehicles." The NWS page says "over half of all flood-related drownings" and attributes it to the CDC. Quote the NWS wording on stage.

## Why these depths

NWS "Turn Around Don't Drown" thresholds, as published:

| Depth over road | NWS wording | Our status |
|---|---|---|
| 6 in | "A mere 6 inches of fast-moving flood water can knock over an adult." | `closed` (for cars) |
| 12 in | "It takes just 12 inches of rushing water to carry away most cars." | `float` |
| 24 in (2 ft) | "just 2 feet of rushing water can carry away SUVs and trucks." | `boat` |

Source: [NWS, Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown). The 3 in `caution` band is our addition. The thresholds live in `backend/config/weights.yaml`.

> [!warning] Brief wording differs from the source
> The brief says "24 in sweeps away most vehicles." The NWS page says 12 in carries away most cars and 2 ft carries SUVs and trucks. Use the NWS figures. The comment in `backend/config/weights.yaml` already matches NWS.

## The July 2025 Kerr County flood

- Destructive flooding began on **July 4, 2025** in the Texas Hill Country. Kerr County and the Guadalupe River watershed were the worst hit. [Wikipedia, July 2025 Central Texas floods](https://en.wikipedia.org/wiki/July_2025_Central_Texas_floods)
- The river surge measured **21 ft in one hour at Kerrville**. [Wikipedia, July 2025 Central Texas floods](https://en.wikipedia.org/wiki/July_2025_Central_Texas_floods)
- Wikipedia reports **136 people killed**, with **117 in Kerr County** (snapshot checked 2026-11-07). [Wikipedia, July 2025 Central Texas floods](https://en.wikipedia.org/wiki/July_2025_Central_Texas_floods)
- Kerr County had no dedicated flood warning system, despite earlier proposals from local officials. [Wikipedia, July 2025 Central Texas floods](https://en.wikipedia.org/wiki/July_2025_Central_Texas_floods)

> [!note] Secondary source
> The death toll and crest figures come from Wikipedia, which cites news outlets. Check them against official Kerr County or NWS reports before quoting them on stage.

## Gap we fill

Drivers get generic alerts. They do not get a pre-trip warning tied to their usual route, a turn-around alert while they are still moving, or an escalation when they stop in water. See [[Pitch]] and [[Architecture]].

## Related

- [[Data Sources]] for the feeds we use
- [[Stage 1 Pre-trip]], [[Stage 2 En route]], [[Stage 3 Stopped in water]]
- [[Privacy and Consent]]
