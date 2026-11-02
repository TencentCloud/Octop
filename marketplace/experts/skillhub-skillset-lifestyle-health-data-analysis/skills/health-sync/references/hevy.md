# Hevy Schema (provider = 'hevy')

This file describes how Hevy data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'hevy'`
- Resources: `workouts`, `workout_events`
- Storage model: one row per workout (plus optional audit/event rows), raw JSON in `payload_json`

Data-quality note:

- If the user identifies a known cleanup/correction date, apply a cutoff when doing trend/report analysis.
- Session baseline from setup errata: `2026-02-12` onward is trusted.

## Resource Map

### `workouts`

- Upstream endpoints:
  - First sync: `GET /v1/workouts` (paged)
  - Delta sync: `GET /v1/workouts/events?since=...` (stores updated workouts)
- `record_id`: `$.id` (UUID string)
- `start_time`: `$.start_time` (ISO datetime)
- `end_time`: `$.end_time` (ISO datetime)
- `source_updated_at`: `$.updated_at` (fallback: `$.created_at`)

Top-level `payload_json` keys commonly present:

- `id` (UUID)
- `title` (string)
- `description` (string or null)
- `routine_id` (UUID or null)
- `start_time` (ISO datetime)
- `end_time` (ISO datetime)
- `created_at` (ISO datetime)
- `updated_at` (ISO datetime)
- `exercises` (array)

`payload_json.exercises[]` element keys:

- `index` (integer)
- `title` (string)
- `notes` (string or null)
- `exercise_template_id` (UUID)
- `superset_id` (UUID or null)
- `sets` (array)

`payload_json.exercises[].sets[]` element keys:

- `index` (integer)
- `type` (string): indicates the set modality
- `weight_kg` (number or null)
- `reps` (integer or null)
- `distance_meters` (number or null)
- `duration_seconds` (integer or null)
- `rpe` (number or null)
- `custom_metric` (varies; may be null)

Notes:

- Hevy uses mixed modalities; do not assume every set has `weight_kg` and `reps`.
- Workout `start_time`/`end_time` strings may be in `...Z` or `...+00:00` format depending on the client.

### `workout_events` (Audit Trail)

This project stores an optional event log when syncing via `/v1/workouts/events`.

- `record_id`:
  - Updated: `updated:{workout_id}:{updated_at}`
  - Deleted: `deleted:{workout_id}:{deleted_at}`
- `start_time`:
  - Updated: `$.workout.updated_at` (or `$.workout.created_at`)
  - Deleted: `$.deleted_at` (if present)
- `source_updated_at`: mirrors `start_time`

Top-level `payload_json` keys commonly present:

- `type` (string): `updated` or `deleted`
- `workout` (object): the full workout (for `updated`)

`payload_json.workout` has the same shape as a normal `workouts` payload.

## Common Analysis Queries

Workout list (most recent first):

```sql
select
  start_time,
  end_time,
  json_extract(payload_json, '$.title') as title,
  json_extract(payload_json, '$.updated_at') as updated_at
from records
where provider = 'hevy'
  and resource = 'workouts'
  and start_time >= '2026-02-12'
order by start_time desc
limit 50;
```

Workouts per month:

```sql
select substr(start_time, 1, 7) as month, count(*) as workouts
from records
where provider = 'hevy'
  and resource = 'workouts'
  and start_time >= '2026-02-12'
group by month
order by month;
```

Top exercises (by appearance in workouts):

```sql
with workouts as (
  select record_id, payload_json
  from records
  where provider = 'hevy'
    and resource = 'workouts'
    and start_time >= '2026-02-12'
),
exercises as (
  select
    workouts.record_id as workout_id,
    json_extract(e.value, '$.title') as exercise_title
  from workouts, json_each(workouts.payload_json, '$.exercises') e
)
select exercise_title, count(*) as n
from exercises
where exercise_title is not null
group by exercise_title
order by n desc
limit 30;
```

Total lifted volume approximation (sum of weight_kg * reps for strength sets):

```sql
with workouts as (
  select record_id, start_time, payload_json
  from records
  where provider = 'hevy'
    and resource = 'workouts'
    and start_time >= '2026-02-12'
),
sets as (
  select
    workouts.record_id as workout_id,
    workouts.start_time as start_time,
    json_extract(s.value, '$.weight_kg') as weight_kg,
    json_extract(s.value, '$.reps') as reps
  from workouts,
       json_each(workouts.payload_json, '$.exercises') e,
       json_each(e.value, '$.sets') s
)
select
  substr(start_time, 1, 10) as day,
  round(sum(weight_kg * reps), 1) as volume_kg_reps
from sets
where weight_kg is not null and reps is not null
group by day
order by day desc
limit 30;
```
