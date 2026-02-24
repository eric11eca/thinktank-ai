import { authFetch } from "@/core/auth/fetch";
import { getBackendBaseURL } from "@/core/config";

export type AgentToolSummary = {
  name: string;
  description: string;
};

export type AgentSkillSummary = {
  name: string;
  description: string;
};

export type AgentContextResponse = {
  tools: AgentToolSummary[];
  skills: AgentSkillSummary[];
  model_name: string | null;
  subagent_enabled: boolean;
};

export type AgentContextParams = {
  modelName?: string;
  subagentEnabled?: boolean;
};

export async function loadAgentContext({
  modelName,
  subagentEnabled,
}: AgentContextParams): Promise<AgentContextResponse> {
  const searchParams = new URLSearchParams();
  if (modelName) {
    searchParams.set("model_name", modelName);
  }
  if (typeof subagentEnabled === "boolean") {
    searchParams.set("subagent_enabled", String(subagentEnabled));
  }
  const query = searchParams.toString();
  const response = await authFetch(
    `${getBackendBaseURL()}/api/agent/context${query ? `?${query}` : ""}`,
  );
  if (!response.ok) {
    throw new Error("Failed to load agent context");
  }
  return response.json() as Promise<AgentContextResponse>;
}
