import { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { Redirect } from "expo-router";
import { useAuth } from "@/src/auth";
import { useTheme } from "@/src/theme";

export default function Index() {
  const { user, loading } = useAuth();
  const { colors } = useTheme();

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: colors.surface }]}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
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
