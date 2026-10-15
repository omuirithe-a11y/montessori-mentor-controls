# Session 15 Oct 2026: a check that makes Claude measure instead of judge

Asked (owner, O6): "I want a hook that makes you measure instead of using your judgement every time. write this now and when it is ready tell me so I can push it to the repository."

Earlier in the session the owner asked for the hooks to be rated, then said "turn your judgment into measurement". The measured figures at that point: tests/prove_it_bites.py printed "167 of 168 checks behaved as expected"; the one failure is the spacing tool test, which needs the playwright module that this container lacks.

Built:
- controls/config.json: a new "measure" block (judgement phrases, what counts as a measuring command, the smallest figure that counts).
- .claude/hooks/stop.py: check 14. A reply that gives a rating ("8 out of 10"), an estimate, a percentage of confidence or an opinion is refused unless a measuring tool ran in the same reply and the reply states a figure that tool printed. Quoted phrases and code are not read as the reply's own words.
- .claude/hooks/user_prompt.py: every owner message now carries the instruction "MEASURE, DO NOT JUDGE", so the measurement is run before the reply is written.
- tests/prove_it_bites.py: eight new scenarios.

Measured: tests/prove_it_bites.py printed "175 of 176 checks behaved as expected". The one failure is the same playwright one.

Not done: nothing is committed or pushed. The owner pushes.

Still open: the Sensorial Curriculum rebuild (START-HERE "Still to do"). The judgement phrases are a fixed list; a judgement worded some other way will not be caught.
