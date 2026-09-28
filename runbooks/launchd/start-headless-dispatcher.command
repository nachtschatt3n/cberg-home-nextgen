#!/bin/zsh -il
# Session program of the iTerm window opened by headless-dispatcher-keeper.sh
# (`create window with default profile command <this file>`), so the dispatcher
# gets a real tty and an iTerm session the OpenClaw pod resolves by its command
# line. `-il` (interactive login) loads ~/.zshrc, so mise's python3 and claude
# resolve exactly as in the operator's own panes -- a plain login shell picked
# the Command Line Tools python 3.9 in the 2026-09-28 install test.
# When the dispatcher exits the session ends; the keeper opens a fresh window
# within one poll. Can also be run by hand from any pane.
printf '\033]1;ai-server-cron\007'
cd /Users/mu/code/cberg-home-nextgen || exit 1
exec python3 runbooks/headless-dispatcher.py
