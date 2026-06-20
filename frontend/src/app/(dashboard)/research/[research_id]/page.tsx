'use client';

import React from 'react';
import { Spin } from 'antd';
import ChatDetailsContainer from '@/features/chat/ChatDetailsContainer';

interface ResearchDetailsPageProps {
  params: Promise<{
    research_id: string;
  }>;
}

export default function ResearchDetailsPage({ params }: ResearchDetailsPageProps) {
  const [researchId, setResearchId] = React.useState<string | null>(null);

  React.useEffect(() => {
    params.then(p => setResearchId(p.research_id));
  }, [params]);

  if (!researchId) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-[#090a0f]">
        <Spin size="large" description="正在加载研究详情..." />
      </div>
    );
  }

  return <ChatDetailsContainer researchId={researchId} />;
}
