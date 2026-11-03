# Strava Schema (provider = 'strava')

This file describes how Strava data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'strava'`
- Resources: `athlete`, `activities`
- Storage model: one row per Strava document, raw JSON in `payload_json`

Important notes about timestamps and watermarks:

- For `activities`, `records.start_time` is `$.start_date` (ISO datetime in UTC).
- For `activities`, `records.source_updated_at` is `$.updated_at` when present, otherwise `$.start_date`.
- For `athlete`, `records.source_updated_at` is set to sync time (`utc_now`) in the provider code, not to Strava's profile `updated_at`.
- `sync_state` for `strava/activities` is stored as an ISO timestamp in SQLite, but is computed from epoch seconds in the sync loop.

## Resource Map

### `athlete` (Profile Snapshot)

- Upstream endpoint: `GET /api/v3/athlete`
- `record_id`: `$.id` (fallback: `"me"`)
- `start_time`: NULL
- `end_time`: NULL
- `source_updated_at`: current sync timestamp (`utc_now_iso()`)

Top-level `payload_json` keys commonly present:

- `id`
- `username`
- `firstname`, `lastname`
- `bio`
- `city`, `state`, `country`
- `sex`
- `weight`
- `profile`, `profile_medium`
- `created_at`, `updated_at`
- `premium`, `summit`, `follower`, `friend`

### `activities`

- Upstream endpoint: `GET /api/v3/athlete/activities`
- Request params used by this project:
  - `after` (epoch seconds)
  - `page`
  - `per_page` (1-200)
- `record_id`: `$.id` (fallback: SHA-256 hash of canonicalized JSON payload)
- `start_time`: `$.start_date` (ISO datetime, usually `...Z`)
- `end_time`: NULL
- `source_updated_at`: `$.updated_at` (if present), otherwise `$.start_date`

Top-level `payload_json` keys commonly present:

- Identity/labeling:
  - `id`
  - `name`
  - `type`
  - `sport_type`
  - `workout_type` (optional)
- Time/location:
  - `start_date`
  - `start_date_local`
  - `timezone`
  - `utc_offset`
  - `location_city`, `location_state`, `location_country`
  - `start_latlng`, `end_latlng`
- Effort metrics:
  - `distance` (meters)
  - `moving_time` (seconds)
  - `elapsed_time` (seconds)
  - `total_elevation_gain` (meters)
  - `average_speed`, `max_speed` (meters/second)
  - `average_heartrate`, `max_heartrate` (optional)
  - `suffer_score` (optional)
  - `kilojoules` (optional)
- Visibility/flags:
  - `private`
  - `visibility`
  - `manual`
  - `trainer`
  - `commute`
  - `flagged`
  - `has_heartrate`
- Social/metadata:
  - `achievement_count`
  - `kudos_count`
  - `comment_count`
  - `athlete_count`
  - `photo_count`
  - `total_photo_count`
  - `pr_count`
  - `has_kudoed`
  - `external_id`
  - `upload_id`
  - `gear_id`
  - `device_name`

Nested objects commonly present:

- `athlete`
  - `id`
  - `resource_state`
- `map`
  - `id`
  - `summary_polyline`
  - `resource_state`

Notes:

- In observed data, `record_id` for `activities` matches `$.id` for all rows.
- `activities` may include many sport types (for example `Run`, `Walk`, `WeightTraining`, `StairStepper`, `Hike`, `Swim`).

## `sync_state` Notes (Strava)

Strava activity sync uses watermark overlap and pagination:

- `sync_state.provider = 'strava'`
- `sync_state.resource = 'activities'`
- Stored watermark tracks the max seen activity start time and is reused as the next `after` baseline minus configured overlap seconds.

The `athlete` resource also writes sync state with a current timestamp watermark, mainly as a freshness marker.

## Common Analysis Queries

Recent Strava activities:

```sql
select
  start_time as start_dt,
  json_extract(payload_json, '$.name') as name,
  json_extract(payload_json, '$.sport_type') as sport_type,
  round(json_extract(payload_json, '$.distance') / 1000.0, 2) as distance_km,
  json_extract(payload_json, '$.moving_time') as moving_time_s,
  json_extract(payload_json, '$.elapsed_time') as elapsed_time_s
from records
where provider = 'strava' and resource = 'activities'
order by start_dt desc
limit 50;
```

Monthly activity counts by sport type:

```sql
select
  substr(start_time, 1, 7) as month,
  json_extract(payload_json, '$.sport_type') as sport_type,
  count(*) as activities
from records
where provider = 'strava' and resource = 'activities'
group by month, sport_type
order by month desc, activities desc;
```

Monthly distance and moving time totals:

```sql
select
  substr(start_time, 1, 7) as month,
  round(sum(json_extract(payload_json, '$.distance')) / 1000.0, 1) as distance_km,
  round(sum(json_extract(payload_json, '$.moving_time')) / 3600.0, 1) as moving_hours,
  count(*) as activities
from records
where provider = 'strava' and resource = 'activities'
group by month
order by month desc;
```

Heart rate coverage by sport type:

```sql
select
  json_extract(payload_json, '$.sport_type') as sport_type,
  sum(case when json_type(payload_json, '$.average_heartrate') is not null then 1 else 0 end) as with_hr,
  count(*) as total,
  round(100.0 * sum(case when json_type(payload_json, '$.average_heartrate') is not null then 1 else 0 end) / count(*), 1) as pct_with_hr
from records
where provider = 'strava' and resource = 'activities'
group by sport_type
order by total desc;
```

Coverage window and sync watermark sanity check:

```sql
select
  (select min(start_time) from records where provider = 'strava' and resource = 'activities') as min_activity_start,
  (select max(start_time) from records where provider = 'strava' and resource = 'activities') as max_activity_start,
  (select watermark from sync_state where provider = 'strava' and resource = 'activities') as sync_watermark;
```

