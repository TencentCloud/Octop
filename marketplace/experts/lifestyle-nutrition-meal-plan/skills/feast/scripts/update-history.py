#!/usr/bin/env python3
"""
Feast: Update meal history after a reveal/cook

Usage:
    python update-history.py --meals-dir ~/.openclaw/workspace/meals \
        --date 2026-02-03 \
        --name "Thai Green Curry" \
        --cuisine "Thai" \
        [--region "Central Thailand"] \
        [--week-file "2026-02-02.md"] \
        [--rating 4] \
        [--notes "Loved it, maybe more chilli next time"]

This script:
1. Loads history.yaml
2. Adds the new meal entry
3. Updates statistics
4. Saves history.yaml
"""

import argparse
import yaml
from pathlib import Path
from datetime import datetime
from collections import Counter


def load_yaml(path: Path) -> dict:
    """Load a YAML file, return empty dict if not found."""
    if not path.exists():
        return {}
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict):
    """Save data to a YAML file."""
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def update_statistics(history: dict) -> dict:
    """Recalculate statistics from meal history."""
    meals = history.get('meals', [])
    
    if not meals:
        return {
            'totalMealsCooked': 0,
            'cuisineBreakdown': {},
            'averageRating': None,
            'topRatedMeals': [],
            'recentCuisines': []
        }
    
    # Count cuisines
    cuisines = [m.get('cuisine') for m in meals if m.get('cuisine')]
    cuisine_counts = dict(Counter(cuisines))
    
    # Calculate average rating (only rated meals)
    ratings = [m.get('rating') for m in meals if m.get('rating') is not None]
    avg_rating = sum(ratings) / len(ratings) if ratings else None
    
    # Top rated meals (rating 5)
    top_rated = [m.get('name') for m in meals if m.get('rating') == 5]
    
    # Recent cuisines (last 4 weeks = last 28 meals max)
    recent = meals[-28:] if len(meals) > 28 else meals
    recent_cuisines = list(dict.fromkeys([m.get('cuisine') for m in recent if m.get('cuisine')]))
    
    return {
        'totalMealsCooked': len(meals),
        'cuisineBreakdown': cuisine_counts,
        'averageRating': round(avg_rating, 1) if avg_rating else None,
        'topRatedMeals': top_rated[-10:],  # Last 10 top-rated
        'recentCuisines': recent_cuisines[-8:]  # Last 8 unique cuisines
    }


def main():
    parser = argparse.ArgumentParser(description='Update Feast meal history')
    parser.add_argument('--meals-dir', required=True, help='Path to meals directory')
    parser.add_argument('--date', required=True, help='Date of meal (YYYY-MM-DD)')
    parser.add_argument('--name', required=True, help='Dish name')
    parser.add_argument('--cuisine', required=True, help='Cuisine type')
    parser.add_argument('--region', help='Specific region (optional)')
    parser.add_argument('--week-file', help='Week file reference (e.g., 2026-02-02.md)')
    parser.add_argument('--rating', type=int, choices=[1, 2, 3, 4, 5], help='Rating 1-5')
    parser.add_argument('--notes', help='Notes about the meal')
    parser.add_argument('--tags', nargs='*', default=[], help='Tags for the meal')
    
    args = parser.parse_args()
    
    meals_dir = Path(args.meals_dir).expanduser()
    history_path = meals_dir / 'history.yaml'
    
    # Load existing history
    history = load_yaml(history_path)
    
    # Ensure structure
    if 'version' not in history:
        history['version'] = 1
    if 'meals' not in history:
        history['meals'] = []
    
    # Create new meal entry
    meal_entry = {
        'date': args.date,
        'name': args.name,
        'cuisine': args.cuisine,
        'region': args.region,
        'weekFile': args.week_file,
        'rating': args.rating,
        'notes': args.notes,
        'tags': args.tags if args.tags else []
    }
    
    # Check for duplicate (same date and name)
    existing = [m for m in history['meals'] 
                if m.get('date') == args.date and m.get('name') == args.name]
    
    if existing:
        # Update existing entry
        idx = history['meals'].index(existing[0])
        history['meals'][idx] = meal_entry
        print(f"Updated existing entry for {args.name} on {args.date}")
    else:
        # Add new entry
        history['meals'].append(meal_entry)
        print(f"Added {args.name} ({args.cuisine}) on {args.date}")
    
    # Update statistics
    history['statistics'] = update_statistics(history)
    history['lastUpdated'] = datetime.now().isoformat()
    
    # Save
    save_yaml(history_path, history)
    print(f"History saved to {history_path}")
    print(f"Total meals: {history['statistics']['totalMealsCooked']}")


if __name__ == '__main__':
    main()
