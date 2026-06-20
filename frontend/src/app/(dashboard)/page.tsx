'use client';

import Dashboard from '@/features/dashboard/Dashboard';
import { useUser } from '@/hooks/useUser';

export default function HomePage() {
  const { user } = useUser();

  const userClaims = {
    sub: user?.user_id || '',
    name: user?.name,
    email: user?.email,
    avatar: user?.avatar,
  };

  return <Dashboard userClaims={userClaims} />;
}
