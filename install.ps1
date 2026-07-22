# Installs deps in two passes to dodge the crewai / livekit-agents json-repair conflict.
# See requirements.txt header for why order matters.
$ErrorActionPreference = "Stop"

pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

pip install -r requirements-voice.txt
exit $LASTEXITCODE
