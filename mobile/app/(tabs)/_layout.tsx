import { Tabs } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useTheme } from "react-native-paper";
import { View, StyleSheet } from "react-native";
import { glassColors, glassHeader, glassTabBar, gradientBackground } from "../../styles/glassStyles";

type IconName = React.ComponentProps<typeof MaterialCommunityIcons>["name"];

function TabIcon({ name, color, size, focused }: { name: IconName; color: string; size: number; focused: boolean }) {
  return (
    <View style={styles.iconContainer}>
      <MaterialCommunityIcons name={name} size={size} color={color} />
      {focused && <View style={styles.activeDot} />}
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
    backgroundColor: glassColors.greenMedium,
    marginTop: 3,
  },
});

export default function TabLayout() {
  const theme = useTheme();

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: glassColors.greenMedium,
        tabBarInactiveTintColor: "#999",
        headerStyle: glassHeader as any,
        headerTintColor: glassColors.greenDark,
        headerTitleStyle: { fontWeight: "bold", color: glassColors.greenDark },
        headerShadowVisible: false,
        tabBarStyle: glassTabBar as any,
        tabBarItemStyle: { paddingVertical: 4 },
        tabBarLabelStyle: { fontWeight: "600" },
        sceneStyle: gradientBackground,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerShown: false,
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="home" color={color} size={size} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="search"
        options={{
          title: "Catalogo",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="view-grid-outline" color={color} size={size} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="flyers"
        options={{
          title: "Volantini",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="newspaper-variant-outline" color={color} size={size} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="watchlist"
        options={{
          title: "La Mia Lista",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="star" color={color} size={size} focused={focused} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Impostazioni",
          tabBarIcon: ({ color, size, focused }) => <TabIcon name="cog" color={color} size={size} focused={focused} />,
        }}
      />
    </Tabs>
  );
}
