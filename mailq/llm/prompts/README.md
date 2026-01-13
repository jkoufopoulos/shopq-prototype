# LLM Prompts Directory

This directory contains externalized LLM prompts for easy experimentation and version control.

## 📁 Files

- **`classifier_prompt.txt`** - Main classification prompt (LLM #1)
- **`verifier_prompt.txt`** - Verification/correction prompt (LLM #2)
- **`__init__.py`** - Prompt loader module

## 🎯 Why External Prompts?

**Before**: Prompts were hardcoded in Python files, making experimentation difficult:
- Had to edit Python code to test new prompts
- Hard to compare different prompt versions
- Risk of introducing syntax errors

**After**: Prompts are in plain text files:
- ✅ Edit prompts without touching Python code
- ✅ Easy A/B testing between prompt versions
- ✅ Version control friendly (git diff shows prompt changes)
- ✅ No risk of breaking Python syntax

## 🚀 Usage

### From Python Code

```python
from mailq.prompts import get_classifier_prompt, get_verifier_prompt

# Classifier prompt
prompt = get_classifier_prompt(
    fewshot_examples="...",
    from_field="sender@example.com",
    subject="Email subject",
    snippet="Email content..."
)

# Verifier prompt
prompt = get_verifier_prompt(
    from_field="sender@example.com",
    subject="Email subject",
    snippet="Email content...",
    type="promotion",
    type_conf=0.67,
    attention="action_required",
    attention_conf=0.52,
    domains="shopping",
    reason="...",
    features_str="has_promo_words, has_action_words",
    contradictions_str="action_required_with_promo_language"
)
```

### Reload Prompts Without Restarting

```python
from mailq.prompts import reload_prompts

# After editing a prompt file:
reload_prompts()  # Clears cache and reloads from disk
```

## 📝 Template Variables

Prompts use Python `str.format()` syntax with curly braces `{}`.

### Classifier Prompt Variables

- `{fewshot_examples}` - Few-shot learning examples (static + learned)
- `{from_field}` - Email sender address
- `{subject}` - Email subject line
- `{snippet}` - Email body snippet (first 300 chars)

### Verifier Prompt Variables

- `{from_field}` - Email sender address
- `{subject}` - Email subject line
- `{snippet}` - Email body snippet (first 200 chars)
- `{type}` - First-pass classification type
- `{type_conf}` - Type confidence (formatted as 0.XX)
- `{attention}` - First-pass attention classification
- `{attention_conf}` - Attention confidence (formatted as 0.XX)
- `{domains}` - Comma-separated domains
- `{reason}` - First-pass reasoning
- `{features_str}` - Detected features (comma-separated)
- `{contradictions_str}` - Detected contradictions (comma-separated)

## 🧪 Experimenting with Prompts

### A/B Testing Different Versions

1. **Create a backup**:
   ```bash
   cp classifier_prompt.txt classifier_prompt_v1.txt
   ```

2. **Edit the prompt**:
   ```bash
   nano classifier_prompt.txt
   # Make your changes
   ```

3. **Test in development**:
   ```bash
   # Prompts are loaded automatically on next classification
   curl -X POST http://localhost:8000/api/organize -d '...'
   ```

4. **Compare results**:
   - Check classification accuracy
   - Compare confidence scores
   - Review reasoning quality

5. **Rollback if needed**:
   ```bash
   cp classifier_prompt_v1.txt classifier_prompt.txt
   ```

### Version Control with Git

```bash
# View prompt changes
git diff mailq/prompts/classifier_prompt.txt

# Commit prompt improvements
git add mailq/prompts/
git commit -m "Improve classifier prompt: reduce hedging language"

# Create a prompt experiment branch
git checkout -b experiment/classifier-prompt-strict-rubric
# Edit prompts
git commit -am "Test stricter rubric enforcement"
```

## 🎨 Prompt Design Tips

### Good Practices

✅ **Be explicit**:
```
BAD:  "Classify the email"
GOOD: "Return ONLY valid JSON with ALL required fields"
```

✅ **Use examples**:
```
BAD:  "Shopping includes purchases"
GOOD: "Shopping: online orders, receipts, deliveries (e.g., Amazon, DoorDash)"
```

✅ **Avoid ambiguity**:
```
BAD:  "Domains are mutually exclusive"
GOOD: "Use single domain in most cases. Add secondary ONLY if both ≥0.60"
```

✅ **Demand definitiveness**:
```
BAD:  "Explain your reasoning"
GOOD: "Avoid hedging like 'probably'. Say 'receipt based on order #' not 'probably receipt'"
```

### Avoid

❌ **Contradictory rules**:
```
"ALWAYS assign a domain" + Example with empty domains = Confused LLM
```

❌ **Vague instructions**:
```
"Think step by step" vs "1. Extract domain 2. Find signals 3. Match examples"
```

❌ **Hedging language in examples**:
```
"This might be a receipt" → LLM copies hedging language
```

## 📊 Monitoring Prompt Changes

Track metrics before/after prompt changes:

```python
# Before prompt change
metrics_before = {
    'avg_confidence': 0.78,
    'verifier_reject_rate': 0.12,
    'uncategorized_rate': 0.05
}

# After prompt change
metrics_after = {
    'avg_confidence': 0.85,  # ✅ Improved!
    'verifier_reject_rate': 0.08,  # ✅ Fewer corrections needed
    'uncategorized_rate': 0.03  # ✅ Better classification
}
```

## 🔧 Advanced: Custom Prompt Versions

### Creating Named Prompt Variants

```python
# In __init__.py, add:
def get_classifier_prompt_v2(**kwargs) -> str:
    """Experimental stricter version"""
    template = load_prompt('classifier_prompt_v2')
    return template.format(**kwargs)
```

### Dynamic Prompt Selection

```python
# Based on environment or A/B test
import os

prompt_version = os.getenv('PROMPT_VERSION', 'default')

if prompt_version == 'strict':
    prompt = get_classifier_prompt_v2(**kwargs)
else:
    prompt = get_classifier_prompt(**kwargs)
```

## 📚 Resources

- [OpenAI Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
- [Anthropic Prompt Library](https://docs.anthropic.com/claude/prompt-library)
- [Google Gemini Best Practices](https://ai.google.dev/docs/prompt_best_practices)

## 🐛 Troubleshooting

### Prompt not updating?

```python
from mailq.prompts import reload_prompts
reload_prompts()  # Force reload from disk
```

### Variable substitution error?

```
KeyError: 'from_field'
```

**Fix**: Ensure all `{variables}` in the template match the kwargs passed to the function.

### Prompt file not found?

```
FileNotFoundError: Prompt file not found: .../classifier_prompt.txt
```

**Fix**: Check the file exists in `mailq/prompts/` directory.

---

**Happy Prompt Engineering!** 🚀
