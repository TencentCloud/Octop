# Feast Onboarding

Guide for onboarding a new user to Feast.

## Overview

Onboarding creates a user profile that personalises the entire Feast experience. Take time to get this right — it's the foundation for everything.

## The Conversation

Keep it natural and friendly. Don't interrogate. Explain why each question matters.

### 1. Welcome & Explain

> "Let's set up Feast — your personal meal planning system. I'll ask a few questions to understand how you like to eat, then I can start planning meals that actually work for you."

### 2. Location (Required)

**Why:** Determines seasonality, units, available stores, cultural context.

> "Where are you based? Country is enough, but if you want hyper-local seasonal produce, I can note your region too."

Store as ISO country code (GB, US, DE, FR, AU, etc.).

### 3. Household Size (Required)

**Why:** Determines portions, shopping quantities.

> "How many people are you cooking for? Just yourself, or feeding others too?"

Also check for special cases:
- OMAD (one meal a day) — needs portion multiplier
- Batch cooking — cook once, portion twice

### 4. Week Structure (Required)

**Why:** Determines the planning and shopping cadence.

> "Let's talk about your week. When does your week feel like it starts — Sunday or Monday?"

> "How many days a week do you actually want to cook? Six? Seven? Less?"

> "Do you have a cheat day — a day you order in or eat out? Is it fixed or flexible?"

### 5. Dietary Requirements (Required)

**Why:** Safety first, health second. Be sensitive to religious constraints, halal, kosher etc.

> "Any allergies or dietary restrictions I absolutely need to know about? Things that would make you ill, not just things you don't fancy."

> "Are you in a particular dietary phase right now? Weight loss, maintenance, building muscle? Or just 'eating well'?"

> "Are you following a vegan or vegetarian diet?"

> "Does your faith restrict certain foods?" 

If weight loss/gain: ask about calorie targets (if they track) or just note the phase.

### 6. Cooking Setup (Important)

**Why:** Can't suggest slow cooker recipes if they don't have one.

> "What's your kitchen like? The usual oven and hob? Anything extra — air fryer, slow cooker, instant pot, fancy gadgets?"

> "How confident are you in the kitchen? Happy to try anything, or prefer foolproof recipes?"

> "How much time do you usually have for cooking? Quick weeknight meals, or happy to spend an hour?"

### 7. Preferences (Nice to Have)

**Why:** Makes recommendations better.

> "Spice — how hot do you like it? Be honest."

> "Any cuisines you particularly love? Or any you just don't enjoy?"

> "How adventurous are you? Stick to comfort food, or excited to try something completely new?"

> "Budget — strict limit, or just be sensible?"

> "Which supermarkets can you easily get to?"

### 8. Units (Required)

**Why:** Recipes must be readable.

> "Last one: how do you like your recipes? Celsius or Fahrenheit? Grams or ounces? Cups or millilitres?"

UK default: Celsius, metric, ml.  
US default: Fahrenheit, imperial, cups.

### 9. Notification Preferences (Required)

**Why:** Feast needs to remind users at the right times via the right channel.

> "How should I remind you about meal planning? I can use whatever channel you prefer — Telegram, Discord, or just here in the chat."

Ask about channel preference:
- `auto` — Use whatever channel they're currently talking on
- Specific channel — telegram, discord, signal, webchat, etc.

> "What times work for you? I'll need to ping you for:
> - Planning (usually Thursday evening)
> - Present and confirm the plan (Friday evening)
> - Shopping list (Firday night / Saturday morning)
> - Daily meal reveals (afternoon)
> - End of week review (Sunday evening)"

Get preferred times:
- Default to sensible times (18:00, 10:00, 15:00, 20:00)
- Adjust to their schedule
- Ask about quiet hours (when NOT to notify)

> "Any times I should never disturb you? Late night, early morning?"

Store in profile under `schedule.notifications` and `schedule.reminders`.

### 10. Set Up Cron Jobs

After saving the profile, create the recurring reminders using the cron tool.

#### Schedule Calculation

```python
# Calculate actual days based on weekStart
# If weekStart = "sunday":
#   planning = Thursday (day -3)
#   confirmation = Friday (day -2)
#   shopping = Saturday (day -1)
#   week starts Sunday (day 0)
#   review = Saturday (day 6)

# Example cron expressions (adjust times from profile):
# Planning: "0 18 * * 4" (Thursday 18:00)
# Confirmation: "0 18 * * 5" (Friday 18:00)
# Shopping: "0 10 * * 6" (Saturday 10:00)
# Daily reveals: Need one per cooking day
# Review: "0 20 * * 6" (Saturday 20:00 if week ends Sat)
```

#### Cron Job Configuration

**Important:** Use `agentTurn` payloads, not `systemEvent`. This ensures notifications are actually delivered to the user via their preferred channel.

Each cron job should be configured as:

```yaml
sessionTarget: "isolated"
payload:
  kind: "agentTurn"
  message: |
    Send a Feast notification.
    
    **Title:** 🍽️ Feast
    **Body:** [specific message for this reminder]
    
    **Delivery Instructions:**
    1. Read the user's profile at workspace/meals/profile.yaml
    2. Check schedule.notifications.channel for their preference
    3. Deliver the notification:
    
       **If channel is "telegram", "discord", or "signal":**
       Use the message tool with action=send and channel=[channel]
       
       **If channel is "webchat" or "auto":**
       Simply output the notification text — it will be delivered to the session
       
       **If push notifications are enabled** (schedule.notifications.push.enabled = true):
       Check schedule.notifications.push.method and send accordingly:
       
       • "pushbullet": Run the pushbullet-notify skill script if available:
         python3 [workspace]/skills/pushbullet-notify/scripts/send_notification.py -t "[title]" -b "[body]"
       
       • "ntfy": POST to ntfy.sh topic (if configured in profile)
       
       If push method is configured but fails, fall back to the channel setting.
    
    4. Confirm the notification was sent.
```

#### Reminder Messages

Create jobs with these specific messages:

1. **Planning reminder**
   ```yaml
   name: "Feast: Planning"
   schedule: { kind: "cron", expr: "0 18 * * 4", tz: "<user timezone>" }
   # Body: "Time to plan next week's meals! Say 'let's plan meals' when you're ready."
   ```

2. **Confirmation reminder**
   ```yaml
   name: "Feast: Confirmation"
   # Body: "Your meal plan is ready for review. Say 'confirm meal plan' to see it and make any changes."
   ```

3. **Shopping list reminder**
   ```yaml
   name: "Feast: Shopping List"
   # Body: "Shopping list is ready! Say 'show shopping list' to review and plan your shop."
   ```

4. **Daily reveal** (create one for each cooking day)
   ```yaml
   name: "Feast: Daily Reveal"
   # Body: "Ready for today's reveal? Say 'what's for dinner?' to find out what's cooking!"
   ```

5. **Morning hint** (if enabled, morning of cooking days)
   ```yaml
   name: "Feast: Morning Hint"
   # Body: "Good morning! Today's cooking adventure awaits... check in this afternoon for the full reveal!"
   ```

6. **Week review**
   ```yaml
   name: "Feast: Week Review"
   # Body: "How was this week's cooking? Say 'review meals' to rate your dishes and capture what worked!"
   ```

**Store the cron job IDs** in `profile.schedule.cronJobs` so they can be updated or removed later.

### 11. Confirm & Save

Read back a summary:

> "Okay, let me make sure I've got this right..."

Then save to `workspace/meals/profile.yaml`.

## Post-Onboarding

### 1. Create the workspace structure

Create all necessary files and folders:
   ```
   workspace/meals/
   ├── profile.yaml
   ├── history.yaml (empty)
   ├── favourites.yaml (empty)
   ├── failures.yaml (empty)
   └── weeks/
   ```

### 2. Ensure reference files exist for user's location

Based on the user's country, check that the seasonality guide exists:
- UK → `references/seasonality/uk.md` (included)
- US → `references/seasonality/us.md` (create if needed)
- Other → Create basic guide or note as limitation

If the seasonality guide for their region doesn't exist, either:
1. Create a basic one during onboarding
2. Note that seasonal suggestions will be limited
3. Offer to research and create one later

The nutrition guide (`references/nutrition.md`) is universal and already included.

### 3. Create cron jobs for all reminders (see step 10).

3. **Confirm everything is set up:**
   > "All set! Here's what I've scheduled:
   > - Planning reminder: Thursdays at 6pm
   > - Plan confirmation: Fridays at 6pm
   > - Shopping list: Saturdays at 10am
   > - Daily reveals: 3pm on cooking days
   > - Week review: Saturday at 8pm
   >
   > I'll message you on [channel]. You can change any of this anytime."

4. **First plan:**
   > "Want to plan your first week now, or shall we wait for Thursday?"

## Managing Schedules Later

Users can adjust their schedule anytime:

- "Change my planning reminder to 7pm"
- "Turn off morning hints"
- "Move my reminders to Telegram"

When updating:
1. Remove old cron job(s) using stored ID
2. Create new cron job(s) with updated settings
3. Update profile with new job IDs

## Removing Feast

If a user wants to stop using Feast:
1. Remove all cron jobs using stored IDs
2. Optionally archive their data
3. Clean up workspace/meals/ folder
