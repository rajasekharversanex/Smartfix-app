import { useEffect, useState } from "react";
import { View, Text, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";

export default function Offers() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => { api.get("/coupons").then((r) => setRows(r.data)); }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800" }}>Offers & Coupons</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md }}>
        {rows.map((c) => (
          <View key={c.id} testID={`coupon-${c.code}`} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderStyle: "dashed", borderColor: colors.brandPrimary, backgroundColor: colors.brandSecondary }}>
            <Text style={{ color: colors.onBrandSecondary, fontWeight: "800", fontSize: 18 }}>{c.code}</Text>
            <Text style={{ color: colors.onSurfaceSecondary, marginTop: 4 }}>{c.description}</Text>
            <Text style={{ color: colors.brandPrimary, marginTop: 8, fontWeight: "600" }}>{c.discount_percent}% off {c.max_discount ? `(max ₹${c.max_discount})` : ""}</Text>
          </View>
        ))}
        {rows.length === 0 && <Text style={{ color: colors.muted, textAlign: "center" }}>No offers right now.</Text>}
      </ScrollView>
    </View>
  );
}
