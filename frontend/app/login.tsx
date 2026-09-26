import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Link, useRouter } from "expo-router";
import { useAuth } from "@/src/auth";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button, Input } from "@/src/ui";
import { errMsg } from "@/src/api";

export default function LoginScreen() {
  const { login } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setErr(null); setLoading(true);
    try {
      await login(identifier.trim(), password);
      router.replace("/");
    } catch (e: any) {
      setErr(errMsg(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ paddingTop: insets.top + 40, paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl }}>
          <View style={styles.brandRow}>
            <View style={[styles.logoBox, { backgroundColor: colors.brandPrimary }]}>
              <Text style={{ color: colors.onBrandPrimary, fontSize: 22, fontWeight: "800" }}>SF</Text>
            </View>
          </View>
          <Text style={[styles.title, { color: colors.onSurface }]}>SmartFix Service</Text>
          <Text style={[styles.sub, { color: colors.muted }]}>by Versanex India · Doorstep experts you can trust</Text>

          <View style={{ marginTop: spacing.xl }}>
            <Input
              label="Username, Email or Mobile"
              value={identifier}
              onChangeText={setIdentifier}
              placeholder="e.g. owner or +919999900001"
              autoCapitalize="none"
              testID="login-identifier-input"
            />
            <Input
              label="Password"
              value={password}
              onChangeText={setPassword}
              placeholder="Enter password"
              secureTextEntry
              testID="login-password-input"
            />
            {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
            <Button label="Log In" onPress={submit} loading={loading} testID="login-submit-button" />
            <Pressable onPress={() => router.push("/forgot-password")} testID="forgot-password-link" style={{ marginTop: spacing.md, alignItems: "center" }}>
              <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Forgot password?</Text>
            </Pressable>
          </View>

          <View style={{ marginTop: spacing.xxl, alignItems: "center" }}>
            <Text style={{ color: colors.muted }}>New to SmartFix?</Text>
            <Link href="/register" asChild>
              <Pressable testID="go-register-button" style={{ marginTop: spacing.sm }}>
                <Text style={{ color: colors.brandPrimary, fontWeight: "700", fontSize: 16 }}>Create an account</Text>
              </Pressable>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  brandRow: { alignItems: "center", marginBottom: spacing.lg },
  logoBox: { width: 64, height: 64, borderRadius: radius.lg, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 28, fontWeight: "800", textAlign: "center" },
  sub: { fontSize: 14, textAlign: "center", marginTop: 6 },
});
