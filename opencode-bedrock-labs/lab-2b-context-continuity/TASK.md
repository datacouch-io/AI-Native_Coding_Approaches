# Task: expense report summarizer

Build a small Python module that summarizes expense reports.

The module file MUST be named `expenses.py`, and the test file MUST be named
`test_expenses.py` and import from `expenses`.

Requirements:

1. Accept a list of expense records. Each record has: an ISO-8601 date string, a
   numeric amount, a category name, and a 3-letter currency code.
2. Reject records that are malformed (bad date, non-numeric or negative amount,
   missing category, currency that is not exactly 3 uppercase letters).
3. Produce per-category totals for the records that were accepted.
4. Money must be rounded to 2 decimal places, using banker's rounding.
5. Support filtering the input to an inclusive date range before summarizing.
6. Mixed currencies in one summary must be treated as an error - do not sum them.
