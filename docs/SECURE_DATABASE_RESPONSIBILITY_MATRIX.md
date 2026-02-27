# Responsibility Matrix: Agent-Side vs Client-Side

> Which security layers do **we** (agent developers) own, and which must the
> **client** (database operators / government IT teams) implement?

---

## Guiding Principle

We cannot enforce security on client databases. What we **can** guarantee is that
**everything between the user's query and the network boundary — and everything
between the filtered result and the user's screen — is as safe and reliable as possible.**

The client is responsible for what happens **inside** their network perimeter, including
the MCP server, database credentials, database access, and first-pass data filtering.
We are responsible for what happens **outside** it: the agent platform, LLM orchestration,
dual-pass security controls, and the user-facing interface.

**Key architectural decision:** The MCP server runs inside the **client's** network
perimeter, not on our platform. We ship the MCP server as a hardened OCI container
("Database Connector Kit") that the client deploys. Our platform communicates with
it exclusively via **Streamable HTTP + mTLS** (port 443). No database protocol ever
crosses the public internet.

---

## Summary View

```
        OUR SIDE (Agent Platform)                 CLIENT SIDE (Client Network Perimeter)
  ========================================    ========================================

  [User Interface]                            [MCP Server (postgres-mcp container)]
  [Authentication / Session Management]       [SQL AST Firewall (2nd pass)]
  [Input Guardrails / Prompt Injection]       [Database Infrastructure]
  [Semantic Layer / Query Abstraction]        [Database Engine Configuration]
  [SQL AST Firewall (1st pass)]               [Row-Level Security Policies]
  [Human-in-the-Loop Gate]                    [Column-Level Masking Rules]
  [MCP Gateway (Streamable HTTP + mTLS)]      [Read-Only Roles / Grants]
  [Output DLP / PII Scanning (2nd pass)]      [Credential Store (Vault / Secrets Mgr)]
  [Classification Filter]                     [Client-side DLP / Result Filter (1st pass)]
  [Differential Privacy (optional)]           [Client-side Audit Logging (SIEM)]
  [Agent-side Audit Logging (WORM)]           [pgAudit / DB-Level Audit Logging]
  [Database Connector Kit (OCI image)]        [MCP Server Deployment & Operations]
                                              [Network Firewall / VPC Configuration]
                                              [Database Replication (Read Replicas)]
                                              [Data Classification / Labeling]
                                              [Compliance Certification (FedRAMP, ATO)]
                                              [Backup / Disaster Recovery]
                                              [Physical Security / Air-Gap]
```

---

## Detailed Breakdown

### Layer 1: Connection & Authentication

| Concern | Owner | What It Means |
|---------|-------|---------------|
| MCP transport selection (Streamable HTTP for production) | **Us** | We use Streamable HTTP + mTLS for all remote MCP connections |
| mTLS certificate management (agent-side client cert) | **Us** | We manage our client certificate for authenticating to client MCP servers |
| mTLS certificate management (server cert on client MCP) | **Client** | They manage TLS certificates on their MCP server endpoint |
| OAuth 2.1 client implementation (PKCE, resource indicators) | **Us** | Our MCP Gateway correctly implements the MCP auth spec |
| OAuth 2.1 authorization server / IdP | **Shared** | Client may provide their IdP; we integrate via OIDC/SAML |
| MCP server inbound authentication (token validation) | **Client** | Their MCP server validates audience-bound OAuth tokens from our gateway |
| Client firewall / edge rules (port 443 only) | **Client** | They allowlist only our platform IPs/certs, block all other inbound |
| Database network access (private subnet / localhost) | **Client** | DB is reachable only from MCP server within client VPC — never from internet |
| Database TLS configuration | **Client** | They enable TLS on PostgreSQL listener (internal traffic) |
| Database user accounts and roles | **Client** | They create the read-only roles that the MCP server connects with |

### Layer 2: Credential Management

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Credential store deployment (Vault, Secrets Manager) | **Client** | Client deploys and manages Vault inside their network perimeter |
| Vault Database Secrets Engine configuration | **Client** | They configure which DBs, roles, and TTLs Vault provisions |
| MCP server credential acquisition (JIT) | **Client** | MCP server requests short-lived credentials from co-located Vault |
| Credential scope: stays inside client network | **Client** | Database credentials are **never** transmitted to our agent platform |
| Credential TTL enforcement (max 5 minutes) | **Client** | Client configures max TTL on Vault roles; MCP server respects it |
| Credential revocation on MCP session end | **Shared** | Our gateway signals session end; client MCP server revokes credentials |
| Database role permissions (SELECT-only, table grants) | **Client** | They define what the provisioned role can access |

### Layer 3: Query Security

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Semantic layer deployment and maintenance | **Us** | We deploy Cube.js / dbt MetricFlow as our query abstraction |
| Semantic model definitions (metrics, dimensions) | **Shared** | Client defines their business metrics; we host the runtime |
| SQL AST validation firewall (1st pass, agent-side) | **Us** | We parse and validate every generated SQL before sending to client |
| SQL AST validation firewall (2nd pass, client-side) | **Client** | Client MCP server re-validates SQL with agency-specific rules |
| Query allowlist/denylist rules | **Shared** | We enforce general rules; client enforces agency-specific table/column allowlists |
| Stored procedure / parameterized template approach | **Shared** | Client creates procedures; we configure the agent to use them |
| Read-only enforcement at agent proxy level | **Us** | Our gateway rejects DML/DDL before it leaves our platform |
| Read-only enforcement at client MCP level | **Client** | Client MCP server independently rejects DML/DDL |
| Read-only enforcement at database level | **Client** | They configure `default_transaction_read_only` on the role |
| Row-Level Security (RLS) policies | **Client** | They define and maintain RLS policies on their tables |
| Column-level grants / restrictions | **Client** | They grant SELECT on specific columns only |
| `statement_timeout` configuration | **Shared** | Client sets at role level; MCP server can also enforce per-query |
| EXPLAIN-before-execute cost validation | **Client** | Client MCP server runs EXPLAIN and rejects queries above cost threshold |

### Layer 4: MCP Server Lifecycle & Deployment

The MCP server (postgres-mcp) runs **inside the client's network perimeter**, shipped
as a hardened OCI container ("Database Connector Kit"). This is the most significant
architectural difference from a traditional agent-hosted MCP pattern.

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Database Connector Kit: OCI image build & signing | **Us** | We build, sign, and publish hardened postgres-mcp images to a curated registry |
| Database Connector Kit: version updates & patches | **Us** | We release updated images; client pulls and redeploys on their schedule |
| MCP server deployment inside client VPC | **Client** | They pull our signed image, deploy it in their network, configure network rules |
| MCP server container hardening (runtime) | **Client** | They run with non-root, read-only rootfs, dropped capabilities, seccomp, resource limits |
| MCP server network egress controls | **Client** | They restrict outbound to only their database (private subnet / localhost) |
| MCP server inbound access controls | **Client** | They allowlist only our platform's mTLS certificates on the MCP server endpoint |
| MCP server process lifecycle (start/stop/restart) | **Client** | They manage uptime, scaling, and health monitoring of their MCP server |
| MCP server session isolation (per-connection state) | **Shared** | We send session-scoped tokens; client MCP server isolates per-session state |
| MCP tool allowlisting (which tools the agent can call) | **Us** | We configure which MCP tools are available to the LLM in the agent graph |
| MCP server tool implementation (which tools are exposed) | **Client** | They can customize which tools are enabled on their MCP server instance |
| Version compatibility / drift detection | **Shared** | We embed version headers in requests; client MCP server validates compatibility |
| MCP server configuration customization | **Client** | They configure agency-specific policies, table allowlists, DLP rules on their instance |

### Layer 5: Human-in-the-Loop

| Concern | Owner | What It Means |
|---------|-------|---------------|
| HITL gate implementation (LangGraph interrupt) | **Us** | We build the approval workflow into the agent graph |
| Risk classification rules (which queries need approval) | **Shared** | We provide defaults; client customizes per their policy |
| Approval UI / notification system | **Us** | We build the frontend for reviewers to approve/reject/edit |
| Designation of authorized approvers | **Client** | They decide who in their org can approve sensitive queries |
| HITL applies before network boundary | **Us** | Human review happens on our side, before dispatching to client MCP |

### Layer 6: Output Security (Dual-Side)

Output security is enforced on **both** sides for defense-in-depth.

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Client-side DLP / result filter (1st pass) | **Client** | Client MCP server scans results with agency-specific PII rules before returning |
| Client-side result set size limits | **Client** | Client MCP server caps row count / data size before returning |
| Agent-side PII/PHI scanning (Presidio, 2nd pass) | **Us** | We scan every response with standard + client-supplied entity rules |
| Agent-side PII detection model training / rules | **Us** (with client input) | We provide defaults; client may add domain-specific rules |
| Classification-aware response filtering | **Shared** | We enforce clearance checks; client provides data classification labels |
| Differential privacy on aggregates | **Us** | We add calibrated noise; client sets epsilon/budget policy |
| Agent-side response size limits | **Us** | We cap the amount of data in the final response to users |

### Layer 7: Audit & Compliance (Dual-Side)

Both sides maintain independent, tamper-evident audit logs correlated by trace ID.

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Agent-side audit logging (tool calls, prompts, responses) | **Us** | We log every interaction with correlation IDs (trace_id) |
| Client-side audit logging (MCP server operations) | **Client** | Client MCP server logs SQL, credentials used, DLP actions, with same trace_id |
| Database-side audit logging (pgAudit) | **Client** | They enable and configure pgAudit on their database |
| Trace ID propagation (X-Trace-ID header) | **Shared** | We generate trace IDs; client MCP server includes them in its logs |
| Agent-side WORM storage for audit logs | **Us** | We store agent logs in append-only, cryptographically hashed storage |
| Client-side SIEM integration | **Client** | They integrate MCP server + pgAudit logs with their SIEM |
| Cross-side log correlation | **Shared** | We provide structured logs; client matches trace IDs in their SIEM |
| Compliance certification (FedRAMP, ATO) | **Shared** | We certify the agent platform; client certifies their infrastructure (incl. MCP server) |
| Data retention policy enforcement | **Shared** | We retain agent logs per policy; client retains MCP/DB logs per their policy |
| Log integrity (cryptographic hashing, signatures) | **Both** | We ensure our logs are tamper-evident; client ensures theirs are too |

### Layer 8: Infrastructure & Network

| Concern | Owner | What It Means |
|---------|-------|---------------|
| Agent platform deployment (cloud, on-prem) | **Us** | We provide deployment options matching client requirements |
| MCP server deployment inside client network | **Client** | They deploy our Database Connector Kit in their VPC/on-prem |
| Database server deployment | **Client** | They own and operate the database infrastructure |
| Network segmentation between MCP server and DB | **Client** | They configure VPCs, subnets, firewalls within their perimeter |
| Network boundary: Streamable HTTP only (port 443) | **Shared** | We send only MCP JSON-RPC; client firewall blocks all other protocols |
| Database replication (read replicas) | **Client** | They set up and maintain read replicas for MCP server access |
| Confidential computing infrastructure (TEEs) | **Shared** | We support TEE deployment; client provides hardware/cloud |
| Air-gap deployment for classified networks | **Shared** | We provide air-gap compatible OCI images; client provides isolated network |
| Physical security | **Client** | They secure the data center / cloud region |
| Backup and disaster recovery | **Client** | They manage DB + MCP server backups; we manage agent platform backups |

---

## What We Ship: The "Agent Security Contract"

This is what our platform **guarantees** regardless of client configuration:

### Always On (cannot be disabled)

1. **SQL AST validation (1st pass, agent-side)** — Every generated SQL is parsed and
   validated before it leaves our platform. DDL and DML writes are always rejected.
2. **Read-only enforcement at gateway** — The MCP Gateway never dispatches DML/DDL to the
   client MCP server, regardless of what the LLM generates.
3. **Output PII scanning (2nd pass, agent-side)** — Every result received from the client
   MCP server is re-scanned for PII patterns before the LLM sees it.
4. **Audit logging (agent-side)** — Every tool call, query, response, and guardrail action
   is logged with correlation IDs (trace_id) and timestamps in WORM storage.
5. **mTLS transport** — All communication to client MCP servers uses mutual TLS with
   certificate pinning. No plaintext MCP traffic.
6. **Envelope encryption** — MCP payloads are encrypted with AES-256-GCM inside the
   mTLS channel for defense-in-depth.
7. **Result set size limits** — Agent-side caps on data returned in final responses.
8. **Input prompt injection detection** — Common injection patterns are detected and
   blocked before reaching the LLM.
9. **Session-scoped tokens** — Each conversation gets a unique, short-lived OAuth token
   bound to the specific client MCP server audience.
10. **Trace ID propagation** — Every request carries an X-Trace-ID for cross-side
    log correlation between our audit logs and the client's SIEM.

### We Ship to Client (Database Connector Kit)

11. **Signed OCI container image** — Hardened postgres-mcp container, signed and published
    to a curated registry. Client pulls and deploys inside their network.
12. **Built-in SQL AST firewall (2nd pass)** — The container includes a second SQL
    validation layer the client can configure with agency-specific rules.
13. **Built-in client-side DLP** — The container includes result filtering that the client
    configures with their PII entity types.
14. **Built-in audit logging** — The container logs all operations with trace ID correlation,
    ready for client SIEM integration.
15. **EXPLAIN-before-execute** — The container runs EXPLAIN on every query and rejects
    queries above configurable cost thresholds.
16. **Version compatibility headers** — The container validates protocol version compatibility
    with our gateway on every request.

### Configurable by Client (on their MCP server instance)

17. **Table/column allowlists** — Client restricts which tables the MCP server can query.
18. **Agency-specific SQL policies** — Client adds custom AST rules beyond our defaults.
19. **DLP entity types** — Client adds domain-specific PII patterns for result filtering.
20. **Cost thresholds** — Client sets EXPLAIN cost limits for query rejection.
21. **Credential TTL** — Client configures max credential lifetime in their Vault.
22. **Tool enablement** — Client enables/disables specific MCP tools on their instance.

### Configurable by Client (on our platform)

23. **Semantic layer** — Client can define business metrics and dimensions to constrain
    query generation (opt-in but recommended).
24. **HITL gate thresholds** — Client configures which query types require human approval.
25. **Agent-side PII rules** — Client can add domain-specific entity types to our Presidio.
26. **Differential privacy** — Client sets epsilon values and privacy budgets.
27. **Agent-side query allowlists** — Client can restrict queries at the gateway level.
28. **Audit log export** — Client configures where our logs are shipped (SIEM, S3, etc.).

### Client Must Provide

29. **Deploy our Database Connector Kit** (MCP server OCI container) inside their VPC.
30. **Configure MCP server endpoint** accessible from our platform (port 443, mTLS).
31. **Manage mTLS certificates** for the MCP server (server cert + trust our client cert).
32. **Deploy a credential store** (Vault, Secrets Manager) co-located with MCP server.
33. **Create a dedicated read-only database user** with SELECT-only grants.
34. **Set up a read-only replica** (recommended) or confirm primary DB is acceptable.
35. **Configure network access** — firewall rules between MCP server and database.
36. **Enable pgAudit** for database-side query logging.
37. **Configure RLS policies** if multi-tenant isolation is required.
38. **Apply column-level masking** on sensitive columns (SSN, PII, etc.).
39. **Set `statement_timeout`** on the agent role (recommended: 30-60 seconds).
40. **Classify data sensitivity levels** for columns/tables.
41. **Designate authorized approvers** for HITL review of sensitive queries.
42. **Provide schema documentation** or semantic model definitions.
43. **Integrate MCP server logs** with their SIEM for audit compliance.

---

## Implementation Priority for Our Platform

Based on this matrix, the highest-impact items **we own** in priority order:

| Priority | Item | Complexity | Impact |
|----------|------|-----------|--------|
| P0 | MCP Gateway with Streamable HTTP + mTLS dispatch | High | Core communication path to client MCP servers |
| P0 | SQL AST validation firewall (1st pass, agent-side) | Medium | Prevents DML/DDL before it leaves our platform |
| P0 | Read-only enforcement at gateway level | Low | Defense-in-depth for write prevention |
| P0 | Agent-side audit logging with trace ID propagation | Medium | Required for compliance; enables cross-side correlation |
| P0 | Session-scoped OAuth token management | Medium | Each conversation gets unique, audience-bound token |
| P1 | Database Connector Kit: hardened OCI image build pipeline | High | The signed container image we ship to clients |
| P1 | Database Connector Kit: built-in SQL AST firewall (2nd pass) | Medium | Client-side query validation baked into the container |
| P1 | Database Connector Kit: built-in DLP / result filter | Medium | Client-side PII scanning baked into the container |
| P1 | Database Connector Kit: built-in audit logging | Medium | Client-side logging with trace ID correlation |
| P1 | Output PII scanning (Presidio, 2nd pass, agent-side) | Medium | Catches what client-side DLP missed |
| P1 | HITL gate (LangGraph interrupt for sensitive queries) | Medium | Gives clients control over high-risk operations |
| P1 | Envelope encryption (AES-256-GCM) for MCP payloads | Medium | Defense-in-depth inside mTLS channel |
| P2 | Semantic layer integration (Cube.js) | High | Strongest query safety; eliminates raw SQL |
| P2 | Differential privacy on aggregates | Medium | Protects individual records |
| P2 | Input prompt injection detection | Medium | Blocks adversarial inputs |
| P2 | Version compatibility / drift detection | Low | Prevents mismatches between gateway and client MCP |
| P3 | Confidential computing support (TEE deployment) | High | Required for classified workloads |

---

## What We Tell Clients

### Onboarding Checklist

When a government client connects a database, we provide this checklist:

**Phase 1: Deploy the Database Connector Kit (MCP Server)**

- [ ] **Pull our signed MCP server OCI image** from the curated registry
- [ ] **Deploy the container** inside your VPC / on-prem network
- [ ] **Configure mTLS certificates** on the MCP server endpoint (port 443)
- [ ] **Trust our agent platform client certificate** for inbound authentication
- [ ] **Configure firewall rules** — allow inbound from our platform IPs only (port 443)
- [ ] **Configure network rules** — MCP server can reach the database (private subnet)
- [ ] **Block all other inbound and outbound** traffic on the MCP server

**Phase 2: Configure the Database**

- [ ] **Create a dedicated read-only database user** with SELECT-only grants on
      authorized tables/columns
- [ ] **Set up a read-only replica** (recommended) for MCP server access
- [ ] **Enable pgAudit** for database-side query logging
- [ ] **Configure RLS policies** if multi-tenant isolation is required
- [ ] **Apply column-level masking** on sensitive columns (SSN, PII, etc.)
- [ ] **Set `statement_timeout`** on the agent role (recommended: 30-60 seconds)
- [ ] **Set `default_transaction_read_only = on`** on the agent role

**Phase 3: Configure Credentials**

- [ ] **Deploy a credential store** (Vault, Secrets Manager) co-located with MCP server
- [ ] **Configure Database Secrets Engine** with agent-readonly-role (max TTL: 5 min)
- [ ] **Grant MCP server access** to the credential store (IAM role / Vault policy)

**Phase 4: Configure Security Policies on MCP Server**

- [ ] **Configure table/column allowlists** on the MCP server instance
- [ ] **Add agency-specific PII entity types** to the built-in DLP module
- [ ] **Set EXPLAIN cost thresholds** for query rejection
- [ ] **Enable/disable specific MCP tools** per agency policy
- [ ] **Integrate MCP server logs** with your SIEM (trace ID correlation)

**Phase 5: Configure on Our Platform**

- [ ] **Register the MCP server endpoint** URL in our platform
- [ ] **Classify data sensitivity levels** for columns/tables
- [ ] **Designate authorized approvers** for HITL review of sensitive queries
- [ ] **Provide schema documentation** or semantic model definitions
- [ ] **Configure HITL thresholds** (which query types need human approval)
- [ ] **(Optional)** Define semantic layer models (business metrics, dimensions)
- [ ] **(Optional)** Set differential privacy epsilon values

### What We Guarantee

> "Our platform ensures that every database query is validated, audited, and filtered
> **twice** — once on our side before it reaches your network, and once on your MCP
> server inside your network perimeter. No database protocol ever crosses the public
> internet. Your credentials never leave your network. Your data is filtered by your
> own DLP rules before it reaches our platform, and then filtered again by ours before
> it reaches the user. Both sides maintain independent, tamper-evident audit logs
> correlated by trace ID for complete end-to-end accountability."
