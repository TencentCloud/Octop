# Eight Sleep Schema (provider = 'eightsleep')

This file describes how Eight Sleep data is stored in the `health-sync` SQLite cache (`health.sqlite`).

At a glance:

- Table: `records`
- Provider: `provider = 'eightsleep'`
- Resources: `users_me`, `devices`, `users`, `trends`
- Storage model: one row per API document/day record, raw JSON in `payload_json`

Important notes about timestamps and watermarks:

- `users_me`, `devices`, and `users` are snapshot-like resources:
  - `records.start_time` and `records.end_time` are NULL.
  - `records.source_updated_at` is sync time (`utc_now_iso()`), not provider-side `updatedAt`.
- For `trends`:
  - `records.start_time` is `$.day` (fallback: `$.presenceStart`).
  - `records.end_time` is `$.presenceEnd`.
  - `records.source_updated_at` is `$.updatedAt` when present, otherwise `$.presenceStart` or `start_time`.
- `sync_state` watermarks for Eight Sleep resources are written as current sync time.
  - For incremental `trends` sync, this project reuses that watermark date and subtracts configured overlap days.

## Resource Map

### `users_me` (Current User Profile)

- Upstream endpoint: `GET /v1/users/me`
- `record_id`: `$.user.id` (fallback: `"me"`)
- `start_time`: NULL
- `end_time`: NULL
- `source_updated_at`: current sync timestamp (`utc_now_iso()`)

Top-level `payload_json` keys commonly present:

- `user` (object)

`payload_json.user` keys commonly present:

- `userId`
- `firstName`, `lastName`
- `email`, `emailVerified`
- `dob`, `gender`, `zip`
- `devices` (array)
- `currentDevice`
- `sleepTracking`
- `autopilotEnabled`
- `tempPreference`
- `createdAt`
- Additional account/app settings fields may appear.

Note:

- In observed data, `payload_json.user` includes `userId` (not `id`), so this code may store `record_id = "me"` unless the API also provides `user.id`.

### `devices`

- Upstream endpoint: `GET /v1/devices/{device_id}`
- `record_id`: first device id from `users_me.user.devices[]`
- `start_time`: NULL
- `end_time`: NULL
- `source_updated_at`: current sync timestamp (`utc_now_iso()`)

Top-level `payload_json` keys commonly present:

- `result` (object)

`payload_json.result` keys commonly present:

- Device/account linkage:
  - `deviceId`
  - `ownerId`
  - `leftUserId`, `rightUserId`
  - `awaySides` (object)
- Device state:
  - `online`
  - `timezone`
  - `firmwareVersion`
  - `firmwareUpdating`, `firmwareUpdated`
  - `lastHeard`
- Pod/side metrics:
  - `leftHeatingLevel`, `rightHeatingLevel`
  - `leftKelvin`, `rightKelvin`
  - `leftNowHeating`, `rightNowHeating`
  - `leftSchedule`, `rightSchedule`
- Additional hardware/network/sensor fields may appear.

### `users` (Bed Occupants / Related Users)

- Upstream endpoint: `GET /v1/users/{user_id}`
- `record_id`: `{user_id}` gathered from:
  - current user id
  - `devices.result.leftUserId`
  - `devices.result.rightUserId`
  - `devices.result.awaySides.*`
- `start_time`: NULL
- `end_time`: NULL
- `source_updated_at`: current sync timestamp (`utc_now_iso()`)

Top-level `payload_json` keys commonly present:

- `user` (object, same general shape as `users_me.user`)

### `trends` (Per-Day Sleep/Presence Metrics)

- Upstream endpoint: `GET /v1/users/{user_id}/trends`
- Request params used by this project:
  - `tz`
  - `from`
  - `to`
  - `include-main=false`
  - `include-all-sessions=true`
  - `model-version=v2`
- Response parsing:
  - loops over `trend_resp.days[]`
  - stores one `records` row per day item
- `record_id`: `{user_id}:{day}` (fallback: `{user_id}:{sha256(day_json)}`)
- `start_time`: `$.day` (fallback: `$.presenceStart`)
- `end_time`: `$.presenceEnd`
- `source_updated_at`: `$.updatedAt` or `$.presenceStart` or `start_time`

Top-level `payload_json` keys commonly present:

- Date/session identity:
  - `day`
  - `mainSessionId`
  - `sessionIds` (array)
  - `sessions` (array)
- Timing:
  - `presenceStart`, `presenceEnd`
  - `sleepStart`, `sleepEnd`
  - `presenceDuration`, `sleepDuration`
- Sleep staging/snoring:
  - `lightDuration`, `deepDuration`, `remDuration`
  - `deepPercent`, `remPercent`
  - `snoreDuration`, `snorePercent`
  - `heavySnoreDuration`, `heavySnorePercent`
- Scoring:
  - `score`
  - `sleepQualityScore`
  - `sleepRoutineScore`
- Other fields often present:
  - `tnt`
  - `performanceWindows` (array)
  - `tags` (array)
  - `hotFlash`
  - `incomplete`
- Additional mitigation/elevation fields may appear in some rows:
  - `mitigationEvents`
  - `stoppedSnoringEvents`
  - `reducedSnoringEvents`
  - `elevationDuration`
  - `snoringReductionPercent`

Nested `sessions[]` objects commonly include:

- `id`
- `duration`
- `sleepStart`, `sleepEnd`
- `presenceEnd`
- `score`
- `timezone`
- `stages`, `stageSummary`
- `timeseries`
- `snoring`

## `sync_state` Notes (Eight Sleep)

Eight Sleep writes sync markers for each resource:

- `sync_state.provider = 'eightsleep'`
- resources: `users_me`, `devices`, `users`, `trends`
- watermark values are sync timestamps (`utc_now_iso()`), not max event times.

For next `trends` run, `_trend_start_date()`:

- parses `sync_state('eightsleep','trends').watermark` as date/datetime
- subtracts `[eightsleep].overlap_days`
- falls back to `[eightsleep].start_date` on first run

## Common Analysis Queries

Latest nightly scores:

```sql
select
  record_id,
  start_time as day,
  json_extract(payload_json, '$.score') as score,
  json_extract(payload_json, '$.sleepQualityScore') as sleep_quality_score,
  json_extract(payload_json, '$.sleepRoutineScore') as sleep_routine_score,
  json_extract(payload_json, '$.sleepDuration') as sleep_duration_s
from records
where provider = 'eightsleep' and resource = 'trends'
order by day desc
limit 50;
```

Daily sleep stage durations:

```sql
select
  start_time as day,
  json_extract(payload_json, '$.lightDuration') as light_s,
  json_extract(payload_json, '$.deepDuration') as deep_s,
  json_extract(payload_json, '$.remDuration') as rem_s
from records
where provider = 'eightsleep' and resource = 'trends'
order by day desc
limit 60;
```

Per-user trend coverage:

```sql
select
  substr(record_id, 1, instr(record_id, ':') - 1) as user_id,
  min(start_time) as first_day,
  max(start_time) as last_day,
  count(*) as days
from records
where provider = 'eightsleep'
  and resource = 'trends'
  and instr(record_id, ':') > 0
group by user_id
order by days desc;
```

Flatten trend sessions for session-level analysis:

```sql
with trend_days as (
  select
    record_id as trend_record_id,
    start_time as day,
    payload_json
  from records
  where provider = 'eightsleep' and resource = 'trends'
)
select
  trend_record_id,
  day,
  json_extract(s.value, '$.id') as session_id,
  json_extract(s.value, '$.duration') as session_duration_s,
  json_extract(s.value, '$.score') as session_score,
  json_extract(s.value, '$.sleepStart') as session_sleep_start,
  json_extract(s.value, '$.sleepEnd') as session_sleep_end
from trend_days, json_each(trend_days.payload_json, '$.sessions') s
order by day desc
limit 200;
```

Device status snapshot:

```sql
select
  record_id as device_record_id,
  json_extract(payload_json, '$.result.deviceId') as device_id,
  json_extract(payload_json, '$.result.online') as online,
  json_extract(payload_json, '$.result.firmwareVersion') as firmware_version,
  json_extract(payload_json, '$.result.timezone') as timezone,
  json_extract(payload_json, '$.result.leftUserId') as left_user_id,
  json_extract(payload_json, '$.result.rightUserId') as right_user_id
from records
where provider = 'eightsleep' and resource = 'devices'
order by fetched_at desc
limit 10;
```

