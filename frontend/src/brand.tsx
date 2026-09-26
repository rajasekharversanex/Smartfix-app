import { Image } from "expo-image";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "@/src/theme";

// Official SmartFix Services logo (approved brand asset — do not replace).
export const LOGO = require("@/assets/brand/smartfix-logo.png");

type Size = "sm" | "md" | "lg" | "xl";

// The source image is a wide (~3.4:1) horizontal wordmark + emblem
// (worker + house + wrench + "SmartFix Services"). Keep this ratio everywhere.
const DIM: Record<Size, { w: number; h: number }> = {
  sm: { w: 108, h: 32 },
  md: { w: 168, h: 50 },
  lg: { w: 236, h: 70 },
  xl: { w: 288, h: 86 },
};

export function Logo({ size = "md", tagline = false }: { size?: Size; tagline?: boolean }) {
  const { colors } = useTheme();
  const { w, h } = DIM[size];
  return (
    <View style={styles.wrap} accessibilityLabel="SmartFix Services logo">
      <Image
        source={LOGO}
        style={{ width: w, height: h }}
        contentFit="contain"
        transition={120}
      />
      {tagline && (
        <Text style={[styles.tag, { color: colors.muted }]}>by Versanex India</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: "center", justifyContent: "center" },
  tag: { fontSize: 11, marginTop: 4, letterSpacing: 0.5, fontWeight: "600" },
});
