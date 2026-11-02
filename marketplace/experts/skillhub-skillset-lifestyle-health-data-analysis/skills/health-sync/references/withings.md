# Withings Schema (provider = 'withings')

This file describes how Withings data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'withings'`
- Resources: `measures`, `activity`, `workouts`, `sleep_summary`
- Storage model: one row per Withings document, raw JSON in `payload_json`

Important note about Withings measure values:

- In `measures`, each element in `$.measures[]` uses a `(value, unit)` pair.
- The real-world value is typically `value * 10^unit` (e.g., grams -> kg scaling).

## Resource Map

### `measures` (Body / Vitals)

- Upstream endpoint: `POST https://wbsapi.withings.net/measure` with `action=getmeas`
- `record_id`: `$.grpid` (measure group id)
- `start_time`: derived from `$.date` (epoch seconds) into ISO timestamp (UTC)
- `end_time`: NULL
- `source_updated_at`: `$.modified` (epoch seconds, stored as string)

Top-level `payload_json` keys commonly present:

- `grpid` (integer)
- `date` (epoch seconds)
- `modified` (epoch seconds)
- `category` (integer)
- `attrib` (integer)
- `timezone` (string)
- `deviceid` / `hash_deviceid` (integers/strings depending on response)
- `model` / `modelid` (device model identifiers)
- `measures` (array)

`payload_json.measures[]` elements:

- `type` (integer): measurement type code (e.g., `1` weight)
- `unit` (integer): base-10 exponent to scale `value`
- `value` (integer): scaled integer value
- `algo` (integer, optional)
- `fm` (integer, optional)

Common `type` codes synced by default (see `health_sync/providers/withings.py`):

- `1` Weight
- `4` Height
- `5` FatFreeMass
- `6` FatRatio
- `8` FatMassWeight
- `9` DiastolicBP
- `10` SystolicBP
- `11` HeartPulse
- `12` Temp
- `54` SPO2
- `71` BodyTemp
- `73` SkinTemp
- `76` MuscleMass
- `77` Hydration
- `88` BoneMass
- `91` Pulse Wave Velocity
- `123` VO2 max

### `activity` (Daily Activity)

- Upstream endpoint: `POST https://wbsapi.withings.net/v2/measure` with `action=getactivity`
- `record_id`: usually `$.date` (YYYY-MM-DD)
- `start_time`: `$.date` (YYYY-MM-DD)
- `end_time`: NULL
- `source_updated_at`: NULL (Withings activity responses typically do not provide a per-row modified timestamp)

Top-level `payload_json` keys commonly present:

- `date` (YYYY-MM-DD)
- `steps`
- `distance`
- `elevation`
- `calories`
- `totalcalories`
- `active`, `soft`, `moderate`, `intense`
- Optional HR zone fields may appear depending on device/data availability:
  - `hr_average`, `hr_min`, `hr_max`, `hr_zone_0..3`
- Plus device metadata fields like `brand`, `deviceid`, `model`, `modelid`, `timezone`, `modified`

### `workouts` (Workout Sessions)

- Upstream endpoint: `POST https://wbsapi.withings.net/v2/measure` with `action=getworkouts`
- `record_id`: `$.id` (workout id)
- `start_time`: derived from `$.startdate` (epoch seconds) into ISO timestamp (UTC)
- `end_time`: derived from `$.enddate` (epoch seconds) into ISO timestamp (UTC)
- `source_updated_at`: `$.modified` (epoch seconds, stored as string)

Top-level `payload_json` keys commonly present:

- `id` (integer)
- `startdate` / `enddate` (epoch seconds)
- `modified` (epoch seconds)
- `date` (YYYY-MM-DD, may be present)
- `timezone` (string)
- `deviceid`, `model`
- `attrib`, `category`
- `data` (object): workout metrics

`payload_json.data` keys commonly requested by this project:

- `calories`
- `effduration`
- `intensity`
- `manual_distance`
- `manual_calories`
- `pause_duration`
- `algo_pause_duration`
- `steps`
- `distance`
- `elevation`
- Heart rate stats:
  - `hr_average`, `hr_min`, `hr_max`, `hr_zone_0..3`
- `spo2_average`

### `sleep_summary` (Aggregated Sleep)

- Upstream endpoint: `POST https://wbsapi.withings.net/v2/sleep` with `action=getsummary`
- `record_id`: `$.id` (sleep summary id)
- `start_time`: derived from `$.startdate` (epoch seconds) into ISO timestamp (UTC)
- `end_time`: derived from `$.enddate` (epoch seconds) into ISO timestamp (UTC)
- `source_updated_at`: `$.modified` (epoch seconds, stored as string)

Top-level `payload_json` keys commonly present:

- `id`
- `startdate` / `enddate` (epoch seconds)
- `modified` (epoch seconds)
- `date` (YYYY-MM-DD, may be present)
- `timezone`
- `created`, `completed`
- `data` (object): summary metrics

`payload_json.data` keys vary by device generation; commonly:

- `sleep_score`
- `lightsleepduration`, `deepsleepduration`, `remsleepduration`
- `wakeupcount`, `wakeupduration`
- `durationtosleep`, `durationtowakeup`
- `hr_average`, `hr_min`, `hr_max`
- `rr_average`, `rr_min`, `rr_max`
- Additional fields may appear, e.g. `snoring`, `chest_movement_rate_*`, etc.

## `sync_state` Notes (Withings)

Withings incremental sync uses epoch seconds.

- `sync_state.provider = 'withings'`
- Provider code computes/uses epoch values for `lastupdate`, but persisted `sync_state.watermark` is normalized to UTC ISO format in SQLite.
- On read, provider code converts the stored watermark back to epoch seconds before calling the API.

## Common Analysis Queries

Daily steps (last 30 days):

```sql
select
  start_time as day,
  json_extract(payload_json, '$.steps') as steps,
  json_extract(payload_json, '$.distance') as distance_m
from records
where provider = 'withings' and resource = 'activity'
order by day desc
limit 30;
```

Weight time series (type = 1) with scaling:

```sql
with grp as (
  select start_time as ts, payload_json
  from records
  where provider = 'withings' and resource = 'measures'
),
meas as (
  select
    grp.ts,
    json_extract(m.value, '$.type') as type,
    json_extract(m.value, '$.value') as value_i,
    json_extract(m.value, '$.unit') as unit_exp
  from grp, json_each(grp.payload_json, '$.measures') m
)
select
  ts,
  (value_i * pow(10, unit_exp)) as value
from meas
where type = 1
order by ts desc
limit 50;
```

Workouts calories and duration:

```sql
select
  start_time as start_dt,
  end_time as end_dt,
  json_extract(payload_json, '$.data.calories') as calories,
  json_extract(payload_json, '$.data.effduration') as effduration_s
from records
where provider = 'withings' and resource = 'workouts'
order by start_dt desc
limit 50;
```
