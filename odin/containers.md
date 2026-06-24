# Containers — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Theme-level determination: the entire Containers theme is Not Applicable.**

The project produces **no container images** and operates **no container infrastructure**.
Verified in the repo: there is **no `Dockerfile`/`Containerfile`, no `docker-compose`, no
`.dockerignore`, no Kubernetes/Helm/Swarm/OpenShift manifests, and no container registry
configuration**. The only YAML files tracked are CI/tooling configs (`.github/workflows/tests.yml`,
`.github/workflows/security.yml`, `.pre-commit-config.yaml`, `environment.yml`) — none are
container/orchestration manifests; the only "registry" references in code are in-process Python
domain/system registries (`config/domains.py`, `config/systems.py`), unrelated to image
registries.

**Production runtime is Streamlit in Snowflake (SiS), deployed from this GitHub repo.** SiS
runs the app inside **Snowflake's managed, sandboxed compute** — Snowflake owns the OS,
runtime, storage, networking, image/build lifecycle, scaling, backup/DR, and monitoring.
There is no Docker Engine, no node/Swarm/UCP/DTR, no overlay network, and no image to scan
or sign at the application layer.

> **Caveat / consistency note:** these items would become **Applicable** only if the
> deployment model changed to a container-based runtime such as **Snowpark Container
> Services** (which *does* use container images), AKS/EKS, or OpenShift. The SiS target
> confirmed for this project does not. Several underlying *principles* (secret management,
> RBAC, backup/DR, centralized logging) are real and are addressed via **Snowflake platform
> controls** and covered in the Data Protection and Architecture themes — cross-referenced
> below rather than claimed as container controls.

---

## Storage requirements

**Question:** Use a suitable, tested storage driver guaranteeing replication/availability.
**Status:** Not Applicable
**Comment:** No containers/storage drivers. Source data persistence is Snowflake's responsibility (replicated, highly available storage); the app persists nothing itself.

**Question:** Persistent data never stored inside a container; use volumes/mount points.
**Status:** Not Applicable
**Comment:** No containers. The app writes no persistent data at all (no file writes; in-memory `session_state` only). Source data lives in Snowflake tables.

**Question:** Production-ready storage backend in use.
**Status:** Not Applicable
**Comment:** No app-managed storage backend; Snowflake provides production-grade storage for source data.

**Question:** Image storage backend redundant and in a secured network zone.
**Status:** Not Applicable
**Comment:** No container images and no image registry exist.

**Question:** Backup strategy for persistent data + tested restore.
**Status:** Not Applicable
**Comment:** No container-persisted data. Platform equivalent: Snowflake **Time Travel / Fail-safe** covers source-data backup/restore (see Data Protection theme). Not an app/container control.

---

## Disaster requirements

**Question:** Infrastructure restoration automated, documented, regularly tested.
**Status:** Not Applicable
**Comment:** No self-managed infrastructure. SiS infrastructure is Snowflake-managed; the app is redeployed from Git if needed.

**Question:** Regular backups of UCP, DTR, and Swarm (≥ weekly).
**Status:** Not Applicable
**Comment:** No Docker UCP/DTR/Swarm in use.

**Question:** On-failure restart policy enabled per container.
**Status:** Not Applicable
**Comment:** No containers; SiS process lifecycle is platform-managed.

**Question:** Automated/documented/tested upgrades & downgrades of infrastructure + Docker Engine.
**Status:** Not Applicable
**Comment:** No Docker Engine / self-managed infrastructure; runtime is patched/managed by Snowflake.

**Question:** Automated/documented/tested recovery of individual apps/services.
**Status:** Not Applicable
**Comment:** No container services. App recovery = redeploy from the Git integration; documenting that deploy procedure is captured as a follow-up in the SiS migration notes, not a container control.

---

## Logging Monitoring requirements

**Question:** Use Docker health-checking for all containers; actively monitor status.
**Status:** Not Applicable
**Comment:** No Docker/containers. SiS app health is platform-monitored.

**Question:** Regularly monitor the storage backend.
**Status:** Not Applicable
**Comment:** No app-managed storage backend; Snowflake monitors its own storage.

**Question:** Monitor resource usage at node and container levels.
**Status:** Not Applicable
**Comment:** No nodes/containers. Warehouse resource usage is observable via Snowflake (a platform capability, not a container control).

**Question:** Set container-platform log level to info in production.
**Status:** Not Applicable
**Comment:** No container platform. App-level logging is covered in the Architecture theme (Snowflake event tables in production).

**Question:** All logs transferred to and stored in a central location.
**Status:** Not Applicable
**Comment:** No container logs. Platform equivalent: Snowflake **event tables / Access History / Query History** (see Architecture theme).

---

## General Containers security requirements

**Question:** Only required software packages installed in images (minimal attack surface).
**Status:** Not Applicable
**Comment:** No images built. Dependency minimization for the SiS Anaconda environment is tracked under the SiS migration notes (`environment.yml`), not as an image build.

**Question:** Use COPY instead of ADD in Dockerfiles.
**Status:** Not Applicable
**Comment:** No Dockerfile exists.

**Question:** Exposed services restricted to trusted systems or require authentication.
**Status:** Not Applicable
**Comment:** No container-exposed services/ports. In SiS the app is reachable only through authenticated Snowflake/Snowsight sessions + USAGE grants (covered in Access Control theme).

**Question:** Base images pinned by hash, not just name/tag.
**Status:** Not Applicable
**Comment:** No base images / Dockerfile.

---

## Secrets and Keys requirements

**Question:** Sensitive info (API keys, passwords) never in configuration files.
**Status:** Not Applicable
**Comment:** Container-specific framing N/A. The underlying principle IS relevant and is covered elsewhere: the repo contains no secrets in tracked files; the local `.env` (gitignored, untracked) holds non-secret connection identifiers; `.env`/dotenv is removed from the SiS runtime path (see Data Protection + SiS migration notes).

**Question:** Secrets managed via a secret-management solution, not env vars.
**Status:** Not Applicable
**Comment:** No container secret store. In SiS the app uses the active Snowflake session (no app-managed secrets); any Git-integration credential is stored as a **Snowflake SECRET object**, not in env vars or the repo (see SiS migration notes).

**Question:** RBAC model in place for access control.
**Status:** Not Applicable
**Comment:** No container-orchestration RBAC. The real RBAC is **Snowflake roles + USAGE grants on the Streamlit object** (covered in Access Control theme); follow-up there recommends a dedicated least-privilege read-only role.

---

## Orchestration Management requirements

**Question:** Only containers with the same exposure level deployed on the same node.
**Status:** Not Applicable
**Comment:** No nodes/containers/orchestrator.

**Question:** Delete containers no longer needed.
**Status:** Not Applicable
**Comment:** No containers to reap. Stale SiS app objects are managed in Snowflake, not via container lifecycle.

**Question:** Predefined labels used to identify/manage resources.
**Status:** Not Applicable
**Comment:** No container resources/labels. Snowflake object naming/tagging is a platform concern, not a container control.

---

## Infrastructure Verification Requirements

**Question:** Document the entire infrastructure (nodes, networks, containers), ideally automated.
**Status:** Not Applicable
**Comment:** No self-managed nodes/networks/containers. The relevant architecture (SiS runtime, data flows, trust boundary) is documented in ARCHITECTURE.md + the Architecture theme; updating it for SiS is a follow-up already recorded.

**Question:** Clearly define architecture/design including networking inside/outside the container solution.
**Status:** Not Applicable
**Comment:** No container solution / container networking. Networking is entirely Snowflake-internal in SiS.

**Question:** Standalone AKS/EKS needs architectural endorsement; OpenShift preferred.
**Status:** Not Applicable
**Comment:** The app uses neither AKS, EKS, nor OpenShift — it runs on Streamlit in Snowflake.

---

## Container Image requirements

**Question:** No images from public repos (e.g. Docker Hub); use vetted internal repos.
**Status:** Not Applicable
**Comment:** No container images are built or pulled. (SiS Python packages come from Snowflake's curated Anaconda channel — a vetted source — but this is a package channel, not a container registry.)

**Question:** Enable and regularly run garbage collection on image registries.
**Status:** Not Applicable
**Comment:** No image registry.

**Question:** Regular automated security scans of images; pull into on-prem/managed cloud; use cloud registry scanning.
**Status:** Not Applicable
**Comment:** No images to scan. Dependency/SCA scanning of the SiS environment is tracked as a follow-up in the Architecture/SiS notes (not image scanning).

**Question:** Images imported to ExxonMobil environment must be security-scanned via goto/ssgrequest 'Container Image Import'.
**Status:** Not Applicable
**Comment:** No container images are imported. Would apply only if the project moved to a container-based runtime (e.g. Snowpark Container Services).

**Question:** Containers always built from the most recent image, not local caches.
**Status:** Not Applicable
**Comment:** No container build/cache. SiS pulls current code from the Git integration on deploy.

**Question:** Use specific image tags; only production/master may use `latest`.
**Status:** Not Applicable
**Comment:** No images/tags. (Versioning is via Git refs on the deploy branch — covered under source-control follow-ups.)

---

## Network requirements

**Question:** Activate load balancing (DNS Round Robin / VIP).
**Status:** Not Applicable
**Comment:** No self-managed network/load balancer. Traffic distribution and scaling are Snowflake-managed in SiS.

**Question:** Encrypt communication between containers/nodes on the overlay network.
**Status:** Not Applicable
**Comment:** No overlay network/containers. In-platform and user↔app traffic is Snowflake-managed TLS (covered in Communications theme).

**Question:** Run only necessary services; open only required ports.
**Status:** Not Applicable
**Comment:** The app opens no ports and exposes no services of its own; SiS controls all network exposure.

**Question:** Prevent inter-container network communication by default.
**Status:** Not Applicable
**Comment:** No containers / container network.

**Question:** Ensure subnets don't overlap (e.g. overlay networks).
**Status:** Not Applicable
**Comment:** No app-managed subnets/overlay networks.

**Question:** Each app/service assigned a separate isolated overlay network (L3 segmentation).
**Status:** Not Applicable
**Comment:** No overlay networks. Isolation is provided by the Snowflake SiS sandbox.

**Question:** Published ports bound to specific node interfaces and minimized.
**Status:** Not Applicable
**Comment:** No published ports / nodes.

**Question:** Implement SPF, DKIM, DMARC for end-user email communications.
**Status:** Not Applicable
**Comment:** The app sends no email and has no email-communication channel.

**Question:** Activate only required network interfaces (wired/wireless/Bluetooth).
**Status:** Not Applicable
**Comment:** No app-managed host/network interfaces; the runtime host is Snowflake-managed.
