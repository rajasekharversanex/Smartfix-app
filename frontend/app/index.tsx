import { View, ActivityIndicator, StyleSheet, Text } from "react-native";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/auth";
import { useTheme, spacing } from "@/src/theme";
import { Logo } from "@/src/brand";

export default function Index() {
  const { user, loading } = useAuth();
  const { colors } = useTheme();

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: colors.surface }]}>
        <Logo size="xl" />
        <Text style={{ color: colors.muted, marginTop: spacing.sm, fontSize: 12, letterSpacing: 0.5 }}>by Versanex India</Text>
        <ActivityIndicator color={colors.brandPrimary} size="large" style={{ marginTop: spacing.xl }} />
      </View>
    );
  }
  if (!user) return <Redirect href="/login" />;
  if (user.role === "OWNER" || user.role === "ADMIN" || user.role === "STAFF")
    return <Redirect href="/admin" />;
  if (user.role === "PROVIDER") return <Redirect href="/provider" />;
  return <Redirect href="/home" />;
}
const styles = StyleSheet.create({ center: { flex: 1, alignItems: "center", justifyContent: "center" } });
