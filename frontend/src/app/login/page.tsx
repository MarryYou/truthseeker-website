import { AUTH_LOGIN_PATH } from '@/lib/constants';

export default async function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[#090a0f] relative overflow-hidden font-sans">
      {/* Decorative gradient blur backgrounds */}
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] bg-blue-500/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-indigo-500/10 rounded-full blur-[140px] pointer-events-none" />
      
      <div className="w-full max-w-[440px] bg-slate-900/40 backdrop-blur-md border border-white/5 rounded-3xl shadow-2xl shadow-black/80 p-10 text-center relative z-10">
        {/* SVG Compass Logo Container */}
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center mx-auto mb-6 shadow-lg shadow-indigo-950/40">
          <svg className="text-white w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
          </svg>
        </div>

        {/* Title */}
        <h1 className="text-3xl font-extrabold text-white tracking-tight mb-2">
          TruthSeeker
        </h1>
        
        {/* Subtitle */}
        <p className="text-sm text-slate-400 mb-8 leading-relaxed">
          AI 驱动的事实核查与多源决策研究助手
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col gap-4">
          <a 
            href={AUTH_LOGIN_PATH}
            className="w-full py-3.5 px-6 rounded-xl border border-transparent bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 !text-white font-semibold text-sm transition-all duration-200 cursor-pointer shadow-lg shadow-indigo-950/50 flex items-center justify-center no-underline"
          >
            登录账号
          </a>

          <a 
            href={AUTH_LOGIN_PATH} 
            className="w-full py-3.5 px-6 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 !text-slate-200 font-semibold text-sm transition-all duration-200 cursor-pointer flex items-center justify-center no-underline"
          >
            注册新账号
          </a>
        </div>

        {/* Footer info */}
        <div className="mt-8 text-xs text-slate-500 leading-relaxed">
          通过登录或注册，即表示您同意我们的服务条款和隐私政策。
        </div>
      </div>
    </div>
  );
}
