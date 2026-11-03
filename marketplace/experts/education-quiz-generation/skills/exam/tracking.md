# Performance Tracking

Monitor progress and identify weak areas.

---

## Metrics Tracked

### Per Question
- Correct/incorrect
- Time spent
- Topic/domain
- Difficulty level
- Date attempted

### Per Topic
- Total questions attempted
- Accuracy percentage
- Trend over time
- Time per question average

### Overall
- Questions completed
- Overall accuracy
- Simulation scores
- Study streak

---

## Identifying Weak Areas

### By Accuracy
```
📊 Topic Performance

✅ Strong (>80%):
   EC2: 92% (24/26)
   S3: 88% (29/33)

⚠️ Needs work (60-80%):
   VPC: 71% (17/24)
   IAM: 68% (15/22)

❌ Weak (<60%):
   Lambda: 52% (11/21)
   DynamoDB: 48% (10/21)
```

### By Recency
Topics not practiced recently:
```
⏰ Stale Topics (no practice in 7+ days):
   - CloudFormation (12 days)
   - Route 53 (9 days)
   - ELB (8 days)
```

---

## Gap Analysis

Before exam, generate report:

```
📋 Readiness Report: AWS SAA

Overall: 76% ready

By Domain:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Design Resilient    ████████░░ 82%
Design Performant   ███████░░░ 71%
Design Secure       ████████░░ 78%
Cost-Optimized      ██████░░░░ 64% ⚠️

Priority Focus:
1. DynamoDB (48%) — 15 more questions recommended
2. Cost Optimization (64%) — 10 more questions
3. Lambda (52%) — 12 more questions

Estimated study time: 4-6 hours
```

---

## Adaptive Practice

Based on performance, agent adjusts:

### Question Selection
- 40% from weak topics
- 30% from medium topics
- 20% from strong topics (maintenance)
- 10% new topics

### Difficulty Adjustment
- Struggling with medium? Add more easy first
- Acing hard? Ready for simulation

---

## Progress Reports

### Daily
```
📊 Today's Practice

Questions: 25
Accuracy: 76%
Time: 32 minutes
Topics: VPC, IAM, Lambda

Streak: 5 days 🔥
```

### Weekly
```
📊 Week Summary (Feb 5-11)

Total questions: 142
Average accuracy: 74% (↑6%)
Time invested: 3.2 hours
Simulations: 2 (avg: 71%)

Top improvement: Lambda +18%
Needs attention: DynamoDB (dropped 5%)

Next week focus: DynamoDB, Cost Optimization
```

---

## Storage Format

**performance.json:**
```json
{
  "updated": "2024-02-13T10:00:00Z",
  "topics": {
    "ec2": {"attempts": 26, "correct": 24, "avg_time": 45},
    "lambda": {"attempts": 21, "correct": 11, "avg_time": 62}
  },
  "overall": {
    "total": 245,
    "correct": 186,
    "accuracy": 0.76
  },
  "streak": {
    "current": 5,
    "longest": 12
  }
}
```

---

## Motivation Features

### Streaks
```
🔥 5 day streak! Keep it up!
```

### Milestones
```
🎯 Achievement: 500 questions completed!
📈 Personal best: 85% on simulation!
```

### Recommendations
```
💡 You're ready for a simulation!
   Last 3 days: 78% accuracy
   Target: 72% passing
```
