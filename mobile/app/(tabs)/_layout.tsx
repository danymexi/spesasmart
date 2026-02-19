import { Tabs } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useTheme } from "react-native-paper";

type IconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

function TabIcon({ name, color, size }: { name: IconName; color: string; size: number }) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}

export default function TabLayout() {
  const theme = useTheme();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: "#999",
        headerStyle: { backgroundColor: theme.colors.primary },
        headerTintColor: "#fff",
        headerTitleStyle: { fontWeight: "bold" },
        tabBarStyle: { paddingBottom: 4, height: 56 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => <TabIcon name="home" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: "Cerca",
          tabBarIcon: ({ color, size }) => <TabIcon name="magnify" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="flyers"
        options={{
          title: "Volantini",
          tabBarIcon: ({ color, size }) => <TabIcon name="newspaper-variant-outline" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="watchlist"
        options={{
          title: "La Mia Lista",
          tabBarIcon: ({ color, size }) => <TabIcon name="star" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Impostazioni",
          tabBarIcon: ({ color, size }) => <TabIcon name="cog" color={color} size={size} />,
        }}
      />
    </Tabs>
  );
}
