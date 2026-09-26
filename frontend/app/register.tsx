import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, KeyboardAvoidingView, Platform, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/auth";
import { useTheme, spacing } from "@/src/theme";
import { Button, Input } from "@/src/ui";
import { errMsg } from "@/src/api";
import { Logo } from "@/src/brand";

export default function Register() {
  const { requestOtp, verifyOtp, complete } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [mobile, setMobile] = useState("");
  const [otp, setOtp] = useState("");
  const [flowToken, setFlowToken] = useState("");
  const [devOtp, setDevOtp] = useState<string | undefined>();

  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const sendOtp = async () => {
    setErr(null); setLoading(true);
    try {
      const dev = await requestOtp(mobile.trim());
      setDevOtp(dev);
      setStep(2);
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  const verify = async () => {
    setErr(null); setLoading(true);
    try {
      const t = await verifyOtp(mobile.trim(), otp.trim());
      setFlowToken(t);
      setStep(3);
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  const finish = async () => {
    setErr(null); setLoading(true);
    try {
      await complete(flowToken, name.trim(), username.trim(), password, email.trim() || undefined);
      router.replace("/");
    } catch (e: any) { setErr(errMsg(e)); }
    finally { setLoading(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ paddingTop: insets.top + 20, paddingHorizontal: spacing.xl, paddingBottom: spacing.xxl }}>
          <Pressable onPress={() => router.back()} testID="register-back-button" style={{ paddingVertical: spacing.sm }}>
            <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>‹ Back</Text>
          </Pressable>
          <View style={{ alignItems: "center", marginTop: spacing.sm, marginBottom: spacing.md }}>
            <Logo size="lg" />
          </View>
          <Text style={[styles.title, { color: colors.onSurface }]}>Create your account</Text>
          <Text style={{ color: colors.muted, marginBottom: spacing.xl }}>Step {step} of 3</Text>

          {step === 1 && (
            <>
              <Input label="Mobile number" value={mobile} onChangeText={setMobile} placeholder="10-digit or +91XXXXXXXXXX" keyboardType="phone-pad" testID="register-mobile-input" />
              {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
              <Button label="Send OTP" onPress={sendOtp} loading={loading} testID="register-send-otp-button" />
              <Text style={{ color: colors.muted, marginTop: spacing.md, fontSize: 12 }}>We&apos;ll verify your mobile once. After this, no OTP is needed to log in.</Text>
            </>
          )}
          {step === 2 && (
            <>
              <Input label="Enter OTP" value={otp} onChangeText={setOtp} placeholder="6-digit code" keyboardType="number-pad" testID="register-otp-input" />
              {devOtp && (
                <Text testID="register-dev-otp-hint" style={{ color: colors.warning, marginBottom: spacing.md }}>
                  DEV MOCK — use OTP: {devOtp}
                </Text>
              )}
              {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
              <Button label="Verify OTP" onPress={verify} loading={loading} testID="register-verify-otp-button" />
            </>
          )}
          {step === 3 && (
            <>
              <Input label="Full Name" value={name} onChangeText={setName} placeholder="Your name" testID="register-name-input" />
              <Input label="Username" value={username} onChangeText={setUsername} placeholder="letters, digits, _" autoCapitalize="none" testID="register-username-input" />
              <Input label="Email (optional but recommended)" value={email} onChangeText={setEmail} placeholder="you@example.com" keyboardType="email-address" autoCapitalize="none" testID="register-email-input" />
              <Input label="Password" value={password} onChangeText={setPassword} placeholder="min 6 characters" secureTextEntry testID="register-password-input" />
              {err && <Text style={{ color: colors.error, marginBottom: spacing.md }}>{err}</Text>}
              <Button label="Create Account" onPress={finish} loading={loading} testID="register-complete-button" />
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}
const styles = StyleSheet.create({ title: { fontSize: 26, fontWeight: "800", marginTop: spacing.sm } });
