import type { ResearchPreset, SettingsSchema, UserSecret, ModelAsset } from '@/types';

/** 所有工作流子组件共享的上下文数据 */
export interface WorkflowShared {
  activePreset: ResearchPreset;
  schema: SettingsSchema | null;
  assets: ModelAsset[];
  secrets: UserSecret[];
  isSystemPreset: boolean;
  updateStageConfig: (stageKey: string, data: Record<string, unknown>) => void;
  updateStageParams: (stageKey: string, nodeType: string, params: Record<string, unknown>) => void;
  updateBusinessConfig: (key: string, val: unknown) => void;
}

/* ── 响应层级 (Response Tiers) 定义 ───────────────────────────── */

/** 
 * 后端 3 个顶级 Response Tiers。
 */
export interface StageDef {
  key: string;
  label: string;
  description: string;
  recommendation?: string;
  /** 该阶段包含的节点类型列表 (用于参数面板渲染) */
  nodes: string[];
}

export const STAGES: StageDef[] = [
  {
    key: 'fast_react',
    label: '极速快问',
    description: '限制 2 次工具调用，仅搜索摘要。适用于简单确认、闲聊或基础查询。',
    recommendation: '推荐轻量级、高并发模型 (如 GPT-4o-mini / DeepSeek-V3)',
    nodes: [],
  },
  {
    key: 'expert_search',
    label: '专家搜索',
    description: '支持多轮迭代及全文阅读。适用于方案解释或理论背景调研。',
    recommendation: '推荐强推理模型 (如 GPT-4o / Claude 3.5 Sonnet / DeepSeek-R1)',
    nodes: ['agent_expert_search'],
  },
  {
    key: 'research_pipeline',
    label: '深度研究',
    description: '意图拆解 → 多源搜索 → 交叉验证 → 结构化报告。适用于严谨调研。',
    recommendation: '推荐强指令遵循模型 (如 Claude 3.5 Sonnet / GPT-4o)',
    nodes: ['intent_analyze', 'keyword_expand', 'multi_search',
            'filter_results', 'cross_verify', 'generate_report'],
  },
];

/** 深度研报专属的子阶段精细化路由定义 */
export const PIPELINE_SUB_STAGES: StageDef[] = [
  {
    key: 'understanding',
    label: '意图拆解',
    description: '分析意图，规划维度与关键词。',
    recommendation: '推荐逻辑严密的模型 (如 GPT-4o)',
    nodes: ['intent_analyze', 'keyword_expand'],
  },
  {
    key: 'search',
    label: '信息检索',
    description: '多引擎并发搜索并筛选结果。',
    recommendation: '推荐高并发、理解力好的模型 (如 GPT-4o-mini)',
    nodes: ['multi_search', 'filter_results'],
  },
  {
    key: 'verification',
    label: '证据核验',
    description: '跨信源验证，识别潜在冲突。',
    recommendation: '推荐具备强推理能力、幻觉低的模型 (如 DeepSeek-R1 / o1)',
    nodes: ['cross_verify'],
  },
  {
    key: 'report',
    label: '研报撰写',
    description: '汇聚证据，生成结构化深度报告。',
    recommendation: '推荐文采好、长上下文支持强的模型 (如 Claude 3.5 / GPT-4o)',
    nodes: ['generate_report'],
  },
];

/** 节点类型 → 友好名称 */
export const NODE_LABELS: Record<string, string> = {
  intent_analyze: '意图分析',
  keyword_expand: '关键词扩展',
  multi_search: '多源搜索',
  filter_results: '结果筛选',
  cross_verify: '交叉验证',
  generate_report: '报告生成',
  agent_expert_search: '自主智能体 (Expert Agent)',
};

/** 嵌入阶段属于底层配置，不再独立作为业务阶段显示 */
export const EMBEDDING_STAGE_KEY = 'embedding';

/* ── 参数说明 ────────────────────────────────────────────────── */

/** 每个参数的中文说明 (科技风格) */
export const PARAMETER_DESCRIPTIONS: Record<string, string> = {
  // ── 全局 Business Params ──
  speed: '响应层级基准。fast_react 极速响应；expert_search 专家深度搜索；research_pipeline 标准深度研究。',
  engines: "搜索引擎组合。支持多选并发调用。",
  intent_confidence_threshold: "意图识别置信度阈值。低于此值将触发二次确认。",

  // ── intent_analyze ──
  intent_max_dimensions: '拆解的最大平行研究维度数范围。',

  // ── keyword_expand ──
  keywords_per_dimension: "每个维度生成的子查询关键词数量范围。",
  max_total_keywords: "单次任务生成的最大关键词总数上限。",
  bilingual: '自动执行中英双语检索，联合翻译扩展英文子查询。',
  include_year: '在搜索词中添加当前年份，优先获取最新资讯。',

  // ── multi_search ──
  max_search_rounds: '补搜循环次数上限。检测到信息缺失时自动补充搜索。',
  max_results_per_query: '每次搜索查询请求返回的最大结果数范围。',
  max_concurrent_engines: "同时调用搜索引擎的最大并发数。",
  max_concurrent_queries: "关键词搜索的物理并发请求上限。",

  // ── filter_results ──
  min_relevance_score: '相关度余弦阈值底线，低于此值直接滤除。',
  max_total_results: '最终保留的最大文档条数。',
  dedup_similarity: '相似度去重门槛。',
  batch_concurrency: '并行调用 LLM 评估网页可信度的最大并发度。',

  // ── cross_verify ──
  min_evidence_per_claim: '每条核心声明需要的最低证据数。',
  numeric_verify: '是否检测数字/数值层面的一致性冲突。',
  contradiction_detection: '是否进行跨源矛盾检测。',

  // ── generate_report ──
  verdict_first: '结论先行。在报告最开头用简短段落直接给出核心结论。',
  include_comparison: '在详细分析中包含 Markdown 对比表。',
  report_sections: '自定义报告包含的章节列表。',

};

/* ── 枚举值标签 ────────────────────────────────────────────── */

export const ENUM_LABELS: Record<string, string> = {
  // speed
  fast_react: '极速快问 (Fast React)',
  expert_search: '专家搜索 (Expert Search)',
  research_pipeline: '深度研究 (Research Pipeline)',
};

/* ── 参数分层: 普通用户 vs 专业用户 ──────────────────────────── */

/** 高级参数集合 */
export const ADVANCED_PARAMS: Record<string, boolean> = {
  max_total_keywords: true,
  max_concurrent_engines: true,
  min_relevance_score: true,
  dedup_similarity: true,
  batch_concurrency: true,
  min_evidence_per_claim: true,
  numeric_verify: true,
};

/** 模式与允许显示的参数键名映射 (用于 UI 剪枝) */
export const MODE_PARAM_MAP: Record<string, string[]> = {
  fast_react: [
    'engines', 'max_results_per_query', 'max_search_rounds'
  ],
  expert_search: [
    'engines', 'max_results_per_query', 'max_search_rounds'
  ],
  research_pipeline: [
    'engines', 'intent_max_dimensions', 'keywords_per_dimension',
    'max_search_rounds', 'max_results_per_query', 'max_total_results',
    'bilingual', 'include_year', 'max_concurrent_engines',
    'min_relevance_score', 'dedup_similarity', 'batch_concurrency',
    'min_evidence_per_claim', 'numeric_verify', 'contradiction_detection'
  ]
};

/** 判断参数是否在当前模式下可见 */
export function isParamVisible(key: string, mode: string): boolean {
  const allowed = MODE_PARAM_MAP[mode];
  if (!allowed) return true; // 默认可见
  return allowed.includes(key);
}

export function isAdvancedParam(key: string): boolean {
  return false; // 显式放开所有参数，不再区分高级/普通
}

/* ── 按目标效果分组 ───────────────────────────────────────── */

export interface ParamRef {
  /** 参数来源位置 */
  source: 'business' | 'node';
  /** 如果是 node 参数，对应的节点类型 */
  nodeType?: string;
  /** 参数 key */
  key: string;
}

export interface GoalGroupDef {
  key: string;
  label: string;
  description: string;
  icon: string; // icon name for mapping
  color: string; // tailwind color
  params: ParamRef[];
}

/**
 * 按用户目标效果分组
 */
export const GOAL_GROUPS: GoalGroupDef[] = [
  {
    key: 'depth',
    label: '研究深度',
    description: '控制研究的广度与深度，影响耗时与信息覆盖面',
    icon: 'CompassOutlined',
    color: 'blue',
    params: [
      { source: 'business', key: 'intent_max_dimensions' },
      { source: 'business', key: 'keywords_per_dimension' },
      { source: 'business', key: 'max_search_rounds' },
      { source: 'business', key: 'max_results_per_query' },
      { source: 'business', key: 'max_total_results' },
      { source: 'node', nodeType: 'keyword_expand', key: 'max_total_keywords' },
    ],
  },
  {
    key: 'search',
    label: '搜索策略',
    description: '搜索引擎组合、语言策略与并发控制',
    icon: 'SearchOutlined',
    color: 'amber',
    params: [
      { source: 'business', key: 'engines' },
      { source: 'business', key: 'bilingual' },
      { source: 'business', key: 'include_year' },
      { source: 'node', nodeType: 'multi_search', key: 'max_concurrent_engines' },
      { source: 'node', nodeType: 'multi_search', key: 'max_concurrent_queries' },
    ],
  },
  {
    key: 'quality',
    label: '质量控制',
    description: '验证强度、去重阈值与可信度评估',
    icon: 'SafetyCertificateOutlined',
    color: 'emerald',
    params: [
      { source: 'node', nodeType: 'filter_results', key: 'min_relevance_score' },
      { source: 'node', nodeType: 'filter_results', key: 'dedup_similarity' },
      { source: 'node', nodeType: 'filter_results', key: 'batch_concurrency' },
      { source: 'node', nodeType: 'intent_analyze', key: 'intent_confidence_threshold' },
      { source: 'node', nodeType: 'cross_verify', key: 'min_evidence_per_claim' },
      { source: 'node', nodeType: 'cross_verify', key: 'numeric_verify' },
      { source: 'node', nodeType: 'cross_verify', key: 'contradiction_detection' },
      { source: 'node', nodeType: 'cross_verify', key: 'marketing_detection' },
      { source: 'business', key: 'verification_level' },
    ],
  },
  {
    key: 'tools',
    label: '底层工具',
    description: '辅助计算配置',
    icon: 'ToolOutlined',
    color: 'slate',
    params: [],
  },
];

/* ── 提供商品牌样式辅助 ────────────────────────────────────── */

/** 供应商品牌样式映射表 */
export const PROVIDER_BRAND_STYLES: Record<string, string> = {
  openai: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  dashscope: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  tongyi: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  qwen: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  deepseek: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  anthropic: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  claude: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  default: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
};

export function getProviderBrandStyles(provider: string): string {
  const norm = provider.toLowerCase();
  for (const [key, style] of Object.entries(PROVIDER_BRAND_STYLES)) {
    if (key !== 'default' && norm.includes(key)) return style;
  }
  return PROVIDER_BRAND_STYLES.default;
}
