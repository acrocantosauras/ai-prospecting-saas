export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
}

export interface WorkspaceInfo {
  id: string;
  slug: string;
  name: string;
  role: string;
}

export interface AuthSession {
  user: AuthUser;
  workspaces: WorkspaceInfo[];
  workspace: WorkspaceInfo | null;
  csrf_token: string | null;
}

export interface AuthStatus {
  authentication_available: boolean;
  bootstrap_required: boolean;
}
