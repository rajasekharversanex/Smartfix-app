import { useCallback, useEffect, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input, Card } from "@/src/ui";

export default function BookFlow() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const [svc, setSvc] = useState<any>(null);
  const [addresses, setAddresses] = useState<any[]>([]);
  const [selectedAddr, setSelectedAddr] = useState<string | null>(null);
  const [when, setWhen] = useState<Date>(() => { const d = new Date(); d.setHours(d.getHours() + 2, 0, 0, 0); return d; });
  const [payment, setPayment] = useState<"CASH" | "UPI">("CASH");
  const [notes, setNotes] = useState("");
  const [coupon, setCoupon] = useState("");
  const [discount, setDiscount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [s, a] = await Promise.all([api.get(`/services/${id}`), api.get("/addresses")]);
    setSvc(s.data); setAddresses(a.data);
    if (a.data.length) setSelectedAddr(a.data[0].id);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const applyCoupon = async () => {
    setErr(null);
    try {
      const r = await api.get("/coupons/validate", { params: { code: coupon.trim().toUpperCase(), amount: svc.base_price } });
      setDiscount(r.data.discount);
    } catch (e: any) { setErr(errMsg(e)); setDiscount(0); }
  };

  const timeSlots = [0, 2, 4, 6, 24].map((offset) => {
    const d = new Date(); d.setHours(d.getHours() + Math.max(1, offset || 1), 0, 0, 0);
    return d;
  });

  const submit = async () => {
    if (!selectedAddr) { setErr("Please select an address"); return; }
    setLoading(true); setErr(null);
    try {
      const r = await api.post("/bookings", {
        service_id: id, address_id: selectedAddr, scheduled_at: when.toISOString(),
        notes, payment_method: payment, coupon_code: coupon.trim() || undefined,
      });
      router.replace({ pathname: "/booking/[id]", params: { id: r.data.id } });
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  if (!svc) return <View style={{ flex: 1, backgroundColor: colors.surface }}><ActivityIndicator style={{ marginTop: 100 }} color={colors.brandPrimary} /></View>;

  const total = Math.max(0, svc.base_price - discount);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Pressable onPress={() => router.back()} testID="book-back-button"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800", marginTop: spacing.sm }}>Confirm booking</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingBottom: 160, gap: spacing.md }}>
        <Card><Text style={{ color: colors.onSurface, fontWeight: "700" }}>{svc.name}</Text><Text style={{ color: colors.muted, marginTop: 4 }}>{svc.category_name} · {svc.duration_minutes} min</Text></Card>

        <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: spacing.sm }}>Address</Text>
        {addresses.length === 0 ? (
          <Pressable onPress={() => router.push("/addresses")} testID="book-add-address" style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, alignItems: "center" }}>
            <Text style={{ color: colors.brandPrimary, fontWeight: "700" }}>+ Add Address</Text>
          </Pressable>
        ) : addresses.map((a) => (
          <Pressable key={a.id} testID={`book-addr-${a.id}`} onPress={() => setSelectedAddr(a.id)} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 2, borderColor: selectedAddr === a.id ? colors.brandPrimary : colors.border, backgroundColor: colors.surface }}>
            <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{a.label}</Text>
            <Text style={{ color: colors.onSurfaceSecondary, marginTop: 2 }}>{a.line1}{a.line2 ? `, ${a.line2}` : ""}, {a.city} - {a.pincode}</Text>
          </Pressable>
        ))}

        <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: spacing.sm }}>Time Slot</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {timeSlots.map((d, i) => (
            <Pressable key={i} testID={`book-slot-${i}`} onPress={() => setWhen(d)} style={{ flexShrink: 0, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: when.getTime() === d.getTime() ? colors.brandPrimary : colors.border, backgroundColor: when.getTime() === d.getTime() ? colors.brandPrimary : colors.surface }}>
              <Text style={{ color: when.getTime() === d.getTime() ? colors.onBrandPrimary : colors.onSurface, fontWeight: "600" }}>{d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" })}</Text>
            </Pressable>
          ))}
        </ScrollView>

        <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: spacing.sm }}>Payment</Text>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {(["CASH", "UPI"] as const).map((m) => (
            <Pressable key={m} testID={`book-pay-${m}`} onPress={() => setPayment(m)} style={{ flex: 1, padding: spacing.md, borderRadius: radius.md, borderWidth: 2, borderColor: payment === m ? colors.brandPrimary : colors.border, alignItems: "center", backgroundColor: payment === m ? colors.brandSecondary : colors.surface }}>
              <Text style={{ color: payment === m ? colors.onBrandSecondary : colors.onSurface, fontWeight: "700" }}>{m === "CASH" ? "💵 Cash" : "📲 UPI"}</Text>
            </Pressable>
          ))}
        </View>

        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
          <View style={{ flex: 1 }}>
            <Input label="Coupon (optional)" value={coupon} onChangeText={setCoupon} placeholder="SMARTFIX10" autoCapitalize="characters" testID="book-coupon-input" />
          </View>
          <View style={{ marginBottom: spacing.md }}>
            <Button label="Apply" variant="secondary" onPress={applyCoupon} testID="book-apply-coupon" />
          </View>
        </View>
        <Input label="Notes for provider (optional)" value={notes} onChangeText={setNotes} multiline testID="book-notes-input" />

        {err && <Text style={{ color: colors.error }}>{err}</Text>}
      </ScrollView>
      <View style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, paddingBottom: insets.bottom + spacing.lg, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.sm }}>
          <Text style={{ color: colors.muted }}>Total{discount > 0 ? ` (₹${discount} off)` : ""}</Text>
          <Text style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 20 }}>₹{total}</Text>
        </View>
        <Button label="Confirm Booking" onPress={submit} loading={loading} testID="book-confirm-button" />
      </View>
    </View>
  );
}
