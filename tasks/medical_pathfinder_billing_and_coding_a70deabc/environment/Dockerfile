FROM ghcr.io/osmosis-ai/handbook-runtime@sha256:b5fb6bc3daab778eaa091c83e9f3505b12d02834cad995693f0c15445c68a0ef

COPY initial_external_services/ /data/
COPY initial_external_services/ /initial_data/
COPY initial_workspace/ /workdir/

ENV INPUTDIR=/data OUTPUTDIR=/data HANDBOOK_TOOL_SETS="handbook_ds_all google_mail_contacts slack_core google_mail_core google_calendar_core jira_core shopify_core"

COPY initial_workspace/ /environment/initial_workspace/
COPY initial_external_services/ /environment/initial_external_services/
