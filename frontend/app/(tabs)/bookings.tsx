import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, RefreshControl, ActivityIndicator } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { StatusPill } from "@/src/ui";

export default function Bookings() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/bookings");
      setRows(r.data);
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800" }}>My Bookings</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: spacing.xl, paddingBottom: spacing.xxxl, gap: spacing.md }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}
      >
        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : rows.length === 0 ? (
          <Text style={{ color: colors.muted, textAlign: "center", marginTop: spacing.xxl }} testID="bookings-empty">
            No bookings yet. Book a service from Home.
          </Text>
        ) : rows.map((b) => (
          <Pressable
            key={b.id}
            testID={`booking-${b.id}`}
            onPress={() => router.push({ pathname: "/booking/[id]", params: { id: b.id } })}
            style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}
          >
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
              <Text style={{ color: colors.onSurface, fontWeight: "700", fontSize: 15, flex: 1 }} numberOfLines={1}>{b.service_name}</Text>
              <StatusPill status={b.status} />
            </View>
            <Text style={{ color: colors.muted, marginTop: 4, fontSize: 12 }}>
              {new Date(b.scheduled_at).toLocaleString()}
            </Text>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.md }}>
              <Text style={{ color: colors.onSurfaceSecondary, fontSize: 13 }}>{b.payment_method} · {b.payment_status}</Text>
              <Text style={{ color: colors.brandPrimary, fontWeight: "800" }}>₹{b.total}</Text>
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}
