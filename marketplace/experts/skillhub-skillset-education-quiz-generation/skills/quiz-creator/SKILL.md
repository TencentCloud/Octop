---
name: quiz-generator
description: Generate quizzes and assessments from any topic or content. Create questions of varying difficulty (easy, medium, hard), multiple formats (multiple choice, true/false, fill-in-blank), with answers and detailed explanations. Use when the user asks to create a quiz, test knowledge, generate questions, or build assessments.
---

# Quiz Generator

## Overview

Generate comprehensive quizzes from topics, documents, or learning materials. Include questions of varying difficulty, different question formats, correct answers, and detailed explanations to reinforce learning.

## Quiz Structure

### Required Elements

1. **Quiz Title and Description**
   - Clear, descriptive title
   - Topic focus
   - Target audience level
   - Estimated completion time
   - Question count

2. **Questions**
   Each question must include:
   - Question text
   - Question difficulty (easy/medium/hard)
   - Question type (see formats below)
   - Correct answer(s)
   - Detailed explanation
   - Optional: reference to source material

3. **Answer Key**
   - Quick reference for all correct answers
   - Usually at the end of the quiz

4. **Scoring Guide** (optional)
   - How many points per question
   - What score indicates mastery
   - Recommended follow-up based on score ranges

### Question Formats

#### Multiple Choice (default)
- 3-5 answer options (1 correct, others plausible distractors)
- Label options A, B, C, D, E
- Distractors should be common misconceptions

#### True/False
- Statement to evaluate
- Explanation for why it's true or false

#### Fill-in-the-Blank
- Sentence or statement with blank(s)
- Case-insensitive matching preferred
- List acceptable alternative answers

#### Short Answer
- Open-ended question
- Provide example acceptable answers
- Explain key points that should be included

#### Matching
- Two columns to match (terms to definitions, dates to events, etc.)
- Indicate the relationship clearly

## Difficulty Guidelines

### Easy
- Basic facts, definitions, terminology
- Direct recall from source material
- Should be answerable after one pass through material
- Example: "What does API stand for?"

### Medium
- Requires understanding concepts, not just facts
- Inference or application of knowledge
- May require connecting multiple pieces of information
- Example: "Which HTTP method would you use to update an existing resource?"

### Hard
- Requires synthesis, analysis, or critical thinking
- Complex scenarios or edge cases
- Comparison or evaluation of options
- Example: "Compare REST and GraphQL architectures for a real-time chat application."

## Writing Guidelines

### Question Quality
- Ensure each question tests something meaningful
- Avoid ambiguous phrasing
- Make questions independent (don require previous answers)
- Balance question types and difficulty levels
- Include 10-20 questions for a comprehensive quiz

### Explanations
- Explain not just the correct answer, but why alternatives are wrong
- Reference the source material when applicable
- Add additional context or related concepts
- Help the learner understand, not just memorize

### Distractor Generation
- Create plausible wrong answers
- Use common misconceptions or errors
- Avoid "all of the above" or "none of the above" (become guesswork)
- Keep distractors similar in length and tone to correct answer

## Example Question

```markdown
### Question 3 (Medium)
What is the primary purpose of environment variables in application configuration?

A) To store sensitive credentials securely
B) To configure application behavior across environments
C) To manage database connections
D) To handle user authentication

**Correct Answer:** B

**Explanation:** Environment variables allow applications to be configured differently across development, testing, and production environments without changing code. While they can store credentials (A), their primary purpose is configuration flexibility. Database connections (C) and authentication (D) are specific use cases, not the primary purpose.
```

## Generation Workflow

1. **Understand the Source**
   - Read the topic or provided material
   - Identify key concepts, facts, and relationships
   - Note common pitfalls or misconceptions

2. **Plan Question Distribution**
   - Target: 40% easy, 40% medium, 20% hard
   - Mix question types based on content
   - Ensure coverage of all key topics

3. **Generate Questions**
   - Draft questions with answers and explanations
   - Review for clarity and accuracy
   - Check that explanations actually explain

4. **Review and Refine**
   - Remove redundant or overlapping questions
   - Ensure difficulty is consistent
   - Verify all answers are correct
   - Add a practice question or bonus if appropriate

## Output Format

Deliver the quiz in the user's preferred format:
- Markdown (default) - with sections clearly marked
- JSON - for programmatic use or quiz platforms
- Plain text - for simple assessments

### JSON Format Example

```json
{
  "title": "Web Development Fundamentals Quiz",
  "description": "Test your knowledge of HTML, CSS, and JavaScript basics",
  "questions": [
    {
      "id": 1,
      "difficulty": "easy",
      "type": "multiple_choice",
      "question": "What does HTML stand for?",
      "options": [
        "Hyper Text Markup Language",
        "High Tech Modern Language",
        "Hyper Transfer Markup Language",
        "Home Tool Markup Language"
      ],
      "correct_answer": 0,
      "explanation": "HTML stands for Hyper Text Markup Language. It's the standard markup language for creating web pages."
    }
  ],
  "answer_key": {
    "1": "A"
  }
}
```

## Quality Checklist

Before finalizing a quiz, verify:

- [ ] All questions are clear and unambiguous
- [ ] Correct answers are accurate
- [ ] Explanations are helpful and educational
- [ ] Difficulty levels are appropriate for audience
- [ ] Question types are varied
- [ ] Key topics from source are covered
- [ ] Distractors are plausible but clearly wrong
- [ ] Quiz title and description are informative
- [ ] Answer key is complete and accurate
