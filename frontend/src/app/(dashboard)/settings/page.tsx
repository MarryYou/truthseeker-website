'use client';

import SettingsLayout from '@/features/settings/SettingsLayout';
import { useUser } from '@/hooks/useUser';

export default function SettingsPage() {
  const { user } = useUser();

  const userClaims = {
    sub: user?.user_id || '',
    name: user?.name,
    email: user?.email,
    avatar: user?.avatar,
  };

  return <SettingsLayout userClaims={userClaims} />;
}
