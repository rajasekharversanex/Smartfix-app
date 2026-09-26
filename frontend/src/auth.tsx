import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, saveToken } from "./api";

export type User = {
  id: string;
  name?: string;
  username: string;
  email?: string;
  mobile: string;
  role: "OWNER" | "ADMIN" | "STAFF" | "PROVIDER" | "CUSTOMER";
};

type Ctx = {
  user: User | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  requestOtp: (mobile: string) => Promise<string | undefined>;
  verifyOtp: (mobile: string, otp: string) => Promise<string>;
  complete: (
    flow_token: string,
    name: string,
    username: string,
    password: string,
    email?: string
  ) => Promise<void>;
  forgot: (identifier: string) => Promise<any>;
  reset: (token: string, new_password: string, otp?: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get("/auth/me");
      setUser(r.data);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const setAuth = async (data: any) => {
    await saveToken(data.access_token);
    await refresh();
  };

  const login = async (identifier: string, password: string) => {
    const r = await api.post("/auth/login", { identifier, password });
    await setAuth(r.data);
  };
  const logout = async () => {
    await saveToken(null);
    setUser(null);
  };
  const requestOtp = async (mobile: string) => {
    const r = await api.post("/auth/register/request-otp", { mobile });
    return r.data?.dev_otp;
  };
  const verifyOtp = async (mobile: string, otp: string) => {
    const r = await api.post("/auth/register/verify-otp", { mobile, otp });
    return r.data.flow_token as string;
  };
  const complete = async (
    flow_token: string,
    name: string,
    username: string,
    password: string,
    email?: string
  ) => {
    const r = await api.post("/auth/register/complete", {
      flow_token,
      name,
      username,
      password,
      email: email || undefined,
    });
    await setAuth(r.data);
  };
  const forgot = async (identifier: string) => (await api.post("/auth/forgot-password", { identifier })).data;
  const reset = async (token: string, new_password: string, otp?: string) => {
    await api.post("/auth/reset-password", { token, new_password, otp });
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, requestOtp, verifyOtp, complete, forgot, reset, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const x = useContext(AuthContext);
  if (!x) throw new Error("AuthProvider missing");
  return x;
};
