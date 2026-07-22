#!/usr/bin/env bash
# Installs deps in two passes to dodge the crewai / livekit-agents json-repair conflict.
# See requirements.txt header for why order matters.
set -e

pip install -r requirements.txt
pip install -r requirements-voice.txt
