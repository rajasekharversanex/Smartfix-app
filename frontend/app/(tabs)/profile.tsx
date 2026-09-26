import { View, Text, ScrollView, Pressable, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";
import { useAuth } from "@/src/auth";
import { useTheme, spacing, radius } from "@/src/theme";
import { Button } from "@/src/ui";
import { Logo } from "@/src/brand";

export default function Profile() {
  const { user, logout } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const Row = ({ icon, label, onPress, testID }: any) => (
    <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [styles.row, { backgroundColor: pressed ? colors.surfaceTertiary : colors.surface, borderColor: colors.divider }]}>
      <Icon name={icon} size={20} color={colors.brandPrimary} />
      <Text style={{ color: colors.onSurface, fontSize: 15, flex: 1, marginLeft: spacing.md }}>{label}</Text>
      <Icon name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + spacing.lg, paddingHorizontal: spacing.xl, paddingBottom: spacing.xxxl }}>
        <View style={{ alignItems: "center", marginBottom: spacing.xl }}>
          <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" }}>
            <Text style={{ color: colors.onBrandPrimary, fontSize: 26, fontWeight: "800" }}>{(user?.name || user?.username || "?").slice(0, 1).toUpperCase()}</Text>
          </View>
          <Text style={{ color: colors.onSurface, fontSize: 20, fontWeight: "700", marginTop: spacing.md }}>{user?.name || user?.username}</Text>
          <Text style={{ color: colors.muted }}>{user?.mobile}</Text>
          {user?.email && <Text style={{ color: colors.muted }}>{user?.email}</Text>}
          <View style={{ marginTop: 8, backgroundColor: colors.brandSecondary, paddingHorizontal: 12, paddingVertical: 4, borderRadius: radius.pill }}>
            <Text style={{ color: colors.onBrandSecondary, fontWeight: "600", fontSize: 12 }}>{user?.role}</Text>
          </View>
        </View>

        <Row icon="location-outline" label="My Addresses" onPress={() => router.push("/addresses")} testID="profile-addresses" />
        <Row icon="clipboard-outline" label="My Bookings" onPress={() => router.push("/(tabs)/bookings")} testID="profile-bookings" />
        <Row icon="chatbubble-ellipses-outline" label="Contact Support" onPress={() => router.push("/support")} testID="profile-support" />
        <Row icon="briefcase-outline" label="Become a Provider" onPress={() => router.push("/provider-apply")} testID="profile-provider-apply" />
        <Row icon="lock-closed-outline" label="Reset Password" onPress={() => router.push("/forgot-password")} testID="profile-reset-password" />

        <View style={{ marginTop: spacing.xl, alignItems: "center" }}>
          <Button label="Log Out" variant="ghost" onPress={async () => { await logout(); router.replace("/login"); }} testID="profile-logout-button" />
          <View style={{ marginTop: spacing.xl, alignItems: "center" }}>
            <Logo size="sm" />
            <Text style={{ color: colors.muted, textAlign: "center", marginTop: 6, fontSize: 11, letterSpacing: 0.4 }}>by Versanex India</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, marginBottom: spacing.sm },
});
