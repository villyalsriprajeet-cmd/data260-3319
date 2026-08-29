# Domain Schema

Domain 7 - Community sports league fixtures.

A fixture is just a scheduled match between two teams. Each one has a title,
the venue it's played at, the email of whoever submitted it, some details about
the match, and a status showing where it's at.

## Fields on the form

- fixtureTitle - text, required. Main field, like "Real Madrid vs Barcelona - Matchweek 5"
- venue - text, required. Where it's played
- email - email, required. Submitter's email
- details - textarea, required. Match description, has to be more than 25 characters
- status - dropdown, required. Scheduled / Live / Completed / Postponed
- terms - checkbox, required. Has to be ticked before submitting

## Dropdown options

Scheduled, Live, Completed, Postponed

## Extra field

submissionDate - not on the form. The JavaScript adds this automatically with the
current date/time when the form is submitted.