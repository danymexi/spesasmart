import { Tabs } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useTheme } from "react-native-paper";
import { glassColors, glassHeader, glassTabBar, gradientBackground } from "../../styles/glassStyles";

type IconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

function TabIcon({ name, color, size }: { name: IconName; color: string; size: number }) {
  return <MaterialCommunityIcons name={name} size={size} color={color} />;
}

export default function TabLayout() {
  const theme = useTheme();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: glassColors.greenDark,
        tabBarInactiveTintColor: "#999",
        headerStyle: glassHeader as any,
        headerTintColor: glassColors.greenDark,
        headerTitleStyle: { fontWeight: "bold", color: glassColors.greenDark },
        headerShadowVisible: false,
        tabBarStyle: glassTabBar as any,
        tabBarItemStyle: { paddingVertical: 4 },
        sceneStyle: gradientBackground,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerShown: false,
          tabBarIcon: ({ color, size }) => <TabIcon name="home" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: "Catalogo",
          tabBarIcon: ({ color, size }) => <TabIcon name="view-grid-outline" color={color} size={size} />,
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
