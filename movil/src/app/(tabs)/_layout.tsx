import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router/js-tabs';

import { Palette } from '@/constants/theme';

export const unstable_settings = {
  anchor: 'caseta',
};

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: {
          backgroundColor: Palette.surface,
        },
        headerTitleStyle: {
          color: Palette.text,
          fontWeight: '700',
        },
        headerShadowVisible: false,
        tabBarActiveTintColor: Palette.primary,
        tabBarInactiveTintColor: Palette.textMuted,
        tabBarStyle: {
          backgroundColor: Palette.surface,
          borderTopColor: Palette.border,
        },
      }}>
      <Tabs.Screen
        name="caseta"
        options={{
          title: 'Caseta',
          tabBarLabel: 'Caseta',
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons
              name={focused ? 'videocam' : 'videocam-outline'}
              size={size}
              color={typeof color === 'string' ? color : focused ? Palette.primary : Palette.textMuted}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="consulta"
        options={{
          title: 'Consulta',
          tabBarLabel: 'Consulta',
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons
              name={focused ? 'chatbubble-ellipses' : 'chatbubble-ellipses-outline'}
              size={size}
              color={typeof color === 'string' ? color : focused ? Palette.primary : Palette.textMuted}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="ajustes"
        options={{
          title: 'Ajustes',
          tabBarLabel: 'Ajustes',
          tabBarIcon: ({ color, size, focused }) => (
            <Ionicons
              name={focused ? 'settings' : 'settings-outline'}
              size={size}
              color={typeof color === 'string' ? color : focused ? Palette.primary : Palette.textMuted}
            />
          ),
        }}
      />
    </Tabs>
  );
}
