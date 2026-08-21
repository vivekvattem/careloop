import type { AuthResponse, LoginInput, RegisterInput, User } from "../types/auth";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(body?.detail ?? "Something went wrong. Please try again.", response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  register: (input: RegisterInput) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify(input) }),
  login: (input: LoginInput) =>
    request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify(input) }),
  refresh: () => request<AuthResponse>("/auth/refresh", { method: "POST" }),
  me: (accessToken: string) => request<User>("/auth/me", {}, accessToken),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
};

