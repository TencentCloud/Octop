# Event Management & Conference Engine

Complete system for planning, executing, and measuring corporate events, conferences, workshops, webinars, and meetups. From initial concept through post-event ROI analysis.

---

## Phase 1: Event Strategy & Concept

### Event Brief YAML

```yaml
event:
  name: ""
  type: "" # conference | workshop | webinar | meetup | summit | retreat | launch | gala | hackathon
  purpose: "" # lead-gen | brand-awareness | education | networking | product-launch | team-building | fundraising
  theme: ""
  
  audience:
    primary_persona: ""
    secondary_persona: ""
    expected_size: 0
    geographic_spread: "" # local | regional | national | international
    seniority_mix: "" # C-suite | directors | managers | ICs | mixed
    
  format: "" # in-person | virtual | hybrid
  duration: "" # half-day | full-day | multi-day | series
  date_target: "" # specific date or window
  
  success_metrics:
    - metric: ""
      target: 0
      measurement: ""
      
  budget:
    total: 0
    currency: "USD"
    funding: "" # company | sponsors | ticket-sales | mixed
    
  stakeholders:
    executive_sponsor: ""
    project_lead: ""
    core_team: []
    
  constraints:
    - ""
    
  kill_criteria:
    - "Registration < 30% of target at T-14 days"
    - "Speaker confirmations < 60% at T-30 days"
    - "Sponsor revenue < 50% of budget gap at T-45 days"
```

### Event Type Decision Matrix

| Type | Best For | Typical Size | Lead Time | Budget Range |
|------|----------|-------------|-----------|-------------|
| Conference | Thought leadership, industry presence | 200-5000 | 6-12 months | $50K-$500K+ |
| Workshop | Skill transfer, product training | 15-50 | 4-8 weeks | $2K-$20K |
| Webinar | Lead gen, education at scale | 50-5000 | 2-4 weeks | $500-$5K |
| Meetup | Community, networking | 20-200 | 2-4 weeks | $500-$5K |
| Summit | Executive alignment, strategy | 50-300 | 3-6 months | $20K-$200K |
| Retreat | Team building, planning | 10-50 | 4-8 weeks | $5K-$50K |
| Product Launch | Awareness, press | 50-500 | 2-4 months | $10K-$100K |
| Hackathon | Innovation, hiring | 30-500 | 4-8 weeks | $5K-$30K |
| Gala/Fundraiser | Revenue, relationships | 100-1000 | 3-6 months | $20K-$200K |

### Go/No-Go Scorecard (Rate 1-5)

| Factor | Score | Weight |
|--------|-------|--------|
| Clear business objective alignment | _ | 3x |
| Audience demand validated | _ | 3x |
| Budget secured or realistic | _ | 2x |
| Team capacity available | _ | 2x |
| Venue/platform feasible | _ | 1x |
| Timeline realistic | _ | 2x |
| Competitive landscape favorable | _ | 1x |
| Sponsor/partner interest | _ | 1x |
| **Total** | _ /75 | |

- **60+**: Green light
- **45-59**: Proceed with risk mitigation
- **<45**: Redesign or kill

---

## Phase 2: Budget & Financial Planning

### Budget Template YAML

```yaml
budget:
  revenue:
    ticket_sales:
      early_bird: { price: 0, qty: 0, total: 0 }
      regular: { price: 0, qty: 0, total: 0 }
      vip: { price: 0, qty: 0, total: 0 }
      group: { price: 0, qty: 0, total: 0 }
    sponsorship:
      platinum: { price: 0, qty: 0, total: 0 }
      gold: { price: 0, qty: 0, total: 0 }
      silver: { price: 0, qty: 0, total: 0 }
      exhibitor: { price: 0, qty: 0, total: 0 }
    other:
      merchandise: 0
      workshop_upsell: 0
      recording_access: 0
    total_revenue: 0
    
  expenses:
    venue:
      rental: 0
      catering: 0 # $50-150/person/day typical
      av_equipment: 0
      wifi_upgrade: 0
      insurance: 0
      security: 0
    speakers:
      fees: 0
      travel: 0
      accommodation: 0
      gifts: 0
    marketing:
      paid_ads: 0
      design: 0
      email_platform: 0
      social_media: 0
      pr_agency: 0
      print_materials: 0
    technology:
      registration_platform: 0
      streaming_platform: 0
      event_app: 0
      wifi: 0
    production:
      stage_design: 0
      lighting: 0
      photography: 0
      videography: 0
      signage: 0
    staffing:
      event_staff: 0
      volunteers: 0
      overtime: 0
    miscellaneous:
      swag: 0
      transportation: 0
      contingency: 0 # 10-15% of total
    total_expenses: 0
    
  summary:
    net_result: 0
    roi_percentage: 0
    cost_per_attendee: 0
    break_even_registrations: 0
```

### Pricing Strategy by Event Type

| Type | Free | Paid | Hybrid |
|------|------|------|--------|
| Webinar | ✅ Max registrations | Premium content only | Free general + paid workshop |
| Conference | ❌ Low commitment | ✅ Qualified attendees | Early sessions free, full access paid |
| Workshop | ❌ No-show risk | ✅ Committed learners | Free intro + paid deep-dive |
| Meetup | ✅ Community growth | Rarely | Free + sponsor-funded |

### Sponsorship Package Design

**Tier structure (typical 4-tier):**

| Benefit | Platinum | Gold | Silver | Bronze |
|---------|----------|------|--------|--------|
| Logo on main stage | ✅ | ✅ | ❌ | ❌ |
| Speaking slot | Keynote | Panel | Lightning | ❌ |
| Booth space | Premium | Standard | Table | ❌ |
| Attendee list | Full | Opt-in only | ❌ | ❌ |
| Social mentions | 10+ | 5 | 3 | 1 |
| Email inclusion | Dedicated | Shared | Footer | ❌ |
| Comp tickets | 10 | 5 | 3 | 2 |
| Branding | All materials | Website+email | Website | Logo wall |
| **Typical price** | $25K-100K | $10K-40K | $5K-15K | $1K-5K |

**Sponsor outreach email template:**

```
Subject: [EVENT NAME] — Partnership opportunity for [COMPANY]

Hi [NAME],

We're hosting [EVENT] on [DATE] — [SIZE] [AUDIENCE TYPE] will be there, 
and [RELEVANT STAT about their audience overlap].

I noticed [COMPANY] has been [SPECIFIC THING — product launch, hiring push, 
market expansion]. Our [TIER] partnership includes [TOP 2-3 BENEFITS most 
relevant to their goals].

Past partners include [2-3 recognizable names] — [SOCIAL PROOF METRIC].

Worth a quick call this week?

[SIGNATURE]
```

---

## Phase 3: Venue & Platform Selection

### In-Person Venue Checklist

**Must-haves:**
- [ ] Capacity matches expected attendance + 10% buffer
- [ ] AV system adequate or upgradeable
- [ ] Reliable WiFi (calculate: attendees × 2 devices × 1 Mbps minimum)
- [ ] Accessible (ADA/DDA compliant)
- [ ] Adequate power outlets for all sessions
- [ ] Climate control
- [ ] Loading dock for setup
- [ ] Sufficient restrooms (1 per 50 attendees minimum)
- [ ] On-site parking or public transit access
- [ ] Cell service coverage

**Nice-to-haves:**
- [ ] Breakout rooms
- [ ] Outdoor space
- [ ] On-site catering
- [ ] Green room for speakers
- [ ] Natural lighting
- [ ] Branding-friendly walls/surfaces
- [ ] Nearby hotels

**Red flags:**
- Venue won't share floor plan → hidden layout issues
- No backup generator → power risk
- Exclusive catering vendor at 3x market rate
- WiFi "included" but capped at 50 connections
- No early access for setup day before

### Virtual Platform Selection

| Need | Platform Type | Examples |
|------|--------------|---------|
| Simple webinar (<500) | Webinar tool | Zoom Webinars, StreamYard |
| Large conference | Virtual event platform | Hopin, Airmeet, Run The World |
| Hybrid (in-person + virtual) | Hybrid platform | Swoogo, Bizzabo, Cvent |
| Workshop/interactive | Meeting tool | Zoom, Google Meet, Teams |
| On-demand/recorded | Video platform | YouTube, Vimeo, Teachable |

### Hybrid Event Considerations

- **80/20 rule**: Design for in-person, adapt for virtual — NOT the other way around
- Virtual attendees need dedicated host/moderator (not just a camera pointed at stage)
- Separate chat moderator for virtual Q&A
- Pre-record backup for every live session (technical failure protection)
- Time zone awareness: publish schedule in 3+ time zones
- Virtual networking requires structured facilitation (random 1:1 matching, topic tables)

---

## Phase 4: Speaker & Content Curation

### Speaker Brief YAML

```yaml
speaker:
  name: ""
  title: ""
  company: ""
  bio: "" # 100-word max
  headshot: "" # high-res link
  social:
    twitter: ""
    linkedin: ""
  
  session:
    title: ""
    format: "" # keynote | panel | workshop | fireside | lightning
    duration_min: 0
    track: ""
    level: "" # beginner | intermediate | advanced
    abstract: "" # 200 words max
    key_takeaways:
      - ""
      - ""
      - ""
    target_audience: ""
    
  logistics:
    travel_required: false
    accommodation_nights: 0
    fee: 0
    av_requirements: "" # slides, demo, video, live coding
    dietary: ""
    
  status: "" # invited | confirmed | declined | backup
  confirmed_date: ""
  contract_signed: false
  materials_received: false # slides, bio, headshot
  materials_deadline: "" # T-14 days minimum
```

### Content Architecture

**For a full-day conference (8 hours):**

| Time | Slot | Type | Notes |
|------|------|------|-------|
| 08:00-08:30 | Registration & networking | Social | Coffee, badges |
| 08:30-08:45 | Welcome & housekeeping | MC | Set energy, logistics |
| 08:45-09:30 | Opening keynote | Keynote | Big name, set theme |
| 09:30-09:45 | Break | - | 15 min minimum |
| 09:45-10:30 | Track sessions (2-3 parallel) | Talk | 30-40 min + Q&A |
| 10:30-10:45 | Break | - | |
| 10:45-11:30 | Track sessions | Talk/Panel | |
| 11:30-12:15 | Panel discussion | Panel | 3-4 panelists + moderator |
| 12:15-13:30 | Lunch & networking | Social | 75 min minimum for lunch |
| 13:30-14:15 | Afternoon keynote | Keynote | Energy boost |
| 14:15-14:30 | Break | - | |
| 14:30-15:15 | Track sessions / workshops | Mixed | Hands-on options |
| 15:15-15:30 | Break | - | Afternoon snack |
| 15:30-16:15 | Track sessions | Talk | |
| 16:15-16:30 | Closing keynote / wrap-up | Keynote | End on high, CTA |
| 16:30-18:00 | Networking reception | Social | Optional, sponsored |

**Content rules:**
1. **No back-to-back talks > 45 min** — attention spans die
2. **Breaks every 90 min minimum** — non-negotiable
3. **Lunch ≥ 75 min** — people need to eat AND network
4. **Last session ≠ most important** — energy drops after lunch
5. **Panel ≤ 4 speakers** — more = chaos
6. **Lightning talks = 5-7 min** — enforce ruthlessly with visible timer
7. **Q&A = collected written questions** — avoid mic-hoggers
8. **Every session needs a clear takeaway** — "what will attendees DO differently?"

### Speaker Management Timeline

| When | Action |
|------|--------|
| T-90 days | Send speaker invitations with brief |
| T-60 days | Confirm all speakers, sign agreements |
| T-30 days | Collect bios, headshots, session abstracts |
| T-14 days | Collect slide decks / materials |
| T-7 days | Speaker briefing call (logistics, AV, timing) |
| T-1 day | Tech check for virtual speakers |
| Day of | Green room available 60 min before slot |
| T+3 days | Thank-you email with event photos/metrics |

---

## Phase 5: Marketing & Registration

### Registration Funnel

```
Awareness → Interest → Registration → Confirmation → Attendance → Post-Event
   |           |            |              |              |            |
Landing    Email       Payment/        Reminder      Check-in     Survey
page      nurture      form           sequence       + badge      + follow-up
```

### Marketing Timeline

| Phase | When | Actions |
|-------|------|---------|
| **Announce** | T-90 days | Landing page live, save-the-date email, social tease |
| **Early Bird** | T-75 to T-45 | Early bird pricing (20-30% off), speaker announcements |
| **Momentum** | T-45 to T-14 | Regular pricing, sponsor announcements, content previews |
| **Urgency** | T-14 to T-3 | Last chance emails, scarcity messaging, social proof |
| **Final Push** | T-3 to T-0 | Day-of logistics email, FOMO for waitlist |

### Email Sequence

**Email 1 — Save the Date (T-90)**
```
Subject: Save the date: [EVENT] — [DATE]

[ONE SENTENCE about what it is]

[WHO it's for] — [WHY they should care]

Early bird registration opens [DATE]. Reply to this email 
if you want first access.

[LINK to landing page]
```

**Email 2 — Early Bird Open (T-75)**
```
Subject: [EVENT] early bird is live — save [X]%

[SPEAKER HIGHLIGHTS — 2-3 names]

[AGENDA PREVIEW — 3 bullet takeaways]

Early bird pricing ends [DATE]:
- General: $[X] (reg $[Y])
- VIP: $[X] (reg $[Y])

[CTA BUTTON]

[SOCIAL PROOF — past attendees, companies represented]
```

**Email 3 — Speaker Spotlight (T-60, repeat weekly)**
```
Subject: [SPEAKER NAME] is joining [EVENT]

[2-sentence bio — why they matter]

They'll be talking about: [TOPIC]

You'll walk away knowing: [3 TAKEAWAYS]

[CTA — Register to see them live]
```

**Email 4 — Last Chance (T-7)**
```
Subject: [X] spots left for [EVENT]

[SOCIAL PROOF — X people registered, Y companies]

Here's what you'll miss if you skip:
1. [SPECIFIC TAKEAWAY]
2. [SPECIFIC TAKEAWAY]  
3. [NETWORKING VALUE]

[CTA — Secure your spot]

P.S. [URGENCY — early bird expired, limited seats, recording NOT included]
```

### Registration Page Checklist

- [ ] Clear event name, date, location above fold
- [ ] 3 bullet "What you'll learn" / value props
- [ ] Speaker photos and names (social proof)
- [ ] Pricing tiers clearly compared
- [ ] FAQ section (refund policy, what's included, dress code)
- [ ] Countdown timer (if appropriate)
- [ ] Past event photos/testimonials
- [ ] Mobile-optimized form (minimal fields)
- [ ] Calendar add button on confirmation
- [ ] Social share buttons on thank-you page

### No-Show Reduction Tactics

Typical no-show rates: Free events 40-60%, Paid events 10-20%

| Tactic | Impact |
|--------|--------|
| Charge even a nominal fee ($5-10) | Reduces no-shows 30-50% |
| Reminder email T-7, T-1, T-0 morning | Reduces 10-15% |
| Calendar invite in confirmation email | Reduces 5-10% |
| "Bring a colleague" incentive | Fills empty seats |
| Waitlist messaging ("X people waiting") | Creates commitment |
| Pre-event engagement (polls, questions) | Builds investment |
| Share attendee list preview | Creates FOMO |

---

## Phase 6: Operations & Logistics

### Master Run Sheet YAML

```yaml
run_sheet:
  date: ""
  venue: ""
  
  team:
    - role: "Event Director"
      name: ""
      phone: ""
      responsibilities: ["overall coordination", "escalation point"]
    - role: "Registration Lead"
      name: ""
      phone: ""
      responsibilities: ["check-in", "badge printing", "walk-ins"]
    - role: "AV/Tech Lead"
      name: ""
      phone: ""
      responsibilities: ["sound", "slides", "streaming", "recording"]
    - role: "Speaker Liaison"
      name: ""
      phone: ""
      responsibilities: ["green room", "speaker timing", "transitions"]
    - role: "Catering Coordinator"
      name: ""
      phone: ""
      responsibilities: ["food timing", "dietary needs", "cleanup"]
    - role: "Social Media / Content"
      name: ""
      phone: ""
      responsibilities: ["live posting", "photos", "attendee engagement"]
      
  timeline:
    - time: "06:00"
      action: "Core team arrives, venue walkthrough"
      owner: "Event Director"
    - time: "06:30"
      action: "AV setup and testing"
      owner: "AV Lead"
    - time: "07:00"
      action: "Registration desk setup, badge check"
      owner: "Registration Lead"
    # ... continue for full day
    
  emergency_contacts:
    venue_manager: ""
    catering: ""
    av_company: ""
    nearest_hospital: ""
    security: ""
```

### Day-Of Checklist

**Pre-Event (4-6 hours before):**
- [ ] Venue walkthrough — exits, restrooms, signage
- [ ] AV full test — every mic, every projector, every clicker
- [ ] WiFi test — speed test from 3+ locations
- [ ] Registration desk setup — badges, programs, swag bags
- [ ] Signage placed — room names, directions, sponsor logos
- [ ] Catering confirmed — timing, quantities, dietary labels
- [ ] Photography/video briefing — shot list, off-limits areas
- [ ] Speaker green room stocked — water, snacks, chargers, mirror
- [ ] Emergency plan reviewed with all staff
- [ ] Streaming/recording test (if applicable)

**During Event:**
- [ ] Timer visible to speakers (5-min, 1-min warnings)
- [ ] Room temperature monitoring (68-72°F / 20-22°C)
- [ ] Social media live posting every 30 min
- [ ] Attendee questions collected for Q&A
- [ ] Breaks started and ended ON TIME
- [ ] Photo coverage of every speaker + audience reactions
- [ ] Sponsor acknowledgments per schedule
- [ ] Emergency exits clear at all times

**Post-Event (same day):**
- [ ] Venue sweep — lost items, damage check
- [ ] AV equipment returned/secured
- [ ] Leftover food donated (arrange in advance)
- [ ] Thank-you to venue staff
- [ ] Quick team debrief (30 min max, fresh memories)
- [ ] Social media recap post
- [ ] Survey email scheduled (send within 24 hours)

### Crisis Management Quick Reference

| Crisis | Immediate Action | Escalation |
|--------|-----------------|------------|
| Speaker no-show | Activate backup speaker or extend adjacent session + networking | Communicate transparently |
| AV failure | Switch to backup laptop/mic; worst case = "unplugged" session | AV vendor emergency line |
| Medical emergency | Call emergency services, clear area, assign guide to entrance | Venue security + event director |
| Venue emergency (fire/weather) | Follow venue evacuation plan, account for all attendees | Venue manager leads |
| Low attendance | Reconfigure room (smaller setup), increase networking time | No public acknowledgment |
| Catering failure | Order emergency delivery (pizza/sandwiches), extend session to buy time | Catering manager |
| WiFi down | Mobile hotspot backup, pause any demos, paper feedback forms | Venue IT |
| Protest/disruption | Security handles, do NOT engage publicly, move to private | Security + event director |

---

## Phase 7: Attendee Experience Design

### Attendee Journey Map

```
Pre-Event                    Day-Of                      Post-Event
─────────────────────────    ────────────────────────    ─────────────────
Registration confirmation    Arrival & check-in         Thank you email (T+1)
↓                           ↓                           ↓
Pre-event email series      Badge + swag bag            Survey (T+1)
↓                           ↓                           ↓
Event app / community       Opening keynote             Recordings access (T+3-7)
↓                           ↓                           ↓
Networking pre-matching      Sessions + networking       Follow-up content (T+7)
↓                           ↓                           ↓
Logistics email (T-1)       Lunch + activities          Community invite (T+14)
                            ↓
                            Afternoon sessions
                            ↓
                            Closing + networking
```

### Networking Facilitation

**Structured networking formats:**

| Format | How | Best For | Time |
|--------|-----|----------|------|
| Speed networking | 3-min rotations, bell timer | Large groups, strangers | 30 min |
| Topic tables | Labeled tables by interest | Targeted connections | During meals |
| Buddy system | Pair first-timers with returners | Community building | All day |
| Unconference | Attendee-proposed sessions | Engaged audiences | 60-90 min |
| Fishbowl | Inner circle discusses, outer observes | Controversial topics | 30-45 min |
| Ask-me-anything | Expert sits at labeled table | Expert access | 20 min slots |

### Accessibility Checklist

- [ ] Wheelchair-accessible venue (ramps, elevators, wide aisles)
- [ ] Reserved seating near stage for hearing/vision impaired
- [ ] Sign language interpreter (if requested or >200 attendees)
- [ ] Live captioning for all sessions
- [ ] Dietary accommodations labeled (vegan, halal, kosher, allergies)
- [ ] Quiet room available (sensory breaks)
- [ ] Gender-neutral restrooms identified
- [ ] Large-print materials available
- [ ] Microphone for ALL speakers (even in small rooms)
- [ ] Color-blind-friendly slide guidelines shared with speakers
- [ ] Nursing/pumping room (private, with power outlet)
- [ ] Service animal policy communicated

---

## Phase 8: Webinar-Specific Playbook

### Webinar Planning YAML

```yaml
webinar:
  title: ""
  date: ""
  time: "" # include timezone
  duration_min: 45 # sweet spot: 45-60 min (30 min content + 15 min Q&A)
  platform: ""
  
  presenters:
    - name: ""
      role: ""
      section: ""
      
  registration_goal: 0
  attendance_goal: 0 # typically 40-50% of registrations
  
  content_outline:
    - section: "Hook"
      duration_min: 3
      notes: "Problem statement, what they'll learn"
    - section: "Main content"
      duration_min: 25
      notes: "3-5 key points, not more"
    - section: "Demo/case study"
      duration_min: 7
      notes: "Show, don't tell"
    - section: "CTA"
      duration_min: 3
      notes: "One clear next step"
    - section: "Q&A"
      duration_min: 15
      notes: "Pre-seed 3 questions"
      
  follow_up:
    recording_send: "T+1 day"
    no_show_email: "T+1 day"
    nurture_sequence: "T+3 to T+14"
```

### Webinar Conversion Metrics

| Metric | Good | Great | World-Class |
|--------|------|-------|-------------|
| Landing page → registration | 20-30% | 30-45% | 45%+ |
| Registration → attendance | 35-45% | 45-55% | 55%+ |
| Attendance → stayed to end | 60-70% | 70-80% | 80%+ |
| Attendees → CTA click | 5-10% | 10-20% | 20%+ |
| Attendees → qualified lead | 10-20% | 20-35% | 35%+ |

### Webinar Engagement Tactics

- **Poll every 7-10 minutes** — keeps attention, generates data
- **Chat prompts** — "Type YES if you've experienced this"
- **Name-drop attendees** — "Great question from Sarah"
- **Pre-seed Q&A** — have 3 questions ready to avoid dead air
- **Handout/resource** — "Download link in chat" drives action
- **Co-host manages chat** — presenter should NEVER monitor chat

---

## Phase 9: Post-Event Analysis

### Post-Event Survey (send within 24 hours)

**Core questions (keep under 10):**

1. Overall satisfaction (1-10 NPS style)
2. "What was the MOST valuable part?" (open text)
3. "What would you CHANGE for next time?" (open text)
4. Speaker ratings (1-5 each, if multi-speaker)
5. Venue/platform rating (1-5)
6. "Would you attend again?" (Yes / Maybe / No)
7. "Would you recommend to a colleague?" (1-10 NPS)
8. "What topics would you want next time?" (open text)
9. "How did you hear about this event?" (multi-select)
10. "Any other feedback?" (open text, optional)

**Response rate targets:** In-person 30-50%, Virtual 15-25%

**Boost response rates:**
- Send within 24 hours while memory is fresh
- Keep under 5 minutes
- Offer incentive (recording access, next event discount)
- Personalize ("Hi [NAME], thanks for joining [SESSION]")

### ROI Calculation

```
Event ROI = (Revenue Generated - Total Cost) / Total Cost × 100

Revenue Generated:
  + Ticket sales
  + Sponsorship revenue
  + Immediate upsells/sales at event
  + Pipeline value generated (deals influenced) × win rate
  + Estimated lifetime value of new contacts
  
Total Cost:
  + All budget line items
  + Internal team time (hours × hourly rate)
  + Opportunity cost of team not doing other work
```

### Post-Event Report YAML

```yaml
event_report:
  event_name: ""
  date: ""
  
  attendance:
    registered: 0
    attended: 0
    show_rate: "0%"
    new_contacts: 0
    
  financial:
    total_revenue: 0
    total_cost: 0
    net_result: 0
    roi: "0%"
    cost_per_attendee: 0
    cost_per_lead: 0
    
  satisfaction:
    nps_score: 0
    overall_rating: 0
    top_rated_session: ""
    lowest_rated_session: ""
    
  leads:
    total_leads: 0
    qualified_leads: 0
    pipeline_value: 0
    deals_closed_30d: 0
    deals_closed_90d: 0
    
  content:
    sessions_recorded: 0
    photos_captured: 0
    social_mentions: 0
    social_reach: 0
    blog_posts_created: 0
    
  top_3_wins:
    - ""
    - ""
    - ""
    
  top_3_improvements:
    - ""
    - ""
    - ""
    
  recommendation: "" # repeat | modify | retire
  next_steps:
    - ""
```

### Content Repurposing Matrix

| Source | Output | Timeline | Channel |
|--------|--------|----------|---------|
| Keynote recording | Blog post summary | T+3 days | Website |
| Keynote recording | 5 social clips (60-90 sec) | T+5 days | LinkedIn, Twitter, YouTube |
| Panel discussion | Quote graphics | T+2 days | Instagram, LinkedIn |
| Workshop materials | Lead magnet / PDF guide | T+7 days | Email list |
| Attendee photos | Event recap post | T+1 day | Social media |
| Q&A questions | FAQ blog post | T+7 days | Website |
| Survey results | "State of [Industry]" report | T+14 days | Gated content |
| Speaker slides | SlideShare / Carousel posts | T+5 days | LinkedIn |

---

## Phase 10: Event Series & Scaling

### Annual Event Calendar YAML

```yaml
event_calendar:
  Q1:
    - type: "webinar"
      theme: "Industry trends"
      month: "January"
      goal: "Pipeline building"
    - type: "meetup"
      theme: "Networking"
      month: "February"
      goal: "Community growth"
    - type: "workshop"
      theme: "Product training"
      month: "March"
      goal: "Customer success"
      
  Q2:
    - type: "conference"
      theme: "Annual summit"
      month: "May"
      goal: "Thought leadership + lead gen"
      
  Q3:
    - type: "webinar series"
      theme: "Deep dives"
      months: ["July", "August"]
      goal: "Education + nurture"
      
  Q4:
    - type: "workshop"
      theme: "Year-end planning"
      month: "October"
      goal: "Upsell + retention"
    - type: "gala"
      theme: "Customer appreciation"
      month: "December"
      goal: "Retention + referrals"
```

### Recurring Event Optimization

**After each event, update:**
1. Email subject line performance (open rates by subject)
2. Registration page conversion (test headlines, CTAs)
3. Optimal day/time for your audience
4. Speaker ratings → invite top performers back
5. Session format performance (keynotes vs panels vs workshops)
6. Sponsor satisfaction → retention and upsell
7. No-show rate trends → adjust tactics

### Event Maturity Model

| Level | Characteristics | Focus |
|-------|----------------|-------|
| 1 — Ad Hoc | One-off events, no process | Just execute |
| 2 — Repeatable | Templates exist, some automation | Consistency |
| 3 — Defined | Full playbook, team roles, metrics | Optimization |
| 4 — Managed | Data-driven decisions, A/B testing | ROI maximization |
| 5 — Optimizing | Event portfolio strategy, predictive analytics | Strategic asset |

---

## Phase 11: Virtual & Hybrid Deep Dive

### Virtual Event Production Checklist

**Technical setup:**
- [ ] Backup internet connection (mobile hotspot)
- [ ] Hardwired ethernet (not WiFi) for all presenters
- [ ] Backup computer ready with all presentations loaded
- [ ] Recording started and confirmed
- [ ] Closed captions enabled
- [ ] Chat moderation active
- [ ] Mute all attendees on entry
- [ ] Disable attendee screen sharing
- [ ] Test all presenter screen shares before going live
- [ ] "We'll begin shortly" holding slide ready

**Engagement plan:**
- [ ] Welcome message in chat at T-5 min
- [ ] Ice-breaker poll at start
- [ ] Interactive element every 7-10 min (poll, chat prompt, quiz)
- [ ] Q&A queue managed by co-host
- [ ] Resource links shared in chat at relevant moments
- [ ] Recording disclaimer stated

### Hybrid Event Rules

1. **Virtual attendees are NOT second-class** — dedicated camera angle, chat moderator, separate networking
2. **Dedicated virtual MC** — someone whose ONLY job is the virtual audience
3. **Repeat in-room questions into mic** — virtual audience can't hear audience mics
4. **Chat → stage pipeline** — virtual questions get equal airtime
5. **Separate swag shipment** — virtual attendees get a box mailed in advance
6. **Time zone respect** — if international, rotate session times or offer recordings

---

## Phase 12: Metrics Dashboard

### Event Health Score (0-100)

| Dimension | Weight | Metrics |
|-----------|--------|---------|
| Registration velocity | 20% | Registrations vs target at each milestone |
| Attendance quality | 20% | Show rate, seniority mix, target company % |
| Engagement | 15% | Session ratings, Q&A participation, app usage |
| Satisfaction | 15% | NPS, overall rating, "would attend again" |
| Business impact | 20% | Leads generated, pipeline value, deals influenced |
| Content leverage | 10% | Repurposed assets, social reach, recording views |

### Benchmarks by Event Type

| Metric | Webinar | Conference | Workshop | Meetup |
|--------|---------|------------|----------|--------|
| Show rate | 40-50% | 80-90% | 85-95% | 60-75% |
| NPS | 30-50 | 40-60 | 50-70 | 40-60 |
| Lead-to-opp | 5-15% | 10-25% | 15-30% | 5-10% |
| Cost/lead | $20-50 | $100-300 | $50-150 | $10-30 |
| Content pieces | 3-5 | 15-30 | 5-10 | 2-5 |

---

## Quality Rubric (0-100)

| Dimension | Weight | 0-25 | 50 | 75 | 100 |
|-----------|--------|------|-----|-----|-----|
| Strategy alignment | 15% | No clear objective | Vague goals | SMART goals defined | Goals tied to business KPIs with measurement plan |
| Content quality | 15% | Generic/irrelevant | Adequate topics | Expert speakers, clear takeaways | Transformative content, unique insights |
| Attendee experience | 15% | Confusing, poor flow | Functional | Smooth, well-organized | Delightful, memorable, shareable |
| Marketing execution | 15% | Minimal outreach | Basic email + social | Multi-channel, segmented | Data-driven, optimized funnel |
| Operations | 10% | Chaos, issues | Minor hiccups | Smooth execution | Flawless, contingencies tested |
| Financial management | 10% | Over budget, no tracking | On budget | Profitable, tracked | ROI optimized, sponsor retention |
| Post-event follow-up | 10% | None | Thank you email | Survey + follow-up sequence | Full repurposing + lead nurture + report |
| Scalability | 10% | One-off, no documentation | Some templates | Full playbook | Repeatable system, continuous improvement |

---

## Edge Cases

### Small Budget (<$5K)
- Use free venues (co-working spaces, partner offices, university rooms)
- Speakers = your team + customer stories (no fees)
- Marketing = organic social + email list + community
- Swag = digital (exclusive content, templates, recordings)
- Photography = team member with good phone + natural light

### First Event Ever
- Start with a meetup or webinar — lowest risk
- Partner with established community for co-hosting
- Under-promise, over-deliver on experience
- Keep it small (30-50 people) — easier to create magic
- Focus on ONE thing going well rather than everything

### International / Multi-Timezone
- Record everything — async consumption is expected
- Rotate live session times across events
- Translate key materials (at minimum: landing page, emails)
- Research local holidays before setting dates
- Consider cultural norms (business card etiquette, dietary defaults)

### Cancellation / Postponement
- Communicate immediately and honestly
- Offer full refunds with no friction
- Provide alternative (virtual option, recording, next event credit)
- Notify sponsors with revised terms
- Update all marketing channels simultaneously
- Post-mortem: what signals did we miss?

### Controversial Speakers / Topics
- Have a clear code of conduct published
- Brief speakers on boundaries
- Moderate Q&A (written questions only for sensitive topics)
- Have a response plan for social media backlash
- Event director has final authority on content decisions

---

## Natural Language Commands

When asked to help with events, respond to these patterns:

1. **"Plan an event"** → Start with Event Brief YAML + Go/No-Go scorecard
2. **"Create event budget"** → Generate Budget Template with estimates
3. **"Find speakers"** → Speaker Brief YAML + outreach email template
4. **"Build event agenda"** → Content Architecture for their event type
5. **"Write event marketing emails"** → Full email sequence for their timeline
6. **"Set up registration"** → Registration page checklist + pricing strategy
7. **"Plan a webinar"** → Webinar Planning YAML + engagement tactics
8. **"Create run sheet"** → Master Run Sheet YAML for day-of operations
9. **"Post-event analysis"** → Post-Event Report YAML + ROI calculation
10. **"Design sponsor packages"** → Sponsorship tier table + outreach email
11. **"Reduce no-shows"** → No-show reduction tactics + reminder sequence
12. **"Rate this event plan"** → Quality rubric scoring with improvement recommendations
