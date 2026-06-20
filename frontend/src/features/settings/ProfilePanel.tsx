'use client';

import React, { useState, useEffect } from 'react';
import { Avatar, Typography, Button, Space, Card, Tag, Divider, Input, App } from 'antd';
import { LogoutOutlined, UserOutlined, MailOutlined, SafetyOutlined, SaveOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useUser } from '@/hooks/useUser';
import { updateProfile } from '@/services/auth';

const { Title, Text } = Typography;

const PRESET_AVATARS = [
  { name: '蓝调机器人', url: 'https://api.dicebear.com/7.x/bottts/svg?seed=Blue' },
  { name: '紫光几何', url: 'https://api.dicebear.com/7.x/identicon/svg?seed=Purple' },
  { name: '炫绿矩阵', url: 'https://api.dicebear.com/7.x/identicon/svg?seed=Green' },
  { name: '霓虹电子', url: 'https://api.dicebear.com/7.x/bottts/svg?seed=Neon' },
  { name: '金色芯片', url: 'https://api.dicebear.com/7.x/bottts/svg?seed=Gold' },
  { name: '虚空旋涡', url: 'https://api.dicebear.com/7.x/identicon/svg?seed=Void' },
];

export default function ProfilePanel({ userClaims }: { userClaims: any }) {
  const router = useRouter();
  const { message } = App.useApp();
  const { user, refreshUser } = useUser();

  const [name, setName] = useState('');
  const [avatar, setAvatar] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user) {
      setName(user.name || '');
      setAvatar(user.avatar || '');
    }
  }, [user]);

  const handleSaveProfile = async () => {
    if (!name.trim()) {
      message.warning('用户名不能为空');
      return;
    }
    setSaving(true);
    try {
      await updateProfile({ name, avatar });
      message.success('个人档案保存成功');
      await refreshUser();
    } catch (err) {
      message.error('请求出错，请重试');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="animate-fade-in space-y-4 sm:space-y-6">
      <Title level={3} className="text-white mb-4 sm:mb-6 text-xl sm:text-2xl">个人档案</Title>
      
      {/* 个人名片展示 */}
      <Card className="bg-[#14161f]/60 border-white/5 rounded-3xl p-2 sm:p-4 shadow-xl">
        <div className="flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6 text-center sm:text-left">
          <Avatar 
            size={80} 
            src={avatar || undefined} 
            icon={<UserOutlined />} 
            className="border-2 border-blue-500/20 shadow-lg shadow-blue-900/20 rounded-2xl shrink-0"
          />
          <div className="min-w-0 flex-1 flex flex-col justify-center h-full pt-1 sm:pt-2">
            <Title level={4} className="m-0 text-white truncate text-lg sm:text-xl">
              {name || user?.name || 'TruthSeeker User'}
            </Title>
            <Text className="text-slate-500 font-mono text-xs truncate block mt-1">
              ID: {user?.user_id || userClaims?.sub || 'Loading...'}
            </Text>
          </div>
          <div className="shrink-0 w-full sm:w-auto mt-2 sm:mt-0 flex justify-center">
            <Tag color="blue" className="rounded-lg px-3 py-1.5 sm:py-1 border-0 bg-blue-500/10 text-blue-400 font-bold uppercase tracking-widest text-micro sm:text-caption text-center">
              Standard Plan
            </Tag>
          </div>
        </div>
      </Card>

      {/* 修改个人信息表单 */}
      <Card className="bg-[#14161f]/60 border-white/5 rounded-3xl p-4 sm:p-6 shadow-xl space-y-4 sm:space-y-6">
        <div className="space-y-2">
          <label className="text-slate-400 text-caption sm:text-xs font-bold uppercase tracking-wider">用户名 (Full Name)</label>
          <Input 
            value={name} 
            onChange={(e) => setName(e.target.value)} 
            placeholder="请输入您的姓名/昵称"
            className="bg-white/5 border-white/10 text-slate-100 hover:border-blue-500/50 focus:border-blue-500/50 h-10 rounded-xl text-sm"
          />
        </div>

        <div className="space-y-4">
          <div className="flex flex-col">
            <label className="text-slate-400 text-caption sm:text-xs font-bold uppercase tracking-wider mb-1">头像设置</label>
            <Text className="text-micro sm:text-caption text-slate-500">支持输入自定义头像链接或从下方推荐快速选择</Text>
          </div>
          
          <Input 
            value={avatar} 
            onChange={(e) => setAvatar(e.target.value)} 
            placeholder="自定义头像 URL"
            className="bg-white/5 border-white/10 text-slate-100 hover:border-blue-500/50 focus:border-blue-500/50 h-10 rounded-xl text-sm"
          />

          {/* 快速推荐头像 */}
          <div className="space-y-2">
            <span className="text-micro sm:text-caption text-slate-500 font-bold block">推荐预设头像：</span>
            <div className="flex flex-wrap gap-2 sm:gap-3.5 justify-center sm:justify-start">
              {PRESET_AVATARS.map((preset, index) => {
                const isSelected = avatar === preset.url;
                return (
                  <div 
                    key={index}
                    onClick={() => setAvatar(preset.url)}
                    className={`cursor-pointer rounded-xl p-0.5 border-2 transition-all ${
                      isSelected 
                        ? 'border-blue-500 bg-blue-500/10 scale-105 shadow-md shadow-blue-500/10' 
                        : 'border-transparent hover:scale-105 hover:bg-white/5'
                    }`}
                  >
                    <Avatar 
                      size={40} 
                      src={preset.url} 
                      className="rounded-lg shadow border border-white/5"
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <Divider className="border-white/5 my-4" />

        <Button 
          type="primary" 
          icon={<SaveOutlined />} 
          loading={saving}
          onClick={handleSaveProfile}
          className="w-full h-11 bg-blue-600 hover:bg-blue-500 border-none shadow-lg shadow-blue-900/20 rounded-xl font-bold text-sm"
        >
          保存个人资料
        </Button>
      </Card>

      {/* 只读账号绑定信息 */}
      <Card className="bg-[#14161f]/60 border-white/5 rounded-3xl p-4 sm:p-6 shadow-xl">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
          <div className="p-4 rounded-2xl bg-white/2 border border-white/5 flex flex-col justify-center items-center sm:items-start text-center sm:text-left">
            <div className="flex items-center gap-2 sm:gap-3 mb-2">
              <MailOutlined className="text-slate-500 text-sm sm:text-base" />
              <Text className="text-slate-400 text-caption sm:text-xs font-bold uppercase tracking-wider">绑定邮箱</Text>
            </div>
            <Text className="text-slate-200 text-xs sm:text-sm truncate w-full">{user?.email || userClaims?.email || '未绑定'}</Text>
          </div>
          <div className="p-4 rounded-2xl bg-white/2 border border-white/5 flex flex-col justify-center items-center sm:items-start text-center sm:text-left">
            <div className="flex items-center gap-2 sm:gap-3 mb-2">
              <SafetyOutlined className="text-slate-500 text-sm sm:text-base" />
              <Text className="text-slate-400 text-caption sm:text-xs font-bold uppercase tracking-wider">租户身份 (Tenant)</Text>
            </div>
            <Text className="text-slate-200 font-mono text-xs sm:text-sm truncate w-full">
              {user?.tenant_id?.split('-')[0].toUpperCase() || 'DEFAULT'}
            </Text>
          </div>
        </div>

        <Divider className="border-white/5 my-4 sm:my-6" />

        <Space orientation="vertical" className="w-full">
          <Button 
            danger 
            type="text" 
            icon={<LogoutOutlined />} 
            className="w-full h-11 rounded-xl bg-rose-500/5 hover:bg-rose-500/10 font-bold text-sm"
            onClick={() => window.location.href = '/api/v1/auth/logout'}
          >
            退出登录 (Sign Out)
          </Button>
          <Text className="text-micro sm:text-caption text-slate-600 text-center block mt-4">
            TruthSeeker Intelligence Engine © 2026. All rights reserved.
          </Text>
        </Space>
      </Card>
    </div>
  );
}
