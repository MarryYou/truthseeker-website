import React from 'react';

interface SessionHeaderProps {
  researchId: string;
  title?: string;
}

export const SessionHeader: React.FC<SessionHeaderProps> = ({ 
  researchId, 
  title
}) => {
  return (
    <header className="h-14 sm:h-16 flex items-center justify-between px-4 sm:px-6 border-b border-white/5 bg-[#090a0f] z-20 shrink-0">
      <div className="flex flex-col min-w-0 max-w-[85%] sm:max-w-[70%]">
        <div className="flex items-center gap-1.5 sm:gap-2 mb-0.5">
          <span className="text-micro font-black text-blue-500 uppercase tracking-widest">Research Session</span>
          <span className="text-micro text-slate-600 font-mono truncate hidden sm:inline">({researchId})</span>
        </div>
        <h2 className="text-xs sm:text-sm font-bold text-slate-100 truncate m-0 leading-normal">
          {title || '深度研究会话'}
        </h2>
      </div>
    </header>
  );
};
