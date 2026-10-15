# Running the checks in every Claude Code session (optional)

Today the checks run only in a Claude Code session that starts inside this repository. Two files let them run everywhere:

- tools/mm-controls-bootstrap.sh keeps a copy of the approved repository in ~/.mm-controls and runs the checks from it.
- controls/user-level-settings.json is the settings block that calls it before and after every action, and when a reply ends.

Inside this repository the block does nothing (the repository's own checks already run), so they never run twice.

## To switch it on

1. Copy tools/mm-controls-bootstrap.sh to ~/.mm-controls-bootstrap.sh in the environment where Claude Code runs.
2. Merge the "hooks" part of controls/user-level-settings.json into that environment's user-level Claude settings (~/.claude/settings.json), or add both steps to the cloud environment's setup script.

## What is proven and what is not

- The proof test (tests/prove_it_bites.py) runs the bootstrap against a copy of the repository from a folder that is not the repository, and shows it blocks and allows what it should.
- Not proven: whether a cloud session honours user-level settings, or runs the setup script before the first prompt. The environment documentation page for the setup script is the place to confirm that. Until it is switched on, nothing changes.
