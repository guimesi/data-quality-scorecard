## Storage requirements

**Use a suitable, tested storage driver guaranteeing replication/availability.**
Status: Not Applicable
Comment: No containers or storage drivers; Snowflake provides replicated, highly available storage for source data.

**Persistent data never stored inside a container; use volumes/mount points.**
Status: Not Applicable
Comment: No containers, and the app persists nothing (in-memory session_state only); source data lives in Snowflake.

**Production-ready storage backend in use.**
Status: Not Applicable
Comment: No app-managed storage backend; Snowflake provides production-grade storage for source data.

**Image storage backend redundant and in a secured network zone.**
Status: Not Applicable
Comment: No container images and no image registry exist.

**Backup strategy for persistent data + tested restore.**
Status: Not Applicable
Comment: No container-persisted data; Snowflake Time Travel / Fail-safe covers source-data backup and restore.

## Disaster requirements

**Infrastructure restoration automated, documented, regularly tested.**
Status: Not Applicable
Comment: No self-managed infrastructure; SiS infrastructure is Snowflake-managed and the app is redeployed from Git.

**Regular backups of UCP, DTR, and Swarm (≥ weekly).**
Status: Not Applicable
Comment: No Docker UCP/DTR/Swarm in use.

**On-failure restart policy enabled per container.**
Status: Not Applicable
Comment: No containers; the SiS process lifecycle is platform-managed.

**Automated/documented/tested upgrades & downgrades of infrastructure + Docker Engine.**
Status: Not Applicable
Comment: No Docker Engine or self-managed infrastructure; the runtime is patched and managed by Snowflake.

**Automated/documented/tested recovery of individual apps/services.**
Status: Not Applicable
Comment: No container services; app recovery is a redeploy from the Git integration.

## Logging Monitoring requirements

**Use Docker health-checking for all containers; actively monitor status.**
Status: Not Applicable
Comment: No Docker or containers; SiS app health is platform-monitored.

**Regularly monitor the storage backend.**
Status: Not Applicable
Comment: No app-managed storage backend; Snowflake monitors its own storage.

**Monitor resource usage at node and container levels.**
Status: Not Applicable
Comment: No nodes or containers; warehouse resource usage is observable via Snowflake.

**Set container-platform log level to info in production.**
Status: Not Applicable
Comment: No container platform; app-level logging uses Snowflake event tables in production.

**All logs transferred to and stored in a central location.**
Status: Not Applicable
Comment: No container logs; Snowflake event tables / Access History / Query History provide centralized logging.

## General Containers security requirements

**Only required software packages installed in images (minimal attack surface).**
Status: Not Applicable
Comment: No images built; dependency minimization is handled via the SiS Anaconda environment.yml.

**Use COPY instead of ADD in Dockerfiles.**
Status: Not Applicable
Comment: No Dockerfile exists.

**Exposed services restricted to trusted systems or require authentication.**
Status: Not Applicable
Comment: No container-exposed services; in SiS the app is reachable only via authenticated Snowflake sessions and USAGE grants.

**Base images pinned by hash, not just name/tag.**
Status: Not Applicable
Comment: No base images or Dockerfile.

## Secrets and Keys requirements

**Sensitive info (API keys, passwords) never in configuration files.**
Status: Not Applicable
Comment: Container framing N/A; the repo has no secrets in tracked files and dotenv is removed from the SiS runtime path.

**Secrets managed via a secret-management solution, not env vars.**
Status: Not Applicable
Comment: No container secret store; SiS uses the active Snowflake session and any Git credential is a Snowflake SECRET object.

**RBAC model in place for access control.**
Status: Not Applicable
Comment: No container-orchestration RBAC; real access control is Snowflake roles plus USAGE grants on the Streamlit object.

## Orchestration Management requirements

**Only containers with the same exposure level deployed on the same node.**
Status: Not Applicable
Comment: No nodes, containers, or orchestrator.

**Delete containers no longer needed.**
Status: Not Applicable
Comment: No containers to reap; stale SiS app objects are managed in Snowflake.

**Predefined labels used to identify/manage resources.**
Status: Not Applicable
Comment: No container resources or labels; Snowflake object naming is a platform concern.

## Infrastructure Verification Requirements

**Document the entire infrastructure (nodes, networks, containers), ideally automated.**
Status: Not Applicable
Comment: No self-managed infrastructure; the SiS architecture and data flows are documented in ARCHITECTURE.md.

**Clearly define architecture/design including networking inside/outside the container solution.**
Status: Not Applicable
Comment: No container solution or container networking; networking is entirely Snowflake-internal in SiS.

**Standalone AKS/EKS needs architectural endorsement; OpenShift preferred.**
Status: Not Applicable
Comment: The app uses neither AKS, EKS, nor OpenShift; it runs on Streamlit in Snowflake.

## Container Image requirements

**No images from public repos (e.g. Docker Hub); use vetted internal repos.**
Status: Not Applicable
Comment: No container images are built or pulled; SiS packages come from Snowflake's curated Anaconda channel.

**Enable and regularly run garbage collection on image registries.**
Status: Not Applicable
Comment: No image registry.

**Regular automated security scans of images; pull into on-prem/managed cloud; use cloud registry scanning.**
Status: Not Applicable
Comment: No images to scan; dependency/SCA scanning of the SiS environment is a tracked follow-up.

**Images imported to ExxonMobil environment must be security-scanned via goto/ssgrequest 'Container Image Import'.**
Status: Not Applicable
Comment: No container images are imported.

**Containers always built from the most recent image, not local caches.**
Status: Not Applicable
Comment: No container build or cache; SiS pulls current code from the Git integration on deploy.

**Use specific image tags; only production/master may use `latest`.**
Status: Not Applicable
Comment: No images or tags; versioning is via Git refs on the deploy branch.

## Network requirements

**Activate load balancing (DNS Round Robin / VIP).**
Status: Not Applicable
Comment: No self-managed network or load balancer; traffic distribution and scaling are Snowflake-managed.

**Encrypt communication between containers/nodes on the overlay network.**
Status: Not Applicable
Comment: No overlay network or containers; in-platform and user-to-app traffic is Snowflake-managed TLS.

**Run only necessary services; open only required ports.**
Status: Not Applicable
Comment: The app opens no ports and exposes no services; SiS controls all network exposure.

**Prevent inter-container network communication by default.**
Status: Not Applicable
Comment: No containers or container network.

**Ensure subnets don't overlap (e.g. overlay networks).**
Status: Not Applicable
Comment: No app-managed subnets or overlay networks.

**Each app/service assigned a separate isolated overlay network (L3 segmentation).**
Status: Not Applicable
Comment: No overlay networks; isolation is provided by the Snowflake SiS sandbox.

**Published ports bound to specific node interfaces and minimized.**
Status: Not Applicable
Comment: No published ports or nodes.

**Implement SPF, DKIM, DMARC for end-user email communications.**
Status: Not Applicable
Comment: The app sends no email and has no email-communication channel.

**Activate only required network interfaces (wired/wireless/Bluetooth).**
Status: Not Applicable
Comment: No app-managed host or network interfaces; the runtime host is Snowflake-managed.
