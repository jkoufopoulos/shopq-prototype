# Dynamic Examples - No Hardcoding

## Philosophy

The digest generator uses **zero hardcoded examples**. Instead, the LLM receives real entities extracted from the user's current inbox batch as its "examples".

## How It Works

### 1. Entity Extraction (Dynamic)
```python
# shopq/entity_extractor.py
# Extracts REAL entities from emails:
# - Flights with departure_time
# - Events with event_time
# - Deadlines with due_date
# - Reminders, promos, notifications
```

### 2. Importance Classification (Dynamic)
```python
# shopq/importance_classifier.py
# Classifies each entity:
entity.importance = 'critical'      # Fraud alerts, bills due today
entity.importance = 'time_sensitive' # Flights, appointments
entity.importance = 'routine'        # Newsletters, promos
```

### 3. Grouping (Dynamic)
```python
# shopq/timeline_synthesizer.py - format_featured_for_llm()
# Groups by importance:

Most urgent:
1. [Real critical item from user's inbox]
2. [Real critical item from user's inbox]

Also important:
3. [Real time-sensitive item from user's inbox]
4. [Real time-sensitive item from user's inbox]
```

### 4. LLM Generation (Uses Real Data)
```python
# shopq/narrative_generator.py
# Sends to LLM:
prompt = f"""
{prompt_template}  # Structure guidance only

## INPUT (Real data from user's inbox)
**Featured Entities** (already grouped by urgency):
{featured_text}  # ← REAL entities, not examples!

**Routine Noise**: {noise_text}  # ← REAL noise breakdown
"""
```

## Example Flow

**User's inbox contains:**
- ChatGPT subscription email (classified as critical)
- Voting reminder (classified as critical)
- Meditation event (classified as time_sensitive)
- 24 newsletters (classified as routine)

**LLM receives:**
```
Most urgent:
1. ChatGPT Plus subscription cancels on Oct 30 ($20/mo)
2. Vote today - polls close at 8 PM

Also important:
3. Downtown Dharma meditation tonight at 7:30 PM
```

**LLM generates:**
```
Hey! It's a cloudy 52° in New York today.

Your ChatGPT Plus subscription cancels on Oct 30 (1).
Don't forget to vote today — polls close at 8 PM (2)!

You have meditation tonight at 7:30 PM (3).

Have a great day!
```

## Benefits

1. ✅ **Always relevant** - Examples match user's actual inbox
2. ✅ **No stale examples** - Updates with every batch
3. ✅ **Personalized** - Reflects user's communication patterns
4. ✅ **No prompt bloat** - No need for 10+ hardcoded examples
5. ✅ **Self-documenting** - The data IS the documentation

## Where Examples Are NOT Used

- ❌ `shopq/prompts/narrative_prompt.txt` - Structure guidance only, no hardcoded examples
- ❌ `shopq/narrative_generator.py` - Passes real data, not examples
- ❌ `shopq/timeline_synthesizer.py` - Formats real entities, not examples

## Where Real Data Flows

```
User's Inbox
    ↓
Entity Extractor (extracts structured data)
    ↓
Importance Classifier (assigns urgency)
    ↓
Timeline Synthesizer (groups by urgency)
    ↓
format_featured_for_llm() (formats real entities)
    ↓
Narrative Generator (passes to LLM)
    ↓
LLM (generates digest from REAL data)
    ↓
User sees digest based on THEIR inbox
```

## Key Design Principle

> The best example is the user's own data.

Instead of teaching the LLM with generic examples, we give it the user's actual emails, already structured and grouped. The LLM's job is simple: convert this structured data into friendly prose while preserving the grouping.
