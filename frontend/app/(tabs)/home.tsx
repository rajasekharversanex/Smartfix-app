import { useEffect, useState, useCallback } from "react";
import { View, Text, ScrollView, StyleSheet, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { useTheme, spacing, radius } from "@/src/theme";

export default function Home() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cats, setCats] = useState<any[]>([]);
  const [services, setServices] = useState<any[]>([]);
  const [selectedCat, setSelectedCat] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        api.get("/categories"),
        api.get("/services", { params: selectedCat ? { category_id: selectedCat } : {} }),
      ]);
      setCats(c.data);
      setServices(s.data);
    } finally { setLoading(false); setRefreshing(false); }
  }, [selectedCat]);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Text style={{ color: colors.muted, fontSize: 13 }}>Namaste 🙏</Text>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800" }} testID="home-greeting">{user?.name || user?.username}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing.xxxl }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.brandPrimary} />}
      >
        {/* Hero */}
        <View style={{ paddingHorizontal: spacing.xl, paddingTop: spacing.lg }}>
          <View style={{ borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.brandPrimary, padding: spacing.xl }}>
            <Text style={{ color: colors.onBrandPrimary, fontSize: 20, fontWeight: "800" }}>Trusted doorstep experts</Text>
            <Text style={{ color: colors.onBrandPrimary, opacity: 0.9, marginTop: 4 }}>Book AC repair, plumbing, cleaning & more</Text>
            <Pressable
              onPress={() => router.push("/(tabs)/bookings")}
              testID="hero-view-bookings"
              style={{ marginTop: spacing.lg, alignSelf: "flex-start", backgroundColor: colors.onBrandPrimary, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill }}
            >
              <Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>My bookings →</Text>
            </Pressable>
          </View>
        </View>

        {/* Categories chip row */}
        <Text style={{ paddingHorizontal: spacing.xl, marginTop: spacing.xl, fontSize: 16, fontWeight: "700", color: colors.onSurface }}>Categories</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.xl, gap: spacing.sm, paddingVertical: spacing.md }}>
          <Chip label="All" active={!selectedCat} onPress={() => setSelectedCat(null)} testID="chip-all" />
          {cats.map((c) => (
            <Chip key={c.id} label={c.name} active={selectedCat === c.id} onPress={() => setSelectedCat(c.id)} testID={`chip-${c.id}`} />
          ))}
        </ScrollView>

        <Text style={{ paddingHorizontal: spacing.xl, fontSize: 16, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm }}>Popular Services</Text>
        {loading ? (
          <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.brandPrimary} />
        ) : (
          <View style={{ paddingHorizontal: spacing.xl, marginTop: spacing.md, gap: spacing.md }}>
            {services.map((s) => (
              <Pressable
                key={s.id}
                testID={`service-${s.id}`}
                onPress={() => router.push({ pathname: "/service/[id]", params: { id: s.id } })}
                style={({ pressed }) => [styles.svcRow, { backgroundColor: colors.surface, borderColor: colors.border, opacity: pressed ? 0.9 : 1 }]}
              >
                <Image source={{ uri: s.image_url }} style={styles.svcImg} contentFit="cover" />
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "600" }}>{s.category_name?.toUpperCase()}</Text>
                  <Text style={{ color: colors.onSurface, fontSize: 15, fontWeight: "700", marginTop: 2 }} numberOfLines={2}>{s.name}</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: 6, gap: 6 }}>
                    <Icon name="star" size={12} color={colors.warning} />
                    <Text style={{ color: colors.onSurfaceSecondary, fontSize: 12 }}>{s.rating?.toFixed(1)}</Text>
                    <Text style={{ color: colors.muted, fontSize: 12 }}>· {s.duration_minutes} min</Text>
                  </View>
                  <Text style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 16, marginTop: 6 }}>₹{s.base_price}</Text>
                </View>
              </Pressable>
            ))}
            {services.length === 0 && (
              <Text style={{ color: colors.muted, textAlign: "center", marginTop: spacing.xl }}>No services in this category.</Text>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function Chip({ label, active, onPress, testID }: { label: string; active: boolean; onPress: () => void; testID?: string }) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      style={{
        flexShrink: 0,
        height: 36,
        paddingHorizontal: spacing.lg,
        borderRadius: radius.pill,
        backgroundColor: active ? colors.brandPrimary : colors.surfaceTertiary,
        borderWidth: 1,
        borderColor: active ? colors.brandPrimary : colors.border,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Text style={{ color: active ? colors.onBrandPrimary : colors.onSurfaceTertiary, fontWeight: "600", fontSize: 13 }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  svcRow: { flexDirection: "row", padding: spacing.md, borderRadius: radius.lg, borderWidth: 1 },
  svcImg: { width: 84, height: 84, borderRadius: radius.md, backgroundColor: "#eee" },
});
