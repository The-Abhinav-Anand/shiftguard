import type {
  SessionCredentials,
  StoredExperiment,
  WorkspaceSnapshot,
} from "../api/types";
import { isPublishedPayload, sanitizeForBrowserCache } from "../api/client";
import type { ExperimentEnvelope } from "../api/types";

const STORAGE_KEY = "shiftguard.browser-workspace.v1";

export const emptyWorkspace = (): WorkspaceSnapshot => ({
  version: 1,
  session: null,
  jobs: [],
  pending_submission: null,
  cached_experiment: null,
});

export interface StorageRead {
  workspace: WorkspaceSnapshot;
  issue: string | null;
}

export function readWorkspace(): StorageRead {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { workspace: emptyWorkspace(), issue: null };
    const parsed = JSON.parse(raw) as Partial<WorkspaceSnapshot>;
    if (parsed.version !== 1) {
      return { workspace: emptyWorkspace(), issue: "Saved browser state uses an unsupported version. A new session will be created." };
    }
    const cached = parsed.cached_experiment ?? null;
    if ((cached && (!isPublishedPayload(cached.payload) || !cached.content_hashes)) ||
      (parsed.session && (typeof parsed.session.session_id !== "string" || typeof parsed.session.capability_token !== "string")) ||
      (parsed.jobs && (!Array.isArray(parsed.jobs) || parsed.jobs.some((job) => typeof job.job_id !== "string")))) {
      return { workspace: emptyWorkspace(), issue: "Saved browser state is invalid. A new session will be created; published server records remain available." };
    }
    if (cached) cached.source = "browser-cache";
    return {
      workspace: {
        version: 1,
        session: parsed.session ?? null,
        jobs: Array.isArray(parsed.jobs) ? parsed.jobs.slice(-8) : [],
        pending_submission: parsed.pending_submission ?? null,
        cached_experiment: cached,
      },
      issue: null,
    };
  } catch {
    return {
      workspace: emptyWorkspace(),
      issue: "Browser storage could not be read. This run will remain available only until the tab closes.",
    };
  }
}

export function writeWorkspace(workspace: WorkspaceSnapshot): string | null {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(workspace));
    return null;
  } catch {
    return "Browser storage is unavailable or full. Current work remains visible, but reload recovery may be limited.";
  }
}

export function cacheExperiment(
  experiment: ExperimentEnvelope,
  source: StoredExperiment["source"],
): StoredExperiment {
  return {
    experiment_id: experiment.experiment_id,
    created_at: experiment.created_at,
    content_hashes: experiment.content_hashes,
    payload: sanitizeForBrowserCache(experiment),
    source,
  };
}

export function saveSession(
  workspace: WorkspaceSnapshot,
  session: SessionCredentials,
): WorkspaceSnapshot {
  return { ...workspace, session };
}
