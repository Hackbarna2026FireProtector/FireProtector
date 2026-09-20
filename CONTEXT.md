# FireProtector

Wildfire values-at-risk tooling for Catalonia. The system answers two questions
about a fire that has not happened yet: where would it spread, and what is in
the way that we should protect first.

## Language

### The fire

**Ignition Scenario**:
A hypothetical ignition at a chosen coordinate, from which a spread forecast is
simulated. Nobody observed it, so it has no detection time and no containment
state.
_Avoid_: Fire, incident, event

**Spread Forecast**:
The set of hourly perimeters produced by one simulation of an Ignition Scenario.
_Avoid_: Prediction, projection

**Arrival Contour**:
One hourly perimeter of a Spread Forecast — the area burned within that many
hours of ignition.
_Avoid_: Isochrone, ring, band

**Arrival Grid**:
A raster of first-arrival hours per 100 m cell, derived from the Arrival
Contours. A display and export artefact, never an input to ranking.
_Avoid_: Raster, heatmap

### The things at risk

**Register Asset**:
A building footprint point in the Catalonia INSPIRE register. Millions of them,
unnamed, typed only by INSPIRE building nature. Counted in aggregate, never
presented individually by name.
_Avoid_: Building, structure, feature

**Critical Facility**:
A named, typed facility whose loss matters beyond its own footprint — a
hospital, school, substation, care home, water plant, telecom tower or fuel
station.
_Avoid_: POI, amenity, important asset

**Asset**:
Either a Register Asset or a Critical Facility. Use the specific term unless a
statement is genuinely true of both; on the wire both are carried in the same
shape.

**Reached Set**:
The Assets that a Spread Forecast's Arrival Contours intersect, plus a small
margin. The only Assets that are ever scored — anything outside has no arrival
time and therefore no risk.
_Avoid_: Affected assets, in-scope assets

### The judgement

**Exposure**:
What an Arrival Contour does to one Asset: when the fire reaches it, and how
much the forecast agrees on that.
_Avoid_: Impact, threat

**Value**:
An Asset's relative importance, 1–100, assigned from its type. A ranking
position, not a monetary amount.
_Avoid_: Cost, worth, price, criticality

**Vulnerability**:
An Asset's susceptibility to fire damage, 0–1, assigned from its type.
_Avoid_: Fragility, susceptibility, risk

**Confidence**:
How far a Spread Forecast agrees with itself about an Arrival Contour. Only
meaningful when the simulation is run as an ensemble; a value invented from
elapsed time is not Confidence.
_Avoid_: Certainty, probability, accuracy

**Risk**:
The product of an Asset's Value, Vulnerability, Confidence and urgency factors,
in 0–1. The quantity the ranking sorts on.
_Avoid_: Score, priority, threat level

**Robustness**:
How far the ranking moves when one scoring parameter is perturbed at a time.
The answer to "should this ranking be trusted", distinct from the ranking
itself.
_Avoid_: Stability, confidence, sensitivity

**Briefing**:
A short natural-language account of a scored Ignition Scenario, in English,
Spanish and Catalan, every number and name in which must appear in the facts it
was generated from.
_Avoid_: Summary, report, narrative

### Plumbing

**Bundle**:
Everything derived from one Ignition Scenario that is expensive to compute — its
Spread Forecast, Reached Set and Exposures — cached together because they are
only ever needed together.
_Avoid_: Cache entry, context, snapshot

**Contract**:
The asset-register request and response shape that other people's code is
written against. Served at the repository root and not ours to change
unilaterally.
_Avoid_: API, schema, interface
