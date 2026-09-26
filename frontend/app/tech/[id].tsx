import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, StyleSheet, Linking } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input, StatusPill } from "@/src/ui";
import { Logo } from "@/src/brand";

type Item = { description: string; qty: string; unit_price: string; kind: "PART" | "LABOUR" | "OTHER" };

// Technician job screen: advance status, create a quotation, share via
// WhatsApp/COPY. Also lists this booking's quotations.
export default function TechJob() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [b, setB] = useState<any>(null);
  const [quotes, setQuotes] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showQ, setShowQ] = useState(false);
  const [desc, setDesc] = useState("");
  const [items, setItems] = useState<Item[]>([{ description: "", qty: "1", unit_price: "", kind: "PART" }]);
  const [tax, setTax] = useState("18");
  const [disc, setDisc] = useState("0");
  const [notes, setNotes] = useState("");
  const [lastSend, setLastSend] = useState<{ url: string; message: string; wa: string | null } | null>(null);

  const load = useCallback(async () => {
    try {
      const [bk, qs] = await Promise.all([api.get(`/bookings/${id}`), api.get("/quotations")]);
      setB(bk.data);
      setQuotes(qs.data.filter((q: any) => q.booking_id === id));
    } catch (e: any) { setErr(errMsg(e)); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const advance = async (next: "ACCEPTED" | "ON_THE_WAY" | "IN_PROGRESS" | "COMPLETED") => {
    setBusy(true); setErr(null);
    try {
      await api.patch(`/bookings/${id}/status`, { status: next });
      await load();
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setBusy(false); }
  };

  const addItem = () => setItems([...items, { description: "", qty: "1", unit_price: "", kind: "PART" }]);
  const setItem = (idx: number, k: keyof Item, v: string) => setItems(items.map((it, i) => i === idx ? { ...it, [k]: v } : it));
  const rmItem = (idx: number) => setItems(items.filter((_, i) => i !== idx));

  const submitQuotation = async () => {
    setBusy(true); setErr(null);
    try {
      const payload = {
        booking_id: id,
        service_description: desc,
        items: items
          .filter((it) => it.description && it.qty && it.unit_price)
          .map((it) => ({ description: it.description, qty: Number(it.qty), unit_price: Number(it.unit_price), kind: it.kind })),
        labour_charge: 0,
        tax_percent: Number(tax) || 0,
        discount: Number(disc) || 0,
        valid_days: 3,
        technician_notes: notes,
      };
      if (!payload.service_description || payload.items.length === 0) { setErr("Add a description and at least one item"); setBusy(false); return; }
      const created = await api.post("/quotations", payload);
      const sent = await api.post(`/quotations/${created.data.id}/send`, { channel: "WHATSAPP" });
      setLastSend({ url: sent.data.public_url, message: sent.data.message, wa: sent.data.wa_link });
      setShowQ(false); setDesc(""); setItems([{ description: "", qty: "1", unit_price: "", kind: "PART" }]); setNotes("");
      await load();
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setBusy(false); }
  };

  if (!b) return <View style={styles.center}><ActivityIndicator /></View>;

  const nextByStatus: Record<string, "ACCEPTED" | "ON_THE_WAY" | "IN_PROGRESS" | "COMPLETED" | null> = {
    PENDING: "ACCEPTED", ACCEPTED: "ON_THE_WAY", ON_THE_WAY: "IN_PROGRESS", IN_PROGRESS: "COMPLETED", COMPLETED: null, CANCELLED: null,
  };
  const next = nextByStatus[b.status];
  const nextLabel: Record<string, string> = { ACCEPTED: "Accept job", ON_THE_WAY: "On the way", IN_PROGRESS: "Start service", COMPLETED: "Mark completed" };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Pressable onPress={() => router.back()} testID="tech-back"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
          <Logo size="sm" />
        </View>

        <View style={{ backgroundColor: colors.surface, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: colors.onSurface, fontWeight: "800", fontSize: 18, flex: 1 }} numberOfLines={2}>{b.service_name}</Text>
            <StatusPill status={b.status} />
          </View>
          <Text style={{ color: colors.muted, marginTop: 6, fontSize: 13 }}>{new Date(b.scheduled_at).toLocaleString()}</Text>

          <View style={{ height: 1, backgroundColor: colors.divider, marginVertical: spacing.md }} />
          <Text style={{ color: colors.muted, fontSize: 12 }}>Customer</Text>
          <Text style={{ color: colors.onSurface, marginTop: 2 }}>{b.customer_name || "—"}</Text>
          {b.customer_mobile ? (
            <Pressable testID="tech-call-customer" onPress={() => Linking.openURL(`tel:${b.customer_mobile}`)}><Text style={{ color: colors.brandPrimary, marginTop: 2 }}>{b.customer_mobile}</Text></Pressable>
          ) : null}

          {b.address && (
            <>
              <View style={{ height: spacing.sm }} />
              <Text style={{ color: colors.muted, fontSize: 12 }}>Service address</Text>
              <Text style={{ color: colors.onSurface, marginTop: 2 }}>{b.address.line1}{b.address.line2 ? `, ${b.address.line2}` : ""}, {b.address.city} - {b.address.pincode}</Text>
            </>
          )}

          {b.notes ? (
            <>
              <View style={{ height: spacing.sm }} />
              <Text style={{ color: colors.muted, fontSize: 12 }}>Notes</Text>
              <Text style={{ color: colors.onSurface, marginTop: 2 }}>{b.notes}</Text>
            </>
          ) : null}
          <View style={{ height: spacing.md }} />
          <Text style={{ color: colors.brandPrimary, fontWeight: "800", fontSize: 20 }}>₹{b.total}</Text>
          <Text style={{ color: colors.muted, fontSize: 12 }}>{b.payment_method} · {b.payment_status}</Text>
        </View>

        {next && (
          <Button label={nextLabel[next]} onPress={() => advance(next)} loading={busy} testID={`tech-advance-${next}`} />
        )}

        {b.status !== "CANCELLED" && b.status !== "PENDING" && (
          <Pressable testID="tech-create-quotation" onPress={() => setShowQ((v) => !v)} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderStyle: "dashed", borderColor: colors.brandPrimary, alignItems: "center" }}>
            <Text style={{ color: colors.brandPrimary, fontWeight: "800" }}>{showQ ? "Cancel" : "+ Create Quotation for additional work"}</Text>
          </Pressable>
        )}

        {showQ && (
          <View style={{ backgroundColor: colors.surface, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm }}>
            <Input label="Work description" placeholder="e.g. Compressor replacement" value={desc} onChangeText={setDesc} testID="q-desc" />
            {items.map((it, idx) => (
              <View key={idx} style={{ gap: 6, padding: spacing.sm, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={{ color: colors.muted, fontSize: 12 }}>Item {idx + 1}</Text>
                  {items.length > 1 && <Pressable onPress={() => rmItem(idx)} testID={`q-rm-${idx}`}><Text style={{ color: colors.error, fontSize: 12 }}>Remove</Text></Pressable>}
                </View>
                <Input placeholder="Description" value={it.description} onChangeText={(v) => setItem(idx, "description", v)} testID={`q-item-desc-${idx}`} />
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}><Input placeholder="Qty" value={it.qty} onChangeText={(v) => setItem(idx, "qty", v)} keyboardType="numeric" testID={`q-item-qty-${idx}`} /></View>
                  <View style={{ flex: 1 }}><Input placeholder="₹ per unit" value={it.unit_price} onChangeText={(v) => setItem(idx, "unit_price", v)} keyboardType="numeric" testID={`q-item-price-${idx}`} /></View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  {(["PART", "LABOUR", "OTHER"] as const).map((k) => (
                    <Pressable key={k} onPress={() => setItem(idx, "kind", k)} style={{ flex: 1, padding: 8, alignItems: "center", borderRadius: radius.md, borderWidth: 1, borderColor: it.kind === k ? colors.brandPrimary : colors.border, backgroundColor: it.kind === k ? colors.brandSecondary : "transparent" }}>
                      <Text style={{ color: it.kind === k ? colors.onBrandSecondary : colors.muted, fontSize: 12, fontWeight: "700" }}>{k}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ))}
            <Pressable onPress={addItem} testID="q-add-item"><Text style={{ color: colors.brandPrimary, fontWeight: "700", padding: spacing.sm }}>+ Add another item</Text></Pressable>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 1 }}><Input label="Tax %" value={tax} onChangeText={setTax} keyboardType="numeric" testID="q-tax" /></View>
              <View style={{ flex: 1 }}><Input label="Discount ₹" value={disc} onChangeText={setDisc} keyboardType="numeric" testID="q-disc" /></View>
            </View>
            <Input label="Technician notes (optional)" value={notes} onChangeText={setNotes} testID="q-notes" />
            <Button label="Create & send via WhatsApp" onPress={submitQuotation} loading={busy} testID="q-submit" />
          </View>
        )}

        {lastSend && (
          <View style={{ backgroundColor: colors.surface, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.success }}>
            <Text style={{ color: colors.success, fontWeight: "800" }}>Quotation sent</Text>
            <Text style={{ color: colors.onSurface, marginTop: 6, fontSize: 12 }}>Public link:</Text>
            <Text selectable style={{ color: colors.brandPrimary, marginTop: 2 }}>{lastSend.url}</Text>
            {lastSend.wa && (
              <Button label="Open WhatsApp" onPress={() => Linking.openURL(lastSend.wa!)} testID="q-open-wa" />
            )}
          </View>
        )}

        {quotes.length > 0 && (
          <>
            <Text style={{ color: colors.onSurface, fontWeight: "700", fontSize: 16, marginTop: spacing.sm }}>Quotations for this job</Text>
            {quotes.map((q) => (
              <View key={q.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={{ color: colors.onSurface, fontWeight: "700" }}>{q.quotation_no}</Text>
                  <StatusPill status={q.status} />
                </View>
                <Text style={{ color: colors.muted, marginTop: 4, fontSize: 12 }}>{q.service_description}</Text>
                <Text style={{ color: colors.brandPrimary, fontWeight: "800", marginTop: 4 }}>₹{q.total}</Text>
              </View>
            ))}
          </>
        )}

        {err && <Text style={{ color: colors.error, textAlign: "center" }}>{err}</Text>}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({ center: { flex: 1, alignItems: "center", justifyContent: "center" } });
