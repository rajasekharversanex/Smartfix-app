import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, errMsg } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input, StatusPill } from "@/src/ui";
import { Logo } from "@/src/brand";

type Tab = "overview" | "bookings" | "services" | "providers" | "coupons" | "users";

export default function Admin() {
  const { user, logout } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [refreshing, setRefreshing] = useState(false);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.muted, fontSize: 13 }}>Control Center</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 2 }}>
              <Logo size="sm" />
            </View>
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 2 }}>{user?.name || user?.username} · {user?.role}</Text>
          </View>
          <Pressable onPress={async () => { await logout(); router.replace("/login"); }} testID="admin-logout"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Logout</Text></Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingTop: spacing.md }}>
          {(["overview", "bookings", "services", "providers", "coupons", "users"] as Tab[]).map((t) => (
            <Pressable key={t} testID={`admin-tab-${t}`} onPress={() => setTab(t)} style={{ flexShrink: 0, height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: tab === t ? colors.brandPrimary : colors.surfaceTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: tab === t ? colors.brandPrimary : colors.border }}>
              <Text style={{ color: tab === t ? colors.onBrandPrimary : colors.onSurfaceTertiary, fontWeight: "600", fontSize: 13, textTransform: "capitalize" }}>{t}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl, gap: spacing.md }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); setTimeout(() => setRefreshing(false), 500); }} tintColor={colors.brandPrimary} />}>
        {tab === "overview" && <Overview />}
        {tab === "bookings" && <BookingsAdmin />}
        {tab === "services" && <ServicesAdmin />}
        {tab === "providers" && <ProvidersAdmin />}
        {tab === "coupons" && <CouponsAdmin />}
        {tab === "users" && <UsersAdmin />}
      </ScrollView>
    </View>
  );
}

function Kpi({ label, value, tint }: { label: string; value: string; tint?: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 140, padding: spacing.lg, borderRadius: radius.lg, backgroundColor: tint || colors.brandSecondary }}>
      <Text style={{ color: colors.onSurfaceSecondary, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: colors.brandPrimary, fontSize: 22, fontWeight: "800", marginTop: 4 }}>{value}</Text>
    </View>
  );
}

function Overview() {
  const { colors } = useTheme();
  const [s, setS] = useState<any>(null);
  useFocusEffect(useCallback(() => { api.get("/admin/stats").then((r) => setS(r.data)); }, []));
  if (!s) return <ActivityIndicator color={colors.brandPrimary} />;
  return (
    <>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
        <Kpi label="Revenue Today" value={`₹${s.revenue_today}`} />
        <Kpi label="Total Revenue" value={`₹${s.revenue_total}`} />
        <Kpi label="Today's Bookings" value={String(s.todays_bookings)} />
        <Kpi label="Pending" value={String(s.pending_bookings)} tint="#FFF4E5" />
        <Kpi label="Active" value={String(s.active_bookings)} />
        <Kpi label="Completed" value={String(s.completed_bookings)} />
        <Kpi label="Cancelled" value={String(s.cancelled_bookings)} tint="#FDECEC" />
        <Kpi label="Customers" value={String(s.total_customers)} />
        <Kpi label="Providers" value={String(s.total_providers)} />
        <Kpi label="Pending Apps" value={String(s.pending_provider_applications)} tint="#FFF4E5" />
      </View>
    </>
  );
}

function BookingsAdmin() {
  const { colors } = useTheme();
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [assigning, setAssigning] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [b, p] = await Promise.all([api.get("/bookings"), api.get("/admin/providers").catch(() => ({ data: [] as any[] }))]);
    setRows(b.data); setProviders(p.data);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const assign = async (bid: string, pid: string) => {
    try { await api.post(`/bookings/${bid}/assign`, { provider_id: pid }); await load(); setAssigning(null); }
    catch (e: any) { alert(errMsg(e)); }
  };
  const verifyPay = async (bid: string) => { await api.post(`/admin/bookings/${bid}/verify-payment`); await load(); };

  return (
    <>
      {rows.length === 0 && <Text style={{ color: colors.muted }}>No bookings yet.</Text>}
      {rows.map((b) => (
        <View key={b.id} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
          <Pressable onPress={() => router.push({ pathname: "/booking/[id]", params: { id: b.id } })} testID={`admin-booking-${b.id}`}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={{ color: colors.onSurface, fontWeight: "700", flex: 1 }} numberOfLines={1}>{b.service_name}</Text>
              <StatusPill status={b.status} />
            </View>
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 4 }}>{new Date(b.scheduled_at).toLocaleString()}</Text>
            <Text style={{ color: colors.onSurfaceSecondary, marginTop: 4 }}>Customer: {b.customer?.name} · {b.customer?.mobile}</Text>
            <Text style={{ color: colors.onSurfaceSecondary }}>Provider: {b.provider?.name || "— unassigned"}</Text>
            <Text style={{ color: colors.brandPrimary, fontWeight: "800", marginTop: 6 }}>₹{b.total} · {b.payment_method} · {b.payment_status}</Text>
          </Pressable>
          {!b.provider_id && b.status === "PENDING" && (
            <>
              <Button label={assigning === b.id ? "Cancel" : "Assign Provider"} variant="secondary" onPress={() => setAssigning(assigning === b.id ? null : b.id)} testID={`admin-assign-toggle-${b.id}`} />
              {assigning === b.id && (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingTop: spacing.sm }}>
                  {providers.map((p) => (
                    <Pressable key={p.id} testID={`admin-assign-${b.id}-${p.id}`} onPress={() => assign(b.id, p.id)} style={{ flexShrink: 0, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brandPrimary }}>
                      <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>{p.name || p.username}</Text>
                    </Pressable>
                  ))}
                  {providers.length === 0 && <Text style={{ color: colors.muted }}>No providers yet.</Text>}
                </ScrollView>
              )}
            </>
          )}
          {b.payment_status === "AWAITING_VERIFICATION" && (
            <View style={{ marginTop: spacing.sm }}>
              <Text style={{ color: colors.warning, marginBottom: spacing.sm }}>UPI Ref: {b.upi_txn_ref}</Text>
              <Button label="Verify Payment" onPress={() => verifyPay(b.id)} testID={`admin-verify-${b.id}`} />
            </View>
          )}
        </View>
      ))}
    </>
  );
}

function ServicesAdmin() {
  const { colors } = useTheme();
  const [rows, setRows] = useState<any[]>([]);
  const [cats, setCats] = useState<any[]>([]);
  const [f, setF] = useState({ name: "", category_id: "", description: "", base_price: "", duration_minutes: "60", image_url: "" });
  const load = useCallback(async () => {
    const [s, c] = await Promise.all([api.get("/services"), api.get("/categories")]);
    setRows(s.data); setCats(c.data);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const create = async () => {
    try {
      await api.post("/admin/services", { ...f, base_price: parseFloat(f.base_price), duration_minutes: parseInt(f.duration_minutes) || 60, active: true });
      setF({ name: "", category_id: "", description: "", base_price: "", duration_minutes: "60", image_url: "" });
      await load();
    } catch (e: any) { alert(errMsg(e)); }
  };
  const del = async (id: string) => { await api.delete(`/admin/services/${id}`); await load(); };

  return (
    <>
      <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
        <Text style={{ color: colors.onSurface, fontWeight: "700", marginBottom: spacing.sm }}>Add Service</Text>
        <Input label="Name" value={f.name} onChangeText={(v) => setF({ ...f, name: v })} testID="svc-name" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, marginBottom: spacing.md }}>
          {cats.map((c) => (
            <Pressable key={c.id} testID={`svc-cat-${c.id}`} onPress={() => setF({ ...f, category_id: c.id })} style={{ flexShrink: 0, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: f.category_id === c.id ? colors.brandPrimary : colors.surfaceTertiary }}>
              <Text style={{ color: f.category_id === c.id ? colors.onBrandPrimary : colors.onSurfaceTertiary, fontWeight: "600" }}>{c.name}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <Input label="Description" value={f.description} onChangeText={(v) => setF({ ...f, description: v })} multiline testID="svc-desc" />
        <Input label="Base Price (₹)" value={f.base_price} onChangeText={(v) => setF({ ...f, base_price: v })} keyboardType="numeric" testID="svc-price" />
        <Input label="Duration (min)" value={f.duration_minutes} onChangeText={(v) => setF({ ...f, duration_minutes: v })} keyboardType="number-pad" testID="svc-duration" />
        <Input label="Image URL" value={f.image_url} onChangeText={(v) => setF({ ...f, image_url: v })} autoCapitalize="none" testID="svc-image" />
        <Button label="Create Service" onPress={create} testID="svc-create" />
      </View>
      {rows.map((s) => (
        <View key={s.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, flexDirection: "row", alignItems: "center", gap: spacing.md }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{s.name}</Text>
            <Text style={{ color: colors.muted, fontSize: 12 }}>{s.category_name} · ₹{s.base_price}</Text>
          </View>
          <Pressable onPress={() => del(s.id)} testID={`svc-del-${s.id}`}><Text style={{ color: colors.error, fontWeight: "600" }}>Delete</Text></Pressable>
        </View>
      ))}
    </>
  );
}

function ProvidersAdmin() {
  const { colors } = useTheme();
  const [apps, setApps] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const load = useCallback(async () => {
    const [a, p] = await Promise.all([api.get("/admin/providers/applications"), api.get("/admin/providers")]);
    setApps(a.data); setProviders(p.data);
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const approve = async (id: string) => { await api.post(`/admin/providers/${id}/approve`); await load(); };
  return (
    <>
      <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Pending Applications</Text>
      {apps.length === 0 && <Text style={{ color: colors.muted }}>No pending applications.</Text>}
      {apps.map((a) => (
        <View key={a.id} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{a.user?.name || a.user_id}</Text>
          <Text style={{ color: colors.muted }}>{a.user?.mobile}</Text>
          <Text style={{ color: colors.onSurfaceSecondary, marginTop: 4 }}>Skills: {a.skills.join(", ") || "—"}</Text>
          <Text style={{ color: colors.onSurfaceSecondary }}>Areas: {a.service_areas.join(", ") || "—"}</Text>
          <Text style={{ color: colors.onSurfaceSecondary }}>Experience: {a.experience_years} yrs</Text>
          <View style={{ marginTop: spacing.md }}>
            <Button label="Approve" onPress={() => approve(a.id)} testID={`admin-approve-${a.id}`} />
          </View>
        </View>
      ))}
      <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: spacing.lg }}>Approved Providers</Text>
      {providers.map((p) => (
        <View key={p.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
          <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{p.name || p.username}</Text>
          <Text style={{ color: colors.muted }}>{p.mobile}</Text>
        </View>
      ))}
    </>
  );
}

function CouponsAdmin() {
  const { colors } = useTheme();
  const [rows, setRows] = useState<any[]>([]);
  const [f, setF] = useState({ code: "", discount_percent: "", max_discount: "", description: "" });
  const load = useCallback(async () => setRows((await api.get("/coupons")).data), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));
  const create = async () => {
    try {
      await api.post("/admin/coupons", { code: f.code.toUpperCase(), discount_percent: parseFloat(f.discount_percent), max_discount: f.max_discount ? parseFloat(f.max_discount) : null, description: f.description, active: true });
      setF({ code: "", discount_percent: "", max_discount: "", description: "" });
      await load();
    } catch (e: any) { alert(errMsg(e)); }
  };
  const del = async (id: string) => { await api.delete(`/admin/coupons/${id}`); await load(); };
  return (
    <>
      <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
        <Text style={{ color: colors.onSurface, fontWeight: "700", marginBottom: spacing.sm }}>New Coupon</Text>
        <Input label="Code" value={f.code} onChangeText={(v) => setF({ ...f, code: v.toUpperCase() })} autoCapitalize="characters" testID="cp-code" />
        <Input label="Discount %" value={f.discount_percent} onChangeText={(v) => setF({ ...f, discount_percent: v })} keyboardType="numeric" testID="cp-percent" />
        <Input label="Max Discount (₹)" value={f.max_discount} onChangeText={(v) => setF({ ...f, max_discount: v })} keyboardType="numeric" testID="cp-max" />
        <Input label="Description" value={f.description} onChangeText={(v) => setF({ ...f, description: v })} testID="cp-desc" />
        <Button label="Create Coupon" onPress={create} testID="cp-create" />
      </View>
      {rows.map((c) => (
        <View key={c.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: colors.onSurface, fontWeight: "800" }}>{c.code}</Text>
            <Text style={{ color: colors.muted, fontSize: 12 }}>{c.discount_percent}% off · {c.description}</Text>
          </View>
          <Pressable onPress={() => del(c.id)} testID={`cp-del-${c.code}`}><Text style={{ color: colors.error, fontWeight: "600" }}>Delete</Text></Pressable>
        </View>
      ))}
    </>
  );
}

function UsersAdmin() {
  const { colors } = useTheme();
  const [rows, setRows] = useState<any[]>([]);
  useFocusEffect(useCallback(() => { api.get("/admin/users").then((r) => setRows(r.data)); }, []));
  return (
    <>
      {rows.map((u) => (
        <View key={u.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{u.name || u.username}</Text>
            <Text style={{ color: colors.brandPrimary, fontWeight: "600", fontSize: 12 }}>{u.role}</Text>
          </View>
          <Text style={{ color: colors.muted, fontSize: 12 }}>{u.mobile} · {u.email || "no email"}</Text>
        </View>
      ))}
    </>
  );
}
