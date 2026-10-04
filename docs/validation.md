# Validation

status: blocked

A second business source (calendar, WhatsApp, payments, spreadsheets, or a CRM) must not be added while this status is `blocked`. The gate is `tests/security/test_validation_gate.py`. Change the status only after the answers below are filled from real conversations. Do not invent interview results.

## Questions

1. Who feels the pain: the owner or a coordinator?
   - Answer:
2. Which repeated task costs the most hours: unanswered mail, scheduling, collections, or quotes?
   - Answer:
3. What do they miss today?
   - Answer:
4. What would they pay to have handled, in their words?
   - Answer:
5. Which source is the real queue?
   - Answer:
6. Which action would they let software take after approval?
   - Answer:

## Measures

Record these after design partners use the operator loop. Leave them blank until then.

- Weekly active businesses:
- Items resolved or dismissed:
- Dismiss reason mix (`not_relevant`, `done`, `waiting`):
- Syncs per week:
- Would be upset if it disappeared (count and notes):

`not_relevant` dominating the dismiss mix means every new inbox message is the wrong attention rule. Change that rule before adding a source.

## Decision

- Next source:
- Why:
- Explicitly not building yet:
