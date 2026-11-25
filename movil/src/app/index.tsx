import { Redirect } from 'expo-router';

import { useAuth } from '@/lib/auth-context';

export default function IndexRoute() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  return <Redirect href={user ? '/(tabs)/caseta' : '/login'} />;
}
