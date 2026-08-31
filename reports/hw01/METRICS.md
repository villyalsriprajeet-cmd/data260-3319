HW1 – Part 3: Measuring Non-Determinism

Domain 7 – Community sports league fixtures. I took one fixed fixture and ran it through the whole pipeline 40 times to see how much the output changes — 20 runs at temperature 0.0 and 20 at temperature 0.7, all on qwen2.5:3b running locally through Ollama. The exact input I used is in reports/hw01/cases/nondeterminism_input.json.

Temperature 0.0:
  Distinct tag sets       : 2
  Tags in all 20 runs     : ['spartan soccer complex']
  Tags in exactly 1 run   : ['fresno state bulldogs', 'san jose state spartans']
  Latency p50/p95/p99 ms  : 330732.5 / 476172.0 / 479911.2

Temperature 0.7:
  Distinct tag sets       : 14
  Tags in all 20 runs     : []
  Tags in exactly 1 run   : ['college_venues', 'conference table', 'conferencegames',
                             'fixture_details', 'fresno bulldogs', 'fresno state bulldogs',
                             'mountainwestsoccer', 'san jose state home game',
                             'san jose state spartans', 'scheduling conflict', 'soccer match',
                             'soccer_teams', 'soccerfixture', 'soccerfixtures',
                             'spartan soccer', 'spartanmatch']
  Latency p50/p95/p99 ms  : 397549.5 / 531446.2 / 532756.4

Notes

All 40 runs (tags + latency) are saved in reports/hw01/raw/ — all_runs.json and all_runs.csv — and the computed numbers are in raw/metrics.json.

I lowered num_ctx to 512 and num_predict to 256 to keep each run from taking too long on my laptop (8 GB MacBook, CPU only). Since the fixture is short, that didn't change the tags or summary.