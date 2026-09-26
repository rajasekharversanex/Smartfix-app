import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, Linking } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input, StatusPill } from "@/src/ui";
import { useAuth } from "@/src/auth";

const STEPS = ["PENDING", "ACCEPTED", "ON_THE_WAY", "IN_PROGRESS", "COMPLETED"];

export default function BookingDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [b, setB] = useState<any>(null);
  const [txn, setTxn] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await api.get(`/bookings/${id}`);
    setB(r.data);
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const cancel = async () => {
    setBusy(true); setErr(null);
    try { await api.patch(`/bookings/${id}/status`, { status: "CANCELLED" }); await load(); }
    catch (e: any) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  const providerAdvance = async (next: string) => {
    setBusy(true); setErr(null);
    try { await api.patch(`/bookings/${id}/status`, { status: next }); await load(); }
    catch (e: any) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  const payUpi = async () => {
    if (!b) return;
    const upiId = "smartfix@upi";
    const url = `upi://pay?pa=${encodeURIComponent(upiId)}&pn=${encodeURIComponent("SmartFix Service")}&am=${b.total}&cu=INR&tn=${encodeURIComponent(`Booking ${b.id.slice(0,8)}`)}`;
    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) await Linking.openURL(url);
      else setErr("No UPI app found. Please install GPay/PhonePe/Paytm or pay by cash.");
    } catch (e: any) { setErr(errMsg(e)); }
  };

  const confirmTxn = async () => {
    if (!txn.trim()) { setErr("Enter your UPI transaction reference"); return; }
    setBusy(true); setErr(null);
    try { await api.post(`/bookings/${id}/upi-confirm`, { txn_ref: txn.trim() }); await load(); setTxn(""); }
    catch (e: any) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  if (!b) return <View style={{ flex: 1, backgroundColor: colors.surface }}><ActivityIndicator style={{ marginTop: 100 }} color={colors.brandPrimary} /></View>;

  const idx = STEPS.indexOf(b.status);
  const isCustomer = user?.role === "CUSTOMER";
  const isProvider = user?.role === "PROVIDER" && b.provider_id === user.id;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Pressable onPress={() => router.back()} testID="booking-back-button"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800", marginTop: spacing.sm }}>Booking Details</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md, paddingBottom: 120 }}>
        <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: colors.onSurface, fontSize: 18, fontWeight: "800", flex: 1 }}>{b.service_name}</Text>
            <StatusPill status={b.status} />
          </View>
          <Text style={{ color: colors.muted, marginTop: 4 }}>Scheduled: {new Date(b.scheduled_at).toLocaleString()}</Text>
          <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.md }} />
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={{ color: colors.onSurfaceSecondary }}>Amount</Text>
            <Text style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 18 }}>₹{b.total}</Text>
          </View>
          <Text style={{ color: colors.muted, marginTop: 4 }}>Payment: {b.payment_method} · <StatusPillInline status={b.payment_status} /></Text>
        </View>

        {b.status !== "CANCELLED" && (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ color: colors.onSurface, fontWeight: "700", marginBottom: spacing.md }}>Progress</Text>
            {STEPS.map((s, i) => {
              const done = i <= idx;
              const active = i === idx;
              return (
                <View key={s} style={{ flexDirection: "row", alignItems: "center", marginBottom: 12 }}>
                  <View style={{ width: 22, height: 22, borderRadius: 11, backgroundColor: done ? colors.brandPrimary : colors.surfaceTertiary, alignItems: "center", justifyContent: "center", marginRight: spacing.md }}>
                    <Text style={{ color: done ? colors.onBrandPrimary : colors.muted, fontSize: 12, fontWeight: "700" }}>{i + 1}</Text>
                  </View>
                  <Text style={{ color: active ? colors.brandPrimary : done ? colors.onSurface : colors.muted, fontWeight: active ? "700" : "500" }}>{s.replace(/_/g, " ")}</Text>
                </View>
              );
            })}
          </View>
        )}

        {b.provider && (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ color: colors.muted, fontSize: 12 }}>Assigned professional</Text>
            <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: 4 }}>{b.provider.name}</Text>
            <Text style={{ color: colors.muted }}>{b.provider.mobile}</Text>
          </View>
        )}

        {b.address && (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
            <Text style={{ color: colors.muted, fontSize: 12 }}>Service address</Text>
            <Text style={{ color: colors.onSurface, marginTop: 4 }}>{b.address.label} · {b.address.line1}{b.address.line2 ? `, ${b.address.line2}` : ""}, {b.address.city} - {b.address.pincode}</Text>
          </View>
        )}

        {err && <Text style={{ color: colors.error }}>{err}</Text>}

        {/* Customer UPI payment section */}
        {isCustomer && b.payment_method === "UPI" && b.payment_status === "PENDING" && b.status !== "CANCELLED" && (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.brandSecondary }}>
            <Text style={{ color: colors.onBrandSecondary, fontWeight: "700", marginBottom: spacing.sm }}>Pay via UPI</Text>
            <Button label={`Open UPI App · ₹${b.total}`} onPress={payUpi} testID="pay-upi-button" />
            <View style={{ height: spacing.md }} />
            <Input label="UPI Transaction Reference" value={txn} onChangeText={setTxn} placeholder="12-digit UTR" testID="pay-upi-txn-input" />
            <Button label="Submit for Verification" variant="secondary" onPress={confirmTxn} loading={busy} testID="pay-upi-submit" />
          </View>
        )}
        {isCustomer && b.payment_status === "AWAITING_VERIFICATION" && (
          <Text style={{ color: colors.warning, textAlign: "center" }}>Your UPI txn ({b.upi_txn_ref}) is awaiting admin verification.</Text>
        )}

        {/* Provider actions */}
        {isProvider && b.status !== "COMPLETED" && b.status !== "CANCELLED" && (
          <View style={{ gap: spacing.sm }}>
            {b.status === "PENDING" && <Button label="Accept Job" onPress={() => providerAdvance("ACCEPTED")} loading={busy} testID="prov-accept" />}
            {b.status === "ACCEPTED" && <Button label="On the way" onPress={() => providerAdvance("ON_THE_WAY")} loading={busy} testID="prov-otw" />}
            {b.status === "ON_THE_WAY" && <Button label="Start Service" onPress={() => providerAdvance("IN_PROGRESS")} loading={busy} testID="prov-start" />}
            {b.status === "IN_PROGRESS" && <Button label="Mark Completed" onPress={() => providerAdvance("COMPLETED")} loading={busy} testID="prov-complete" />}
          </View>
        )}

        {/* Cancel */}
        {isCustomer && b.status === "PENDING" && (
          <Button label="Cancel Booking" variant="danger" onPress={cancel} loading={busy} testID="booking-cancel-button" />
        )}
      </ScrollView>
    </View>
  );
}

function StatusPillInline({ status }: { status: string }) {
  return <Text>{status}</Text>;
}
