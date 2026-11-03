# Whoop API Reference

Base URL: `https://api.prod.whoop.com/developer/v2`

> **Note**: v1 endpoints return 404 for sleep and recovery. Use v2 for all endpoints.
> All requests require a custom User-Agent header (Cloudflare blocks Python's default).

## Authentication
OAuth 2.0 Authorization Code flow.
- Auth URL: `https://api.prod.whoop.com/oauth/oauth2/auth`
- Token URL: `https://api.prod.whoop.com/oauth/oauth2/token`
- Scopes: `read:recovery read:cycles read:workout read:sleep read:profile read:body_measurement`

## Endpoints

### User
- `GET /user/profile/basic` → `{user_id, email, first_name, last_name}`
- `GET /user/measurement/body` → `{height_meter, weight_kilogram, max_heart_rate}`

### Sleep
- `GET /activity/sleep` → paginated list (params: start, end, limit, nextToken)
- `GET /activity/sleep/{sleepId}` → single sleep
- Score fields: `stage_summary` (total_in_bed, awake, light, deep/SWS, REM), `sleep_performance_percentage`, `sleep_consistency_percentage`, `sleep_efficiency_percentage`, `respiratory_rate`
- `sleep_needed`: baseline_milli, need_from_sleep_debt, need_from_recent_strain, need_from_recent_nap

### Recovery
- `GET /recovery` → paginated list
- `GET /recovery/cycle/{cycleId}` → single recovery for cycle
- Score fields: `recovery_score` (0-100%), `resting_heart_rate`, `hrv_rmssd_milli`, `spo2_percentage`, `skin_temp_celsius`
- Recovery zones: Green (67-100%), Yellow (34-66%), Red (0-33%)

### Cycles (Strain)
- `GET /cycle` → paginated list
- `GET /cycle/{cycleId}` → single cycle
- Score fields: `strain` (0-21 scale), `kilojoule`, `average_heart_rate`, `max_heart_rate`

### Workouts
- `GET /activity/workout` → paginated list
- `GET /activity/workout/{workoutId}` → single workout
- Score fields: `strain`, `average_heart_rate`, `max_heart_rate`, `kilojoule`, `distance_meter`, `altitude_gain_meter`, `zone_duration` (HR zones in ms)

## Pagination
All collection endpoints support: `limit` (max 25), `start` (ISO datetime), `end` (ISO datetime), `nextToken`.
Response: `{records: [...], next_token: "..."}`.

## Rate Limits
Not officially documented. Use reasonable delays between batch requests.
