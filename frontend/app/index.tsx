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
  // Back-office roles land on the admin control center; field roles on the
  // technician dashboard; everyone else is a customer.
  const BACKOFFICE = ["OWNER", "ADMIN", "STAFF", "SUPERVISOR", "OPERATIONS", "SUPPORT", "FINANCE"];
  const FIELD = ["PROVIDER", "TECHNICIAN"];
  if (BACKOFFICE.includes(user.role)) return <Redirect href="/admin" />;
  if (FIELD.includes(user.role)) return <Redirect href="/provider" />;
  return <Redirect href="/home" />;
}
const styles = StyleSheet.create({ center: { flex: 1, alignItems: "center", justifyContent: "center" } });
