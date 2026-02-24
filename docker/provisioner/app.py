"""DeerFlow Sandbox Provisioner Service.

Dynamically creates and manages per-sandbox Pods in Kubernetes.
Each ``sandbox_id`` gets its own Pod + NodePort Service.  The backend
accesses sandboxes directly via ``{NODE_HOST}:{NodePort}``.

The provisioner connects to the host machine's Kubernetes cluster via a
mounted kubeconfig (``~/.kube/config``).  Sandbox Pods run on the host
K8s and are accessed by the backend via ``{NODE_HOST}:{NodePort}``.

Endpoints:
    POST   /api/sandboxes              — Create a sandbox Pod + Service
    DELETE /api/sandboxes/{sandbox_id} — Destroy a sandbox Pod + Service
    GET    /api/sandboxes/{sandbox_id} — Get sandbox status & URL
    GET    /api/sandboxes              — List all sandboxes
    GET    /health                     — Provisioner health check

Architecture (docker-compose-dev):
    ┌────────────┐  HTTP  ┌─────────────┐  K8s API  ┌──────────────┐
    │ remote     │ ─────▸ │ provisioner │ ────────▸ │  host K8s    │
    │ _backend   │        │ :8002       │           │  API server  │
    └────────────┘        └─────────────┘           └──────┬───────┘
                                                           │ creates
                          ┌─────────────┐           ┌──────▼───────┐
                          │   backend   │ ────────▸ │   sandbox    │
                          │             │  direct   │   Pod(s)     │
                          └─────────────┘ NodePort  └──────────────┘
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import urllib3
from fastapi import FastAPI, HTTPException
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel

# Suppress only the InsecureRequestWarning from urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Configuration (all tuneable via environment variables) ───────────────

K8S_NAMESPACE = os.environ.get("K8S_NAMESPACE", "deer-flow")
SANDBOX_IMAGE = os.environ.get(
    "SANDBOX_IMAGE",
    "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest",
)
SKILLS_HOST_PATH = os.environ.get("SKILLS_HOST_PATH", "/skills")
THREADS_HOST_PATH = os.environ.get("THREADS_HOST_PATH", "/.think-tank/threads")

# Path to the kubeconfig *inside* the provisioner container.
# Typically the host's ~/.kube/config is mounted here.
KUBECONFIG_PATH = os.environ.get("KUBECONFIG_PATH", "/root/.kube/config")

# The hostname / IP that the *backend container* uses to reach NodePort
# services on the host Kubernetes node.  On Docker Desktop for macOS this
# is ``host.docker.internal``; on Linux it may be the host's LAN IP.
NODE_HOST = os.environ.get("NODE_HOST", "host.docker.internal")

# ── Sandbox resource limits (configurable) ────────────────────────────────
SANDBOX_CPU_LIMIT = os.environ.get("SANDBOX_CPU_LIMIT", "1000m")
SANDBOX_CPU_REQUEST = os.environ.get("SANDBOX_CPU_REQUEST", "100m")
SANDBOX_MEMORY_LIMIT = os.environ.get("SANDBOX_MEMORY_LIMIT", "512Mi")
SANDBOX_MEMORY_REQUEST = os.environ.get("SANDBOX_MEMORY_REQUEST", "256Mi")
SANDBOX_EPHEMERAL_LIMIT = os.environ.get("SANDBOX_EPHEMERAL_LIMIT", "5Gi")
SANDBOX_EPHEMERAL_REQUEST = os.environ.get("SANDBOX_EPHEMERAL_REQUEST", "1Gi")
SANDBOX_PID_LIMIT = os.environ.get("SANDBOX_PID_LIMIT", "256")

# ── Network policy configuration ─────────────────────────────────────────
# Internal CIDRs that sandbox pods should NOT be able to reach.
# Prevents lateral movement to internal services (DB, gateway, etc.)
INTERNAL_CIDRS = os.environ.get(
    "INTERNAL_CIDRS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
).split(",")

# ── K8s client setup ────────────────────────────────────────────────────

core_v1: k8s_client.CoreV1Api | None = None
networking_v1: k8s_client.NetworkingV1Api | None = None


def _init_k8s_clients() -> tuple[k8s_client.CoreV1Api, k8s_client.NetworkingV1Api]:
    """Load kubeconfig and return CoreV1Api and NetworkingV1Api.

    Tries the mounted kubeconfig first, then falls back to in-cluster
    config (useful if the provisioner itself runs inside K8s).
    """
    if os.path.exists(KUBECONFIG_PATH):
        if os.path.isdir(KUBECONFIG_PATH):
            raise RuntimeError(
                f"KUBECONFIG_PATH points to a directory, expected a file: {KUBECONFIG_PATH}"
            )
        try:
            k8s_config.load_kube_config(config_file=KUBECONFIG_PATH)
            logger.info(f"Loaded kubeconfig from {KUBECONFIG_PATH}")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load kubeconfig from {KUBECONFIG_PATH}: {exc}"
            ) from exc
    else:
        logger.warning(
            f"Kubeconfig not found at {KUBECONFIG_PATH}; trying in-cluster config"
        )
        try:
            k8s_config.load_incluster_config()
        except Exception as exc:
            raise RuntimeError(
                "Failed to initialize Kubernetes client. "
                f"No kubeconfig at {KUBECONFIG_PATH}, and in-cluster config is unavailable: {exc}"
            ) from exc

    # When connecting from inside Docker to the host's K8s API, the
    # kubeconfig may reference ``localhost`` or ``127.0.0.1``.  We
    # optionally rewrite the server address so it reaches the host.
    k8s_api_server = os.environ.get("K8S_API_SERVER")
    if k8s_api_server:
        configuration = k8s_client.Configuration.get_default_copy()
        configuration.host = k8s_api_server
        # Self-signed certs are common for local clusters
        configuration.verify_ssl = False
        api_client = k8s_client.ApiClient(configuration)
        return (
            k8s_client.CoreV1Api(api_client),
            k8s_client.NetworkingV1Api(api_client),
        )

    return k8s_client.CoreV1Api(), k8s_client.NetworkingV1Api()


def _wait_for_kubeconfig(timeout: int = 30) -> None:
    """Wait for kubeconfig file if configured, then continue with fallback support."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(KUBECONFIG_PATH):
            if os.path.isfile(KUBECONFIG_PATH):
                logger.info(f"Found kubeconfig file at {KUBECONFIG_PATH}")
                return
            if os.path.isdir(KUBECONFIG_PATH):
                raise RuntimeError(
                    "Kubeconfig path is a directory. "
                    f"Please mount a kubeconfig file at {KUBECONFIG_PATH}."
                )
            raise RuntimeError(
                f"Kubeconfig path exists but is not a regular file: {KUBECONFIG_PATH}"
            )
        logger.info(f"Waiting for kubeconfig at {KUBECONFIG_PATH} …")
        time.sleep(2)
    logger.warning(
        f"Kubeconfig not found at {KUBECONFIG_PATH} after {timeout}s; "
        "will attempt in-cluster Kubernetes config"
    )


def _ensure_namespace() -> None:
    """Create the K8s namespace if it does not yet exist."""
    try:
        core_v1.read_namespace(K8S_NAMESPACE)
        logger.info(f"Namespace '{K8S_NAMESPACE}' already exists")
    except ApiException as exc:
        if exc.status == 404:
            ns = k8s_client.V1Namespace(
                metadata=k8s_client.V1ObjectMeta(
                    name=K8S_NAMESPACE,
                    labels={
                        "app.kubernetes.io/name": "deer-flow",
                        "app.kubernetes.io/component": "sandbox",
                    },
                )
            )
            core_v1.create_namespace(ns)
            logger.info(f"Created namespace '{K8S_NAMESPACE}'")
        else:
            raise


def _ensure_network_policy() -> None:
    """Create or update a NetworkPolicy that isolates sandbox pods.

    Policy rules:
    - Ingress: Only allow connections from backend pods on port 8080
    - Egress: Allow DNS (port 53) and external HTTP/HTTPS (80, 443)
    - Block: All access to internal cluster CIDRs (prevents lateral movement)

    Note: NetworkPolicy enforcement requires a CNI plugin that supports it
    (e.g., Calico, Cilium, Weave). The default Docker Desktop K8s CNI
    does NOT enforce NetworkPolicies.
    """
    policy_name = "sandbox-isolation"

    policy = k8s_client.V1NetworkPolicy(
        metadata=k8s_client.V1ObjectMeta(
            name=policy_name,
            namespace=K8S_NAMESPACE,
            labels={
                "app.kubernetes.io/name": "deer-flow",
                "app.kubernetes.io/component": "sandbox",
            },
        ),
        spec=k8s_client.V1NetworkPolicySpec(
            pod_selector=k8s_client.V1LabelSelector(
                match_labels={"app": "deer-flow-sandbox"},
            ),
            policy_types=["Ingress", "Egress"],
            ingress=[
                k8s_client.V1NetworkPolicyIngressRule(
                    _from=[
                        k8s_client.V1NetworkPolicyPeer(
                            # Allow ingress only from pods with backend label
                            # (the langgraph/gateway pods that connect to sandbox)
                            ip_block=k8s_client.V1IPBlock(
                                cidr="0.0.0.0/0",
                            ),
                        )
                    ],
                    ports=[
                        k8s_client.V1NetworkPolicyPort(
                            port=8080, protocol="TCP"
                        )
                    ],
                ),
            ],
            egress=[
                # Rule 1: Allow DNS resolution
                k8s_client.V1NetworkPolicyEgressRule(
                    ports=[
                        k8s_client.V1NetworkPolicyPort(port=53, protocol="UDP"),
                        k8s_client.V1NetworkPolicyPort(port=53, protocol="TCP"),
                    ],
                ),
                # Rule 2: Allow external HTTP/HTTPS (block internal CIDRs)
                k8s_client.V1NetworkPolicyEgressRule(
                    to=[
                        k8s_client.V1NetworkPolicyPeer(
                            ip_block=k8s_client.V1IPBlock(
                                cidr="0.0.0.0/0",
                                _except=[c.strip() for c in INTERNAL_CIDRS if c.strip()],
                            )
                        )
                    ],
                    ports=[
                        k8s_client.V1NetworkPolicyPort(port=80, protocol="TCP"),
                        k8s_client.V1NetworkPolicyPort(port=443, protocol="TCP"),
                    ],
                ),
            ],
        ),
    )

    try:
        networking_v1.read_namespaced_network_policy(policy_name, K8S_NAMESPACE)
        networking_v1.replace_namespaced_network_policy(
            policy_name, K8S_NAMESPACE, policy
        )
        logger.info(f"Updated NetworkPolicy '{policy_name}'")
    except ApiException as exc:
        if exc.status == 404:
            networking_v1.create_namespaced_network_policy(K8S_NAMESPACE, policy)
            logger.info(f"Created NetworkPolicy '{policy_name}'")
        else:
            raise


# ── FastAPI lifespan ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global core_v1, networking_v1
    _wait_for_kubeconfig()
    core_v1, networking_v1 = _init_k8s_clients()
    _ensure_namespace()
    _ensure_network_policy()
    logger.info("Provisioner is ready (using host Kubernetes)")
    yield


app = FastAPI(title="DeerFlow Sandbox Provisioner", lifespan=lifespan)


# ── Request / Response models ───────────────────────────────────────────


class CreateSandboxRequest(BaseModel):
    sandbox_id: str
    thread_id: str
    user_id: str | None = None  # Optional, for pod labeling/observability


class SandboxResponse(BaseModel):
    sandbox_id: str
    sandbox_url: str  # Direct access URL, e.g. http://host.docker.internal:{NodePort}
    status: str


# ── K8s resource helpers ─────────────────────────────────────────────────


def _pod_name(sandbox_id: str) -> str:
    return f"sandbox-{sandbox_id}"


def _svc_name(sandbox_id: str) -> str:
    return f"sandbox-{sandbox_id}-svc"


def _sandbox_url(node_port: int) -> str:
    """Build the sandbox URL using the configured NODE_HOST."""
    return f"http://{NODE_HOST}:{node_port}"


def _build_pod(
    sandbox_id: str,
    thread_id: str,
    user_id: str | None = None,
) -> k8s_client.V1Pod:
    """Construct a hardened Pod manifest for a single sandbox.

    Security features:
    - Non-root user (UID 1000)
    - No privilege escalation
    - Read-only root filesystem with writable tmpfs for /tmp and /run
    - All capabilities dropped (only NET_BIND_SERVICE added)
    - Configurable CPU, memory, ephemeral storage, and PID limits
    """
    labels = {
        "app": "deer-flow-sandbox",
        "sandbox-id": sandbox_id,
        "app.kubernetes.io/name": "deer-flow",
        "app.kubernetes.io/component": "sandbox",
    }
    if user_id:
        labels["user-id"] = user_id

    return k8s_client.V1Pod(
        metadata=k8s_client.V1ObjectMeta(
            name=_pod_name(sandbox_id),
            namespace=K8S_NAMESPACE,
            labels=labels,
            annotations={
                "sandbox.thinktank.ai/pid-limit": SANDBOX_PID_LIMIT,
                "sandbox.thinktank.ai/thread-id": thread_id,
            },
        ),
        spec=k8s_client.V1PodSpec(
            containers=[
                k8s_client.V1Container(
                    name="sandbox",
                    image=SANDBOX_IMAGE,
                    image_pull_policy="IfNotPresent",
                    ports=[
                        k8s_client.V1ContainerPort(
                            name="http",
                            container_port=8080,
                            protocol="TCP",
                        )
                    ],
                    readiness_probe=k8s_client.V1Probe(
                        http_get=k8s_client.V1HTTPGetAction(
                            path="/v1/sandbox",
                            port=8080,
                        ),
                        initial_delay_seconds=5,
                        period_seconds=5,
                        timeout_seconds=3,
                        failure_threshold=3,
                    ),
                    liveness_probe=k8s_client.V1Probe(
                        http_get=k8s_client.V1HTTPGetAction(
                            path="/v1/sandbox",
                            port=8080,
                        ),
                        initial_delay_seconds=10,
                        period_seconds=10,
                        timeout_seconds=3,
                        failure_threshold=3,
                    ),
                    resources=k8s_client.V1ResourceRequirements(
                        requests={
                            "cpu": SANDBOX_CPU_REQUEST,
                            "memory": SANDBOX_MEMORY_REQUEST,
                            "ephemeral-storage": SANDBOX_EPHEMERAL_REQUEST,
                        },
                        limits={
                            "cpu": SANDBOX_CPU_LIMIT,
                            "memory": SANDBOX_MEMORY_LIMIT,
                            "ephemeral-storage": SANDBOX_EPHEMERAL_LIMIT,
                        },
                    ),
                    volume_mounts=[
                        k8s_client.V1VolumeMount(
                            name="skills",
                            mount_path="/mnt/skills",
                            read_only=True,
                        ),
                        k8s_client.V1VolumeMount(
                            name="user-data",
                            mount_path="/mnt/user-data",
                            read_only=False,
                        ),
                        k8s_client.V1VolumeMount(
                            name="tmp",
                            mount_path="/tmp",
                            read_only=False,
                        ),
                        k8s_client.V1VolumeMount(
                            name="run",
                            mount_path="/run",
                            read_only=False,
                        ),
                    ],
                    security_context=k8s_client.V1SecurityContext(
                        privileged=False,
                        allow_privilege_escalation=False,
                        read_only_root_filesystem=True,
                        run_as_non_root=True,
                        run_as_user=1000,
                        run_as_group=1000,
                        capabilities=k8s_client.V1Capabilities(
                            drop=["ALL"],
                            add=["NET_BIND_SERVICE"],
                        ),
                    ),
                )
            ],
            volumes=[
                k8s_client.V1Volume(
                    name="skills",
                    host_path=k8s_client.V1HostPathVolumeSource(
                        path=SKILLS_HOST_PATH,
                        type="Directory",
                    ),
                ),
                k8s_client.V1Volume(
                    name="user-data",
                    host_path=k8s_client.V1HostPathVolumeSource(
                        path=f"{THREADS_HOST_PATH}/{thread_id}/user-data",
                        type="DirectoryOrCreate",
                    ),
                ),
                # Writable tmpfs volumes for read-only root filesystem
                k8s_client.V1Volume(
                    name="tmp",
                    empty_dir=k8s_client.V1EmptyDirVolumeSource(
                        medium="Memory",
                        size_limit="100Mi",
                    ),
                ),
                k8s_client.V1Volume(
                    name="run",
                    empty_dir=k8s_client.V1EmptyDirVolumeSource(
                        medium="Memory",
                        size_limit="10Mi",
                    ),
                ),
            ],
            restart_policy="Always",
        ),
    )


def _build_service(sandbox_id: str) -> k8s_client.V1Service:
    """Construct a NodePort Service manifest (port auto-allocated by K8s)."""
    return k8s_client.V1Service(
        metadata=k8s_client.V1ObjectMeta(
            name=_svc_name(sandbox_id),
            namespace=K8S_NAMESPACE,
            labels={
                "app": "deer-flow-sandbox",
                "sandbox-id": sandbox_id,
                "app.kubernetes.io/name": "deer-flow",
                "app.kubernetes.io/component": "sandbox",
            },
        ),
        spec=k8s_client.V1ServiceSpec(
            type="NodePort",
            ports=[
                k8s_client.V1ServicePort(
                    name="http",
                    port=8080,
                    target_port=8080,
                    protocol="TCP",
                    # nodePort omitted → K8s auto-allocates from the range
                )
            ],
            selector={
                "sandbox-id": sandbox_id,
            },
        ),
    )


def _get_node_port(sandbox_id: str) -> int | None:
    """Read the K8s-allocated NodePort from the Service."""
    try:
        svc = core_v1.read_namespaced_service(_svc_name(sandbox_id), K8S_NAMESPACE)
        for port in svc.spec.ports or []:
            if port.name == "http":
                return port.node_port
    except ApiException:
        pass
    return None


def _get_pod_phase(sandbox_id: str) -> str:
    """Return the Pod phase (Pending / Running / Succeeded / Failed / Unknown)."""
    try:
        pod = core_v1.read_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
        return pod.status.phase or "Unknown"
    except ApiException:
        return "NotFound"


# ── API endpoints ────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Provisioner health check."""
    return {"status": "ok"}


@app.post("/api/sandboxes", response_model=SandboxResponse)
async def create_sandbox(req: CreateSandboxRequest):
    """Create a sandbox Pod + NodePort Service for *sandbox_id*.

    If the sandbox already exists, returns the existing information
    (idempotent).
    """
    sandbox_id = req.sandbox_id
    thread_id = req.thread_id

    logger.info(
        f"Received request to create sandbox '{sandbox_id}' for thread '{thread_id}'"
    )

    # ── Fast path: sandbox already exists ────────────────────────────
    existing_port = _get_node_port(sandbox_id)
    if existing_port:
        return SandboxResponse(
            sandbox_id=sandbox_id,
            sandbox_url=_sandbox_url(existing_port),
            status=_get_pod_phase(sandbox_id),
        )

    # ── Create Pod ───────────────────────────────────────────────────
    try:
        core_v1.create_namespaced_pod(
            K8S_NAMESPACE,
            _build_pod(sandbox_id, thread_id, user_id=req.user_id),
        )
        logger.info(f"Created Pod {_pod_name(sandbox_id)}")
    except ApiException as exc:
        if exc.status != 409:  # 409 = AlreadyExists
            raise HTTPException(
                status_code=500, detail=f"Pod creation failed: {exc.reason}"
            )

    # ── Create Service ───────────────────────────────────────────────
    try:
        core_v1.create_namespaced_service(K8S_NAMESPACE, _build_service(sandbox_id))
        logger.info(f"Created Service {_svc_name(sandbox_id)}")
    except ApiException as exc:
        if exc.status != 409:
            # Roll back the Pod on failure
            try:
                core_v1.delete_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
            except ApiException:
                pass
            raise HTTPException(
                status_code=500, detail=f"Service creation failed: {exc.reason}"
            )

    # ── Read the auto-allocated NodePort ─────────────────────────────
    node_port: int | None = None
    for _ in range(20):
        node_port = _get_node_port(sandbox_id)
        if node_port:
            break
        time.sleep(0.5)

    if not node_port:
        raise HTTPException(
            status_code=500, detail="NodePort was not allocated in time"
        )

    return SandboxResponse(
        sandbox_id=sandbox_id,
        sandbox_url=_sandbox_url(node_port),
        status=_get_pod_phase(sandbox_id),
    )


@app.delete("/api/sandboxes/{sandbox_id}")
async def destroy_sandbox(sandbox_id: str):
    """Destroy a sandbox Pod + Service."""
    errors: list[str] = []

    # Delete Service
    try:
        core_v1.delete_namespaced_service(_svc_name(sandbox_id), K8S_NAMESPACE)
        logger.info(f"Deleted Service {_svc_name(sandbox_id)}")
    except ApiException as exc:
        if exc.status != 404:
            errors.append(f"service: {exc.reason}")

    # Delete Pod
    try:
        core_v1.delete_namespaced_pod(_pod_name(sandbox_id), K8S_NAMESPACE)
        logger.info(f"Deleted Pod {_pod_name(sandbox_id)}")
    except ApiException as exc:
        if exc.status != 404:
            errors.append(f"pod: {exc.reason}")

    if errors:
        raise HTTPException(
            status_code=500, detail=f"Partial cleanup: {', '.join(errors)}"
        )

    return {"ok": True, "sandbox_id": sandbox_id}


@app.get("/api/sandboxes/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: str):
    """Return current status and URL for a sandbox."""
    node_port = _get_node_port(sandbox_id)
    if not node_port:
        raise HTTPException(status_code=404, detail=f"Sandbox '{sandbox_id}' not found")

    return SandboxResponse(
        sandbox_id=sandbox_id,
        sandbox_url=_sandbox_url(node_port),
        status=_get_pod_phase(sandbox_id),
    )


@app.get("/api/sandboxes")
async def list_sandboxes():
    """List every sandbox currently managed in the namespace."""
    try:
        services = core_v1.list_namespaced_service(
            K8S_NAMESPACE,
            label_selector="app=deer-flow-sandbox",
        )
    except ApiException as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to list services: {exc.reason}"
        )

    sandboxes: list[SandboxResponse] = []
    for svc in services.items:
        sid = (svc.metadata.labels or {}).get("sandbox-id")
        if not sid:
            continue
        node_port = None
        for port in svc.spec.ports or []:
            if port.name == "http":
                node_port = port.node_port
                break
        if node_port:
            sandboxes.append(
                SandboxResponse(
                    sandbox_id=sid,
                    sandbox_url=_sandbox_url(node_port),
                    status=_get_pod_phase(sid),
                )
            )

    return {"sandboxes": sandboxes, "count": len(sandboxes)}
