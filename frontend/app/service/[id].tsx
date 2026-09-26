import { useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button } from "@/src/ui";

export default function ServiceDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [svc, setSvc] = useState<any>(null);

  useEffect(() => { api.get(`/services/${id}`).then((r) => setSvc(r.data)); }, [id]);
  if (!svc) return <View style={{ flex: 1, backgroundColor: colors.surface }} />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingBottom: 140 }}>
        <View>
          <Image source={{ uri: svc.image_url }} style={{ width: "100%", height: 260 }} />
          <Pressable onPress={() => router.back()} testID="service-back-button" style={{ position: "absolute", top: insets.top + 12, left: spacing.lg, backgroundColor: "rgba(0,0,0,0.4)", width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" }}>
            <Text style={{ color: "#fff", fontSize: 20 }}>‹</Text>
          </Pressable>
        </View>
        <View style={{ padding: spacing.xl }}>
          <Text style={{ color: colors.muted, fontSize: 12, fontWeight: "700" }}>{svc.category_name?.toUpperCase()}</Text>
          <Text style={{ color: colors.onSurface, fontSize: 24, fontWeight: "800", marginTop: 4 }}>{svc.name}</Text>
          <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.md }}>
            <Text style={{ color: colors.warning }}>★ {svc.rating?.toFixed(1)}</Text>
            <Text style={{ color: colors.muted }}>· {svc.duration_minutes} min</Text>
            <Text style={{ color: colors.muted }}>· {svc.bookings_count} bookings</Text>
          </View>
          <Text style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 26, marginTop: spacing.md }}>₹{svc.base_price}</Text>
          <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.lg }} />
          <Text style={{ color: colors.onSurface, fontWeight: "700", marginBottom: 6 }}>About this service</Text>
          <Text style={{ color: colors.onSurfaceSecondary, lineHeight: 22 }}>{svc.description}</Text>

          <View style={{ marginTop: spacing.xl, padding: spacing.lg, backgroundColor: colors.brandSecondary, borderRadius: radius.lg }}>
            <Text style={{ color: colors.onBrandSecondary, fontWeight: "700" }}>✓ Verified professionals</Text>
            <Text style={{ color: colors.onBrandSecondary, marginTop: 4 }}>✓ Transparent pricing — no hidden fees</Text>
            <Text style={{ color: colors.onBrandSecondary, marginTop: 4 }}>✓ Pay via UPI or Cash after service</Text>
          </View>
        </View>
      </ScrollView>
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.lg, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider }}>
        <Button label={`Book Now · ₹${svc.base_price}`} onPress={() => router.push({ pathname: "/book/[id]", params: { id: svc.id } })} testID="service-book-now-button" />
      </View>
    </View>
  );
}
