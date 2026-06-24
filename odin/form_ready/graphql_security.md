## GraphQL and other Web Service Data Layer Security Requirements

**Use query whitelisting, depth/amount limiting, and query cost analysis to prevent DoS from expensive nested queries.**
Status: Not Applicable
Comment: No client-facing GraphQL/query layer exists; only fixed-shape, parameterized Snowflake reads with bounded result volume.

**Implement authorization logic at the business-logic layer rather than the GraphQL layer.**
Status: Not Applicable
Comment: No GraphQL layer exists; authorization is enforced at the Snowflake RBAC tier, not in the application.
