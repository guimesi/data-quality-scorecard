# GraphQL Security — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Theme-level determination: Not Applicable — the app uses no GraphQL and exposes no
web-service data layer / external API.** It is a Streamlit application whose only data access is
**parameterized Snowflake `SELECT` queries** through `src/snowflake_client.py` (no GraphQL
server/client, no REST API, no resolver layer — confirmed: no `graphql`/`graphene`/`ariadne`/
`strawberry` dependencies or code). There is no query language exposed to clients.

---

## GraphQL and other Web Service Data Layer Security Requirements

**Question:** Use query whitelisting, depth/amount limiting, and query cost analysis to prevent DoS from expensive nested queries.
**Status:** Not Applicable
**Comment:** There is no GraphQL (or other client-facing query) layer — clients cannot submit arbitrary or nested queries. The only queries are app-constructed, fixed-shape Snowflake reads with bound parameters; result volume is bounded operationally by `MAX_ROWS_PER_TABLE` / Sample mode and by the Snowflake warehouse, not by a GraphQL cost limiter. No expensive-nested-query DoS surface exists.

**Question:** Implement authorization logic at the business-logic layer rather than the GraphQL layer.
**Status:** Not Applicable
**Comment:** No GraphQL layer exists. Authorization is enforced at the **Snowflake RBAC** tier (the session role's grants), not in the application — see the Access Control theme. There is no resolver-level authorization to relocate.
