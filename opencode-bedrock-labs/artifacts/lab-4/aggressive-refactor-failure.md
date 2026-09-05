I'll analyze this refactoring request for `durations.py`. Let me break down what I see:

## Current Implementation Analysis

**Strengths:**
- Comprehensive error handling with specific `DurationError` messages
- Clear separation of concerns (parsing vs. formatting)
- Good use of regex and helper data structures (`_UNIT_SECONDS`, `_UNIT_RANK`)
- Proper validation of input types

**Areas for Improvement:**

1. **Variable naming clarity:**
   - `_UNIT_SECONDS` and `_UNIT_RANK` could have more descriptive names
   - `seen_ranks` could be more specific about what it tracks
   - `normalized` is clear, but the normalization steps could be better organized

2. **Regex patterns:**
   - `_COMPONENT_RE` and `_FULL_RE` are single-use helper regexes that could benefit from inline documentation
   - The pattern logic could be more explicit about what it's validating

3. **Code organization:**
   - In `parse_duration`, the logic for tracking and validating unit ordering could be extracted
   - The "bare integer" case is handled clearly but could be slightly better organized

4. **Format function logic:**
   - The `divmod` chain works but could be more readable with better variable names
   - The conditional logic for `parts` could be clearer

5. **Documentation:**
   - The module docstring could be more detailed about constraints
   - Some validation errors could have clearer explanatory messages

## Refactoring Proposal

I would suggest:

1. **Rename internal constants** for clarity (e.g., `_UNIT_MULTIPLIERS` instead of `_UNIT_SECONDS`, `_UNIT_ORDER` instead of `_UNIT_RANK`)
2. **Extract unit validation logic** in `parse_duration` into a helper function
3. **Improve variable naming** in `format_duration` (e.g., `remaining_seconds` instead of `remainder`)
4. **Add inline regex documentation** with comments explaining what each pattern validates
5. **Enhance error messages** with more context where helpful

**Question for you:** Are there any specific areas you'd like me to prioritize? For instance:
- Is readability the primary goal, or should I also focus on any potential performance considerations?
- Any particular naming conventions you prefer?
- Should I add more docstring detail to helper logic?

Once you confirm, I can proceed with the refactored implementation.