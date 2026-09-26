import React from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useTheme, spacing, radius } from "./theme";

export function Button({
  label,
  onPress,
  loading,
  variant = "primary",
  testID,
  disabled,
}: {
  label: string;
  onPress: () => void;
  loading?: boolean;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  testID?: string;
  disabled?: boolean;
}) {
  const { colors } = useTheme();
  const bg =
    variant === "primary" ? colors.brandPrimary :
    variant === "secondary" ? colors.brandSecondary :
    variant === "danger" ? colors.error :
    "transparent";
  const fg =
    variant === "primary" ? colors.onBrandPrimary :
    variant === "secondary" ? colors.onBrandSecondary :
    variant === "danger" ? colors.onError :
    colors.brandPrimary;
  const isDisabled = disabled || loading;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        {
          backgroundColor: bg,
          opacity: isDisabled ? 0.5 : pressed ? 0.85 : 1,
          borderRadius: radius.md,
          paddingVertical: 14,
          paddingHorizontal: spacing.lg,
          alignItems: "center",
          justifyContent: "center",
          minHeight: 48,
          borderWidth: variant === "ghost" ? 1 : 0,
          borderColor: variant === "ghost" ? colors.border : "transparent",
        },
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={{ color: fg, fontWeight: "600", fontSize: 16 }}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Input(props: {
  label?: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  secureTextEntry?: boolean;
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  keyboardType?: any;
  testID?: string;
  multiline?: boolean;
}) {
  const { colors } = useTheme();
  const { label, ...rest } = props;
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label && (
        <Text style={{ color: colors.onSurfaceSecondary, marginBottom: 6, fontWeight: "500", fontSize: 14 }}>
          {label}
        </Text>
      )}
      <View
        style={{
          backgroundColor: colors.surfaceTertiary,
          borderRadius: radius.md,
          paddingHorizontal: spacing.md,
          paddingVertical: props.multiline ? spacing.md : 12,
          borderWidth: 1,
          borderColor: colors.border,
        }}
      >
        <TextInputImpl {...rest} colors={colors} />
      </View>
    </View>
  );
}

import { TextInput } from "react-native";
function TextInputImpl(props: any) {
  const { colors, ...rest } = props;
  return (
    <TextInput
      {...rest}
      placeholderTextColor={colors.muted}
      style={{ color: colors.onSurface, fontSize: 16, minHeight: 20 }}
    />
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: colors.surface,
          borderRadius: radius.lg,
          padding: spacing.lg,
          borderWidth: 1,
          borderColor: colors.border,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function StatusPill({ status }: { status: string }) {
  const { colors } = useTheme();
  const map: Record<string, { bg: string; fg: string }> = {
    PENDING: { bg: colors.surfaceTertiary, fg: colors.onSurfaceTertiary },
    ACCEPTED: { bg: colors.brandSecondary, fg: colors.onBrandSecondary },
    ON_THE_WAY: { bg: "#FFF4E5", fg: "#B45309" },
    IN_PROGRESS: { bg: "#FFF4E5", fg: "#B45309" },
    COMPLETED: { bg: "#E8F3ED", fg: colors.success },
    CANCELLED: { bg: "#FDECEC", fg: colors.error },
    PAID: { bg: "#E8F3ED", fg: colors.success },
    AWAITING_VERIFICATION: { bg: "#FFF4E5", fg: "#B45309" },
  };
  const s = map[status] || { bg: colors.surfaceTertiary, fg: colors.onSurfaceTertiary };
  return (
    <View style={{ backgroundColor: s.bg, paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, alignSelf: "flex-start" }}>
      <Text style={{ color: s.fg, fontSize: 12, fontWeight: "600" }}>{status.replace(/_/g, " ")}</Text>
    </View>
  );
}
