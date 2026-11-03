#!/usr/bin/env python3
"""
Ephemeris helper — fetch planetary positions and major aspects.
Requires: pip install pyswisseph
"""

import swisseph as swe
from datetime import datetime, timedelta

SIGNS = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo',
         'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']

PLANETS = {
    'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY,
    'Venus': swe.VENUS, 'Mars': swe.MARS, 'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN, 'Uranus': swe.URANUS, 'Neptune': swe.NEPTUNE,
    'Pluto': swe.PLUTO
}

ASPECTS = {
    'conjunction': 0, 'sextile': 60, 'square': 90,
    'trine': 120, 'opposition': 180
}
ASPECT_ORBS = {
    'conjunction': 8, 'sextile': 6, 'square': 7,
    'trine': 8, 'opposition': 8
}


def get_julian_day(dt):
    """Convert datetime to Julian day."""
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0)


def get_planet_position(planet_id, dt):
    """Return (sign, degree, longitude) for a planet at given datetime."""
    jd = get_julian_day(dt)
    result = swe.calc_ut(jd, planet_id)
    lon = result[0][0]
    sign_idx = int(lon / 30)
    degree = lon % 30
    return SIGNS[sign_idx], degree, lon


def get_all_positions(dt):
    """Get all planet positions at a given datetime."""
    positions = {}
    for name, pid in PLANETS.items():
        sign, deg, lon = get_planet_position(pid, dt)
        positions[name] = {
            'sign': sign, 'degree': round(deg, 2), 'longitude': round(lon, 4)
        }
    return positions


def find_aspects(dt, orb_factor=1.0):
    """Find all major aspects between planets."""
    positions = get_all_positions(dt)
    planet_names = list(positions.keys())
    aspects_found = []

    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1, p2 = planet_names[i], planet_names[j]
            lon1 = positions[p1]['longitude']
            lon2 = positions[p2]['longitude']
            diff = abs(lon1 - lon2)
            if diff > 180:
                diff = 360 - diff

            for aspect_name, angle in ASPECTS.items():
                orb = ASPECT_ORBS[aspect_name] * orb_factor
                if abs(diff - angle) <= orb:
                    aspects_found.append({
                        'planet1': p1, 'planet2': p2,
                        'aspect': aspect_name,
                        'orb': round(abs(diff - angle), 2),
                        'exact_diff': round(diff, 2)
                    })

    return aspects_found


def weekly_summary(start_date):
    """Generate a weekly planetary summary."""
    positions_start = get_all_positions(start_date)
    end_date = start_date + timedelta(days=7)
    positions_end = get_all_positions(end_date)
    aspects = find_aspects(start_date + timedelta(days=3))  # mid-week aspects

    sign_changes = []
    for planet in PLANETS:
        if positions_start[planet]['sign'] != positions_end[planet]['sign']:
            sign_changes.append({
                'planet': planet,
                'from': positions_start[planet]['sign'],
                'to': positions_end[planet]['sign']
            })

    return {
        'start': start_date.isoformat(),
        'end': end_date.isoformat(),
        'positions': positions_start,
        'aspects': aspects,
        'sign_changes': sign_changes
    }


if __name__ == '__main__':
    import json
    now = datetime.utcnow()
    print("=== Planetary Positions ===")
    for name, data in get_all_positions(now).items():
        print(f"  {name:10s}: {data['sign']:13s} {data['degree']:6.2f}°")

    print("\n=== Major Aspects ===")
    for a in find_aspects(now):
        print(f"  {a['planet1']} {a['aspect']} {a['planet2']} (orb: {a['orb']}°)")

    print("\n=== Weekly Summary (JSON) ===")
    summary = weekly_summary(now)
    print(json.dumps(summary, indent=2, default=str))
