import { Tabs } from "expo-router";
import Icon from "@react-native-vector-icons/ionicons";
import { useTheme } from "@/src/theme";
import { Platform } from "react-native";

export default function TabsLayout() {
  const { colors } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
      }}
    >
      <Tabs.Screen name="home" options={{ title: "Home", tabBarButtonTestID: "tab-home", tabBarIcon: ({ color, size }) => <Icon name="home-outline" size={size} color={color} /> }} />
      <Tabs.Screen name="bookings" options={{ title: "Bookings", tabBarButtonTestID: "tab-bookings", tabBarIcon: ({ color, size }) => <Icon name="clipboard-outline" size={size} color={color} /> }} />
      <Tabs.Screen name="offers" options={{ title: "Offers", tabBarButtonTestID: "tab-offers", tabBarIcon: ({ color, size }) => <Icon name="pricetag-outline" size={size} color={color} /> }} />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarButtonTestID: "tab-profile", tabBarIcon: ({ color, size }) => <Icon name="person-outline" size={size} color={color} /> }} />
    </Tabs>
  );
}
