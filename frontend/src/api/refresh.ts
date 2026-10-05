/** Dashboard Refresh button endpoints. */

import { api } from "./client";

export type RefreshJobStatus = "idle" | "running" | "done" | "skipped" | "failed";

export interface RefreshJob {
  key: string;
  label: string;
  status: RefreshJobStatus;
  message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface RefreshStatus {
  running: boolean;
  jobs: RefreshJob[];
}

export const fetchRefreshStatus = () => api.get<RefreshStatus>("/refresh/status");
export const startRefresh = () => api.post<RefreshStatus>("/refresh");
