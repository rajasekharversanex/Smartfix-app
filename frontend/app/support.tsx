import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input, StatusPill } from "@/src/ui";

// Simple customer support inbox: file a ticket and see previous ones with
// their support status. Support agents work these from Admin → Support.
export default function Support() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [show, setShow] = useState(false);
  const [subject, setSubject] = useState("");
  const [desc, setDesc] = useState("");
  const [priority, setPriority] = useState<"LOW" | "NORMAL" | "HIGH" | "URGENT">("NORMAL");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.get("/tickets").then((r) => setRows(r.data)).catch(() => {}), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const submit = async () => {
    setBusy(true); setErr(null);
    try { await api.post("/tickets", { subject, description: desc, priority }); setShow(false); setSubject(""); setDesc(""); setPriority("NORMAL"); await load(); }
    catch (e: any) { setErr(errMsg(e)); }
    finally { setBusy(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.xl, paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xl, gap: spacing.md }}>
          <Pressable onPress={() => router.back()} testID="support-back"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
          <Text style={{ color: colors.onSurface, fontSize: 24, fontWeight: "800" }}>Support</Text>
          <Text style={{ color: colors.muted }}>Tell us anything — refunds, complaints, missed technicians. We&apos;ll get back within one working day.</Text>
          <Button label={show ? "Cancel" : "+ New ticket"} variant={show ? "ghost" : "primary"} onPress={() => setShow((v) => !v)} testID="support-new" />
          {show && (
            <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm }}>
              <Input label="Subject" value={subject} onChangeText={setSubject} testID="ticket-subject" />
              <Input label="Description" value={desc} onChangeText={setDesc} multiline numberOfLines={4} style={{ minHeight: 100 }} testID="ticket-desc" />
              <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
                {(["LOW", "NORMAL", "HIGH", "URGENT"] as const).map((p) => (
                  <Pressable key={p} onPress={() => setPriority(p)} testID={`ticket-p-${p}`} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: priority === p ? colors.brandPrimary : colors.border, backgroundColor: priority === p ? colors.brandSecondary : "transparent" }}>
                    <Text style={{ color: priority === p ? colors.onBrandSecondary : colors.onSurface, fontSize: 12, fontWeight: "600" }}>{p}</Text>
                  </Pressable>
                ))}
              </View>
              <Button label="Submit ticket" onPress={submit} loading={busy} testID="ticket-submit" />
              {err && <Text style={{ color: colors.error }}>{err}</Text>}
            </View>
          )}
          <Text style={{ color: colors.onSurface, fontWeight: "700", marginTop: spacing.md }}>My tickets</Text>
          {rows.length === 0 ? (
            <Text style={{ color: colors.muted }}>No tickets yet.</Text>
          ) : rows.map((t) => (
            <View key={t.id} style={{ padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Text style={{ color: colors.onSurface, fontWeight: "700", flex: 1 }} numberOfLines={1}>{t.subject}</Text>
                <StatusPill status={t.status} />
              </View>
              <Text style={{ color: colors.muted, fontSize: 12, marginTop: 4 }}>{t.priority} · {new Date(t.created_at).toLocaleString()}</Text>
              <Text style={{ color: colors.onSurfaceSecondary, marginTop: 6 }} numberOfLines={3}>{t.description}</Text>
            </View>
          ))}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}
