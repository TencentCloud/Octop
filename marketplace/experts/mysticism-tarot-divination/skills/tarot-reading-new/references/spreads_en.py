# Tarot Spreads - English Version
spreads = {
    "Single Card": {
        "cards": 1,
        "suitable": ["Yes/No", "Find"],
        "description": "Draw one card for a quick answer. Best for yes/no questions or locating an item.",
        "positions": {
            1: "Answer / Item Location or Status"
        }
    },

    "Past-Present-Future": {
        "cards": 3,
        "suitable": ["Advice", "Reminder", "Yes/No"],
        "description": "The classic three-card spread revealing the past context, present state, and possible future path.",
        "positions": {
            1: "Past (Root cause or background of the issue)",
            2: "Present (Current actual situation)",
            3: "Future (Where things are heading if nothing changes)"
        }
    },

    "Situation-Advice-Outcome": {
        "cards": 3,
        "suitable": ["Advice", "Reminder"],
        "description": "Focuses on objective analysis with clear action guidance.",
        "positions": {
            1: "Situation (Objective analysis of the current circumstances)",
            2: "Advice (Action or mindset you should take)",
            3: "Outcome (What happens if you follow the advice)"
        }
    },

    "Self-Others-Relationship": {
        "cards": 3,
        "suitable": ["Advice", "Reminder"],
        "description": "Designed for interpersonal questions, analyzing both parties' positions and the nature of the relationship.",
        "positions": {
            1: "Your position and mindset",
            2: "The other person's position and mindset",
            3: "The nature and direction of the relationship"
        }
    },

    "Four Elements": {
        "cards": 4,
        "suitable": ["Advice", "Reminder"],
        "description": "Analyzes the situation from four dimensions using the classical four elements.",
        "positions": {
            1: "Fire - Action, passion, what you want to do",
            2: "Water - Emotion, feeling, your inner state",
            3: "Air - Mind, communication, your thoughts",
            4: "Earth - Material, reality, practical action"
        }
    },

    "Horseshoe": {
        "cards": 7,
        "suitable": ["Advice", "Reminder"],
        "description": "The Horseshoe spread forms a U-shape, specifically designed to analyze obstacles and how to remove them.",
        "positions": {
            1: "Obstacle (The biggest obstacle right now)",
            2: "Foundation (The root or support of the issue)",
            3: "Past (Recent events that have impacted the situation)",
            4: "Present (The actual current situation)",
            5: "Surrounding (Factors influencing the situation)",
            6: "Possible Future (Where things go if no action is taken)",
            7: "Advice (How to remove the obstacle)"
        }
    },

    "Celtic Cross": {
        "cards": 10,
        "suitable": ["Advice", "Reminder"],
        "description": "The most comprehensive and classic tarot spread. Best for in-depth analysis of complex issues, especially those involving others or external factors.",
        "positions": {
            1: "Core (The heart of the current issue)",
            2: "Obstacle (The obstacle in your way)",
            3: "Foundation (The deep root of the issue)",
            4: "Past (Recent relevant events)",
            5: "Possible Future (Outcome if you take no action)",
            6: "Above (Upcoming influence or advice)",
            7: "Self (Your mindset and position)",
            8: "Surroundings (How your environment sees this)",
            9: "Hope/Fear (Your deepest feelings)",
            10: "Outcome (Final conclusion)"
        }
    },

    "Finding": {
        "cards": 3,
        "suitable": ["Find"],
        "description": "Specifically for locating lost items.",
        "positions": {
            1: "Item Status (Where the item is / what condition it's in)",
            2: "Hidden Factor (Why you can't find it / what the obstacle is)",
            3: "Guidance (Clues on how to find it)"
        }
    },

    "Finding Extended": {
        "cards": 5,
        "suitable": ["Find"],
        "description": "Detailed spread for finding items with more clues.",
        "positions": {
            1: "General Area (Which area the item is likely in)",
            2: "Item Condition (Intact / Damaged / Hidden)",
            3: "Why Unfound (Psychological or physical barrier)",
            4: "Time Clue (When you might find it)",
            5: "Action Guidance (How you should search)"
        }
    }
}

question_spread_map = {
    "Yes/No": ["Single Card", "Past-Present-Future"],
    "Find": ["Single Card", "Finding", "Finding Extended"],
    "Advice": ["Past-Present-Future", "Situation-Advice-Outcome", "Celtic Cross"],
    "Reminder": ["Past-Present-Future", "Situation-Advice-Outcome", "Celtic Cross"]
}
