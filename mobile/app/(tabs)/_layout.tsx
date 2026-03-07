import { Tabs } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useTheme } from "react-native-paper";
import { View, StyleSheet } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useGlassTheme } from "../../styles/useGlassTheme";
import { getShoppingListCount } from "../../services/api";
import { useAppStore } from "../../stores/useAppStore";

type IconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

function TabIcon({ name, color, size, focused, dotColor }: { name: IconName; color: string; size: number; focused: boolean; dotColor: string }) {
  return (
    <View style={styles.iconContainer}>
      <MaterialCommunityIcons name={name} size={size} color={color} />
      {focused && <View style={[styles.activeDot, { backgroundColor: dotColor }]} />}
    </View>
  );
}

const styles = StyleSheet.create({
  iconContainer: {
    alignItems: "center",
    justifyContent: "center",
  },
  activeDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    marginTop: 3,
  },
});

export default function TabLayout() {
  const theme = useTheme();
  const glass = useGlassTheme();
  const isLoggedIn = useAppStore((s) => s.isLoggedIn);

  const { data: shoppingCount } = useQuery({
    queryKey: ["shoppingListCount"],
    queryFn: () => getShoppingListCount(),
    enabled: isLoggedIn,
    refetchInterval: 30000,
  });

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: glass.colors.greenMedium,
        tabBarInactiveTintColor: glass.isDark ? "#666" : "#999",
        headerStyle: glass.header as any,
        headerTintColor: glass.colors.greenDark,
        headerTitleStyle: { fontWeight: "bold", color: glass.colors.greenDark },
        headerShadowVisible: false,
        tabBarStyle: glass.tabBar as any,
        tabBarItemStyle: { paddingVertical: 4 },
        tabBarLabelStyle: { fontWeight: "600" },
        sceneStyle: glass.background,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerShown: false,
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="home" color={color} size={size} focused={focused} dotColor={glass.colors.greenMedium} />,
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: "Catalogo",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="view-grid-outline" color={color} size={size} focused={focused} dotColor={glass.colors.greenMedium} />,
        }}
      />
      <Tabs.Screen
        name="flyers"
        options={{
          title: "Volantini",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="newspaper-variant-outline" color={color} size={size} focused={focused} dotColor={glass.colors.greenMedium} />,
        }}
      />
      <Tabs.Screen
        name="watchlist"
        options={{
          title: "La Mia Lista",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="star" color={color} size={size} focused={focused} dotColor={glass.colors.greenMedium} />,
          tabBarBadge: shoppingCount && shoppingCount > 0 ? shoppingCount : undefined,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Impostazioni",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="cog" color={color} size={size} focused={focused} dotColor={glass.colors.greenMedium} />,
        }}
      />
    </Tabs>
  );
}
