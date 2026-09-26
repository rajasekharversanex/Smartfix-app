import { useState } from "react";
import { View, Text, ScrollView, KeyboardAvoidingView, Platform, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/auth";
import { useTheme, spacing } from "@/src/theme";
import { Button, Input } from "@/src/ui";
import { errMsg } from "@/src/api";

export default function Forgot() {
  const { forgot, reset } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [channel, setChannel] = useState<"email" | "mobile" | null>(null);
  const [resetToken, setResetToken] = useState("");
  const [devOtp, setDevOtp] = useState<string | undefined>();
  const [otp, setOtp] = useState("");
  const [newPass, setNewPass] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const request = async () => {
    setErr(null); setLoading(true);
    try {
      const r = await forgot(identifier.trim());
      setChannel(r.channel);
      setResetToken(r.reset_token || "");
      setDevOtp(r.dev_otp);
      setMsg(r.message);
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  const doReset = async () => {
    setErr(null); setLoading(true);
    try {
      await reset(resetToken, newPass, channel === "mobile" ? otp : undefined);
      router.replace("/login");
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ paddingTop: insets.top + 20, paddingHorizontal: spacing.xl }}>
          <Pressable onPress={() => router.back()} testID="forgot-back-button" style={{ paddingVertical: spacing.sm }}>
            <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text>
          </Pressable>
          <Text style={{ fontSize: 26, fontWeight: "800", color: colors.onSurface, marginTop: spacing.sm }}>Reset password</Text>
          <Text style={{ color: colors.muted, marginBottom: spacing.xl }}>Email recovery is preferred. Mobile OTP is a fallback.</Text>

          {!channel && (
            <>
              <Input label="Email, username or mobile" value={identifier} onChangeText={setIdentifier} placeholder="you@example.com" autoCapitalize="none" testID="forgot-identifier-input" />
              {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
              <Button label="Send Reset Instructions" onPress={request} loading={loading} testID="forgot-request-button" />
            </>
          )}
          {channel && (
            <>
              {msg && <Text testID="forgot-message" style={{ color: colors.success, marginBottom: spacing.md }}>{msg}</Text>}
              {channel === "mobile" && (
                <Input label="OTP received on mobile" value={otp} onChangeText={setOtp} keyboardType="number-pad" testID="forgot-otp-input" />
              )}
              {devOtp && <Text testID="forgot-dev-hint" style={{ color: colors.warning, marginBottom: spacing.md }}>DEV MOCK OTP: {devOtp}</Text>}
              <Input label="New Password" value={newPass} onChangeText={setNewPass} secureTextEntry placeholder="min 6 characters" testID="forgot-new-password-input" />
              {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
              <Button label="Reset Password" onPress={doReset} loading={loading} testID="forgot-reset-button" />
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}
