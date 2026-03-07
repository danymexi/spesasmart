import { useEffect } from "react";
import { Platform, StyleSheet, View, type ViewStyle } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { useGlassTheme } from "../styles/useGlassTheme";

interface SkeletonProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
  style?: ViewStyle;
}

export function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = 8,
  style,
}: SkeletonProps) {
  const { isDark, colors } = useGlassTheme();
  const shimmer = useSharedValue(0);

  useEffect(() => {
    shimmer.value = withRepeat(
      withTiming(1, { duration: 1200, easing: Easing.inOut(Easing.ease) }),
      -1,
      true
    );
  }, [shimmer]);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: 0.4 + shimmer.value * 0.4,
  }));

  const bg = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.06)";

  return (
    <Animated.View
      style={[
        {
          width: width as any,
          height,
          borderRadius,
          backgroundColor: bg,
        },
        animatedStyle,
        style,
      ]}
    />
  );
}

/** Pre-composed skeleton that mimics a product card row. */
export function SkeletonCard() {
  return (
    <View style={skStyles.card}>
      <Skeleton width={56} height={56} borderRadius={12} />
      <View style={skStyles.lines}>
        <Skeleton width="70%" height={14} />
        <Skeleton width="45%" height={12} />
        <Skeleton width="30%" height={12} />
      </View>
    </View>
  );
}

/** Pre-composed skeleton that mimics a list of cards. */
export function SkeletonList({ count = 4 }: { count?: number }) {
  return (
    <View style={skStyles.list}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </View>
  );
}

const skStyles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  lines: {
    flex: 1,
    gap: 6,
  },
  list: {
    paddingTop: 8,
  },
});
