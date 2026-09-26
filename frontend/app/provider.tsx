import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useTheme, spacing, radius } from "@/src/theme";
import { StatusPill } from "@/src/ui";

export default function ProviderDashboard() {
  const { user, logout } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { setRows((await api.get("/bookings")).data); } finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const stats = {
    active: rows.filter((r) => ["ACCEPTED", "ON_THE_WAY", "IN_PROGRESS"].includes(r.status)).length,
    completed: rows.filter((r) => r.status === "COMPLETED").length,
    earnings: rows.filter((r) => r.status === "COMPLETED").reduce((s, r) => s + (r.total || 0), 0),
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
        <View>
          <Text style={{ color: colors.muted, fontSize: 13 }}>Provider</Text>
          <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800" }}>{user?.name || user?.username}</Text>
        </View>
        <Pressable onPress={async () => { await logout(); router.replace("/login"); }} testID="provider-logout"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Logout</Text></Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md, paddingBottom: spacing.xxxl }}>
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <Kpi label="Active" value={String(stats.active)} />
          <Kpi label="Completed" value={String(stats.completed)} />
          <Kpi label="Earnings" value={`₹${stats.earnings}`} />
        </View>
        <Text style={{ color: colors.onSurface, fontWeight: "700", fontSize: 16, marginTop: spacing.sm }}>My Jobs</Text>
        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : rows.length === 0 ? (
          <Text style={{ color: colors.muted, textAlign: "center", marginTop: spacing.xl }}>No jobs assigned yet.</Text>
        ) : rows.map((b) => (
          <Pressable key={b.id} testID={`prov-booking-${b.id}`} onPress={() => router.push({ pathname: "/booking/[id]", params: { id: b.id } })} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={{ color: colors.onSurface, fontWeight: "700", flex: 1 }} numberOfLines={1}>{b.service_name}</Text>
              <StatusPill status={b.status} />
            </View>
            <Text style={{ color: colors.muted, marginTop: 4, fontSize: 12 }}>{new Date(b.scheduled_at).toLocaleString()}</Text>
            {b.address && <Text style={{ color: colors.onSurfaceSecondary, marginTop: 6, fontSize: 13 }}>{b.address.city} - {b.address.pincode}</Text>}
            <Text style={{ color: colors.brandPrimary, fontWeight: "800", marginTop: 6 }}>₹{b.total}</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1, padding: spacing.md, borderRadius: radius.lg, backgroundColor: colors.brandSecondary }}>
      <Text style={{ color: colors.onBrandSecondary, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: colors.brandPrimary, fontSize: 20, fontWeight: "800", marginTop: 4 }}>{value}</Text>
    </View>
  );
}
