import { useState } from "react";
import { View, Text, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { api, errMsg } from "@/src/api";
import { useTheme, spacing } from "@/src/theme";
import { Button, Input } from "@/src/ui";

export default function ProviderApply() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [skills, setSkills] = useState("");
  const [areas, setAreas] = useState("");
  const [years, setYears] = useState("0");
  const [bio, setBio] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await api.post("/providers/apply", {
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        service_areas: areas.split(",").map((s) => s.trim()).filter(Boolean),
        experience_years: parseInt(years) || 0, bio,
      });
      setMsg("Application submitted. An admin will review your account shortly.");
    } catch (e: any) { setErr(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.xl, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider }}>
        <Pressable onPress={() => router.back()} testID="apply-back"><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text></Pressable>
        <Text style={{ color: colors.onSurface, fontSize: 22, fontWeight: "800", marginTop: spacing.sm }}>Become a Provider</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.xl }}>
        <Text style={{ color: colors.muted, marginBottom: spacing.lg }}>Apply to offer your services on SmartFix. Admin will review and approve.</Text>
        <Input label="Skills (comma separated)" value={skills} onChangeText={setSkills} placeholder="AC repair, Wiring" testID="apply-skills" />
        <Input label="Service Areas (comma separated)" value={areas} onChangeText={setAreas} placeholder="Bangalore, Mysore" testID="apply-areas" />
        <Input label="Experience (years)" value={years} onChangeText={setYears} keyboardType="number-pad" testID="apply-years" />
        <Input label="About you" value={bio} onChangeText={setBio} multiline testID="apply-bio" />
        {msg && <Text style={{ color: colors.success, marginBottom: spacing.md }} testID="apply-success">{msg}</Text>}
        {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
        <Button label="Submit Application" onPress={submit} loading={busy} testID="apply-submit" />
      </ScrollView>
    </View>
  );
}
