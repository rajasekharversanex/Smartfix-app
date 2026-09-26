import { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, StyleSheet } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import axios from "axios";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button } from "@/src/ui";
import { Logo } from "@/src/brand";

// Public quotation page — a customer without the SmartFix app can open
// /quote/<token> in any browser, view the quotation, and Accept / Reject / Ask
// for clarification. No login. The API validates the token server-side.
const BASE = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/$/, "") + "/api";

export default function PublicQuotation() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const r = await axios.get(`${BASE}/public/quotations/${token}`);
      setQ(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Quotation not found");
    }
  }, [token]);
  useEffect(() => { load(); }, [load]);

  const respond = async (decision: "ACCEPT" | "REJECT" | "CLARIFY") => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(`${BASE}/public/quotations/${token}/respond`, { decision });
      setDone(r.data.status);
      await load();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Could not submit response");
    } finally { setBusy(false); }
  };

  if (!q && !err) return <View style={[styles.center, { backgroundColor: colors.bg }]}><ActivityIndicator /></View>;
  if (err && !q) return (
    <View style={[styles.center, { backgroundColor: colors.bg, padding: spacing.lg }]}>
      <Logo size="md" />
      <Text style={{ color: colors.error, marginTop: spacing.md, textAlign: "center" }}>{err}</Text>
    </View>
  );

  const isFinal = ["ACCEPTED", "REJECTED", "EXPIRED", "CANCELLED"].includes(q.status);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl }}>
        <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
          <Logo size="lg" />
          <Text style={{ color: colors.muted, fontSize: 12, marginTop: 6, letterSpacing: 0.5 }}>QUOTATION</Text>
        </View>

        <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg }}>
          <Text style={{ color: colors.muted, fontSize: 12 }}>Quotation No.</Text>
          <Text testID="q-number" style={{ color: colors.onSurface, fontSize: 18, fontWeight: "800" }}>{q.quotation_no}</Text>
          <View style={{ height: spacing.md }} />
          <Text style={{ color: colors.muted, fontSize: 12 }}>Service Description</Text>
          <Text style={{ color: colors.onSurface, marginTop: 2 }}>{q.service_description}</Text>
          {q.technician_notes ? (
            <>
              <View style={{ height: spacing.md }} />
              <Text style={{ color: colors.muted, fontSize: 12 }}>Technician notes</Text>
              <Text style={{ color: colors.onSurface, marginTop: 2 }}>{q.technician_notes}</Text>
            </>
          ) : null}
        </View>

        <View style={{ height: spacing.md }} />
        <View style={{ backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg }}>
          <Text style={{ color: colors.onSurface, fontWeight: "800", marginBottom: spacing.sm }}>Items</Text>
          {q.items.map((it: any, i: number) => (
            <View key={i} style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 }}>
              <Text style={{ color: colors.onSurface, flex: 1 }}>{it.description}  <Text style={{ color: colors.muted, fontSize: 12 }}>× {it.qty}</Text></Text>
              <Text style={{ color: colors.onSurface }}>₹{(it.qty * it.unit_price).toFixed(2)}</Text>
            </View>
          ))}
          <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm }} />
          <Row label="Parts" value={`₹${q.parts_charge.toFixed(2)}`} c={colors} />
          <Row label="Labour" value={`₹${q.labour_charge.toFixed(2)}`} c={colors} />
          {q.discount > 0 && <Row label="Discount" value={`- ₹${q.discount.toFixed(2)}`} c={colors} />}
          <Row label={`Tax (${q.tax_percent}%)`} value={`₹${q.tax.toFixed(2)}`} c={colors} />
          <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.sm }} />
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={{ color: colors.onSurface, fontWeight: "800", fontSize: 16 }}>Total</Text>
            <Text testID="q-total" style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 20 }}>₹{q.total.toFixed(2)}</Text>
          </View>
          <Text style={{ color: colors.muted, fontSize: 12, marginTop: spacing.sm }}>Valid until {new Date(q.valid_until).toLocaleString()}</Text>
        </View>

        <View style={{ height: spacing.xl }} />
        {isFinal ? (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 2, borderColor: q.status === "ACCEPTED" ? colors.success : colors.error, alignItems: "center" }}>
            <Text testID="q-status" style={{ color: q.status === "ACCEPTED" ? colors.success : colors.error, fontSize: 18, fontWeight: "800" }}>{q.status}</Text>
            <Text style={{ color: colors.muted, fontSize: 12, marginTop: 4 }}>Thank you. SmartFix Services will follow up shortly.</Text>
          </View>
        ) : (
          <>
            <Button label={`Accept quotation · ₹${q.total.toFixed(2)}`} onPress={() => respond("ACCEPT")} loading={busy} testID="q-accept" />
            <View style={{ height: spacing.sm }} />
            <Button label="Reject" variant="ghost" onPress={() => respond("REJECT")} loading={busy} testID="q-reject" />
            <View style={{ height: spacing.sm }} />
            <Pressable onPress={() => respond("CLARIFY")} testID="q-clarify" style={{ padding: spacing.md, alignItems: "center" }}>
              <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Request clarification</Text>
            </Pressable>
          </>
        )}
        {err && <Text style={{ color: colors.error, marginTop: spacing.md, textAlign: "center" }}>{err}</Text>}
        {done && !isFinal && <Text style={{ color: colors.success, marginTop: spacing.md, textAlign: "center" }}>Response submitted.</Text>}

        <Text style={{ color: colors.muted, textAlign: "center", marginTop: spacing.xl, fontSize: 11 }}>SmartFix Services · by Versanex India</Text>
      </ScrollView>
    </View>
  );
}

function Row({ label, value, c }: { label: string; value: string; c: any }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 3 }}>
      <Text style={{ color: c.muted }}>{label}</Text>
      <Text style={{ color: c.onSurface }}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({ center: { flex: 1, alignItems: "center", justifyContent: "center" } });
