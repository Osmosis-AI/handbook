FROM ghcr.io/osmosis-ai/handbook-runtime@sha256:067945097f3f12bde65af9d8282e43227b6767ae1750eae17515350cf81cf8b4

COPY initial_external_services/ /data/
COPY initial_external_services/ /initial_data/
COPY initial_workspace/ /workdir/

ENV INPUTDIR=/data OUTPUTDIR=/data HANDBOOK_TOOL_SETS="handbook_ds_all google_mail_contacts slack_core google_mail_core google_calendar_core jira_core shopify_core"

COPY initial_workspace/ /environment/initial_workspace/
COPY initial_external_services/ /environment/initial_external_services/
