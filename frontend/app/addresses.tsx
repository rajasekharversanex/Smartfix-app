import { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input } from "@/src/ui";

export default function Addresses() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [f, setF] = useState({ label: "Home", line1: "", line2: "", city: "", state: "", pincode: "", landmark: "", is_default: false });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => setRows((await api.get("/addresses")).data), []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const save = async () => {
    setErr(null); setBusy(true);
    try { await api.post("/addresses", f); await load(); setShowForm(false); setF({ label: "Home", line1: "", line2: "", city: "", state: "", pincode: "", landmark: "", is_default: false }); }
    catch (e: any) { setErr(errMsg(e)); } finally { setBusy(false); }
  };
  const del = async (id: string) => { await api.delete(`/addresses/${id}`); await load(); };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Pressable onPress={() => router.back()} testID="addresses-back"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800", marginTop: spacing.sm }}>My Addresses</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl, gap: spacing.md, paddingBottom: 120 }}>
        {rows.map((a) => (
          <View key={a.id} style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={{ color: colors.onSurface, fontWeight: "800" }}>{a.label}{a.is_default ? " · Default" : ""}</Text>
              <Pressable onPress={() => del(a.id)} testID={`addr-del-${a.id}`}><Text style={{ color: colors.error }}>Delete</Text></Pressable>
            </View>
            <Text style={{ color: colors.onSurfaceSecondary, marginTop: 4 }}>{a.line1}{a.line2 ? `, ${a.line2}` : ""}</Text>
            <Text style={{ color: colors.muted }}>{a.city} {a.state} - {a.pincode}</Text>
          </View>
        ))}
        {!showForm && <Button label="+ Add New Address" onPress={() => setShowForm(true)} testID="addresses-add-button" />}
        {showForm && (
          <View style={{ padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, gap: 0 }}>
            <Input label="Label (Home/Office/Other)" value={f.label} onChangeText={(v) => setF({ ...f, label: v })} testID="addr-label" />
            <Input label="Address Line 1" value={f.line1} onChangeText={(v) => setF({ ...f, line1: v })} testID="addr-line1" />
            <Input label="Address Line 2 (optional)" value={f.line2} onChangeText={(v) => setF({ ...f, line2: v })} testID="addr-line2" />
            <Input label="City" value={f.city} onChangeText={(v) => setF({ ...f, city: v })} testID="addr-city" />
            <Input label="State" value={f.state} onChangeText={(v) => setF({ ...f, state: v })} testID="addr-state" />
            <Input label="Pincode" value={f.pincode} onChangeText={(v) => setF({ ...f, pincode: v })} keyboardType="number-pad" testID="addr-pincode" />
            {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
            <Button label="Save Address" onPress={save} loading={busy} testID="addr-save" />
          </View>
        )}
      </ScrollView>
    </View>
  );
}
