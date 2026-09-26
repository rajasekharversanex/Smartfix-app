import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const light = {
  surface: "#FFFFFF",
  onSurface: "#1A1D1C",
  surfaceSecondary: "#F4F7F5",
  onSurfaceSecondary: "#2D3330",
  surfaceTertiary: "#E8EBE9",
  onSurfaceTertiary: "#3E4542",
  surfaceInverse: "#111614",
  onSurfaceInverse: "#FFFFFF",
  muted: "#707A76",

  brand: "#0A5C36",
  onBrand: "#FFFFFF",
  brandPrimary: "#0F7A49",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#E8F3ED",
  onBrandSecondary: "#0F7A49",
  brandTertiary: "#D2E8DD",
  onBrandTertiary: "#0A5C36",

  success: "#14854F",
  onSuccess: "#FFFFFF",
  warning: "#D9822B",
  onWarning: "#FFFFFF",
  error: "#D14343",
  onError: "#FFFFFF",
  info: "#4A5568",
  onInfo: "#FFFFFF",

  border: "#E4E7E5",
  borderStrong: "#C8CCC9",
  divider: "#EDF0EE",
};

const dark: typeof light = {
  surface: "#0C100E",
  onSurface: "#F0F3F1",
  surfaceSecondary: "#1A201C",
  onSurfaceSecondary: "#DCE0DD",
  surfaceTertiary: "#252B28",
  onSurfaceTertiary: "#B8BCBA",
  surfaceInverse: "#F0F3F1",
  onSurfaceInverse: "#0C100E",
  muted: "#87938D",

  brand: "#0A5C36",
  onBrand: "#F0F3F1",
  brandPrimary: "#139659",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#182F24",
  onBrandSecondary: "#2DD382",
  brandTertiary: "#234A36",
  onBrandTertiary: "#45EBA0",

  success: "#1BB169",
  onSuccess: "#FFFFFF",
  warning: "#F09E41",
  onWarning: "#1A1105",
  error: "#ED5F5F",
  onError: "#FFFFFF",
  info: "#8E9DAE",
  onInfo: "#FFFFFF",

  border: "#2D3531",
  borderStrong: "#3E4943",
  divider: "#202623",
};

export type ThemeColors = typeof light;
export const defaultScheme = "light" satisfies ColorScheme;
export const themes: { light: ThemeColors; dark?: ThemeColors } = { light, dark };

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(themes.dark ? null : defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  const scheme: ColorScheme = system && themes[system] ? system : defaultScheme;
  return { scheme, colors: themes[scheme] ?? themes.light };
}

export const colors = light;

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
